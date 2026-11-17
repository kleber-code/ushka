"""OpenAPI, MCP, Static and Sessions as pieces: `app.use(X())`, and the old calls as shortcuts."""

import json

import pytest

from ushka.api.mcp import MCP, tool
from ushka.api.openapi import OpenAPI
from ushka.sessions import Sessions
from ushka.sessions.stores import get_store
from ushka.static import Static

# -- OpenAPI ------------------------------------------------------------------------------------


async def test_openapi_with_no_arguments(app, call):
    @app.get("/ping")
    async def ping():
        return "pong"

    assert app.use(OpenAPI()) is app.pieces["openapi"]
    doc = json.loads((await call(app, "GET", "/openapi.json"))["body"])
    assert "/ping" in doc["paths"] and "/openapi.json" not in doc["paths"]


async def test_openapi_options_and_the_old_shortcut_are_the_same(app, call):
    @app.get("/ping")
    async def ping():
        return "pong"

    app.use(OpenAPI("/spec.json", title="Shop", version="2"))
    piece = json.loads((await call(app, "GET", "/spec.json"))["body"])
    app.enable_openapi("/old.json", title="Shop", version="2")
    old = json.loads((await call(app, "GET", "/old.json"))["body"])
    assert piece["info"] == old["info"] == {"title": "Shop", "version": "2"}
    assert piece["paths"] == old["paths"]
    assert "/old.json" not in old["paths"] and "/spec.json" not in old["paths"]
    assert isinstance(app.pieces["openapi"], OpenAPI)


# -- MCP ----------------------------------------------------------------------------------------


def rpc(method, params=None):
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params is not None else {})}).encode()


def add_tool(app):
    @app.get("/ping")
    @tool(reads=["x"], description="Ping")
    async def ping():
        return {"ok": True}


async def test_mcp_with_a_token(app, call):
    add_tool(app)
    app.use(MCP(token="s3"))
    headers = {"Authorization": "Bearer s3", "Content-Type": "application/json"}
    res = await call(app, "POST", "/mcp", body=rpc("tools/list"), headers=headers)
    assert [t["name"] for t in json.loads(res["body"])["result"]["tools"]] == ["get_ping"]
    assert (await call(app, "POST", "/mcp", body=rpc("tools/list"), headers={"Authorization": "Bearer no"}))["status"] == 401
    assert app.mcp.path == "/mcp"


async def test_mcp_token_from_the_environment_and_a_path(app, call, monkeypatch):
    monkeypatch.setenv("USHKA_MCP_TOKEN", "from-env")
    app.config.load_from_file()
    add_tool(app)
    app.use(MCP(path="/agents", name="shop", instructions="Be kind"))
    assert app.mcp.token == "from-env" and app.mcp.server_name == "shop" and app.mcp.instructions == "Be kind"
    res = await call(app, "POST", "/agents", body=rpc("tools/list"), headers={"Authorization": "Bearer from-env"})
    assert res["status"] == 200


def test_mcp_needs_a_token_and_enable_mcp_is_the_same(app, monkeypatch):
    monkeypatch.delenv("USHKA_MCP_TOKEN", raising=False)
    with pytest.raises(ValueError, match="needs a token"):
        app.use(MCP())
    with pytest.raises(ValueError, match="needs a token"):
        app.enable_mcp()
    app.enable_mcp("/m", token="t", name="n")
    assert isinstance(app.pieces["mcp"], MCP)
    assert app.mcp.path == "/m" and app.mcp.token == "t" and app.mcp.server_name == "n"


def test_mcp_typo_suggests_the_option():
    with pytest.raises(TypeError, match="did you mean 'instructions'"):
        MCP(token="t", instrucions="x")
    with pytest.raises(TypeError, match="unexpected option 'bogus'"):
        MCP(token="t", bogus=1)


# -- Static -------------------------------------------------------------------------------------


@pytest.fixture
def files(workdir):
    (workdir / "static").mkdir()
    (workdir / "static" / "a.txt").write_text("from static")
    (workdir / "public").mkdir()
    (workdir / "public" / "b.txt").write_text("from public")


async def test_static_with_a_folder_is_mount_static(app, call, files):
    app.use(Static("public", url="/assets", cache_control="no-store"))
    res = await call(app, "GET", "/assets/b.txt")
    assert res["status"] == 200 and res["body"] == "from public" and res["headers"]["cache-control"] == "no-store"
    assert (await call(app, "GET", "/assets/nope.txt"))["status"] == 404


async def test_static_matches_mount_static(app, call, files):
    app.use(Static("public", url="/one"))
    app.mount_static("/two", "public")
    a, b = await call(app, "GET", "/one/b.txt"), await call(app, "GET", "/two/b.txt")
    assert (a["status"], a["body"], a["headers"]["cache-control"]) == (b["status"], b["body"], b["headers"]["cache-control"])


async def test_static_html_option(app, call, workdir):
    (workdir / "site").mkdir()
    (workdir / "site" / "index.html").write_text("<p>home</p>")
    app.use(Static("site", url="/site", html=True))
    assert (await call(app, "GET", "/site/"))["body"] == "<p>home</p>"


async def test_static_without_a_folder_turns_the_static_dir_on(app, call, files):
    assert (await call(app, "GET", "/static/a.txt"))["body"] != "from static"  # an app with no routes shows the welcome page
    app.use(Static())
    assert (await call(app, "GET", "/static/a.txt"))["body"] == "from static"
    assert app.config.get("static_enable") and app.config.source_of("static_enable") == "code"


async def test_static_options_in_code_lose_to_the_file(workdir, make_app, call, files):
    (workdir / "ushka.toml").write_text('[static]\nurl = "/files"\n')
    app = make_app()
    app.use(Static(url="/ignored", cache_control="no-store"))
    assert (await call(app, "GET", "/files/a.txt"))["body"] == "from static"
    assert (await call(app, "GET", "/ignored/a.txt"))["status"] == 404
    assert (await call(app, "GET", "/files/a.txt"))["headers"]["cache-control"] == "no-store"


async def test_static_from_toml_alone_still_works_and_use_does_not_double_it(workdir, make_app, call, files):
    (workdir / "ushka.toml").write_text("[static]\nenable = true\n")
    app = make_app()
    app.use(Static())
    assert (await call(app, "GET", "/static/a.txt"))["status"] == 200


def test_static_html_without_a_folder_is_an_error():
    with pytest.raises(TypeError, match="needs a folder"):
        Static(html=True)


def test_static_rejects_an_unknown_option():
    with pytest.raises(TypeError):
        Static("public", urll="/x")


# -- Sessions -----------------------------------------------------------------------------------


def session_app(make_app, workdir, toml=""):
    if toml:
        (workdir / "ushka.toml").write_text(toml)
    app = make_app()

    @app.post("/login")
    async def login(request):
        request.session["user_id"] = 7
        return {"ok": True}

    @app.get("/me")
    async def me(request):
        return {"user": request.session.get("user_id")}

    return app


async def login_and_read(call, app):
    res = await call(app, "POST", "/login")
    cookie = res["headers"]["set-cookie"].split(";", 1)[0]
    body = (await call(app, "GET", "/me", headers={"cookie": cookie}))["body"]
    return cookie, json.loads(body)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", "k" * 40)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("USHKA_DB_URL", raising=False)


async def test_sessions_database_after_the_app_exists(make_app, workdir, call):
    app = session_app(make_app, workdir, f'[database]\nurl = "sqlite:///{workdir}/s.db"\n')
    assert get_store(app) is None  # cookies until told otherwise (and the lookup must not stick)
    app.use(Sessions("database"))
    store = get_store(app)
    assert store is not None and app.config.source_of("session_store") == "code"
    cookie, me = await login_and_read(call, app)
    assert me == {"user": 7} and cookie.count(".") < 2  # an opaque id, not a signed payload
    await store._engine.dispose()


async def test_sessions_switch_drops_the_store_built_before(make_app, workdir):
    app = session_app(make_app, workdir, f'[database]\nurl = "sqlite:///{workdir}/s.db"\n')
    app.use(Sessions("database"))
    first = get_store(app)
    app.use(Sessions("cookie"))
    assert get_store(app) is None
    await first._engine.dispose()


async def test_sessions_database_without_a_database_falls_back_with_a_warning(make_app, workdir, call, caplog):
    import logging

    app = session_app(make_app, workdir)
    app.use(Sessions("database"))
    with caplog.at_level(logging.WARNING):
        assert get_store(app) is None
    assert any("needs a database" in r.getMessage() for r in caplog.records)
    _, me = await login_and_read(call, app)
    assert me == {"user": 7}


async def test_sessions_cookie_encrypt(make_app, workdir, call):
    pytest.importorskip("cryptography")
    app = session_app(make_app, workdir)
    app.use(Sessions("cookie", encrypt=True, cookie_name="shop"))
    res = await call(app, "POST", "/login")
    assert res["headers"]["set-cookie"].startswith("shop=") and app.config.get("session_encrypt")
    cookie = res["headers"]["set-cookie"].split(";", 1)[0]
    assert (await call(app, "GET", "/me", headers={"cookie": cookie}))["body"] == '{"user": 7}'


def test_sessions_options_lose_to_ushka_toml(make_app, workdir):
    app = session_app(make_app, workdir, "[session]\nmax_age = 60\n")
    app.use(Sessions("cookie", max_age=999, idle_timeout=5))
    assert app.config.get("session_max_age") == 60 and app.config.get("session_idle_timeout") == 5


def test_sessions_environment_wins(make_app, workdir, monkeypatch):
    monkeypatch.setenv("USHKA_SESSION_STORE", "cookie")
    app = session_app(make_app, workdir)
    app.use(Sessions("database"))
    assert app.config.get("session_store") == "cookie"


def test_sessions_typo_suggests_the_key(make_app, workdir):
    app = session_app(make_app, workdir)
    with pytest.raises(TypeError, match="max_age"):
        app.use(Sessions("cookie", maxage=5))


def test_sessions_without_arguments_changes_nothing(make_app, workdir):
    app = session_app(make_app, workdir)
    app.use(Sessions())
    assert app.config.get("session_store") == "cookie"
