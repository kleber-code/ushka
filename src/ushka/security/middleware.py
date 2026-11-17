"""Security middleware, on by default.

It runs around every request, outside your own middleware, so even error pages
and CORS preflights carry the protections. Everything is configured in the
``[security]`` section of ``ushka.toml`` (or ``USHKA_SECURITY_*``).

Order: trusted hosts, CORS preflight, CSRF, your handler, then the headers.

CSRF protection needs no token and no secret key. Browsers tell the server
where a request came from (``Sec-Fetch-Site`` and ``Origin``), and a
state-changing request that came from another site is refused. Requests with
neither header are not from a browser (curl, a mobile app, a server), so they
cannot be forged through a victim's browser and pass.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from ushka.http.exceptions import HTTPBadRequest, HTTPForbidden
from ushka.http.request import Request
from ushka.http.response import Response

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Applied unless the route or `[security] headers = false` says otherwise.
DEFAULT_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)

CallNext = Callable[[Request], Awaitable[Response]]


def _split(value) -> list[str]:
    """A list setting, written as a TOML list or as ``a, b`` in an env var."""
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def _origin_host(origin: str) -> str:
    return urlsplit(origin).netloc.lower()


def _host_allowed(host: str, patterns: list[str]) -> bool:
    host = host.lower()
    bare = host.rsplit(":", 1)[0] if not host.endswith("]") and ":" in host else host
    for pattern in patterns:
        pattern = pattern.lower()
        if pattern == "*" or host == pattern or bare == pattern:
            return True
        if pattern.startswith("*.") and bare.endswith(pattern[1:]):
            return True
    return False


class SecurityMiddleware:
    """Trusted hosts, CSRF, CORS and security headers, built from the config."""

    def __init__(self, config) -> None:
        get = config.get
        self.allowed_hosts = _split(get("security_allowed_hosts"))
        self.csrf = get("security_csrf", True) is not False
        self.csrf_trusted = [o.lower().rstrip("/") for o in _split(get("security_csrf_trusted_origins"))]
        self.csrf_exempt = _split(get("security_csrf_exempt_paths"))
        self.cors_origins = [o.lower().rstrip("/") for o in _split(get("security_cors_origins"))]
        self.cors_methods = ", ".join(_split(get("security_cors_methods")) or ["GET", "POST", "PUT", "PATCH", "DELETE"])
        self.cors_headers = _split(get("security_cors_headers"))
        self.cors_credentials = get("security_cors_credentials", False) is True
        self.cors_max_age = int(get("security_cors_max_age", 600) or 0)
        self.headers = self._build_headers(get) if get("security_headers", True) is not False else {}

        if self.cors_credentials and "*" in self.cors_origins:
            raise ValueError(
                "[security] cors_credentials cannot be combined with cors_origins = [\"*\"]: "
                "list the exact origins that may send cookies"
            )

    @staticmethod
    def _build_headers(get) -> dict[str, str]:
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": get("security_frame_options", "DENY"),
            "Referrer-Policy": get("security_referrer_policy", "strict-origin-when-cross-origin"),
            "Cross-Origin-Opener-Policy": "same-origin",
        }
        csp = get("security_csp") or DEFAULT_CSP
        if csp.lower() != "off":
            headers["Content-Security-Policy"] = csp
        return {k: v for k, v in headers.items() if v}

    # -- the middleware ----------------------------------------------------------

    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        h = request.headers
        origin = (h.get("origin") or "").lower().rstrip("/")

        if self.allowed_hosts and not _host_allowed(str(h.get("host") or ""), self.allowed_hosts):
            return await self._refuse(request, HTTPBadRequest(message="Invalid Host header"))

        cors_ok = bool(origin) and self._cors_allows(origin)
        if request.method == "OPTIONS" and origin and h.get("access-control-request-method"):
            if not cors_ok:
                return await self._refuse(request, HTTPForbidden(message="CORS origin not allowed"))
            response = Response(b"", status_code=204)
            self._cors_headers(response, origin, preflight=True, request_headers=h.get("access-control-request-headers"))
            return self._finish(request, response)

        if self.csrf and request.method not in SAFE_METHODS and not self._same_site_ok(request, origin, cors_ok):
            return await self._refuse(
                request,
                HTTPForbidden(message="Cross-site request blocked (CSRF protection)"),
            )

        response = await call_next(request)
        if cors_ok:
            self._cors_headers(response, origin)
        return self._finish(request, response)

    def websocket_allowed(self, request: Request) -> bool:
        """Handshake check: trusted host, and no cross-site browser (the
        WebSocket twin of CSRF: cookies ride along on a cross-site `new WebSocket`)."""
        h = request.headers
        if self.allowed_hosts and not _host_allowed(str(h.get("host") or ""), self.allowed_hosts):
            return False
        origin = (h.get("origin") or "").lower().rstrip("/")
        if not self.csrf:
            return True
        return self._same_site_ok(request, origin, bool(origin) and self._cors_allows(origin))

    # -- parts -------------------------------------------------------------------

    def _same_site_ok(self, request: Request, origin: str, cors_ok: bool) -> bool:
        path = request.path
        if any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.csrf_exempt):
            return True
        h = request.headers
        if origin and (cors_ok or origin in self.csrf_trusted):
            return True
        site = (h.get("sec-fetch-site") or "").lower()
        if site in ("same-origin", "none"):
            return True
        if site:  # same-site or cross-site, and the origin was not trusted above
            return False
        if not origin:
            return True  # not a browser, or an old one: nothing to forge through
        return origin != "null" and _origin_host(origin) == str(h.get("host") or "").lower()

    def _cors_allows(self, origin: str) -> bool:
        return "*" in self.cors_origins or origin in self.cors_origins

    def _cors_headers(self, response: Response, origin: str, preflight: bool = False, request_headers=None) -> None:
        allow = origin if (self.cors_credentials or "*" not in self.cors_origins) else "*"
        response.headers["Access-Control-Allow-Origin"] = allow
        if allow != "*":
            _vary(response, "Origin")
        if self.cors_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        if preflight:
            response.headers["Access-Control-Allow-Methods"] = self.cors_methods
            asked = self.cors_headers and ", ".join(self.cors_headers) or (str(request_headers) if request_headers else "")
            if asked:
                response.headers["Access-Control-Allow-Headers"] = asked
            if self.cors_max_age:
                response.headers["Access-Control-Max-Age"] = str(self.cors_max_age)

    async def _refuse(self, request: Request, error) -> Response:
        response = await request.app.error_handler.handle_exception(error, request)
        return self._finish(request, response)

    def _finish(self, request: Request, response: Response) -> Response:
        have = {k.lower() for k in response.headers}
        for name, value in self.headers.items():
            if name.lower() not in have:  # a route that set its own header wins
                response.headers[name] = value
        if request.is_secure and "strict-transport-security" not in have:
            hsts = request.app.config.get("security_hsts_seconds", 31536000)
            if hsts:
                response.headers["Strict-Transport-Security"] = f"max-age={int(hsts)}; includeSubDomains"
        return response


def _vary(response: Response, value: str) -> None:
    existing = next((k for k in response.headers if k.lower() == "vary"), None)
    if existing is None:
        response.headers["Vary"] = value
    elif value.lower() not in response.headers[existing].lower():
        response.headers[existing] += f", {value}"
