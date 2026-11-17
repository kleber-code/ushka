"""`ImapClient`: read the inbox of a mailbox (support, leads, receipts) from an app.

It is the standard library's `imaplib` (blocking) called outside the event
loop with `asyncio.to_thread`, and `email` to parse, so it adds no dependency.

The e-mail is written by strangers, so everything in it is hostile input:

* every text taken from a message (subject, sender, body, attachment names) is
  `Untrusted` and the guard refuses it in HTML, redirects, paths and SQL;
* values you put *into* an IMAP command (search terms, folder names) are quoted
  and escaped, and CR, LF and NUL are refused, so a search term cannot append a
  command;
* the connection is TLS with the certificate and host name verified; plain text
  needs ``allow_insecure = true``;
* a message over ``max_message_kb`` is refused from its size, before its body is
  downloaded, and the number and depth of MIME parts are capped;
* the password and the message bodies are never logged and never in a ``repr``.

Import it explicitly (``from ushka.mail import ImapClient``): ``import ushka``
does not load it.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import codecs
import contextlib
import imaplib
import io
import logging
import os
import re
import ssl
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any

from ushka.guard import Untrusted
from ushka.http.uploads import UploadFile, safe_filename

__all__ = [
    "Attachment",
    "ImapClient",
    "ImapError",
    "ImapSecurityError",
    "Message",
    "MessageNotFound",
    "MessageRefused",
    "build_search",
    "decode_folder",
    "encode_folder",
    "parse_message",
]

log = logging.getLogger("ushka.mail")

MAX_DEPTH = 10
_MAX_ADDRESSES = 200
_MAX_HEADERS = 500
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ImapError(Exception):
    """The server or the connection failed. The message never contains the password or a message body."""


class ImapSecurityError(ImapError, ValueError):
    """Refused because it would be unsafe: an injected command, an unverified or plain-text connection."""


class MessageRefused(ImapError):
    """A message over the size, part or depth limit. It is not downloaded or not parsed."""


class MessageNotFound(ImapError, LookupError):
    """No message with that UID in the selected folder."""


# -- quoting what goes into a command --------------------------------------------

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ATOM = re.compile(r"[A-Za-z0-9_$.\-]{1,64}\Z")
_UID_SET = re.compile(r"(?:\d+|\*)(?::(?:\d+|\*))?(?:,(?:\d+|\*)(?::(?:\d+|\*))?)*\Z")


def _quote(value: object, what: str = "value") -> str:
    """An IMAP quoted string. CR, LF, NUL and every other control character are refused."""
    if not isinstance(value, str):
        raise TypeError(f"{what} must be a str, not {type(value).__name__}")
    if _CONTROL.search(value):
        raise ImapSecurityError(f"{what} contains a control character (CR, LF or NUL); refused to build an IMAP command from it")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def encode_folder(name: str) -> str:
    """A folder name in IMAP's modified UTF-7 (``"Caixa de Entrada/Faturas ção"`` -> ASCII)."""
    if not isinstance(name, str):
        raise TypeError("a folder name must be a str")
    if _CONTROL.search(name):
        raise ImapSecurityError("a folder name contains a control character; refused")
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if run:
            data = "".join(run).encode("utf-16-be")
            out.append("&" + base64.b64encode(data).decode("ascii").rstrip("=").replace("/", ",") + "-")
            run.clear()

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            run.append(ch)
    flush()
    return "".join(out)


def decode_folder(name: str) -> str:
    """The inverse of `encode_folder`. Malformed runs are left as they are."""

    def repl(m: re.Match[str]) -> str:
        chunk = m.group(1)
        if not chunk:
            return "&"
        raw = chunk.replace(",", "/")
        try:
            return base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-16-be", "replace")
        except (binascii.Error, ValueError):
            return m.group(0)

    return re.sub(r"&([^-]*)-", repl, name)


def _folder_arg(name: str) -> str:
    return _quote(encode_folder(name), "folder name")


def _imap_date(value: object, what: str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return f"{value.day:02d}-{_MONTHS[value.month - 1]}-{value.year:04d}"


_FLAG_KEYS = {
    "seen": "SEEN",
    "unseen": "UNSEEN",
    "flagged": "FLAGGED",
    "unflagged": "UNFLAGGED",
    "answered": "ANSWERED",
    "unanswered": "UNANSWERED",
    "deleted": "DELETED",
    "undeleted": "UNDELETED",
    "draft": "DRAFT",
    "undraft": "UNDRAFT",
}
_TEXT_KEYS = {"from_": "FROM", "to": "TO", "cc": "CC", "bcc": "BCC", "subject": "SUBJECT", "body": "BODY", "text": "TEXT"}
_DATE_KEYS = {
    "since": "SINCE",
    "before": "BEFORE",
    "on": "ON",
    "sent_since": "SENTSINCE",
    "sent_before": "SENTBEFORE",
    "sent_on": "SENTON",
}
_SIZE_KEYS = {"larger": "LARGER", "smaller": "SMALLER"}


def build_search(**criteria: Any) -> list[bytes]:
    """The tokens of a ``UID SEARCH``, built only from validated parts.

    Keywords: flags (``unseen=True``, ``seen``, ``flagged``, ``answered``,
    ``deleted``, ``draft`` and their negations), text (``from_``, ``to``,
    ``cc``, ``bcc``, ``subject``, ``body``, ``text``), dates (``since``,
    ``before``, ``on``, ``sent_since``, ``sent_before``, ``sent_on``), sizes
    (``larger``, ``smaller``, in bytes), ``header=("X-Name", "value")``,
    ``keyword=`` / ``unkeyword=`` and ``uid=`` (an int, a list of ints or a set
    such as ``"5:9"``). No criteria means ``ALL``.

    Text values are quoted and escaped; one with a CR, LF or NUL raises
    `ImapSecurityError`. Non-ASCII text is sent as UTF-8 quoted text (the
    client then adds ``CHARSET UTF-8``).
    """
    out: list[str] = []
    for key, value in criteria.items():
        if value is None:
            continue
        if key in _FLAG_KEYS:
            if not isinstance(value, bool):
                raise TypeError(f"{key} must be True or False")
            if value:
                out.append(_FLAG_KEYS[key])
        elif key in _TEXT_KEYS:
            out += [_TEXT_KEYS[key], _quote(value, key)]
        elif key in _DATE_KEYS:
            out += [_DATE_KEYS[key], _imap_date(value, key)]
        elif key in _SIZE_KEYS:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypeError(f"{key} must be a non-negative int (bytes)")
            out += [_SIZE_KEYS[key], str(value)]
        elif key == "header":
            if not (isinstance(value, tuple) and len(value) == 2):
                raise TypeError('header must be a ("Name", "value") pair')
            name, text = value
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", name):
                raise ImapSecurityError("a header name may only have letters, digits and dashes")
            out += ["HEADER", name, _quote(text, "header value")]
        elif key in ("keyword", "unkeyword"):
            if not isinstance(value, str) or not _ATOM.match(value):
                raise ImapSecurityError(f"{key} must be a plain flag name (letters, digits, _ $ . -)")
            out += [key.upper(), value]
        elif key == "uid":
            out += ["UID", _uid_set(value)]
        else:
            raise TypeError(f"unknown search criterion {key!r}")
    return [t.encode("utf-8") for t in (out or ["ALL"])]


def _uid(value: object) -> int:
    if isinstance(value, bool):
        raise ImapSecurityError("a UID must be a positive integer")
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
        value = int(value)
    if not isinstance(value, int) or not 0 < value < 2**32:
        raise ImapSecurityError("a UID must be a positive integer")
    return value


def _uid_set(value: object) -> str:
    if isinstance(value, str):
        if not _UID_SET.match(value):
            raise ImapSecurityError('a UID set looks like "5", "5:9" or "1,4:6"')
        return value
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        items = [str(_uid(v)) for v in value]
        if not items:
            raise ImapSecurityError("an empty UID list")
        return ",".join(items)
    return str(_uid(value))


# -- messages ----------------------------------------------------------------------


@dataclass(eq=False)
class Attachment:
    """A file attached to a message. Everything the sender wrote about it is `Untrusted`.

    `filename` and `content_type` are the sender's claims; use `safe_filename`
    for a name on disk and let `save` do the writing.
    """

    filename: str
    content_type: str
    _data: bytes = field(repr=False)

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def safe_filename(self) -> str:
        """`filename` cleaned for the file system: only the base name, no ``/``, ``\\``, ``..`` or NUL."""
        return safe_filename(self.filename, default="attachment")

    def read(self) -> bytes:
        """The decoded content."""
        return self._data

    def save(
        self,
        directory: str | os.PathLike[str],
        name: str | None = None,
        *,
        extensions: Iterable[str] | None = None,
        overwrite: bool = False,
    ) -> Any:
        """Writes it into `directory` exactly like `UploadFile.save`.

        Without `name` a random name with the cleaned extension is used; pass
        ``name=att.safe_filename`` to keep the sender's. Never overwrites unless
        asked, never follows a symlink, and `extensions` limits what is accepted.
        """
        upload = UploadFile(self.safe_filename, "application/octet-stream", io.BytesIO(self._data), len(self._data), taint=False)
        return upload.save(directory, name, extensions=extensions, overwrite=overwrite)

    def __repr__(self) -> str:
        return f"Attachment(filename={str.__repr__(self.safe_filename)}, size={self.size})"


@dataclass(eq=False)
class Message:
    """One e-mail. Every text field is `Untrusted` (source ``"mail:<field>"``).

    `html` is the raw HTML of the sender: render it only after `safe.html` or
    a sanitiser, never with ``|safe``. `date` is timezone-aware, or ``None``
    when the header is missing or invalid; `message_id` is ``None`` when absent.
    """

    uid: int
    message_id: str | None = None
    subject: str = ""
    from_: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    date: datetime | None = None
    text: str = ""
    html: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    size: int = 0

    @property
    def from_address(self) -> str:
        """Only the address of `from_` (still `Untrusted`, and still the sender's claim: ``From`` is easy to forge)."""
        addr = parseaddr(str(self.from_))[1]
        return Untrusted(addr, "mail:from") if isinstance(self.from_, Untrusted) else addr

    def __repr__(self) -> str:  # no subject, no body: a repr ends up in logs
        return f"Message(uid={self.uid}, size={self.size}, attachments={len(self.attachments)})"


def _scrub(text: str) -> str:
    """Valid text without NUL, whatever bytes the sender used."""
    try:
        text = text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except UnicodeEncodeError:
        text = text.encode("utf-8", "replace").decode("utf-8", "replace")
    return text.replace("\x00", "\ufffd")


_LINE_BREAKS = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]+")


def _line(text: str) -> str:
    return _LINE_BREAKS.sub(" ", _scrub(text)).strip()


def _decode_words(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001 - an invalid encoded word or unknown charset must not lose the message
        return raw


def _header(msg: Any, name: str) -> str | None:
    """A header decoded (RFC 2047), or ``None``; never raises."""
    try:
        value = msg[name]
        return None if value is None else str(value)
    except Exception:  # noqa: BLE001 - a malformed header must not raise: fall back to the raw one
        for key, raw in msg.raw_items():
            if key.lower() == name.lower():
                return _decode_words(str(raw))
        return None


def _decode_body(data: bytes, charset: str | None) -> str:
    name = "utf-8"
    if charset:
        try:
            codecs.lookup(charset)
            name = charset
        except LookupError:
            pass
    try:
        return data.decode(name, "replace")
    except (LookupError, TypeError):  # codecs that are not text encodings (zlib, base64...)
        return data.decode("utf-8", "replace")


def _addresses(msg: Any, name: str, mark: Callable[[str, str], str]) -> list[str]:
    values = []
    for value in msg.get_all(name, []) or []:
        try:
            values.append(str(value))
        except Exception:  # noqa: BLE001, S112 - a header that cannot be read is skipped
            continue
    out = []
    for display, addr in getaddresses(values)[:_MAX_ADDRESSES]:
        entry = _line(f"{display} <{addr}>" if display and addr else addr or display)
        if entry:
            out.append(mark(entry, f"mail:{name}"))
    return out


def _parse_date(msg: Any) -> datetime | None:
    raw = _header(msg, "date")
    if not raw:
        return None
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if when is None:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def parse_message(
    raw: bytes,
    uid: int = 0,
    *,
    max_parts: int = 100,
    max_depth: int = MAX_DEPTH,
    taint: bool = True,
) -> Message:
    """Parses RFC 822 bytes into a `Message`. Raises `MessageRefused` over the part or depth limits.

    It never raises for a malformed header, a broken charset or a bad date:
    those become replacement characters, ``None`` or the raw text.
    """

    def mark(value: str, source: str) -> str:
        return Untrusted(value, source) if taint else value

    try:
        msg = message_from_bytes(raw, policy=policy.default)
    except RecursionError:
        raise MessageRefused("message refused: MIME parts nested too deeply") from None

    text: list[str] = []
    html: list[str] = []
    attachments: list[Attachment] = []
    seen = 0
    stack: list[tuple[Any, int]] = [(msg, 0)]
    while stack:
        part, depth = stack.pop()
        seen += 1
        if seen + len(stack) > max_parts:
            raise MessageRefused(f"message refused: more than {max_parts} MIME parts")
        if depth > max_depth:
            raise MessageRefused(f"message refused: MIME parts nested deeper than {max_depth}")
        maintype = part.get_content_maintype()
        if maintype == "multipart":
            children = part.get_payload()
            if isinstance(children, list):
                stack.extend((child, depth + 1) for child in reversed(children))
            continue
        try:
            filename = part.get_filename()
        except Exception:  # noqa: BLE001 - a part that cannot be read is an attachment without a name
            filename = None
        ctype = part.get_content_type()
        try:
            disposition = part.get_content_disposition()
        except Exception:  # noqa: BLE001 - a part that cannot be read has no disposition
            disposition = None
        if maintype == "message":
            children = part.get_payload()
            try:
                data = b"".join(c.as_bytes() for c in children) if isinstance(children, list) else b""
            except Exception:  # noqa: BLE001 - an attached message that cannot be serialised is kept empty
                data = b""
        else:
            try:
                data = part.get_payload(decode=True) or b""
            except Exception:  # noqa: BLE001 - a payload that cannot be decoded is empty
                data = b""
        is_body = ctype in ("text/plain", "text/html") and disposition != "attachment" and not filename
        if is_body:
            body = _scrub(_decode_body(data, part.get_content_charset()))
            (html if ctype == "text/html" else text).append(body)
        else:
            attachments.append(
                Attachment(
                    mark(_scrub(filename or ""), "mail:attachment_filename"),
                    mark(_line(ctype), "mail:attachment_type"),
                    data,
                )
            )

    headers: dict[str, str] = {}
    for key, _value in list(msg.raw_items())[:_MAX_HEADERS]:
        name = _line(key).lower()
        if name and name not in headers:
            headers[name] = mark(_line(_header(msg, key) or ""), "mail:header")
    message_id = _header(msg, "message-id")
    return Message(
        uid=uid,
        message_id=mark(_line(message_id), "mail:message_id") if message_id and _line(message_id) else None,
        subject=mark(_line(_header(msg, "subject") or ""), "mail:subject"),
        from_=mark(_line(_header(msg, "from") or ""), "mail:from"),
        to=_addresses(msg, "to", mark),
        cc=_addresses(msg, "cc", mark),
        date=_parse_date(msg),
        text=mark("\n\n".join(text), "mail:text"),
        html=mark("\n".join(html), "mail:html"),
        attachments=attachments,
        headers=headers,
        size=len(raw),
    )


# -- the client ----------------------------------------------------------------------


class _Secret:
    """Holds the password so that a repr, a log line or a debug page shows ``***``."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "'***'"

    __str__ = __repr__

    def __reduce__(self) -> Any:
        raise TypeError("a password is not pickled")


def _verified(context: ssl.SSLContext) -> ssl.SSLContext:
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise ImapSecurityError("ssl_context must verify the certificate and the host name (CERT_REQUIRED and check_hostname)")
    return context


#: IMAP servers of the big mail providers, by short name. ``host = "gmail"`` is ``imap.gmail.com``.
PROVIDER_HOSTS = {
    "gmail": "imap.gmail.com",
    "outlook": "outlook.office365.com",
    "icloud": "imap.mail.me.com",
    "yahoo": "imap.mail.yahoo.com",
    "fastmail": "imap.fastmail.com",
    "zoho": "imap.zoho.com",
}
#: Address domains that map to a provider in `PROVIDER_HOSTS`.
_DOMAINS = {
    "gmail.com": "gmail", "googlemail.com": "gmail",
    "outlook.com": "outlook", "hotmail.com": "outlook", "live.com": "outlook", "msn.com": "outlook",
    "icloud.com": "icloud", "me.com": "icloud", "mac.com": "icloud",
    "yahoo.com": "yahoo", "ymail.com": "yahoo",
    "fastmail.com": "fastmail", "fastmail.fm": "fastmail",
    "zoho.com": "zoho",
}


def host_for(address: str) -> str:
    """The IMAP host of a well-known provider from an e-mail address, or "" (no guess for other domains)."""
    provider = _DOMAINS.get(address.rpartition("@")[2].strip().lower())
    return PROVIDER_HOSTS[provider] if provider else ""


class ImapClient:
    """An asynchronous IMAP client with one connection, used as ``async with``.

    >>> async with ImapClient() as mail:      # doctest: +SKIP
    ...     async for msg in mail.unseen():
    ...         ...
    ...         await mail.mark_seen(msg.uid)

    Commands are serialised by a lock (`imaplib` is not thread-safe), run in a
    worker thread, and use UIDs, never sequence numbers. After a dropped
    connection the next command reconnects and selects the same folder again.

    Whatever you do not pass comes from ``[imap]`` (and ``USHKA_IMAP_PASSWORD``), so
    ``ImapClient()`` is the client of ``ushka.toml``. A misspelt option raises `TypeError`.

    With no host, it is taken from the user's address when that is at a well-known provider
    (``you@gmail.com`` is ``imap.gmail.com``), and ``host="gmail"`` names a provider too
    (see `PROVIDER_HOSTS`). Any other server needs its host: Ushka does not guess where to
    send a password.

    Parameters
    ----------
    host, user, password : str, optional
        The password is kept out of ``repr`` and error messages.
    **options
        The other keys of ``[imap]``: ``port`` (993), ``ssl`` (TLS from the first byte,
        certificate and host name verified), ``starttls`` (with ``ssl=False``: upgrade a plain
        connection to verified TLS before logging in), ``allow_insecure`` (needed for plain text;
        logs a warning), ``folder``, ``timeout``, ``max_message_kb``, ``max_parts``. And three
        that are code: ``ssl_context`` (a private CA; it must verify certificate and host
        name), ``taint`` (text from the e-mail is `Untrusted`; follows ``[security] taint``)
        and ``max_depth`` (nesting of MIME parts). ``config`` is the `Config` to read
        (the app's by default).
    """

    #: Keys of ``[imap]`` taken as options, then the ones that exist only in code.
    _OPTIONS = ("port", "ssl", "starttls", "allow_insecure", "folder", "timeout", "max_message_kb", "max_parts")
    _CODE_OPTIONS = ("ssl_context", "taint", "max_depth", "config")

    def __init__(self, host: str | None = None, user: str | None = None, password: str | None = None, **options: Any) -> None:
        from ushka.core.settings import reject_options

        reject_options("ImapClient()", options, (*self._OPTIONS, *self._CODE_OPTIONS))
        config = options.pop("config", None)
        if config is None:
            from ushka.core.config import Config

            config = Config()
            config.load_from_file(config._path)  # a script reads ushka.toml too; the app's is read again, unchanged
        host = config.get("imap_host") if host is None else host
        user = config.get("imap_user") if user is None else user
        password = config.get("imap_password") if password is None else password
        values = {key: config.get(f"imap_{key}") for key in self._OPTIONS}
        values.update(options)
        port, ssl, starttls, allow_insecure = values["port"], values["ssl"], values["starttls"], values["allow_insecure"]
        folder, timeout = values["folder"], values["timeout"]
        max_message_kb, max_parts = values["max_message_kb"], values["max_parts"]
        max_depth = values.get("max_depth", MAX_DEPTH)
        ssl_context = values.get("ssl_context")
        taint = values["taint"] if "taint" in values else config.get("security_taint", True) is not False
        if not host and isinstance(user, str):
            host = host_for(user)  # a well-known provider, from the address
        elif isinstance(host, str) and host.lower() in PROVIDER_HOSTS:
            host = PROVIDER_HOSTS[host.lower()]  # ImapClient("gmail")
        if not host:
            raise ImapError("no IMAP host: set [imap] host, pass host=, or use an address at a known provider (gmail, outlook, icloud, yahoo, fastmail, zoho)")
        for what, value in (("host", host), ("user", user), ("password", password)):
            if not isinstance(value, str) or _CONTROL.search(value):
                raise ImapSecurityError(f"the IMAP {what} must be a str without control characters")
        if ssl and starttls:
            raise ImapSecurityError("ssl = true and starttls = true are exclusive: starttls upgrades a plain connection, so set ssl = false")
        if not ssl and not starttls and not allow_insecure:
            raise ImapSecurityError(
                "refusing a plain-text IMAP connection: use ssl = true (port 993) or starttls = true, "
                "or set allow_insecure = true to send the password in the clear (local test servers only)"
            )
        if not ssl and not starttls:
            log.warning("IMAP connection to %s is NOT encrypted (allow_insecure = true): the password and the mail travel in clear text", host)
        self.host = host
        self.user = user
        self._password = _Secret(password)
        self.port = int(port)
        self.ssl = bool(ssl)
        self.starttls = bool(starttls)
        self.allow_insecure = bool(allow_insecure)
        self.folder = folder
        self.timeout = timeout
        self.max_message_bytes = int(max_message_kb) * 1024
        self.max_parts = int(max_parts)
        self.max_depth = int(max_depth)
        self.taint = taint
        self._ssl_context = _verified(ssl_context) if ssl_context is not None else None
        self._conn: Any = None
        self._current = folder
        self._caps: set[str] = set()
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, config: Any = None, **overrides: Any) -> ImapClient:
        """``ImapClient(config=config, **overrides)``: a client from ``[imap]``; keywords override single settings."""
        return cls(config=config, **overrides)

    def __repr__(self) -> str:
        return f"ImapClient(host={self.host!r}, user={self.user!r}, port={self.port}, ssl={self.ssl})"

    # -- connection ------------------------------------------------------------------

    async def __aenter__(self) -> ImapClient:  # noqa: PYI034
        await self._call("connect", lambda conn: None)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Logs out and closes the connection. Safe to call twice."""
        async with self._lock:
            conn, self._conn = self._conn, None
            if conn is not None:
                await asyncio.to_thread(self._logout, conn)

    @staticmethod
    def _logout(conn: Any) -> None:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 - closing must never raise
            with contextlib.suppress(Exception):
                conn.shutdown()

    def _connect(self) -> Any:
        if not self._password:
            raise ImapError("no IMAP password: set USHKA_IMAP_PASSWORD")
        context = self._ssl_context or ssl.create_default_context()
        if self.ssl:
            conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=context, timeout=self.timeout)
        else:
            conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
            if self.starttls:
                try:
                    conn.starttls(ssl_context=context)
                except Exception:
                    with contextlib.suppress(Exception):
                        conn.shutdown()
                    raise
        try:
            try:
                conn.login(self.user, self._password.reveal())
            except UnicodeEncodeError:
                raise ImapError("IMAP credentials must be ASCII; use an app password") from None
            typ, data = conn.capability()
            self._caps = {c.upper() for c in b" ".join(d for d in data if isinstance(d, bytes)).decode("ascii", "replace").split()}
            typ, data = conn.select(_folder_arg(self._current))
            if typ != "OK":
                raise ImapError(f"cannot select folder {self._current!r}")
        except BaseException:
            with contextlib.suppress(Exception):
                conn.shutdown()
            raise
        log.debug("IMAP connected to %s as %s, folder %s", self.host, self.user, self._current)
        return conn

    def _short(self, exc: BaseException) -> str:
        text = exc.args[0] if exc.args else str(exc)
        text = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
        secret = self._password.reveal()
        if secret:
            text = text.replace(secret, "***")
        return (type(exc).__name__ + ": " + _line(text))[:200]

    async def _call(self, op: str, work: Callable[[Any], Any]) -> Any:
        """Runs `work(conn)` in a thread while holding the lock; the connection is made on demand."""

        def run() -> Any:
            if self._conn is None:
                self._conn = self._connect()
            return work(self._conn)

        async with self._lock:
            future = asyncio.ensure_future(asyncio.to_thread(run))
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                # a thread cannot be interrupted: keep the lock until it stops, or two commands would interleave
                with contextlib.suppress(BaseException):
                    await future
                raise
            except ImapError:
                raise
            except (imaplib.IMAP4.error, OSError, EOFError) as exc:
                if isinstance(exc, (imaplib.IMAP4.abort, OSError, EOFError)):
                    self._drop()
                what = "timed out" if isinstance(exc, TimeoutError) else "failed"
                raise ImapError(f"IMAP {op} {what}: {self._short(exc)}") from exc

    def _drop(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.shutdown()

    @staticmethod
    def _ok(op: str, result: tuple[str, list[Any]]) -> list[Any]:
        typ, data = result
        if typ != "OK":
            raise ImapError(f"IMAP {op} was refused by the server")
        return data

    # -- folders ---------------------------------------------------------------------

    async def folders(self) -> list[str]:
        """The names of all folders, decoded from modified UTF-7."""

        def work(conn: Any) -> list[str]:
            data = self._ok("LIST", conn.list())
            names = []
            for item in data:
                if isinstance(item, tuple):  # the name came as a literal
                    names.append(item[1].decode("utf-8", "replace"))
                elif isinstance(item, bytes):
                    m = re.match(rb'\((?P<flags>[^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)\Z', item)
                    if not m:
                        continue
                    name = m.group("name").decode("utf-8", "replace")
                    if name.startswith('"') and name.endswith('"'):
                        name = re.sub(r"\\(.)", r"\1", name[1:-1])
                    names.append(name)
            return [decode_folder(n) for n in names]

        return await self._call("LIST", work)

    async def select(self, folder: str, *, readonly: bool = False) -> int:
        """Selects `folder`; returns how many messages it has."""
        arg = _folder_arg(folder)

        def work(conn: Any) -> int:
            typ, data = conn.select(arg, readonly)
            if typ != "OK":
                raise ImapError(f"cannot select folder {folder!r}")
            self._current = folder
            try:
                return int(data[0])
            except (TypeError, ValueError, IndexError):
                return 0

        return await self._call("SELECT", work)

    # -- searching and reading ------------------------------------------------------------

    async def search(self, *, limit: int | None = None, oldest: bool = False, **criteria: Any) -> list[int]:
        """UIDs of the messages matching `criteria` (see `build_search`), oldest first.

        With `limit`, only the newest `limit` UIDs, or the oldest ones with ``oldest=True``
        (what a queue wants: the next ones to process).
        """
        tokens = build_search(**criteria)
        if any(b > 127 for t in tokens for b in t):
            tokens = [b"CHARSET", b"UTF-8", *tokens]

        def work(conn: Any) -> list[int]:
            data = self._ok("SEARCH", conn.uid("SEARCH", *tokens))
            found = b" ".join(d for d in data if isinstance(d, bytes))
            uids = sorted(int(x) for x in found.split() if x.isdigit())
            if not limit:
                return uids
            return uids[:limit] if oldest else uids[-limit:]

        return await self._call("SEARCH", work)

    async def fetch(self, uid: int) -> Message:
        """Downloads and parses one message, without marking it seen.

        Raises `MessageRefused` when it is over ``max_message_kb`` (decided from
        ``RFC822.SIZE`` before the body is downloaded) or has too many or too deeply
        nested parts, and `MessageNotFound` when the UID does not exist.
        """
        number = _uid(uid)

        def work(conn: Any) -> bytes:
            data = self._ok("FETCH", conn.uid("FETCH", str(number), "(RFC822.SIZE)"))
            m = re.search(rb"RFC822\.SIZE\s+(\d+)", b" ".join(d for d in data if isinstance(d, bytes)))
            if not m:
                raise MessageNotFound(f"no message with UID {number}")
            if int(m.group(1)) > self.max_message_bytes:
                raise MessageRefused(f"message {number} refused: {int(m.group(1)) // 1024} KB is over max_message_kb")
            data = self._ok("FETCH", conn.uid("FETCH", str(number), "(BODY.PEEK[])"))
            raw = next((d[1] for d in data if isinstance(d, tuple) and isinstance(d[1], bytes)), None)
            if raw is None:
                raise MessageNotFound(f"no message with UID {number}")
            if len(raw) > self.max_message_bytes:
                raise MessageRefused(f"message {number} refused: it is over max_message_kb")
            return raw

        raw = await self._call("FETCH", work)
        log.debug("IMAP fetched uid %d (%d bytes)", number, len(raw))
        return await asyncio.to_thread(
            parse_message, raw, number, max_parts=self.max_parts, max_depth=self.max_depth, taint=self.taint
        )

    async def unseen(
        self,
        *,
        limit: int | None = None,
        on_error: Callable[[int, ImapError], Any] | None = None,
        mark_refused: bool = False,
    ) -> AsyncIterator[Message]:
        """The unread messages of the selected folder, oldest first. They stay unread: call `mark_seen`.

        With `limit`, the oldest `limit` unread messages: the next ones to process, so a queue
        drains from the front.

        A refused message (too big, too many parts) raises `MessageRefused`, or, when
        `on_error(uid, error)` is given, is passed to it and skipped. It stays unread and comes
        back on the next call, where it would take a place in `limit` again; with
        ``mark_refused=True`` it is marked read first, so it is reported once.
        """
        for uid in await self.search(unseen=True, limit=limit, oldest=True):
            try:
                yield await self.fetch(uid)
            except (MessageRefused, MessageNotFound) as exc:
                if mark_refused and isinstance(exc, MessageRefused):
                    await self.mark_seen(uid)
                if on_error is None:
                    raise
                on_error(uid, exc)

    # -- changing -----------------------------------------------------------------------

    async def _flag(self, uid: int, op: str, flag: str) -> None:
        number = _uid(uid)
        await self._call("STORE", lambda conn: self._ok("STORE", conn.uid("STORE", str(number), op, f"({flag})")))

    async def mark_seen(self, uid: int) -> None:
        await self._flag(uid, "+FLAGS.SILENT", r"\Seen")

    async def mark_unseen(self, uid: int) -> None:
        await self._flag(uid, "-FLAGS.SILENT", r"\Seen")

    def _delete(self, conn: Any, number: int) -> None:
        if "UIDPLUS" not in self._caps:
            # a plain EXPUNGE would also remove whatever else is flagged \Deleted: only do it when nothing else is
            data = self._ok("SEARCH", conn.uid("SEARCH", b"DELETED"))
            others = [x for x in b" ".join(d for d in data if isinstance(d, bytes)).split() if x.isdigit() and int(x) != number]
            if others:
                raise ImapError("the server lacks UIDPLUS and other messages are flagged \\Deleted: expunge them yourself first")
        self._ok("STORE", conn.uid("STORE", str(number), "+FLAGS.SILENT", r"(\Deleted)"))
        if "UIDPLUS" in self._caps:
            self._ok("EXPUNGE", conn.uid("EXPUNGE", str(number)))
        else:
            self._ok("EXPUNGE", conn.expunge())

    async def delete(self, uid: int) -> None:
        """Flags the message ``\\Deleted`` and expunges only that message (``UID EXPUNGE``)."""
        number = _uid(uid)
        await self._call("DELETE", lambda conn: self._delete(conn, number))

    async def move(self, uid: int, folder: str) -> None:
        """Copies the message to `folder`, then deletes it here. A failed copy deletes nothing."""
        number = _uid(uid)
        target = _folder_arg(folder)

        def work(conn: Any) -> None:
            self._ok("COPY", conn.uid("COPY", str(number), target))
            self._delete(conn, number)

        await self._call("MOVE", work)

