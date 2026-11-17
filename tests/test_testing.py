"""`ushka.testing.TestClient`: lifespan, cookies, forms, CSRF."""

import pytest

from ushka import Request
from ushka.testing import TestClient


async def test_lifespan_runs_startup_and_shutdown(app):
    events = []

    @app.on_startup
    async def up():
        events.append("up")

    @app.on_shutdown
    def down():
        events.append("down")

    @app.get("/")
    async def home():
        return "hi"

    async with TestClient(app) as client:
        assert events == ["up"]
        res = await client.get("/")
        assert res.status_code == 200 and res.text == "hi"
    assert events == ["up", "down"]


async def test_httpx_asgitransport_does_not_run_startup(app):
    httpx = pytest.importorskip("httpx")
    events = []

    @app.on_startup
    async def up():
        events.append("up")

    @app.get("/")
    async def home():
        return "hi"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/")).status_code == 200
    assert events == []  # the reason TestClient exists


async def test_failing_startup_raises(app):
    @app.on_startup
    def boom():
        raise ValueError("nope")

    with pytest.raises(RuntimeError, match="startup failed"):
        async with TestClient(app):
            pass


async def test_cookies_persist_between_requests(app):
    @app.get("/set")
    async def set_it(request: Request):
        request.cookies.set("sid", "abc123")
        return "ok"

    @app.get("/who")
    async def who(request: Request):
        return {"sid": str(request.cookies.get("sid"))}

    async with TestClient(app) as client:
        first = await client.get("/set")
        assert first.cookies == {"sid": "abc123"}
        assert client.cookies == {"sid": "abc123"}
        assert (await client.get("/who")).json() == {"sid": "abc123"}
        assert (await client.get("/who", cookies={"sid": "other"})).json() == {"sid": "other"}
        client.cookies.clear()
        assert (await client.get("/who")).json() == {"sid": "None"}


async def test_session_survives_across_requests(monkeypatch, make_app):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", "k" * 40)
    app = make_app()

    @app.post("/login")
    async def login(request: Request):
        request.session["user"] = "ada"
        return "ok"

    @app.get("/me")
    async def me(request: Request):
        return {"user": request.session.get("user")}

    async with TestClient(app) as client:
        assert (await client.post("/login")).status_code == 200
        assert (await client.get("/me")).json() == {"user": "ada"}
        client.cookies.clear()
        assert (await client.get("/me")).json() == {"user": None}


async def test_json_form_files_params_and_headers(app):
    @app.post("/echo")
    async def echo(request: Request):
        ctype = request.headers.get("content-type", "")
        if "json" in ctype:
            return {"json": await request.json(), "x": request.headers.get("x-test")}
        form = await request.form()
        files = await request.files()
        return {"form": {str(k): str(v) for k, v in form.items()}, "files": [str(f["filename"]) for f in files.values()]}

    app.put("/echo")(echo)
    app.patch("/echo")(echo)
    app.delete("/echo")(echo)

    @app.get("/q")
    async def q(request: Request):
        return {"q": str(request.query.get("a")), "tags": list(request.query.get("t"))}

    async with TestClient(app) as c:
        res = await c.post("/echo", json={"a": 1}, headers={"X-Test": "yes"})
        assert res.json() == {"json": {"a": 1}, "x": "yes"}
        assert res.headers["content-type"].startswith("application/json")
        res = await c.post("/echo", data={"a": "1"})
        assert res.json()["form"] == {"a": "1"}
        res = await c.post("/echo", data={"a": "1"}, files={"f": ("n.txt", b"data")})
        assert res.json() == {"form": {"a": "1"}, "files": ["n.txt"]}
        res = await c.get("/q", params={"a": "x y", "t": ["1", "2"]})
        assert res.json() == {"q": "x y", "tags": ["1", "2"]}
        for verb in ("put", "patch", "delete"):
            assert (await getattr(c, verb)("/echo", json={})).status_code == 200


async def test_csrf_script_passes_and_cross_site_browser_is_blocked(app):
    @app.post("/act")
    async def act():
        return "done"

    async with TestClient(app) as script:
        assert (await script.post("/act")).status_code == 200  # no browser headers: not forgeable
        evil = await script.post("/act", headers={"Sec-Fetch-Site": "cross-site"})
        assert evil.status_code == 403
        bad_origin = await script.post("/act", headers={"Origin": "http://evil.example"})
        assert bad_origin.status_code == 403

    async with TestClient(app, browser=True) as browser:
        assert (await browser.post("/act")).status_code == 200  # same-origin browser
        evil = await browser.post("/act", headers={"Sec-Fetch-Site": "cross-site"})
        assert evil.status_code == 403


async def test_follow_redirects(app):
    from ushka import redirect

    @app.get("/old")
    async def old():
        return redirect("/new")

    @app.get("/new")
    async def new():
        return "arrived"

    async with TestClient(app) as c:
        first = await c.get("/old")
        assert first.status_code in (301, 302, 303, 307, 308)
        assert first.headers["location"] == "/new"
        assert (await c.get("/old", follow_redirects=True)).text == "arrived"
