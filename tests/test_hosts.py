"""Routing by Host (L3): `[routes] hosts`, `app.host()`."""

import textwrap

from ushka.core.app import Ushka


def _headers(res):
    return {k: v for k, v in (res["headers"].items() if isinstance(res["headers"], dict) else res["headers"])}


async def test_app_host_routes_only_answer_on_their_host(app, call):
    @app.get("/")
    async def home():
        return "public"

    @app.host("dashboard.*").get("/")
    async def dash():
        return "dashboard"

    @app.host("api.example.com").get("/status")
    async def status():
        return {"ok": True}

    assert (await call(app, "GET", "/", headers={"host": "www.example.com"}))["body"] == "public"
    assert (await call(app, "GET", "/", headers={"host": "dashboard.example.com:8000"}))["body"] == "dashboard"
    assert (await call(app, "GET", "/status", headers={"host": "api.example.com"}))["status"] == 200
    # a host route does not leak onto the default host, nor the reverse
    assert (await call(app, "GET", "/status", headers={"host": "www.example.com"}))["status"] == 404
    assert (await call(app, "GET", "/status", headers={"host": "dashboard.example.com"}))["status"] == 404


async def test_hosts_from_config_load_a_folder_apart_from_routes(workdir, monkeypatch, call):
    (workdir / "routes").mkdir()
    (workdir / "routes" / "index.py").write_text("def get():\n    return 'site'\n")
    (workdir / "routes_admin").mkdir()
    (workdir / "routes_admin" / "index.py").write_text("def get():\n    return 'admin'\n")
    (workdir / "routes_admin" / "users.py").write_text("def get():\n    return 'users'\n")
    (workdir / "ushka.toml").write_text(textwrap.dedent("""
        [routes]
        hosts = { "admin.example.com" = "routes_admin" }
    """))
    monkeypatch.setattr(Ushka, "_setup_workdir", lambda self: setattr(self, "workdir", workdir))
    app = Ushka()
    assert (await call(app, "GET", "/", headers={"host": "admin.example.com"}))["body"] == "admin"
    assert (await call(app, "GET", "/users", headers={"host": "admin.example.com"}))["body"] == "users"
    assert (await call(app, "GET", "/", headers={"host": "example.com"}))["body"] == "site"
    assert (await call(app, "GET", "/users", headers={"host": "example.com"}))["status"] == 404


async def test_405_uses_the_routes_of_the_host(app, call):
    @app.host("api.*").post("/x")
    async def x():
        return "x"

    res = await call(app, "GET", "/x", headers={"host": "api.example.com"})
    assert res["status"] == 405 and "POST" in _headers(res)["allow"]
