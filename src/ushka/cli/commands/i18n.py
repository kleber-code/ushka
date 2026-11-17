"""``ushka i18n extract`` and ``ushka i18n compile``: the two steps of a translation workflow."""

from __future__ import annotations

from pathlib import Path

from ushka.cli import ui
from ushka.core.config import Config
from ushka.i18n import tools


def _settings(root: Path) -> tuple[Path, str]:
    config = Config(root).load_from_file()
    directory = Path(str(config.get("i18n_catalog_dir") or "locale"))
    return (directory if directory.is_absolute() else root / directory), str(config.get("i18n_domain") or "messages")


def extract(output: str = "", root: Path | None = None) -> int:
    """Writes the ``.pot`` with every message found in the project. Returns the exit status."""
    root = Path(root or Path.cwd())
    directory, domain = _settings(root)
    target = Path(output) if output else directory / f"{domain}.pot"
    messages = tools.extract(root, skip=(directory,))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tools.write_pot(messages, root.name), "utf-8")
    ui.ok(f"{len(messages)} message(s) written to {target}")
    ui.hint(f"Start a language: copy it to {directory}/<lang>/LC_MESSAGES/{domain}.po, translate, then `ushka i18n compile`.")
    return 0


def compile_catalogs(root: Path | None = None) -> int:
    """Compiles every ``.po`` under the catalog folder. Returns the exit status (1 when one is invalid)."""
    root = Path(root or Path.cwd())
    directory, _domain = _settings(root)
    files = sorted(directory.glob("*/LC_MESSAGES/*.po"))
    if not files:
        ui.fail(f"No .po files in {directory}/<lang>/LC_MESSAGES/. Run `ushka i18n extract` first.")
    failed = 0
    for po in files:
        try:
            mo = tools.compile_po(po)
        except (ValueError, OSError) as exc:
            ui.error(str(exc))
            failed += 1
        else:
            ui.ok(f"{po.relative_to(root) if po.is_relative_to(root) else po} -> {mo.name}")
    return 1 if failed else 0
