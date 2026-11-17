"""``ushka verify``: send attack payloads to your own routes and report what got through."""

from __future__ import annotations

import asyncio
import json

from ushka.cli import ui
from ushka.cli.commands.routes import load_app
from ushka.security import verify as engine
from ushka.sessions.forge import parse_session_pairs


def verify(
    app_path: str,
    include_writes: bool = False,
    params: list[str] | None = None,
    as_json: bool = False,
    fail_on: str = "medium",
    skip_exempt: bool = False,
    as_session: list[str] | None = None,
    cookies: list[str] | None = None,
    headers: list[str] | None = None,
) -> int:
    """Runs the probes and prints a report. Returns 1 when findings reach `fail_on`."""
    session_data = None
    if as_session:
        try:
            session_data = parse_session_pairs(as_session)
        except ValueError as exc:
            ui.fail(f"--as-session: {exc}")
    sent: dict[str, str] = {}
    for item in headers or []:
        name, sep, value = item.partition(":")
        if not sep or not name.strip():
            ui.fail("--header expects 'Name: value'")
        sent[name.strip()] = value.strip()
    for item in cookies or []:
        if "=" not in item or not item.split("=", 1)[0].strip():
            ui.fail("--cookie expects NAME=VALUE")
    cookie = "; ".join(c.strip() for c in cookies or [])
    app = load_app(app_path)
    if session_data and not app.config.get("app_debug") and not as_json:
        ui.warn("--as-session signs a session with this app's secret key while debug is off: use a development key and a test database.")
    report = asyncio.run(
        engine.run(app, include_writes=include_writes, extra_params=params or (), skip_exempt=skip_exempt, cookie=cookie, session_data=session_data, headers=sent)
    )
    failing = report.failing(fail_on)

    if as_json:
        print(json.dumps({**report.to_dict(), "failed": bool(failing)}, indent=2))
        return 1 if failing else 0

    o = report.outcomes
    ui.title(f"Ushka verify · {report.routes} route(s), {report.probes} hostile request(s)")
    ui.line(
        f"\n  {o['blocked']} blocked · {o['guard']} stopped by the guard · {o['handled']} handled safely · "
        f"{o['vulnerable']} vulnerable · {o['crash']} crashed"
    )
    if report.session_keys:
        ui.info("probed as a logged-in user (forged session with: " + ", ".join(report.session_keys) + ")")
    if report.exempt:
        ui.info(f"{len(report.exempt)} route(s) exempt from CSRF were probed too: " + ", ".join(report.exempt))
    for note in report.skipped:
        ui.info(f"skipped: {note}")

    order = sorted(report.findings, key=lambda f: -engine.SEVERITY[f.severity])
    vulnerable = [f for f in order if f.kind in ("VULNERABLE", "config")]
    crashes = [f for f in order if f.kind == "crash"]
    guards = [f for f in order if f.kind == "guard"]

    if vulnerable:
        ui.line("\n  Got through")
        for f in vulnerable:
            ui.error(f"{f.route}  {f.slot}  [{f.category}]" + ("  (exempt from CSRF)" if f.exempt else ""))
            ui.line(f"      {f.detail}")
            if f.fix:
                ui.hint(f.fix)
    if crashes:
        ui.line("\n  Crashed on hostile input")
        for f in crashes:
            ui.warn(f"{f.route}  {f.slot}  [{f.category}]")
            ui.line(f"      {f.detail}")
            if f.fix:
                ui.hint(f.fix)
    if guards:
        seen: set[tuple] = set()
        ui.line("\n  Stopped by Ushka Guard (safe, but a real visitor would see a 500: sanitise here)")
        for f in guards:
            key = (f.route, f.slot, f.detail)
            if key in seen:
                continue
            seen.add(key)
            ui.warn(f"{f.route}  {f.slot}")
            ui.line(f"      {f.detail}")
            ui.hint(f.fix)

    if not (vulnerable or crashes):
        ui.ok("\nNothing got through.")
    ui.line()
    return 1 if failing else 0
