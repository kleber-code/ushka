"""`Sessions`: the piece that picks how sessions are kept, ``app.use(Sessions("database"))``."""

from __future__ import annotations


class Sessions:
    """Chooses where sessions live: ``app.use(Sessions("database"))``.

    ``"cookie"`` (the default) signs the session into the browser's cookie; ``"database"``
    keeps it on the server, so logging out or `revoke_user_sessions` really ends it (it needs a
    database; without one it falls back to cookies, with a warning). The other options are the
    keys of ``[session]`` in ``ushka.toml``, which still overrides what you write here::

        app.use(Sessions("database", idle_timeout=1800))
        app.use(Sessions("cookie", encrypt=True))        # needs ushka[crypto]

    Parameters
    ----------
    store : str, optional
        ``"cookie"`` or ``"database"``; left out, ``[session] store`` decides.
    **options
        ``cookie_name``, ``max_age``, ``idle_timeout``, ``user_key``, ``table``, ``encrypt``.
    """

    name = "sessions"

    def __init__(self, store: str | None = None, **options) -> None:
        if store is not None:
            options["store"] = store
        self.options = options

    def install(self, app) -> None:
        app.config.defaults("session", **self.options)
        # Everything is read per request, except a store built earlier from the old setting.
        if getattr(app.session_store, "_from_config", False):
            app.session_store = None
        app._session_fallback_logged = False
        if app.config.get("session_encrypt"):
            from ushka.crypto.fernet import validate_config

            validate_config(app.config)
