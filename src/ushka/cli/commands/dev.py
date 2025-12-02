import logging
import sys
from pathlib import Path

import uvicorn

from ushka.core.config import Config
from ushka.core.log import setup_logging

log = logging.getLogger("ushka")


def run(app_path: str, host: str, port: int):
    """
    Starts the Uvicorn server in development mode.
    This command starts the Uvicorn server with auto-reload enabled.

    Args:
        app_path (str): The application to run, in the format 'module:instance'.
        host (str): The host to bind to.
        port (int): The port to listen on.
    """
    setup_logging()
    config = Config(Path.cwd()).load_from_file()

    # Get server configurations from config file or use default values
    host = host if host else config.get("server_host", "127.0.0.1")
    port = port if port else config.get("server_port", 8000)
    debug = True

    log.info(f"Starting Ushka server in development mode on http://{host}:{port}")
    log.info("Auto-reload is enabled.")

    try:
        uvicorn.run(
            app_path,
            host=host,
            port=port,
            reload=debug,
            lifespan="on",
            log_config=None,  # Disable Uvicorn's default logger to use Ushka's custom logger
            use_colors=True,
        )
    except Exception as e:
        log.error(f"❌ Error starting server: {e}")
        sys.exit(1)
