"""ushka verify: hostile probes against your own app."""

import pytest

from ushka import verify as engine


def write_routes(workdir, files: dict):
    (workdir / "routes").mkdir(exist_ok=True)
    for name, source in files.items():
        (workdir / "routes" / name).write_text(source)


ROUTES = {
    "greet.py": 'from ushka import Response\nasync def get(request):\n    return Response(f"<h1>Hi {request.query.get(\'name\', \'x\')}</h1>", media_type="text/html")\n',
    "go.py": "from ushka.http import redirect\nasync def get(request):\n    return redirect(request.query.get('next', '/'))\n",
    "typed.py": "async def get(limit: int = 10, mode: str = 'a'):\n    return {'limit': limit}\n",
    "boom.py": "async def get(request):\n    q = request.query.get('q', '')\n    return {'n': 1 // (len(q) - len(q))}\n",
    "safe.py": "async def get(request):\n    return {'q': request.query.get('q', '')}\n",
    "save.py": "async def post(request):\n    return {'saved': True}\n",
}


def kinds(report):
    return {(f.kind, f.route, f.category) for f in report.findings}


async def test_guard_on_nothing_gets_through_and_fixes_are_reported(make_app, workdir):
    write_routes(workdir, ROUTES)
    report = await engine.run(make_app())

    assert report.outcomes["vulnerable"] == 0
    guard = {(f.route, f.detail.split("]")[0].lstrip("[")) for f in report.findings if f.kind == "guard"}
    assert ("GET /greet", "USHKA-G001") in guard and ("GET /go", "USHKA-G003") in guard
    assert all(f.fix for f in report.findings if f.kind == "guard")  # each one says what to write


async def test_guard_off_shows_what_gets_through(make_app, workdir):
    write_routes(workdir, ROUTES)
    (workdir / "ushka.toml").write_text("[security]\ntaint = false\n")
    report = await engine.run(make_app())

    got = kinds(report)
    assert ("VULNERABLE", "GET /greet", "xss") in got
    assert ("VULNERABLE", "GET /go", "redirect") in got
    assert ("config", "-", "guard") in got
    assert report.failing("high") and report.failing("medium")


async def test_a_crash_on_hostile_input_is_reported(make_app, workdir):
    write_routes(workdir, ROUTES)
    report = await engine.run(make_app())
    crash = [f for f in report.findings if f.kind == "crash"]
    assert crash and all(f.route == "GET /boom" for f in crash)
    assert "ZeroDivisionError" in crash[0].detail and crash[0].severity == "medium"


async def test_typed_and_harmless_routes_have_no_findings(make_app, workdir):
    write_routes(workdir, {k: v for k, v in ROUTES.items() if k in ("typed.py", "safe.py")})
    report = await engine.run(make_app())
    assert report.findings == [] and report.probes > 0 and report.outcomes["blocked"] > 0
    assert report.failing() == []


async def test_writes_are_skipped_unless_asked_and_csrf_is_probed(make_app, workdir):
    write_routes(workdir, {"save.py": ROUTES["save.py"]})
    report = await engine.run(make_app())
    assert any("POST /save" in s for s in report.skipped)
    assert report.outcomes["blocked"] == 1 and report.findings == []  # the cross-site POST got a 403


async def test_csrf_off_is_flagged_and_not_probed(make_app, workdir):
    write_routes(workdir, {"save.py": ROUTES["save.py"]})
    (workdir / "ushka.toml").write_text("[security]\ncsrf = false\n")
    report = await engine.run(make_app())
    assert ("config", "POST /save", "csrf") in kinds(report)


async def test_include_writes_probes_unsafe_routes(make_app, workdir):
    write_routes(workdir, {"save.py": "async def post(request):\n    return {'q': request.query.get('q', '')}\n"})
    report = await engine.run(make_app(), include_writes=True)
    assert not report.skipped and report.probes > 1


async def test_debug_and_disabled_headers_are_flagged(make_app, workdir):
    write_routes(workdir, {"safe.py": ROUTES["safe.py"]})
    (workdir / "ushka.toml").write_text("[app]\ndebug = true\n[security]\nheaders = false\n")
    got = kinds(await engine.run(make_app()))
    assert ("config", "-", "debug") in got and ("config", "-", "headers") in got


async def test_findings_are_deduplicated(make_app, workdir):
    write_routes(workdir, {"greet.py": ROUTES["greet.py"]})
    (workdir / "ushka.toml").write_text("[security]\ntaint = false\n")
    report = await engine.run(make_app())
    xss = [f for f in report.findings if f.category == "xss"]
    assert len(xss) == 1  # two payloads, one problem


async def test_lifespan_hooks_run_around_the_probes(make_app, workdir):
    write_routes(workdir, {"safe.py": ROUTES["safe.py"]})
    app = make_app()
    events = []
    app.on_startup(lambda: events.append("start"))
    app.on_shutdown(lambda: events.append("stop"))

    seen_during = []
    original = app.error_handler.handle_exception

    @app.get("/probe-me")
    async def probe_me(request):
        request.query.get("x")
        seen_during.append(list(events))
        return "ok"

    await engine.run(app)
    assert events == ["start", "stop"] and seen_during and seen_during[0] == ["start"]
    assert app.error_handler.handle_exception.__func__ is original.__func__  # the recorder is removed


async def test_only_your_app_is_reachable():
    import inspect

    assert "http://" not in inspect.getsource(engine) and "socket" not in inspect.getsource(engine)


def test_slot_discovery_reads_signatures_and_source(workdir):
    def handler(request, item_id: int, page: int = 1):
        request.query.get("search")
        request.query["filter"]

    slots = {(s.where, s.name): s.baseline for s in engine.discover_slots("GET", "/items/[item_id]", handler, extra_params=["extra"])}
    assert slots == {("path", "item_id"): "1", ("query", "page"): 1, ("query", "search"): "test", ("query", "filter"): "test", ("query", "extra"): "test"}


def test_baselines_are_valid_values():
    import dataclasses
    import enum
    import uuid
    from typing import Literal, Optional

    class Color(enum.Enum):
        red = "red"

    @dataclasses.dataclass
    class Item:
        name: str
        qty: int
        color: Color

    assert engine._baseline(Item) == {"name": "test", "qty": 1, "color": "red"}
    assert engine._baseline(Optional[int]) == 1 and engine._baseline(Literal["a", "b"]) == "a"
    assert uuid.UUID(engine._baseline(uuid.UUID))


def test_failing_threshold():
    r = engine.Report()
    r.add(engine.Finding("low", "guard", "xss", "GET /a", "query:q", "d"))
    assert r.failing("medium") == [] and r.failing("high") == []
    r.add(engine.Finding("medium", "crash", "junk", "GET /a", "query:q", "d"))
    assert len(r.failing("medium")) == 1 and r.failing("high") == [] and r.failing("none") == []


async def test_headers_are_sent_with_every_probe(make_app, workdir):
    write_routes(workdir, {"me.py": "from ushka import Response\nasync def get(request):\n    if request.cookies.get('sid') != 'ok':\n        return Response('login', 401)\n    return {'me': 1}\n"})
    app = make_app()
    client = engine._Client(app, "localhost", {"Cookie": "sid=ok"})
    try:
        res = await client.send("GET", "/me")
        anon = await engine._Client(app, "localhost").send("GET", "/me")
    finally:
        client.close()
    assert res["status"] == 200 and anon["status"] == 401
    report = await engine.run(make_app(), headers={"Cookie": "sid=ok"})
    assert report.routes >= 1
