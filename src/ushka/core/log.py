"""This module provides logging configuration for the Ushka framework.

It sets up a visually appealing and informative logging system using the `rich`
library. It includes a custom `RichHandler` for console output and provides
a method to configure Uvicorn for silent logging, ensuring that all output
is consistently formatted.
"""

import logging
from typing import Literal

from rich.logging import RichHandler

from ushka.http import Request, Response

LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

log = logging.getLogger("ushka")


def setup_logging(level: LogLevelType = "INFO"):
    """Configures the 'ushka' logger with a `RichHandler`.

    This sets up a visually appealing and informative console logger.

    Args:
        level: The desired logging level.
    """
    log.setLevel(level)
    handler = RichHandler(rich_tracebacks=True)
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    log.addHandler(handler)
    log.propagate = False


def log_http(request: Request, response: Response, process_time: float):
    """Logs an HTTP request/response cycle.

    Formats the log message with icons and colors based on the response
    status code.

    Args:
        request: The incoming `Request` object.
        response: The outgoing `Response` object;
        process_time: The total time taken to process the request, in
            milliseconds.
    """
    log.info("Request processed in %.2fms", process_time)


def get_log_config(level: LogLevelType = "INFO") -> dict:
    """Gets a logging configuration to silence default Uvicorn loggers.

    This method returns a dictionary that can be passed to `uvicorn.run`
    to route Uvicorn's logs through Ushka's custom handler, ensuring
    consistent log formatting.

    Args:
        level: The desired logging level for the 'ushka' logger.

    Returns:
        A dictionary containing the logging configuration for Uvicorn.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level},
            "uvicorn.error": {"level": level},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": level,
                "propagate": False,
            },
        },
    }
