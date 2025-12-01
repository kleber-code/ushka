"""This module provides logging configuration for the Ushka framework.

It sets up a visually appealing and informative logging system using the `rich`
library. It includes a custom `RichHandler` for console output and provides
a method to configure Uvicorn for silent logging, ensuring that all output
is consistently formatted.
"""

import logging
from typing import Literal

from rich.logging import RichHandler
from rich.markup import escape

from ushka.http import Request, Response

LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LogSystem:
    """Manages the logging system for the Ushka framework.

    This class configures the 'ushka' logger with a custom `UshkaHandler` to
    provide rich, formatted console output.
    """

    def __init__(self):
        """Initializes the LogSystem and configures the 'ushka' logger."""
        self.log = logging.getLogger("ushka")
        self.log.propagate = False  # Prevent logs from going to the root logger

        # Add UshkaHandler if not already present
        if not any(isinstance(h, UshkaHandler) for h in self.log.handlers):
            handler = UshkaHandler(
                rich_tracebacks=True,
                show_path=False,
                markup=True,
                enable_link_path=False,
            )
            formatter = logging.Formatter(fmt="%(message)s")
            handler.setFormatter(formatter)
            self.log.addHandler(handler)

        self.log.setLevel(logging.INFO)

    def log_http(self, request: Request, response: Response, process_time: float):
        """Logs an HTTP request/response cycle.

        Formats the log message with icons and colors based on the response
        status code.

        Args:
            request: The incoming `Request` object.
            response: The outgoing `Response` object.
            process_time: The total time taken to process the request, in
                milliseconds.
        """
        status_code = int(response.status_code)

        log_config = {}
        if status_code >= 500:
            log_config["status_color"] = "red"
            log_config["icon"] = "🔥"
            log_config["log_func"] = self.log.error
        elif status_code >= 400:
            log_config["status_color"] = "yellow"
            log_config["icon"] = "⚠️"
            log_config["log_func"] = self.log.warning
        elif status_code >= 300:
            log_config["status_color"] = "cyan"
            log_config["icon"] = "🚀"
            log_config["log_func"] = self.log.info
        else:  # < 300
            log_config["status_color"] = "green"
            log_config["icon"] = "✅"
            log_config["log_func"] = self.log.info

        log_config["log_func"](
            "%s [bold blue]%s[/] [white]%s[/] [bold %s]%s[/] [dim]in %.2fms[/]",
            log_config["icon"],
            escape(request.method),
            escape(request.path),
            log_config["status_color"],
            status_code,
            process_time,
        )

    @staticmethod
    def get_silent_uvicorn_config(level: LogLevelType = "INFO") -> dict:
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
            "disable_existing_loggers": True,
            "formatters": {"rich": {"datefmt": "[%X]", "format": "%(message)s"}},
            "handlers": {
                "rich": {
                    "class": "ushka.core.log.UshkaHandler",
                    "formatter": "rich",
                    "rich_tracebacks": True,
                    "show_path": False,
                    "markup": True,
                    "enable_link_path": False,
                }
            },
            "loggers": {
                "ushka": {"handlers": ["rich"], "level": level, "propagate": False},
                "uvicorn": {
                    "handlers": ["rich"],
                    "level": "CRITICAL",
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["rich"],
                    "level": "CRITICAL",
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["rich"],
                    "level": "CRITICAL",
                    "propagate": False,
                },
            },
        }


class UshkaHandler(RichHandler):
    """Custom `RichHandler` for Ushka logging.

    This class extends `rich.logging.RichHandler` to ensure a consistent
    look and feel for all framework and application logs.
    """

    def __init__(self, *args, **kwargs):
        """Initializes the UshkaHandler."""
        super().__init__(*args, **kwargs)
