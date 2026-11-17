"""Forging a session for tests: the supported way to be "logged in" without a login.

``forge_session_cookie(app, {"uid": 1})`` returns ``"_ushka_session=..."``, a
cookie signed with the app's own secret key, ready for a test client, a
``curl --cookie`` or ``ushka verify --as-session uid=1``.

This is a **testing tool**. Whoever can run it holds the secret key and so can
become any user. Keep the key in the environment or ``.env`` (never on a command
line, never in ``ushka.toml``), and do not run it against the key of a real
production deployment. Nothing here logs a session value.
"""

from __future__ import annotations

from typing import Any

from .session import ServerSession, Session

__all__ = ["aforge_session_cookie", "forge_session_cookie", "parse_session_pairs"]


def _config(app_or_config: Any) -> Any:
    return getattr(app_or_config, "config", app_or_config)


def _secret(config: Any) -> str:
    secret = config.get("APP_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "Forging a session needs the app's secret key. Set USHKA_APP_SECRET_KEY in the environment "
            "or in .env (in debug mode Ushka makes a per-process key, which only works inside that process)."
        )
    return str(secret)


def _name(config: Any) -> str:
    return str(config.get("session_cookie_name", Session.COOKIE_NAME))


def _uses_server_store(app_or_config: Any) -> bool:
    from .stores import get_store

    return hasattr(app_or_config, "config") and get_store(app_or_config) is not None


def forge_session_cookie(app_or_config: Any, data: dict[str, Any]) -> str:
    """A signed session cookie holding `data`, as ``"name=value"``.

    `app_or_config` is the app (or its ``Config``). Works for the default
    signed-cookie sessions; when the app keeps sessions on the server
    (``[session] store = "database"``) use the coroutine `aforge_session_cookie`,
    which also creates the record in the store.

    Raises
    ------
    RuntimeError
        If there is no secret key, or the app uses a server-side store.
    """
    if _uses_server_store(app_or_config):
        raise RuntimeError('This app keeps sessions in a store ([session] store = "database"): use "await aforge_session_cookie(app, data)".')
    config = _config(app_or_config)
    session = Session(_secret(config), max_age=int(config.get("session_max_age", 1209600)))
    session.update(data)
    return f"{_name(config)}={session._encode()}"


async def aforge_session_cookie(app_or_config: Any, data: dict[str, Any]) -> str:
    """Like `forge_session_cookie`, and also works with a server-side store.

    With ``[session] store = "database"`` it writes the session record to the
    store (so use a test database) and returns the cookie that points to it.
    """
    from .stores import get_store

    config = _config(app_or_config)
    store = get_store(app_or_config) if hasattr(app_or_config, "config") else None
    if store is None:
        return forge_session_cookie(app_or_config, data)
    session = ServerSession(
        store,
        _secret(config),
        max_age=int(config.get("session_max_age", 1209600)),
        idle_timeout=int(config.get("session_idle_timeout", 0)),
        user_key=config.get("session_user_key", "user_id"),
    )
    session.update(data)
    await session.commit()
    return f"{_name(config)}={session._encode()}"


def _infer(raw: str) -> Any:
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


def parse_session_pairs(pairs: list[str]) -> dict[str, Any]:
    """``["uid=1", "admin=true", "name=ana"]`` -> ``{"uid": 1, "admin": True, "name": "ana"}``.

    Whole numbers become ``int``, ``true``/``false`` become ``bool``, anything
    else stays a string. Raises ``ValueError`` for an item without ``key=``.
    """
    data: dict[str, Any] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError("expected key=value (for example uid=1)")  # never echo the item: it may be a secret
        data[key] = _infer(raw)
    return data
