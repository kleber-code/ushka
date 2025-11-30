from typing import Literal
from rich.logging import RichHandler

AVAILABLE_LOG_LEVELS_TYPE = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

class UshkaHandler(RichHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def get_silent_uvicorn_config(level:AVAILABLE_LOG_LEVELS_TYPE="INFO"):
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
            "uvicorn": {"handlers": ["rich"], "level": "CRITICAL", "propagate": False},
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
