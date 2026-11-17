"""Internationalisation: translations from standard gettext catalogs, no extra packages.

Turn it on in ``ushka.toml``::

    [i18n]
    enable = true
    default_locale = "en"
    locales = ["en", "pt-BR"]

Catalogs are the usual gettext layout, ``locale/<lang>/LC_MESSAGES/messages.mo``,
so a ``.mo`` made by Django, ``msgfmt`` or ``ushka i18n compile`` works as it is.

In templates::

    <html lang="{{ lang }}">
    {{ _("Welcome") }}  {{ ngettext("%(num)d item", "%(num)d items", n) }}
    {% trans name=user.name %}Hello {{ name }}{% endtrans %}

In Python (the language of the request being served)::

    from ushka import gettext as _
    message = _("Saved")
    title = lazy_gettext("Dashboard")      # translated when it is used, not when it is defined

The language of a request is picked from ``?lang=``, the ``lang`` cookie and the
``Accept-Language`` header, in the order of ``[i18n] order``. All of that is
client data: it is only ever matched against ``[i18n] locales``, and the
catalog path is built from the configured name, never from what the client sent.
A missing catalog or message gives the original text back, never an error.
"""

from __future__ import annotations

import gettext as _gettext_module
import logging
import re
import struct
from contextvars import ContextVar, Token
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ushka.http.request import Request

log = logging.getLogger("ushka")

_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8}){0,3}$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_TAG_RE = re.compile(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*")
_SOURCES = ("query", "cookie", "header")
_MAX_ACCEPT_LENGTH = 1024
_MAX_ACCEPT_ITEMS = 32
_YEAR = 365 * 24 * 3600


def _key(tag: str) -> str:
    return tag.strip().lower().replace("_", "-")


def _plain(value: Any) -> str:
    """A plain ``str`` (client data may arrive as `Untrusted`)."""
    return str.__str__(value) if isinstance(value, str) else ""


def parse_accept_language(header: str) -> list[str]:
    """Language tags of an ``Accept-Language`` header, best first.

    ``"pt-BR,pt;q=0.9,en;q=0.8,*;q=0.1"`` gives ``["pt-br", "pt", "en"]``. Tags
    with ``q=0`` (refused) or a malformed ``q`` are dropped; equal ``q`` keep
    the order of the header. The header is capped, since anyone can send it.
    """
    found: list[tuple[float, int, str]] = []
    for position, item in enumerate(_plain(header)[:_MAX_ACCEPT_LENGTH].split(",")[:_MAX_ACCEPT_ITEMS]):
        tag, *params = (part.strip() for part in item.split(";"))
        if not _TAG_RE.fullmatch(tag):  # also drops "*" and empty items
            continue
        quality = 1.0
        for param in params:
            name, _sep, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = -1.0
        if 0 < quality <= 1:
            found.append((quality, position, _key(tag)))
    found.sort(key=lambda entry: (-entry[0], entry[1]))
    return [tag for _quality, _position, tag in found]


class Catalogs:
    """The ``.mo`` files of one app, read once and kept in memory.

    With `reload` (debug), a file whose modification time changed is read
    again, so editing a translation shows up without restarting.
    """

    def __init__(self, directory: Path, domain: str, reload: bool = False) -> None:
        self.directory = Path(directory)
        self.domain = domain
        self.reload = reload
        self._cache: dict[str, tuple[Any, tuple]] = {}

    def _files(self, locale: str) -> list[Path]:
        folder = locale.replace("-", "_")
        names = [folder] + ([folder.split("_")[0]] if "_" in folder else [])
        return [self.directory / n / "LC_MESSAGES" / f"{self.domain}.mo" for n in names]

    @staticmethod
    def _stamp(files: list[Path]) -> tuple:
        out = []
        for file in files:
            try:
                out.append(file.stat().st_mtime_ns)
            except OSError:
                out.append(None)
        return tuple(out)

    def get(self, locale: str) -> Any:
        """The translations of `locale` (a configured one), falling back to its language."""
        files = self._files(locale)
        cached = self._cache.get(locale)
        if cached is not None and (not self.reload or cached[1] == self._stamp(files)):
            return cached[0]
        stamp = self._stamp(files)
        chain: Any = _gettext_module.NullTranslations()
        for file in reversed(files):
            if not file.is_file():
                continue
            try:
                with open(file, "rb") as fp:
                    found = _gettext_module.GNUTranslations(fp)
            except (OSError, ValueError, EOFError, struct.error) as exc:
                log.warning("i18n: cannot read %s (%s); ignoring it", file, exc)
                continue
            found.add_fallback(chain)
            chain = found
        self._cache[locale] = (chain, stamp)
        return chain


class Translator:
    """The translation settings of one app (``[i18n]``) and the language choice (``app.i18n``)."""

    def __init__(self, config: Any, workdir: Path) -> None:
        self.enabled = bool(config.get("i18n_enable"))
        default = _plain(config.get("i18n_default_locale")).strip() or "en"
        listed = [_plain(v).strip() for v in (config.get("i18n_locales") or []) if _plain(v).strip()]
        if default not in listed:
            listed.insert(0, default)
        for name in listed:
            if not _LOCALE_RE.match(name):
                raise ValueError(f"[i18n] locales: {name!r} is not a language code such as 'en' or 'pt-BR'")
        domain = _plain(config.get("i18n_domain")) or "messages"
        if not _DOMAIN_RE.match(domain):
            raise ValueError(f"[i18n] domain: {domain!r} must be a plain name such as 'messages'")
        self.default = default
        self.locales = listed
        self._by_key = {_key(name): name for name in reversed(listed)}
        self.order = [s for s in (_plain(v).strip().lower() for v in (config.get("i18n_order") or [])) if s in _SOURCES]
        self.query_param = _plain(config.get("i18n_query_param")) or "lang"
        self.cookie = _plain(config.get("i18n_cookie")) or "lang"
        self.remember = bool(config.get("i18n_remember"))
        directory = Path(_plain(config.get("i18n_catalog_dir")) or "locale")
        if not directory.is_absolute():
            directory = Path(workdir) / directory
        self.catalogs = Catalogs(directory, domain, reload=bool(config.get("app_debug")))

    # -- choosing the language ---------------------------------------------------

    def match(self, tag: Any) -> str | None:
        """The configured locale for a client-supplied tag, or ``None``.

        ``pt-br`` finds ``pt-BR``; ``pt-PT`` or ``pt`` find ``pt`` or, failing
        that, the first configured ``pt-*``. The result is always one of the
        configured names, never the client's text.
        """
        key = _key(_plain(tag))
        if len(key) > 35 or not _TAG_RE.fullmatch(key):
            return None
        if key in self._by_key:
            return self._by_key[key]
        language = key.split("-")[0]
        if language in self._by_key:
            return self._by_key[language]
        for configured in self.locales:
            if _key(configured).split("-")[0] == language:
                return configured
        return None

    def negotiate(self, request: Request) -> tuple[str, str]:
        """``(locale, source)`` for `request`; the source is ``query``, ``cookie``, ``header`` or ``default``."""
        for source in self.order:
            try:
                if source == "query":
                    found = self.match(request.query.get(self.query_param))
                elif source == "cookie":
                    found = self.match(request.cookies.get(self.cookie))
                else:
                    tags = parse_accept_language(request.headers.get("accept-language", ""))
                    found = next(filter(None, map(self.match, tags)), None)
            except Exception:  # a broken query string must not break the page
                found = None
            if found:
                return found, source
        return self.default, "default"

    # -- translating -----------------------------------------------------------

    def translations(self, locale: str) -> Any:
        return self.catalogs.get(locale)

    def activate(self, request: Request) -> Token | None:
        """Chooses the language of `request` and makes it the current one.

        Returns what `deactivate` needs. With i18n off the language is just the
        default and messages come back untranslated.
        """
        if not self.enabled:
            request.locale = self.default
            return None
        locale, source = self.negotiate(request)
        request.locale = locale
        if source == "query" and self.remember and _plain(request.cookies.get(self.cookie)) != locale:
            request.cookies.set(self.cookie, locale, max_age=_YEAR, path="/", httponly=True, samesite="Lax")
        return _current.set((self, locale))

    @staticmethod
    def deactivate(token: Token | None) -> None:
        if token is not None:
            _current.reset(token)


#: ``(Translator, locale)`` of the request being served in this task, else ``None``.
_current: ContextVar[tuple[Translator, str] | None] = ContextVar("ushka_i18n", default=None)


class I18n:
    """``app.use(I18n(locales=["en", "pt"], default="en"))``: translations on, in one line.

    Using it turns i18n on (no ``enable = true``); ``ushka.toml`` and the environment still
    win. ``default`` is ``default_locale``; ``**options`` are any other keys of ``[i18n]``.
    """

    name = "i18n"

    def __new__(cls, *args: Any, **options: Any):
        if len(args) == 2 and isinstance(args[1], Path):  # I18n(config, workdir): what ``app.i18n`` used to be
            return Translator(*args)
        return super().__new__(cls)

    def __init__(self, locales: list[str] | None = None, default: str | None = None, **options: Any) -> None:
        given = {"locales": locales, "default_locale": default}
        self.options = {"enable": True, **{k: v for k, v in given.items() if v is not None}, **options}

    def install(self, app: Any) -> None:
        app.config.defaults("i18n", **self.options)
        app.i18n = Translator(app.config, app.workdir)


def get_locale() -> str | None:
    """The language of the request being served (``"pt-BR"``); ``None`` outside one or with i18n off."""
    current = _current.get()
    return current[1] if current else None


def _active() -> Any:
    current = _current.get()
    return current[0].translations(current[1]) if current else None


# -- what the templates call ------------------------------------------------------


def template_gettext(message: str) -> str:
    t = _active()
    return t.gettext(message) if t else message


def template_ngettext(singular: str, plural: str, n: int) -> str:
    t = _active()
    if t:
        return t.ngettext(singular, plural, n)
    return singular if n == 1 else plural


def template_pgettext(context: str, message: str) -> str:
    t = _active()
    return t.pgettext(context, message) if t else message


def template_npgettext(context: str, singular: str, plural: str, n: int) -> str:
    t = _active()
    if t:
        return t.npgettext(context, singular, plural, n)
    return singular if n == 1 else plural


def template_variables() -> dict[str, str]:
    """``lang`` (``pt-BR``, for ``<html lang>``) and ``locale`` (``pt_BR``), added to every template."""
    current = _current.get()
    name = current[1] if current else "en"
    return {"lang": name.replace("_", "-"), "locale": name.replace("-", "_")}


# -- what Python code calls -------------------------------------------------------


def _fill(text: str, variables: dict[str, Any]) -> str:
    return text % variables if variables else text


def gettext(message: str, **variables: Any) -> str:
    """`message` in the language of the current request; ``%(name)s`` placeholders are filled from `variables`."""
    return _fill(template_gettext(message), variables)


_ = gettext


def ngettext(singular: str, plural: str, n: int, **variables: Any) -> str:
    """The plural form for `n` (``%(num)d`` is filled with `n`)."""
    variables.setdefault("num", n)
    return template_ngettext(singular, plural, n) % variables


def pgettext(context: str, message: str, **variables: Any) -> str:
    """`message` disambiguated by `context` (``pgettext("menu", "File")``)."""
    return _fill(template_pgettext(context, message), variables)


class LazyString:
    """A message translated when it is turned into text, not when it is defined.

    For module-level texts (form labels, constants) that are read before any
    request exists: ``TITLE = lazy_gettext("Dashboard")``.
    """

    __slots__ = ("_message", "_variables")

    def __init__(self, message: str, variables: dict[str, Any] | None = None) -> None:
        self._message = message
        self._variables = variables or {}

    def __str__(self) -> str:
        return gettext(self._message, **self._variables)

    def __repr__(self) -> str:
        return f"LazyString({self._message!r})"

    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(self._message)

    def __add__(self, other: Any) -> str:
        return str(self) + str(other)

    def __radd__(self, other: Any) -> str:
        return str(other) + str(self)

    def __mod__(self, other: Any) -> str:
        return str(self) % other

    def __len__(self) -> int:
        return len(str(self))


def lazy_gettext(message: str, **variables: Any) -> LazyString:
    """Like `gettext`, but translated each time the result is used."""
    return LazyString(message, variables)


def _of(request: Request) -> tuple[Any, str | None]:
    i18n = getattr(request.app, "i18n", None)
    locale = getattr(request, "locale", None)
    return (i18n, locale) if i18n is not None and i18n.enabled and locale else (None, None)


def translate(request: Request, message: str, **variables: Any) -> str:
    """`message` in the language of `request` (no current-request context needed, e.g. in a thread)."""
    i18n, locale = _of(request)
    return _fill(i18n.translations(locale).gettext(message) if i18n else message, variables)


def ntranslate(request: Request, singular: str, plural: str, n: int, **variables: Any) -> str:
    """The plural form for `n` in the language of `request`."""
    i18n, locale = _of(request)
    variables.setdefault("num", n)
    if i18n:
        return i18n.translations(locale).ngettext(singular, plural, n) % variables
    return (singular if n == 1 else plural) % variables


__all__ = [
    "Catalogs",
    "I18n",
    "LazyString",
    "Translator",
    "get_locale",
    "gettext",
    "lazy_gettext",
    "ngettext",
    "ntranslate",
    "parse_accept_language",
    "pgettext",
    "translate",
]
