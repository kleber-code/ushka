"""``ushka check``: validates configuration and security settings.

Exits with status 1 when a problem is found, so it can run in CI or before a
deploy (``ushka check --production``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from ushka.cli import ui
from ushka.core.config import Config
from ushka.guard import TEMPLATES_SUPPORTED
from ushka.pwa import icons as pwa_icons

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


def check(production: bool = False) -> int:
    """Prints a report and returns the number of problems found."""
    workdir = Path.cwd()
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
    toml = workdir / "ushka.toml"
    if toml.exists():
        ui.ok("ushka.toml found")
        if config.source_of("app_secret_key") == "ushka.toml":
            problems += 1
            ui.error("ushka.toml contains secret_key: move it to .env / USHKA_APP_SECRET_KEY")
    else:
        ui.warn("no ushka.toml: using defaults")

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

    gitignore = workdir / ".gitignore"
    if (workdir / ".env").exists():
        ignored = gitignore.exists() and ".env" in gitignore.read_text("utf-8").split()
        if ignored:
            ui.ok(".env is git-ignored")
        else:
            problems += 1
            ui.error(".env exists but is not in .gitignore")

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
