"""``ushka dev``: development server with reload and debug on."""

from ushka.cli.commands.run import serve


def run(app_path: str, host: str, port: int) -> None:
    """Development server."""
    serve(app_path, host, port, dev=True)
