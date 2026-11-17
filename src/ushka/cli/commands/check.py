"""``ushka check``: validates configuration and security settings.

Exits with status 1 when a problem is found, so it can run in CI or before a
deploy (``ushka check --production``).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from ushka.cli import ui
from ushka.cli.commands.structure import structure_warnings
from ushka.core.config import Config
from ushka.guard import TEMPLATES_SUPPORTED
from ushka.sessions.stores import no_database_reason
from ushka.web.pwa import icons as pwa_icons

SETTINGS = (
    "app_debug",
    "app_secret_key",
    "database_url",
    "security_taint",
    "server_host",
    "server_port",
    "static_enable",
)


def _display(key: str, value: object) -> str:
    if key == "app_secret_key":
        return "(set)" if value else "(not set)"
    return repr(value)


_SCRIPT = re.compile(r"<script\b([^>]*)>", re.IGNORECASE | re.DOTALL)
_LINK = re.compile(r"<link\b([^>]*)>", re.IGNORECASE | re.DOTALL)
_TEMPLATE_SUFFIXES = {".html", ".htm", ".jinja", ".jinja2", ".j2"}
_MAX_CSP_FINDINGS = 12


def _attr(tag: str, name: str) -> str | None:
    found = re.search(rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.IGNORECASE)
    return next((g for g in found.groups() if g is not None), "") if found else None


def _line(text: str, match: re.Match) -> int:
    return text.count("\n", 0, match.start()) + 1


def csp_findings(workdir: Path, csp: str) -> list[tuple[str, int, str]]:
    """What the browser will block in ``templates/`` under this CSP, as
    ``(file, line, what)``. ``csp`` is the configured policy ("" = Ushka's default)."""
    templates = workdir / "templates"
    if not templates.is_dir():
        return []
    custom = csp.lower()
    inline_ok = "'unsafe-inline'" in custom or "nonce-" in custom
    found: list[tuple[str, int, str]] = []
    for path in sorted(p for p in templates.rglob("*") if p.suffix.lower() in _TEMPLATE_SUFFIXES):
        text = path.read_text("utf-8", errors="replace")
        name = str(path.relative_to(workdir))

        def external(url: str | None) -> str | None:
            """The host of an absolute URL the policy does not already name."""
            if not url or not re.match(r"(https?:)?//", url.strip()):
                return None
            host = urlsplit(url.strip() if not url.strip().startswith("//") else "https:" + url.strip()).hostname or ""
            return None if host and custom and host.lower() in custom else host or url

        for m in _SCRIPT.finditer(text):
            src = _attr(m.group(1), "src")
            if src is not None:
                host = external(src)
                if host:
                    found.append((name, _line(text, m), f"<script src> from {host} is blocked"))
            elif not inline_ok and "json" not in (_attr(m.group(1), "type") or "").lower() and "template" not in (_attr(m.group(1), "type") or "").lower():
                found.append((name, _line(text, m), "inline <script> is blocked"))
        for m in _LINK.finditer(text):
            rel = (_attr(m.group(1), "rel") or "").lower()
            if any(k in rel for k in ("stylesheet", "preload", "modulepreload")):
                host = external(_attr(m.group(1), "href"))
                if host:
                    found.append((name, _line(text, m), f"<link> to {host} is blocked"))
    return found


_CRYPTO_USE = re.compile(r"\bEncrypted\(|ushka\.crypto|from ushka import [^\n]*\bcrypto\b")
_SKIP_DIRS = {"node_modules", "site-packages", "__pycache__", "build", "dist"}


def _uses_crypto(workdir: Path) -> bool:
    """True when the app's own code uses ``db.Encrypted`` or ``ushka.crypto``."""
    for root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS and not d.startswith(("venv", "env"))]
        for name in files:
            if not name.endswith(".py"):
                continue
            try:
                if _CRYPTO_USE.search((Path(root) / name).read_text("utf-8", errors="replace")):
                    return True
            except OSError:
                continue
    return False


def imap_warnings(config: Config) -> list[str]:
    """What is wrong with ``[imap]`` once a host is set (the section is off without one)."""
    out = []
    if config.source_of("imap_password") == "ushka.toml":
        out.append("[imap] password is in ushka.toml: move it to .env as USHKA_IMAP_PASSWORD")
    elif not config.get("imap_password"):
        out.append("[imap] host is set but USHKA_IMAP_PASSWORD is not")
    if not config.get("imap_ssl"):
        if config.get("imap_starttls"):
            out.append("[imap] ssl = false: the connection starts in plain text and is upgraded with STARTTLS; make sure the server requires it")
        elif config.get("imap_allow_insecure"):
            out.append("[imap] STRONG WARNING: allow_insecure = true sends the password and every message in plain text; use it only for a local test server")
        else:
            out.append("[imap] ssl = false without starttls or allow_insecure: ImapClient will refuse to connect")
    elif config.get("imap_allow_insecure"):
        out.append("[imap] allow_insecure = true has no effect while ssl = true; remove it")
    return out


def load_app_quietly(workdir: Path, target: str):
    """Imports ``module:attribute`` from `workdir` so the options given in code (``app.use(Seo(url=...))``)
    are part of the report. Returns ``(app, "")``, or ``(None, reason)``; importing never stops the check."""
    module_name, _, attr = target.partition(":")
    if not (workdir / f"{module_name.replace('.', '/')}.py").exists() and not (workdir / module_name.replace(".", "/") / "__init__.py").exists():
        return None, ""
    import importlib

    sys.path.insert(0, str(workdir))
    try:
        return getattr(importlib.import_module(module_name), attr or "app"), ""
    except Exception as exc:  # noqa: BLE001 - the app is user code: whatever it raises is a finding, not a crash
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        if sys.path and sys.path[0] == str(workdir):
            sys.path.pop(0)


def check(production: bool = False, app_path: str = "app:app") -> int:
    """Prints a report and returns the number of problems found.

    The app (``app:app``) is imported when it exists, so what `app.use(...)` set from code counts too.
    """
    workdir = Path.cwd()
    app, import_error = load_app_quietly(workdir, app_path)
    try:
        config = Config(workdir).load_from_file()
    except ValueError as exc:
        ui.fail(str(exc))

    problems = 0
    ui.title(f"Ushka {config.get('ushka_version')} · checking {workdir}")

    ui.line("\n  Settings")
    for key in SETTINGS:
        ui.info(f"{key} = {_display(key, config.get(key))}  " + ui.code(f"[{config.source_of(key)}]"))

    ui.line("\n  Checks")
    if app is not None:
        pieces = ", ".join(getattr(app, "pieces", {})) or "none"
        ui.ok(f"{app_path} loaded: pieces in use: {pieces}; options set in code are included")
    elif import_error:
        ui.warn(f"could not import {app_path} ({import_error}): only ushka.toml, .env and the environment were checked")
    toml = workdir / "ushka.toml"
    if toml.exists():
        ui.ok("ushka.toml found")
        if config.source_of("app_secret_key") == "ushka.toml":
            problems += 1
            ui.error("ushka.toml contains secret_key: move it to .env / USHKA_APP_SECRET_KEY")
    else:
        ui.warn("no ushka.toml: using defaults")

    if config.source_of("crypto_keys") == "ushka.toml":
        problems += 1
        ui.error("ushka.toml contains [crypto] keys: move them to .env / USHKA_CRYPTO_KEYS")

    for mistake in config.problems:
        problems += 1
        ui.error(f"ushka.toml: {mistake}")

    if config.get("security_taint") is False:
        problems += 1
        ui.error("Ushka Guard is disabled ([security] taint = false)")
    else:
        ui.ok("Ushka Guard is on")

    secret_source = config.source_of("app_secret_key")
    if production:
        if not config.get("security_allowed_hosts"):
            ui.warn("[security] allowed_hosts is empty: any Host header is accepted (set your domains)")
        if config.get("app_debug"):
            problems += 1
            ui.error("debug is on: visitors would see tracebacks and local variables")
        else:
            ui.ok("debug is off")
        if not config.get("app_secret_key") or secret_source.startswith("generated"):
            problems += 1
            ui.error("USHKA_APP_SECRET_KEY is not set: sessions will fail")
        elif len(str(config.get("app_secret_key"))) < 32:
            problems += 1
            ui.error("USHKA_APP_SECRET_KEY is shorter than 32 characters")
        else:
            ui.ok("secret key is set")
    elif not config.get("app_secret_key"):
        ui.warn("USHKA_APP_SECRET_KEY is not set (needed for sessions in production)")
    if production and config.get("server_host") in ("0.0.0.0", "::") and not config.get("security_trusted_proxies"):
        ui.warn(
            "[server] host is 0.0.0.0 and [security] trusted_proxies is empty: behind Caddy or nginx, "
            "request.client_ip is the proxy and X-Forwarded-* is ignored"
        )

    if config.get("session_encrypt"):
        from ushka.crypto.fernet import INSTALL_HINT, is_available, validate_config

        if not is_available():
            problems += 1
            ui.error(f"[session] encrypt = true: {INSTALL_HINT}")
        else:
            try:
                validate_config(config)
            except (RuntimeError, ValueError) as exc:
                problems += 1
                ui.error(f"[session] encrypt = true: {exc}")
    if production and not config.get("crypto_keys") and (config.get("session_encrypt") or _uses_crypto(workdir)):
        ui.warn(
            "encryption uses a key derived from [app] secret_key, so rotating the secret key would make "
            "everything encrypted unreadable: make a dedicated key with `ushka crypto genkey` "
            "and set USHKA_CRYPTO_KEYS"
        )
    if config.get("imap_host"):
        for message in imap_warnings(config):
            ui.warn(message)

    gitignore = workdir / ".gitignore"
    if (workdir / ".env").exists():
        ignored = gitignore.exists() and ".env" in gitignore.read_text("utf-8").split()
        if ignored:
            ui.ok(".env is git-ignored")
        else:
            problems += 1
            ui.error(".env exists but is not in .gitignore")

    if str(config.get("session_store", "cookie")).lower() == "database":
        reason = no_database_reason(config)
        if not reason:
            ui.ok("sessions: revocable, kept in the database")
        elif production:
            problems += 1
            ui.error(f"[session] store = \"database\" has no database, so sessions stay signed cookies: {reason}")
        else:
            ui.warn(f"[session] store = \"database\" has no database, so sessions stay signed cookies: {reason}")

    if any(config.get(f"oauth_{n}_client_id") or config.get(f"oauth_{n}_client_secret") for n in ("google", "github")):
        from ushka.auth import problems as oauth_problems

        found = oauth_problems(config, production)
        for name in ("google", "github"):
            if config.source_of(f"oauth_{name}_client_secret") == "ushka.toml":
                problems += 1
                ui.error(f"ushka.toml contains {name}_client_secret: move it to .env / USHKA_OAUTH_{name.upper()}_CLIENT_SECRET")
        for level, message in found:
            if level == "error":
                problems += 1
                ui.error(message)
            else:
                ui.warn(message)
        if not found:
            ui.ok("OAuth login: configured")

    if config.get("seo_enable", True):
        if config.get("seo_url"):
            ui.ok(f"SEO: public URL is {config.get('seo_url')}")
        else:
            ui.warn("[seo] url is not set: set it before going live (canonical links and sitemap.xml need it)")
        if not config.get("seo_description"):
            ui.warn("[seo] description is empty: pages without their own have no meta description")
        if "noindex" in str(config.get("seo_robots")).lower() and production:
            ui.warn('[seo] robots says "noindex": search engines will skip this site')
    if config.get("pwa_enable"):
        sizes = {i.get("sizes") for i in pwa_icons(config)}
        if {"192x192", "512x512"} <= sizes:
            ui.ok("PWA: manifest and 192/512 icons configured")
        else:
            problems += 1
            ui.error("[pwa] needs icons of 192x192 and 512x512 (PNG) to be installable")

    csp = str(config.get("security_csp") or "")
    if csp.lower() != "off":
        findings = csp_findings(workdir, csp)
        for name, number, what in findings[:_MAX_CSP_FINDINGS]:
            ui.warn(f"{name}:{number}: {what} by the Content-Security-Policy, silently")
        if len(findings) > _MAX_CSP_FINDINGS:
            ui.warn(f"... and {len(findings) - _MAX_CSP_FINDINGS} more")
        if findings:
            ui.info(
                "fix: host the file under static/, or allow it in [security] csp "
                "(see docs/guide/security.md#csp), or move inline code to a .js file"
            )

    routes = workdir / "routes"
    if routes.is_dir():
        ui.ok(f"{sum(1 for _ in routes.rglob('*.py'))} route file(s) in routes/")

    layout = structure_warnings(workdir, config)
    if layout:
        for message in layout:
            ui.warn(message)
        ui.hint("the layout rules are in the guide 'Application structure'; they only warn")
    else:
        ui.ok("project layout follows the Ushka structure")

    if TEMPLATES_SUPPORTED:
        ui.ok(f"Python {sys.version.split()[0]}: t-strings available")
    else:
        ui.info(f"Python {sys.version.split()[0]}: t-strings need 3.14+")

    ui.line()
    if problems:
        ui.error(f"{problems} problem(s) found")
    else:
        ui.ok("all good")
    return problems
