"""Application configuration: defaults < ``ushka.toml`` < ``.env`` < environment.

`Config` is a process-wide singleton. Values are exposed as ``SECTION_KEY``
attributes (``[app] debug`` becomes ``config.APP_DEBUG``) and through
``config.get("app_debug")``.

Layers, lowest to highest priority:

1. Built-in defaults (`DEFAULTS` below).
2. ``ushka.toml`` in the application directory. It is only *read*: Ushka
   never rewrites your file.
3. A ``.env`` file next to it (``KEY=value`` lines), for secrets you keep
   out of version control.
4. Real environment variables.

Layers 3 and 4 use the name ``USHKA_<SECTION>_<KEY>``, e.g.
``USHKA_APP_DEBUG=true`` or ``USHKA_APP_SECRET_KEY=...``. Values are
converted to the type of the default (``true/false/1/0/yes/no/on/off`` for
booleans). Two common names are understood too: ``DATABASE_URL`` (set by
most hosting platforms) and the older ``USHKA_DB_URL``.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10 only
    import tomli as tomllib

log = logging.getLogger("ushka")

DEFAULTS: dict[str, dict[str, Any]] = {
    "app": {
        "name": "Ushka App",
        "debug": False,
        "auto_discover": True,
        # Never put a real key in ushka.toml: use USHKA_APP_SECRET_KEY (.env).
        "secret_key": "",
    },
    "database": {"url": "sqlite:///ushka.db"},
    "server": {"host": "127.0.0.1", "port": 8000, "workers": 1},
    "static": {
        "enable": False,
        "url": "/static",
        "dir": "static",
        "cache_control": "public, max-age=3600",
    },
    "limits": {
        "max_request_body_size_in_KB": 2048,
        "max_request_body_multipart_size_in_KB": 51200,
    },
    # Ushka Guard: request data arrives as `Untrusted` and dangerous sinks
    # refuse it. Turning it off is a migration aid, not a mode.
    "security": {"taint": True},
}

# Environment names honoured in addition to USHKA_<SECTION>_<KEY>.
ENV_ALIASES = {"USHKA_DATABASE_URL": ("DATABASE_URL", "USHKA_DB_URL")}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _package_version() -> str:
    try:
        return version("ushka")
    except PackageNotFoundError:  # running from a source checkout
        return "dev"


def parse_dotenv(text: str) -> dict[str, str]:
    """Parses ``.env`` content: ``KEY=value`` lines, ``#`` comments, optional quotes.

    ``export KEY=value`` is accepted. Variable expansion is not supported.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:  # inline comment on an unquoted value
            value = value.split(" #", 1)[0].rstrip()
        if key:
            values[key] = value
    return values


def _coerce(raw: str, like: Any, name: str) -> Any:
    if isinstance(like, bool):
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise ValueError(f"{name}={raw!r} is not a boolean (use true/false)")
    if isinstance(like, int):
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"{name}={raw!r} is not an integer") from None
    if isinstance(like, float):
        return float(raw)
    return raw


class Config:
    """Process-wide application configuration (singleton).

    Parameters
    ----------
    workdir : Path | str, optional
        The application directory, where ``ushka.toml`` and ``.env`` live.
        Defaults to the current working directory, resolved when the first
        instance is created.
    """

    _instance: Config | None = None
    _lock = threading.Lock()
    _initialized = False
    _sentinel = object()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, workdir: Path | str | None = None) -> None:
        if self._initialized:
            return
        self.log = log
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.default_config_file_path = self.workdir / "ushka.toml"
        self.sources: dict[str, str] = {}
        self._applied: set[str] = set()
        self._apply(self._merged(file_data={}, dotenv={}, environ=dict(os.environ)))
        self._initialized = True

    # -- loading ---------------------------------------------------------------

    def set_workdir(self, workdir: Path | str) -> Config:
        """Re-roots the configuration at `workdir` (where ushka.toml/.env live).

        The application calls this with its own directory, so a CLI that
        created the singleton earlier from another current directory does not
        decide where the app's files are.
        """
        self.workdir = Path(workdir)
        self.default_config_file_path = self.workdir / "ushka.toml"
        return self

    def load_from_file(self, config_path: Path | None = None) -> Config:
        """Reads ``ushka.toml`` and ``.env`` and applies the environment.

        A missing ``ushka.toml`` is fine: defaults are used. The file is never
        created or modified.

        Returns
        -------
        Config
            The instance, for chaining.
        """
        path = Path(config_path) if config_path else self.default_config_file_path
        file_data: dict[str, Any] = {}
        if path.exists():
            with open(path, "rb") as fh:
                try:
                    file_data = tomllib.load(fh)
                except tomllib.TOMLDecodeError as exc:
                    raise ValueError(f"Invalid TOML in {path}: {exc}") from exc

        dotenv_path = path.parent / ".env"
        dotenv = parse_dotenv(dotenv_path.read_text("utf-8")) if dotenv_path.exists() else {}

        self._apply(self._merged(file_data, dotenv, dict(os.environ)))
        return self

    def _merged(self, file_data: dict, dotenv: dict, environ: dict) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {s: dict(v) for s, v in DEFAULTS.items()}
        self.sources = {}

        for section, content in file_data.items():
            if section == "ushka" or not isinstance(content, dict):
                continue  # [ushka] is runtime information, not settings
            target = merged.setdefault(section, {})
            for key, value in content.items():
                target[key] = value
                self.sources[f"{section}_{key}".upper()] = "ushka.toml"

        for section, content in merged.items():
            for key, current in content.items():
                name = f"USHKA_{section}_{key}".upper()
                candidates = (name, *ENV_ALIASES.get(name, ()))
                for layer_name, layer in (("environment", environ), (".env", dotenv)):
                    raw = next((layer[c] for c in candidates if c in layer), None)
                    if raw is not None:
                        content[key] = _coerce(raw, current, name)
                        self.sources[f"{section}_{key}".upper()] = layer_name
                        break

        app = merged["app"]
        if not app.get("secret_key") and app.get("debug"):
            # Per-process key: sessions work in development, but a key that
            # is never written anywhere cannot leak or be reused in production.
            app["secret_key"] = secrets.token_urlsafe(48)
            self.sources["APP_SECRET_KEY"] = "generated (debug only)"

        merged["ushka"] = {"version": _package_version(), "workdir": str(self.workdir)}
        return merged

    def _apply(self, data: dict[str, dict[str, Any]]) -> None:
        names = set()
        for section, content in data.items():
            for key, value in content.items():
                name = f"{section.upper()}_{key.upper()}"
                setattr(self, name, value)
                names.add(name)
        for stale in getattr(self, "_applied", set()) - names:
            delattr(self, stale)
        self._applied = names

    # -- access ----------------------------------------------------------------

    def get(self, key: str, default: Any = None, required: bool = False) -> Any:
        """Returns the value of ``SECTION_KEY`` (case-insensitive).

        Raises
        ------
        KeyError
            If the key is missing and `required` is true.
        """
        value = getattr(self, key.upper(), self._sentinel)
        if value is self._sentinel:
            if required:
                raise KeyError(f"Missing required configuration key: '{key.upper()}'")
            return default
        return value

    def source_of(self, key: str) -> str:
        """Where the value of `key` came from: ``default``, ``ushka.toml``, ``.env``..."""
        return self.sources.get(key.upper(), "default")
