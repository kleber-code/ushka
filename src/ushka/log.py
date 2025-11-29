from rich.logging import RichHandler


# --- CLASSE NOVA ---
class UshkaHandler(RichHandler):
    """
    Um Handler do Rich que NÃO pinta números automaticamente.
    Nós queremos controle total das cores via markup (ex: [red]500[/]).
    """

    def __init__(self, *args, **kwargs):
        # Inicializa o RichHandler normal
        super().__init__(*args, **kwargs)
        # DESLIGA O HIGHLIGHTER AUTOMÁTICO
        self.highlighter = None


def get_silent_uvicorn_config(level="INFO"):
    return {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {"rich": {"datefmt": "[%X]", "format": "%(message)s"}},
        "handlers": {
            "rich": {
                # --- AQUI MUDOU: Usamos nossa classe customizada ---
                "class": "ushka.log.UshkaHandler",
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
