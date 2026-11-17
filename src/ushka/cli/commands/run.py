"""``ushka run`` (production) and the server logic shared with ``ushka dev``."""

from __future__ import annotations

import os
from pathlib import Path

from ushka.cli import ui
from ushka.core.config import Config
from ushka.core.log import get_log_config, setup_logging


def serve(app_path: str, host: str, port: int, *, dev: bool) -> None:
    """Starts Uvicorn for `app_path` (``module:attribute``).

    In development, debug is forced on through ``USHKA_APP_DEBUG`` (inherited
    by Uvicorn's reload worker) and the code is reloaded on change. In
    production, debug comes from the configuration and several workers can
    be used.
    """
    import uvicorn

    if ":" not in app_path:
        ui.fail(f"Expected the app as 'module:attribute' (e.g. app:app), got {app_path!r}.")
    if dev:
        os.environ["USHKA_APP_DEBUG"] = "true"

    setup_logging()
    try:
        config = Config(Path.cwd()).load_from_file()
    except ValueError as exc:
        ui.fail(str(exc))

    host = host or config.get("server_host", "127.0.0.1")
    port = port or int(config.get("server_port", 8000))
    workers = 1 if dev else int(config.get("server_workers", 1))

    ui.title(f"Ushka {config.get('ushka_version')} · {'development' if dev else 'production'}")
    ui.info(f"http://{host}:{port}")
    if dev:
        ui.info("debug on, reloading on change")
    else:
        if config.get("app_debug"):
            ui.warn("debug is ON in production: tracebacks are shown to visitors.")
            ui.hint("set [app] debug = false or USHKA_APP_DEBUG=false")
        if not config.get("app_secret_key"):
            ui.warn("no USHKA_APP_SECRET_KEY: sessions will fail.")
        if os.environ.get("FORWARDED_ALLOW_IPS") and not config.get("security_trusted_proxies"):
            ui.warn("FORWARDED_ALLOW_IPS is no longer read: list your proxies in [security] trusted_proxies.")
        if workers > 1:
            ui.info(f"{workers} workers")
    ui.hint("press Ctrl+C to stop")

    if dev:
        uvicorn.run(app_path, host=host, port=port, reload=True, lifespan="on", log_config=get_log_config(), proxy_headers=False)
        return
    # Production: a server that stays asleep when idle (see ushka.core.server).
    from ushka.core.server import run_server

    run_server(app_path, host=host, port=port, workers=workers, log_config=get_log_config())


def run(app_path: str, host: str, port: int) -> None:
    """Production server."""
    serve(app_path, host, port, dev=False)
