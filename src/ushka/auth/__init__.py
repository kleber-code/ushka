"""Login with OAuth 2.0 / OpenID Connect: Google and GitHub, no extra dependency.

Configure the provider in ``[oauth]`` (the secret in the environment), and Ushka
serves ``/auth/google/login`` and ``/auth/google/callback``. In your routes::

    from ushka import Depends
    from ushka.auth import current_user, login_required

    @app.get("/account")
    async def account(user=Depends(login_required)):
        return f"Hello {user['name']}"

``current_user(request)`` is the profile (``provider, sub, email, name, picture``)
or None, ``login_url("google", next="/x")`` is the link for a button and
``logout(request)`` ends the session. See the guide: Sign in with Google and GitHub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from ushka.auth.flow import (
    after_login,
    enabled_providers,
    install,
    prefix_of,
    problems,
    session_key,
)
from ushka.auth.providers import (
    PROVIDERS,
    GitHub,
    Google,
    Identity,
    OAuthError,
    Provider,
)
from ushka.guard import safe
from ushka.http.exceptions import HTTPRedirect

if TYPE_CHECKING:
    from ushka.http.request import Request

__all__ = [
    "GitHub", "Google", "Identity", "OAuthError", "Provider",
    "current_user", "install", "login_required", "login_required_for", "login_url", "logout", "problems",
]


def current_user(request: Request) -> dict[str, str] | None:
    """The logged-in user's profile (``provider, sub, email, name, picture``), or None."""
    user = request.session.get(session_key(request.app.config))
    if isinstance(user, dict) and user.get("provider") and user.get("sub"):
        return dict(user)
    return None


def login_url(provider: str, next: str | None = None, *, config: Any = None) -> str:
    """The path that starts a login with `provider`, ready for a link or a button.

    `next` is where the visitor lands afterwards; it is checked again when the
    login starts, so any value is safe to pass.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; use one of {sorted(PROVIDERS)}")
    if config is None:
        from ushka.core.config import Config

        config = Config()
    url = f"{prefix_of(config)}/{provider}/login"
    if next:
        url += "?" + urlencode({"next": str(next)})
    return url


def _login_dependency(provider: str | None):
    async def dependency(request: Request) -> dict[str, str]:
        user = current_user(request)
        if user is not None:
            return user
        config = request.app.config
        name = provider or (enabled_providers(config) or [None])[0]
        if name is None:
            raise RuntimeError("login_required needs a provider: set [oauth] google_client_id and google_client_secret (or github_...)")
        query = request.scope.get("query_string", b"").decode("latin-1")
        here = str(request.path) + (f"?{query}" if query else "")
        target = safe.url(here, allow=["/"], default=after_login(config))
        raise HTTPRedirect(login_url(name, target, config=config))

    return dependency


#: ``Depends(login_required)``: the user's profile, or a redirect to the login (back here afterwards).
#: With several providers it uses the first configured one; see `login_required_for`.
login_required = _login_dependency(None)


def login_required_for(provider: str):
    """Like `login_required`, but sends visitors to `provider`: ``Depends(login_required_for("github"))``."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; use one of {sorted(PROVIDERS)}")
    return _login_dependency(provider)


def logout(request: Request) -> None:
    """Ends the login: the session is emptied (server-side sessions are revoked)."""
    request.session.clear()
