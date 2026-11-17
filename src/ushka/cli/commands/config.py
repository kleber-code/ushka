"""``ushka config``: every setting Ushka reads, its value and where it came from.

Nothing is hidden: the list comes from the same schema that provides the
defaults, the annotated ``ushka.toml`` of ``ushka new`` and the docs table.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ushka.cli import ui
from ushka.core.config import Config
from ushka.core.settings import (
    ENV_ALIASES,
    RUNTIME,
    SCHEMA,
    SECTIONS,
    env_name,
    render_markdown,
    render_toml,
)


def _shown(setting, value) -> str:
    if setting.secret:
        return "(set)" if value else "(not set)"
    return repr(value)


def show(section: str = "", describe: bool = False, template: bool = False, markdown: bool = False) -> int:
    """Prints the settings. Returns the number of mistakes found in ``ushka.toml``."""
    if template:
        sys.stdout.write(render_toml(header="# Ushka configuration: every setting, with its default."))
        return 0
    if markdown:
        sys.stdout.write(render_markdown())
        return 0
    if section and section not in SCHEMA:
        ui.fail(f"Unknown section [{section}]. Sections: {', '.join(SCHEMA)}.")

    try:
        config = Config(Path.cwd()).load_from_file()
    except ValueError as exc:
        ui.fail(str(exc))

    ui.title(f"Ushka {config.get('ushka_version')} · settings of {Path.cwd()}")
    for name, keys in SCHEMA.items():
        if section and name != section:
            continue
        ui.line(f"\n  [{name}]  {SECTIONS[name]}")
        for key, setting in keys.items():
            value = config.get(f"{name}_{key}")
            source = config.source_of(f"{name}_{key}")
            ui.info(f"{key} = {_shown(setting, value)}  " + ui.code(f"[{source}]"))
            if describe:
                ui.line(f"        {setting.help}")
                aliases = ENV_ALIASES.get(env_name(name, key), ())
                names = ", ".join((env_name(name, key), *aliases))
                ui.line(f"        environment: {names}")
    if not section:
        ui.line("\n  [ushka]  Read-only information Ushka adds itself.")
        for key, text in RUNTIME.items():
            ui.info(f"{key} = {config.get(f'ushka_{key}')!r}  " + ui.code(f"({text})"))

    ui.line()
    ui.hint("sources: default < ushka.toml < .env < environment. `ushka config --template` prints a complete ushka.toml.")
    for problem in config.problems:
        ui.error(f"ushka.toml: {problem}")
    return len(config.problems)
