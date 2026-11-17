"""OAuth 2.0 / OpenID Connect providers: Google and GitHub, on the standard library.

A `Provider` knows its endpoints, how to build the authorization URL, how to
trade the code for a token and how to turn the token into an `Identity`.
Endpoints are class attributes: a test points them at a fake server by
subclassing or monkeypatching; they are never read from the user's
configuration, so a setting can not send the client secret somewhere else.

The HTTP transport is ``urllib`` run in a thread: TLS verification on, a
timeout, a cap on the size of the answer, and redirects are never followed.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

#: Largest answer read from a provider, in bytes.
MAX_RESPONSE_BYTES = 256 * 1024
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class OAuthError(Exception):
    """A login that failed. `code` is a short, fixed word safe to show in a URL.

    The message never holds text written by the provider or any secret.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Identity:
    """Who the provider says the user is (already verified)."""

    provider: str
    sub: str
    email: str
    name: str = ""
    picture: str = ""
    #: Google Workspace domain (the ``hd`` claim); empty for other accounts.
    hd: str = ""

    def profile(self) -> dict[str, str]:
        """The minimal profile kept in the session."""
        return {"provider": self.provider, "sub": self.sub, "email": self.email, "name": self.name, "picture": self.picture}

    @property
    def domain(self) -> str:
        return self.email.rpartition("@")[2].lower()


# -- PKCE and random values ----------------------------------------------------------


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def pkce_challenge(verifier: str) -> str:
    """The S256 code challenge of `verifier` (RFC 7636)."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


# -- transport -----------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the 3xx answer is raised as an HTTPError, never followed


def _fetch(url: str, data: bytes | None, headers: dict[str, str], timeout: float, allow_http: bool, limit: int) -> Any:
    scheme = urlsplit(url).scheme
    if scheme != "https" and not (allow_http and scheme == "http"):
        raise OAuthError("config")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(limit + 1)
    except urllib.error.HTTPError:
        raise OAuthError("provider") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise OAuthError("network") from None
    if len(body) > limit:
        raise OAuthError("provider")
    try:
        result = json.loads(body)
    except ValueError:
        raise OAuthError("provider") from None
    if not isinstance(result, (dict, list)):
        raise OAuthError("provider")
    return result


def _text(value: Any, limit: int) -> str:
    """A short plain string from provider data: no control characters."""
    if not isinstance(value, str):
        return ""
    return _CONTROL.sub("", value).strip()[:limit]


def _https_url(value: Any) -> str:
    value = _text(value, 500)
    parts = urlsplit(value)
    return value if parts.scheme == "https" and parts.netloc else ""


def _email(value: Any) -> str:
    value = _text(value, 320).lower()
    local, at, domain = value.rpartition("@")
    bad = any(c.isspace() or c in "<>\"',;" for c in value)
    return value if at and local and "." in domain and value.count("@") == 1 and not bad else ""


def _b64json(segment: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise OAuthError("token") from None
    if not isinstance(data, dict):
        raise OAuthError("token")
    return data


# -- providers -----------------------------------------------------------------------


class Provider:
    """Base of the providers. Subclass it and set the endpoints to add another one."""

    name = ""
    authorize_url = ""
    token_url = ""
    userinfo_url = ""
    scopes: tuple[str, ...] = ()
    #: OpenID Connect: send a ``nonce`` and check it in the ``id_token``.
    oidc = False
    #: Plain ``http`` endpoints (a fake server in tests). Never true for a real provider.
    allow_http = False
    timeout = 10.0
    max_response_bytes = MAX_RESPONSE_BYTES

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self._client_secret = client_secret

    def __repr__(self) -> str:  # the secret never shows up in a log or a traceback
        return f"<{type(self).__name__} client_id={self.client_id!r}>"

    # -- the browser leg
    def authorization_url(self, redirect_uri: str, state: str, verifier: str, nonce: str, domains: list[str]) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            **self.extra_params(domains),
        }
        if self.oidc:
            params["nonce"] = nonce
        return f"{self.authorize_url}?{urlencode(params)}"

    def extra_params(self, domains: list[str]) -> dict[str, str]:
        return {}

    # -- the server leg
    async def _get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        merged = {"Accept": "application/json", "User-Agent": "ushka-oauth", **(headers or {})}
        return await asyncio.to_thread(_fetch, url, None, merged, self.timeout, self.allow_http, self.max_response_bytes)

    async def _post(self, url: str, form: dict[str, str]) -> Any:
        headers = {"Accept": "application/json", "User-Agent": "ushka-oauth", "Content-Type": "application/x-www-form-urlencoded"}
        body = urlencode(form).encode("ascii")
        return await asyncio.to_thread(_fetch, url, body, headers, self.timeout, self.allow_http, self.max_response_bytes)

    async def exchange(self, code: str, verifier: str, redirect_uri: str) -> dict:
        """Trades the authorization code for a token response (client secret: server to server)."""
        try:
            token = await self._post(self.token_url, {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self._client_secret,
                "code_verifier": verifier,
            })
        except OAuthError as exc:
            raise OAuthError("token" if exc.code == "provider" else exc.code) from None
        if not isinstance(token, dict) or "error" in token:
            raise OAuthError("token")
        access = token.get("access_token")
        if not isinstance(access, str) or not access:
            raise OAuthError("token")
        kind = token.get("token_type")
        if kind is not None and (not isinstance(kind, str) or kind.lower() != "bearer"):
            raise OAuthError("token")
        return token

    async def identity(self, token: dict, nonce: str) -> Identity:
        raise NotImplementedError


class Google(Provider):
    """Google, as OpenID Connect: the ``userinfo`` endpoint with the access token from the token endpoint."""

    name = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
    scopes = ("openid", "email", "profile")
    oidc = True
    issuers = ("https://accounts.google.com", "accounts.google.com")

    def extra_params(self, domains: list[str]) -> dict[str, str]:
        # A hint for the account chooser only; the check is `identity` + the domain test.
        return {"hd": domains[0]} if len(domains) == 1 and domains[0] != "gmail.com" else {}

    def _check_id_token(self, token: dict, nonce: str) -> str:
        """The ``sub`` of the ``id_token``, after checking nonce, issuer, audience and expiry.

        The token came straight from the token endpoint over TLS, so its signature
        need not be checked (OpenID Connect Core 3.1.3.7); the claims still are.
        """
        raw = token.get("id_token")
        if not isinstance(raw, str) or raw.count(".") != 2:
            raise OAuthError("token")
        claims = _b64json(raw.split(".")[1])
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        expires = claims.get("exp")
        got_nonce = claims.get("nonce")
        valid = (
            claims.get("iss") in self.issuers
            and self.client_id in audiences
            and isinstance(expires, (int, float)) and expires > time.time() - 60
            and isinstance(got_nonce, str) and secrets.compare_digest(got_nonce.encode(), nonce.encode())
            and isinstance(claims.get("sub"), str)
        )
        if not valid:
            raise OAuthError("token")
        return claims["sub"]

    async def identity(self, token: dict, nonce: str) -> Identity:
        id_sub = self._check_id_token(token, nonce)
        info = await self._get(self.userinfo_url, {"Authorization": f"Bearer {token['access_token']}"})
        if not isinstance(info, dict):
            raise OAuthError("profile")
        sub = _text(info.get("sub"), 255)
        if not sub or sub != id_sub:
            raise OAuthError("profile")
        email = _email(info.get("email"))
        if not email:
            raise OAuthError("profile")
        if info.get("email_verified") not in (True, "true"):
            raise OAuthError("unverified")
        picture = _https_url(info.get("picture"))
        return Identity("google", sub, email, _text(info.get("name"), 200), picture, _text(info.get("hd"), 255).lower())


class GitHub(Provider):
    """GitHub: the user, and the primary verified e-mail address."""

    name = "github"
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    userinfo_url = "https://api.github.com/user"
    emails_url = "https://api.github.com/user/emails"
    scopes = ("read:user", "user:email")

    async def identity(self, token: dict, nonce: str) -> Identity:
        headers = {"Authorization": f"Bearer {token['access_token']}", "X-GitHub-Api-Version": "2022-11-28"}
        user = await self._get(self.userinfo_url, headers)
        emails = await self._get(self.emails_url, headers)
        if not isinstance(user, dict) or not isinstance(emails, list):
            raise OAuthError("profile")
        user_id = user.get("id")
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            raise OAuthError("profile")
        primary = [e for e in emails if isinstance(e, dict) and e.get("primary") is True and e.get("verified") is True]
        email = _email(primary[0].get("email")) if primary else ""
        if not email:
            raise OAuthError("unverified")
        name = _text(user.get("name"), 200) or _text(user.get("login"), 100)
        return Identity("github", str(user_id), email, name, _https_url(user.get("avatar_url")))


#: ``{name: class}`` of the providers Ushka ships.
PROVIDERS: dict[str, type[Provider]] = {"google": Google, "github": GitHub}
