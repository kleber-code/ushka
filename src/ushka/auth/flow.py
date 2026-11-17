"""The built-in login routes: ``/auth/<provider>/login`` and ``/auth/<provider>/callback``.

The flow, step by step:

1. ``login``: random ``state``, PKCE verifier and (OpenID Connect) ``nonce`` are
   made with `secrets` and kept in the session, together with the ``next`` page
   the visitor asked for, validated *before* it is stored. Then a redirect to the
   provider.
2. ``callback``: the stored flow is removed from the session first (it works
   once), ``state`` is compared in constant time, the code is traded for a token
   by the server (the client secret never reaches the browser), the profile is
   fetched, the e-mail must be verified and in an allowed domain. Only then the
   minimal profile goes in the session, the session id is rotated and the visitor
   is redirected to the stored ``next``.

Whatever goes wrong ends in a redirect to ``[oauth] login_error_path`` with a
short code (``?login_error=state``); text from the provider is never echoed.
"""

from __future__ import annotations

import hmac
import logging
import time
from typing import TYPE_CHECKING, Any

from ushka.auth.providers import PROVIDERS, OAuthError, Provider, new_token
from ushka.guard import safe
from ushka.guard.safe import plain
from ushka.http.exceptions import HTTPMethodNotAllowed, HTTPRedirect
from ushka.web.seo import origin_of, safe_url

if TYPE_CHECKING:
    from ushka.core.app import Ushka
    from ushka.http.request import Request

log = logging.getLogger("ushka")

#: How long a login may take between the redirect and the callback, in seconds.
FLOW_TTL = 600
#: Error codes that can appear in ``?login_error=``.
ERROR_CODES = ("denied", "provider", "state", "network", "token", "profile", "unverified", "domain", "config")


def _s(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def domains_of(config: Any) -> list[str]:
    """``[oauth] allowed_email_domains``, lower case, without a leading ``@``."""
    return [d.lower().lstrip("@") for d in _list(config.get("oauth_allowed_email_domains"))]


def enabled_providers(config: Any) -> list[str]:
    """The providers that have both a client id and a client secret."""
    return [n for n in PROVIDERS if _s(config.get(f"oauth_{n}_client_id")) and _s(config.get(f"oauth_{n}_client_secret"))]


def half_configured(config: Any) -> list[str]:
    """Providers with a client id or a secret, but not both."""
    return [n for n in PROVIDERS if bool(_s(config.get(f"oauth_{n}_client_id"))) != bool(_s(config.get(f"oauth_{n}_client_secret")))]


def prefix_of(config: Any) -> str:
    return (safe_url(_s(config.get("oauth_login_prefix") or "/auth")) or "/auth").rstrip("/")


def session_key(config: Any) -> str:
    return _s(config.get("oauth_session_key")) or "user"


def after_login(config: Any) -> str:
    return safe_url(_s(config.get("oauth_after_login") or "/")) or "/"


def error_path(config: Any) -> str:
    return safe_url(_s(config.get("oauth_login_error_path") or "/")) or "/"


def redirect_origin(request: Request | None, config: Any) -> str | None:
    """Where the provider sends the browser back: ``[oauth] redirect_base``, else the ``[seo] url`` rule.

    Never the ``Host`` header on its own: see `ushka.web.seo.origin_of`.
    """
    base = _s(config.get("oauth_redirect_base")).rstrip("/")
    if base:
        return base if safe_url(base).startswith(("http://", "https://")) else None
    return origin_of(request, config)


def problems(config: Any, production: bool = False) -> list[tuple[str, str]]:
    """``[(level, message)]`` for ``ushka check``; level is ``"error"`` or ``"warn"``."""
    found: list[tuple[str, str]] = []
    for name in half_configured(config):
        found.append(("warn", f"[oauth] {name}: set both {name}_client_id and {name}_client_secret (USHKA_OAUTH_{name.upper()}_CLIENT_SECRET); the {name} login is off"))
    active = enabled_providers(config)
    if not active:
        return found
    if redirect_origin(None, config) is None and not (config.get("app_debug") or _list(config.get("security_allowed_hosts"))):
        found.append(("error", "[oauth] has no trusted address for the redirect URI: set [oauth] redirect_base (or [seo] url), e.g. \"https://example.com\""))
    base = redirect_origin(None, config)
    if production and base and base.startswith("http://") and "localhost" not in base and "127.0.0.1" not in base:
        found.append(("warn", f"[oauth] redirect_base {base} is not https: providers and browsers expect https in production"))
    if production and _s(config.get("session_store") or "cookie").lower() == "cookie":
        found.append(("warn", '[oauth] [session] store is "cookie": a login lives in the browser and can not be revoked from the server; use store = "database"'))
    return found


# -- the routes ---------------------------------------------------------------------


def _param(request: Request, name: str, limit: int = 2048) -> str:
    """A query parameter as a plain ``str`` ("" when missing, repeated or too long)."""
    value = request.query.get(name)
    if not isinstance(value, str) or len(value) > limit:
        return ""
    return plain(value)


def _fail(config: Any, name: str, code: str) -> HTTPRedirect:
    log.warning("oauth %s: login failed (%s)", name, code)
    return HTTPRedirect(error_path(config), query={"login_error": code})


def _provider(config: Any, name: str) -> Provider:
    return PROVIDERS[name](_s(config.get(f"oauth_{name}_client_id")), _s(config.get(f"oauth_{name}_client_secret")))


def _domain_ok(identity: Any, domains: list[str]) -> bool:
    if not domains:
        return True
    domain = identity.domain
    if domain not in domains:
        return False
    # An address at a custom domain proves little on Google (any account can use one);
    # the Workspace domain claim does. gmail.com has no ``hd``.
    return not (identity.provider == "google" and domain != "gmail.com" and identity.hd != domain)


def install(app: Ushka) -> None:
    """Registers the login and callback routes of every provider that has credentials (yours win)."""
    config = app.config
    names = enabled_providers(config)
    if not names:
        return
    if redirect_origin(None, config) is None and not (config.get("app_debug") or _list(config.get("security_allowed_hosts"))):
        raise RuntimeError(
            "OAuth login needs a trusted address for the redirect URI. Set [oauth] redirect_base "
            '(or [seo] url) to your public origin, such as "https://example.com"; the Host header is never trusted.'
        )
    prefix = prefix_of(config)
    for name in names:
        app.add_builtin_route(f"{prefix}/{name}/login", _login_view(name, config))
        app.add_builtin_route(f"{prefix}/{name}/callback", _callback_view(name, config))


def _redirect_uri(request: Request, config: Any, name: str) -> str:
    origin = redirect_origin(request, config)
    if not origin:
        raise OAuthError("config")
    return f"{origin}{prefix_of(config)}/{name}/callback"


def _login_view(name: str, config: Any):
    async def login(request: Request):
        if request.method != "GET":
            raise HTTPMethodNotAllowed(["GET"])
        # `next` is checked now, before it is stored; the callback never reads it from the URL.
        target = safe.url(request.query.get("next"), allow=["/"], default=after_login(config))
        try:
            uri = _redirect_uri(request, config, name)
        except OAuthError as exc:
            raise _fail(config, name, exc.code) from None
        state, verifier, nonce = new_token(), new_token(64), new_token()
        request.session[f"_oauth_{name}"] = {"state": state, "verifier": verifier, "nonce": nonce, "next": target, "t": int(time.time())}
        url = _provider(config, name).authorization_url(uri, state, verifier, nonce, domains_of(config))
        raise HTTPRedirect(url)

    return login


def _callback_view(name: str, config: Any):
    async def callback(request: Request):
        if request.method != "GET":
            raise HTTPMethodNotAllowed(["GET"])
        session = request.session
        flow = session.pop(f"_oauth_{name}", None)  # one use: a replayed callback finds nothing
        got_state = _param(request, "state", 256)
        if not (
            isinstance(flow, dict)
            and isinstance(flow.get("state"), str)
            and got_state
            and hmac.compare_digest(got_state.encode(), flow["state"].encode())
            and isinstance(flow.get("t"), int) and 0 <= time.time() - flow["t"] <= FLOW_TTL
        ):
            raise _fail(config, name, "state")
        if _param(request, "error", 256):
            raise _fail(config, name, "denied" if _param(request, "error", 256) == "access_denied" else "provider")
        code = _param(request, "code")
        if not code:
            raise _fail(config, name, "provider")
        try:
            provider = _provider(config, name)
            token = await provider.exchange(code, flow["verifier"], _redirect_uri(request, config, name))
            identity = await provider.identity(token, flow["nonce"])
        except OAuthError as exc:
            raise _fail(config, name, exc.code) from None
        except Exception as exc:  # noqa: BLE001 - never a 500, never the message (it may hold provider text)
            log.warning("oauth %s: unexpected %s", name, type(exc).__name__)
            raise _fail(config, name, "provider") from None
        if not _domain_ok(identity, domains_of(config)):
            raise _fail(config, name, "domain")
        session[session_key(config)] = identity.profile()
        rotate = getattr(session, "rotate", None)
        if rotate is not None:  # server-side sessions: a new id at login (session fixation)
            rotate()
        target = safe.url(flow.get("next"), allow=["/"], default=after_login(config))
        raise HTTPRedirect(target)

    return callback
