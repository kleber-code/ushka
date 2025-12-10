"""
This module provides the Command Line Interface (CLI) command for starting
the Ushka production server.

It uses Uvicorn to run the ASGI application in a production-ready setup,
including support for multiple worker processes.

Commands
--------
run: Starts the Uvicorn production server.
"""

import logging
import sys
from pathlib import Path

import uvicorn

from ushka.core.config import Config
from ushka.core.log import setup_logging

log = logging.getLogger("ushka")


def run(app_path: str, host: str, port: int):
    """Starts the Uvicorn server in production mode.

    This command configures and runs the Uvicorn server for production
    deployments. Host, port, and number of workers can be specified via
    arguments or default to values from `ushka.toml`.

    Parameters
    ----------
    app_path : str
        The application entry point, typically in the format 'module:instance'
        (e.g., 'app:app').
    host : str
        The host IP address to bind the server to (e.g., '0.0.0.0').
        If empty, it defaults to the value in `ushka.toml` or '127.0.0.1'.
    port : int
        The port number to listen on. If 0, it defaults to the value
        in `ushka.toml` or 8000.

    Raises
    ------
    SystemExit
        If an error occurs while starting the Uvicorn server.
    """
    setup_logging()
    config = Config(Path.cwd()).load_from_file()

    # Get server configurations from config file or use default values
    host = host if host else config.get("server_host", "127.0.0.1")
    port = port if port else config.get("server_port", 8000)
    workers = config.get("server_workers", 1)

    log.info(
        f"Starting Ushka server in production mode on http://{host}:{port} with {workers} workers."
    )

    try:
        uvicorn.run(
            app_path,
            host=host,
            port=port,
            workers=workers,
            lifespan="on",
            log_config=None,  # Disable Uvicorn's default logger to use Ushka's custom logger
            use_colors=True,
        )
    except Exception as e:
        log.error(f"❌ Error starting server: {e}")
        sys.exit(1)
