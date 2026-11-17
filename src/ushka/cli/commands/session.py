"""``ushka session``: print a forged session cookie, to test as a logged-in user.

A testing tool. It signs the cookie with the app's own secret key, so it is
refused unless the key comes from the environment or ``.env`` (it is never read
from the command line) and the app is in debug mode, and it never prints
anything but the cookie.
"""

from __future__ import annotations

import asyncio

from ushka.cli import ui
from ushka.cli.commands.routes import load_app
from ushka.sessions.forge import aforge_session_cookie, parse_session_pairs

KEY_SOURCES = ("environment", ".env")


def session(app_path: str, pairs: list[str], allow_non_debug: bool = False) -> int:
    """Prints ``name=value`` for the session described by `pairs`. Returns 1 on a refusal."""
    try:
        data = parse_session_pairs(pairs)
    except ValueError as exc:
        ui.fail(str(exc))
    if not data:
        ui.fail("Nothing to put in the session: pass --set key=value (for example --set uid=1).")
    app = load_app(app_path)
    config = app.config
    source = config.source_of("app_secret_key")
    if source not in KEY_SOURCES:
        ui.fail(
            f"The secret key comes from {source!r}: set USHKA_APP_SECRET_KEY in the environment or in .env "
            "(a key made for one process, or one in ushka.toml, cannot sign a cookie another server accepts)."
        )
    if not config.get("app_debug") and not allow_non_debug:
        ui.fail(
            "Refusing to sign a session: debug is off, so this looks like a production setup, and anyone who can run "
            "this holds the key to every account. Use a development key (USHKA_APP_DEBUG=true), "
            "or pass --allow-non-debug if this key really belongs to a test deployment."
        )
    try:
        cookie = asyncio.run(aforge_session_cookie(app, data))
    except Exception as exc:  # noqa: BLE001 - the CLI reports, never shows a traceback with session values
        ui.fail(f"Could not forge the session: {type(exc).__name__}: {str(exc)[:200]}")
    print(cookie)
    return 0
