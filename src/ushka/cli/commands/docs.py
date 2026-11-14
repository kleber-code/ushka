"""``ushka docs``: check or preview a folder of Markdown docs (needs ushka[docs])."""

from __future__ import annotations

from pathlib import Path

from ushka.cli import ui


def _load():
    try:
        from ushka.docs import Docs
    except ImportError as exc:
        ui.fail(str(exc))
    return Docs


def check(directory: str, api: str | None, api_path: str) -> int:
    """Builds every page and reports broken links, anchors and nav entries."""
    Docs = _load()
    docs = Docs(directory, api_package=api, api_path=Path(api_path).resolve())
    root = Path(directory)
    if not root.is_dir():
        ui.fail(f"Docs folder not found: {root}")
    problems = docs.build(root.resolve())
    ui.title(f"Ushka Docs · {len(docs.pages)} page(s) in {root}")
    for problem in problems:
        ui.error(str(problem))
    if problems:
        ui.error(f"{len(problems)} problem(s) found")
    else:
        ui.ok("all links, anchors and nav entries resolve")
    return len(problems)


def serve(directory: str, api: str | None, api_path: str, host: str, port: int) -> None:
    """Serves the docs at http://host:port/docs/ for writing and previewing."""
    import uvicorn

    from ushka import Ushka, redirect
    from ushka.core.log import get_log_config, setup_logging

    Docs = _load()
    setup_logging()
    app = Ushka()
    app.workdir = Path.cwd()
    Docs(Path(directory).resolve(), api_package=api, api_path=Path(api_path).resolve()).mount(app)

    @app.get("/")
    async def home():
        return redirect("/docs/")

    ui.title(f"Ushka Docs · http://{host}:{port}/docs/")
    ui.hint("restart to pick up changes; press Ctrl+C to stop")
    uvicorn.run(app, host=host, port=port, log_config=get_log_config())
