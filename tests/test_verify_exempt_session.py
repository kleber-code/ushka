"""ushka verify: CSRF-exempt routes, redirects to the login page, and probing as a logged-in user."""

from __future__ import annotations

import json

import pytest

from tests.test_verify import kinds, write_routes
from ushka.cli import main
from ushka.security import verify as engine
from ushka.sessions import (
    aforge_session_cookie,
    forge_session_cookie,
    parse_session_pairs,
)

KEY = "k" * 48

ECHO_HTML = (
    "from ushka import Response\n"
    "async def get(request):\n"
    "    return Response(f\"<h1>{request.query.get('name', 'x')}</h1>\", media_type='text/html')\n"
)
WRITE = "async def post(request):\n    return {'q': request.query.get('q', '')}\n"


# -- 1. routes exempt from CSRF ---------------------------------------------------------------


async def test_exempt_routes_are_probed_and_marked(make_app, workdir):
    write_routes(workdir, {"save.py": WRITE})
    (workdir / "routes" / "hooks").mkdir()
    (workdir / "routes" / "hooks" / "pay.py").write_text(WRITE)
    (workdir / "routes" / "hooks" / "echo.py").write_text(ECHO_HTML)
    (workdir / "ushka.toml").write_text('[security]\ncsrf_exempt_paths = ["/hooks"]\ntaint = false\n')
    report = await engine.run(make_app())

    assert report.exempt == ["GET /hooks/echo", "POST /hooks/pay"]
    hit = [f for f in report.findings if f.route == "GET /hooks/echo" and f.category == "xss"]
    assert hit and hit[0].kind == "VULNERABLE" and hit[0].exempt  # the payload reached an exempt route
    assert not any(f.category == "csrf" for f in report.findings)  # exempt on purpose: no false CSRF alarm
    assert any("POST /hooks/pay" in s and "include-writes" in s for s in report.skipped)  # same method rules
    assert all("not probed" not in s for s in report.skipped)
    assert report.outcomes["blocked"] >= 1  # the non-exempt POST /save still got its cross-site probe refused
    assert report.to_dict()["exempt"] == report.exempt


async def test_exempt_writes_follow_include_writes(make_app, workdir):
    (workdir / "routes" / "hooks").mkdir(parents=True)
    (workdir / "routes" / "hooks" / "pay.py").write_text(
        "from ushka import Response\nasync def post(request):\n    return Response(f\"<b>{request.query.get('q', '')}</b>\", media_type='text/html')\n"
    )
    (workdir / "ushka.toml").write_text('[security]\ncsrf_exempt_paths = "/hooks"\ntaint = false\n')
    report = await engine.run(make_app(), include_writes=True)

    assert not report.skipped
    assert ("VULNERABLE", "POST /hooks/pay", "xss") in kinds(report)  # a probe with no cross-site headers is not masked by CSRF


async def test_skip_exempt_restores_leaving_them_out(make_app, workdir):
    (workdir / "routes" / "hooks").mkdir(parents=True)
    (workdir / "routes" / "hooks" / "echo.py").write_text(ECHO_HTML)
    (workdir / "ushka.toml").write_text('[security]\ncsrf_exempt_paths = ["/hooks"]\ntaint = false\n')
    report = await engine.run(make_app(), skip_exempt=True)

    assert report.exempt == [] and report.probes == 0
    assert any("GET /hooks/echo" in s and "--skip-exempt" in s for s in report.skipped)
    assert not [f for f in report.findings if f.kind == "VULNERABLE"]


async def test_csrf_off_is_not_reported_as_exempt(make_app, workdir):
    write_routes(workdir, {"save.py": WRITE})
    (workdir / "ushka.toml").write_text('[security]\ncsrf = false\ncsrf_exempt_paths = ["/save"]\n')
    report = await engine.run(make_app())
    assert report.exempt == [] and ("config", "POST /save", "csrf") in kinds(report)


# -- 2. redirects ----------------------------------------------------------------------------


REDIRECTS = {
    "a.py": "from ushka.http import redirect\nasync def get(request):\n    request.query.get('q')\n    return redirect('/login?next=/a')\n",
    "b.py": "from ushka.http import redirect\nasync def get(request):\n    return redirect('/login?next=/b%3Fq%3D' + request.query.get('q', ''))\n",
    "c.py": "from ushka.http import redirect\nasync def get(request):\n    return redirect('/login?next=' + request.query.get('q', ''))\n",
    "d.py": "from ushka.http import redirect\nasync def get(request):\n    return redirect(request.query.get('q', '/'))\n",
    "e.py": (
        "from ushka import Response\nasync def get(request):\n"
        "    return Response(f\"<a href='/login'>{request.query.get('q', '')}</a>\", 302, {'location': '/login'}, media_type='text/html')\n"
    ),
}


@pytest.fixture
async def redirect_report(make_app, workdir):
    write_routes(workdir, REDIRECTS)
    (workdir / "ushka.toml").write_text("[security]\ntaint = false\n")
    return await engine.run(make_app())


def about(report, route):
    return [f for f in report.findings if f.route == route]


async def test_a_redirect_to_the_login_is_not_a_finding(redirect_report):
    assert about(redirect_report, "GET /a") == []
    assert redirect_report.outcomes["handled"] > 0


async def test_the_probe_buried_in_the_visitors_own_url_is_not_a_finding(redirect_report):
    assert about(redirect_report, "GET /b") == []


async def test_the_probe_as_the_next_destination_is_medium(redirect_report):
    found = about(redirect_report, "GET /c")
    assert [(f.kind, f.severity, f.category) for f in found] == [("VULNERABLE", "medium", "redirect")]
    assert "'next'" in found[0].detail and "evil.example" in found[0].detail


async def test_a_location_on_the_probe_host_is_high(redirect_report):
    found = about(redirect_report, "GET /d")
    assert [(f.severity, f.category) for f in found] == [("high", "redirect")]
    assert redirect_report.failing("high")


async def test_the_body_of_a_redirect_is_not_scanned_for_markup(redirect_report):
    assert about(redirect_report, "GET /e") == []  # a browser follows the Location and never renders this body


def test_redirect_evidence_rules():
    ev = engine._redirect_evidence
    assert ev("/login?next=/x") is None and ev("") is None
    assert ev("https://evil.example/x")[0] == "high" and ev("//evil.example/x")[0] == "high"
    assert ev("\\\\evil.example\\x")[0] == "high"
    assert ev("/login?next=%2F%2Fevil.example%2Fx")[0] == "medium"
    assert ev("/login?next=https://evil.example/x&u=1")[0] == "medium"
    assert ev("/login?next=/p?q=//evil.example/x") is None
    assert ev("https://good.example/?next=/p") is None


# -- 3. forging a session -----------------------------------------------------------------------


@pytest.fixture
def app(make_app, workdir, monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    monkeypatch.setenv("USHKA_APP_DEBUG", "true")

    def build(toml=""):
        (workdir / "ushka.toml").write_text(toml)
        app = make_app()
        seen = []
        app.seen = seen

        @app.get("/me")
        async def me(request):
            seen.append(dict(request.session))
            return {"uid": request.session.get("uid"), "admin": request.session.get("admin")}

        return app

    return build


def test_parse_session_pairs_infers_types():
    assert parse_session_pairs(["uid=1", "admin=true", "off=False", "name=ana", "eq=a=b", "empty="]) == {
        "uid": 1, "admin": True, "off": False, "name": "ana", "eq": "a=b", "empty": "",
    }
    for bad in ("tokenvalue123", "=tokenvalue123", ""):
        with pytest.raises(ValueError) as info:
            parse_session_pairs([bad])
        assert "tokenvalue123" not in str(info.value)  # the malformed item is never echoed


async def test_a_forged_cookie_logs_in_the_app(app, call):
    a = app()
    cookie = forge_session_cookie(a, {"uid": 1, "admin": True, "name": "ana"})
    assert cookie.startswith("_ushka_session=")
    res = await call(a, "GET", "/me", headers={"cookie": cookie})
    assert json.loads(res["body"]) == {"uid": 1, "admin": True}
    assert forge_session_cookie(a.config, {"uid": 1}).startswith("_ushka_session=")  # a Config works too
    other = await call(a, "GET", "/me", headers={"cookie": cookie[:-3] + "xxx"})
    assert json.loads(other["body"])["uid"] is None  # a tampered one is worthless


async def test_the_cookie_name_follows_the_settings(app):
    a = app('[session]\ncookie_name = "sid"\n')
    assert forge_session_cookie(a, {"uid": 1}).startswith("sid=")


def test_forging_needs_a_secret_key(make_app, workdir, monkeypatch):
    monkeypatch.delenv("USHKA_APP_SECRET_KEY", raising=False)
    monkeypatch.delenv("USHKA_APP_DEBUG", raising=False)
    with pytest.raises(RuntimeError, match="USHKA_APP_SECRET_KEY"):
        forge_session_cookie(make_app(), {"uid": 1})


async def test_database_store_needs_the_async_function(app, call, workdir):
    a = app(f'[database]\nurl = "sqlite:///{workdir}/s.db"\n[session]\nstore = "database"\n')
    with pytest.raises(RuntimeError, match="aforge_session_cookie"):
        forge_session_cookie(a, {"uid": 1})
    cookie = await aforge_session_cookie(a, {"uid": 5, "admin": True})
    res = await call(a, "GET", "/me", headers={"cookie": cookie})
    assert json.loads(res["body"]) == {"uid": 5, "admin": True}  # the record exists in the store


async def test_aforge_also_serves_signed_cookies(app, call):
    a = app()
    cookie = await aforge_session_cookie(a, {"uid": 2})
    assert json.loads((await call(a, "GET", "/me", headers={"cookie": cookie}))["body"])["uid"] == 2


async def test_verify_probes_as_the_forged_user_and_never_reports_values(app):
    a = app()
    report = await engine.run(a, session_data={"uid": 1, "role": "very-secret-role"})
    assert a.seen and all(s == {"uid": 1, "role": "very-secret-role"} for s in a.seen)
    assert report.session_keys == ["role", "uid"]
    assert "very-secret-role" not in json.dumps(report.to_dict())


async def test_verify_without_a_session_sends_no_cookie(app):
    a = app()
    await engine.run(a)
    assert a.seen and all(s == {} for s in a.seen)


async def test_verify_cookie_option_is_sent(app):
    a = app()
    await engine.run(a, cookie=forge_session_cookie(a, {"uid": 9}))
    assert a.seen and all(s == {"uid": 9} for s in a.seen)


async def test_verify_with_a_database_store_leaves_no_record_behind(app, workdir):
    from ushka.sessions import get_store

    a = app(f'[database]\nurl = "sqlite:///{workdir}/v.db"\n[session]\nstore = "database"\n')

    async def records():
        store = get_store(a)
        await store._setup()
        async with store._engine.connect() as conn:
            return len((await conn.execute(store._sa.select(store._table))).all())

    report = await engine.run(a, session_data={"uid": 3})
    assert a.seen and all(s == {"uid": 3} for s in a.seen) and report.session_keys == ["uid"]
    assert await records() == 0
    await aforge_session_cookie(a, {"uid": 3})
    assert await records() == 1  # control: forging on its own does leave one for you to use


async def test_session_probes_reach_routes_behind_a_login(make_app, workdir, monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    (workdir / "routes").mkdir()
    (workdir / "routes" / "panel.py").write_text(
        "from ushka.http import redirect\nasync def get(request):\n"
        "    if not request.session.get('uid'):\n        return redirect('/login?next=/panel')\n"
        "    request.query.get('q')\n    return {'ok': True}\n"
    )
    anonymous = await engine.run(make_app())
    assert anonymous.findings == []  # the redirect is not a finding
    logged = await engine.run(make_app(), session_data={"uid": 1})
    assert logged.findings == [] and logged.outcomes["handled"] > 0


# -- CLI -----------------------------------------------------------------------------------------


@pytest.fixture
def cli_app(app, monkeypatch):
    a = app()
    for module in ("ushka.cli.commands.session", "ushka.cli.commands.verify"):
        monkeypatch.setattr(f"{module}.load_app", lambda _path, a=a: a)
    return a


def test_session_command_prints_a_working_cookie(cli_app, capsys):
    main(["session", "--set", "uid=1", "--set", "admin=true"])
    out = capsys.readouterr().out.strip()
    assert out.startswith("_ushka_session=") and "\n" not in out
    assert out.partition("=")[2].count(".") == 2  # data.timestamp.signature, as the app expects


def test_session_command_refuses_without_a_real_key(app, monkeypatch, capsys):
    monkeypatch.delenv("USHKA_APP_SECRET_KEY")  # debug then generates a per-process key
    a = app()
    assert a.config.source_of("app_secret_key").startswith("generated")
    monkeypatch.setattr("ushka.cli.commands.session.load_app", lambda _p: a)
    with pytest.raises(SystemExit) as info:
        main(["session", "--set", "uid=1"])
    captured = capsys.readouterr()
    assert info.value.code == 1 and "USHKA_APP_SECRET_KEY" in captured.err and captured.out == ""


def test_session_command_refuses_when_debug_is_off_unless_allowed(app, monkeypatch, capsys):
    monkeypatch.setenv("USHKA_APP_DEBUG", "false")
    a = app()
    monkeypatch.setattr("ushka.cli.commands.session.load_app", lambda _p: a)
    with pytest.raises(SystemExit) as info:
        main(["session", "--set", "uid=1"])
    err = capsys.readouterr()
    assert info.value.code == 1 and "debug is off" in err.err and "_ushka_session" not in err.out
    main(["session", "--set", "uid=1", "--allow-non-debug"])
    assert capsys.readouterr().out.startswith("_ushka_session=")


def test_session_command_needs_items_and_valid_pairs(cli_app, capsys):
    for argv in (["session"], ["session", "--set", "oops"]):
        with pytest.raises(SystemExit) as info:
            main(argv)
        assert info.value.code == 1
    assert capsys.readouterr().out == ""


def test_verify_command_flags(cli_app, workdir, capsys):
    main(["verify", "app:app", "--json", "--fail-on", "none", "--as-session", "uid=1", "--as-session", "admin=true", "--skip-exempt"])
    data = json.loads(capsys.readouterr().out)
    assert data["session_keys"] == ["admin", "uid"] and data["failed"] is False
    assert cli_app.seen and all(s == {"uid": 1, "admin": True} for s in cli_app.seen)


def test_verify_command_rejects_a_bad_as_session(cli_app, capsys):
    with pytest.raises(SystemExit) as info:
        main(["verify", "app:app", "--as-session", "nope"])
    assert info.value.code == 1 and "--as-session" in capsys.readouterr().err
