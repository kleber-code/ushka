"""End-to-end tests driving `Ushka` through the raw ASGI interface."""

import json

from ushka.http.response import Response


async def test_plain_text_route(app, call):
    @app.get("/hello")
    async def hello():
        return "hi"

    result = await call(app, "GET", "/hello")

    assert result["status"] == 200
    assert result["headers"]["content-type"] == "text/plain; charset=utf-8"
    assert result["body"] == "hi"


async def test_dict_return_becomes_json(app, call):
    @app.get("/payload")
    async def payload():
        return {"framework": "ushka"}

    result = await call(app, "GET", "/payload")

    assert result["headers"]["content-type"] == "application/json; charset=utf-8"
    assert json.loads(result["body"]) == {"framework": "ushka"}


async def test_sync_handlers_are_supported(app, call):
    @app.get("/sync")
    def sync_handler():
        return "sync"

    result = await call(app, "GET", "/sync")

    assert result["body"] == "sync"


async def test_dynamic_segment_is_passed_to_the_handler(app, call):
    @app.get("/users/[int:uid]")
    async def user(uid):
        return f"user {uid}"

    result = await call(app, "GET", "/users/42")

    assert result["body"] == "user 42"


async def test_request_is_injected_and_body_is_readable(app, call):
    @app.post("/echo")
    async def echo(request):
        return Response(await request.text(), status_code=201)

    result = await call(app, "POST", "/echo", body=b"ping")

    assert result["status"] == 201
    assert result["body"] == "ping"


async def test_json_body_is_parsed(app, call):
    @app.post("/sum")
    async def total(request):
        data = await request.json()
        return {"total": data["a"] + data["b"]}

    result = await call(
        app,
        "POST",
        "/sum",
        body=b'{"a": 2, "b": 3}',
        headers={"content-type": "application/json"},
    )

    assert json.loads(result["body"]) == {"total": 5}


async def test_query_string_is_exposed(app, call):
    @app.get("/search")
    async def search(request):
        return {"q": request.query.get("q")}

    result = await call(app, "GET", "/search", query=b"q=cats")

    assert json.loads(result["body"]) == {"q": "cats"}


async def test_all_verbs_are_registered(app, call):
    for verb in ("get", "post", "put", "patch", "delete"):
        getattr(app, verb)(f"/{verb}")(lambda verb=verb: verb)

    for verb in ("get", "post", "put", "patch", "delete"):
        result = await call(app, verb.upper(), f"/{verb}")
        assert result["body"] == verb


async def test_unknown_path_returns_404(app, call):
    @app.get("/known")
    async def known():
        return "yes"

    result = await call(app, "GET", "/missing")

    assert result["status"] == 404


async def test_empty_app_serves_the_startup_page(app, call):
    result = await call(app, "GET", "/")

    assert result["status"] == 200
    assert result["headers"]["content-type"] == "text/html; charset=utf-8"


async def test_handler_exception_becomes_a_500(app, call):
    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    result = await call(app, "GET", "/boom")

    assert result["status"] == 500


async def test_lifespan_protocol(app):
    events = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent = []

    async def receive():
        return next(events)

    async def send(message):
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)

    assert [m["type"] for m in sent] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]


async def test_websocket_without_a_route_is_refused(app):
    sent = []
    inbox = [{"type": "websocket.connect"}]

    async def receive():
        return inbox.pop(0) if inbox else {"type": "websocket.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "websocket", "path": "/nothing", "query_string": b"", "headers": [], "scheme": "ws"}
    await app(scope, receive, send)

    # No handler: the handshake is refused (the client sees HTTP 403).
    assert [m["type"] for m in sent] == ["websocket.close"] and sent[0]["code"] == 1008


# --- return values, HEAD, lifespan, discovery ---------------------------------


async def test_tuple_return_sets_status_and_headers(app, call):
    @app.post("/items")
    async def create():
        return {"id": 1}, 201, {"X-Id": "1"}

    res = await call(app, "POST", "/items")
    assert res["status"] == 201 and res["headers"]["x-id"] == "1"
    assert res["body"] == '{"id": 1}'


async def test_none_return_is_204(app, call):
    @app.delete("/items")
    async def remove():
        return None

    res = await call(app, "DELETE", "/items")
    assert res["status"] == 204 and res["body"] == ""


async def test_unsupported_body_type_is_a_clear_error(app, call):
    @app.get("/bad")
    async def bad():
        return object()

    assert (await call(app, "GET", "/bad"))["status"] == 500


async def test_head_uses_the_get_handler_without_body(app, call):
    @app.get("/page")
    async def page():
        return "hello"

    res = await call(app, "HEAD", "/page")
    assert res["status"] == 200 and res["body"] == ""


async def test_invalid_json_is_400(app, call):
    @app.post("/json")
    async def handler(request):
        return await request.json()

    res = await call(app, "POST", "/json", body=b"{not json")
    assert res["status"] == 400


async def test_config_is_injected_by_name(app, call):
    @app.get("/name")
    async def handler(config):
        return config.get("app_name")

    assert (await call(app, "GET", "/name"))["body"] == "Ushka App"


async def test_lifespan_hooks_run_in_order(app):
    events = []

    @app.on_startup
    async def start():
        events.append("start")

    @app.on_shutdown
    def stop():
        events.append("stop")

    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message["type"])

    await app({"type": "lifespan"}, receive, send)
    assert events == ["start", "stop"]
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


async def test_failing_startup_hook_is_reported(app):
    @app.on_startup
    def boom():
        raise RuntimeError("db down")

    sent = []

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)
    assert sent[0]["type"] == "lifespan.startup.failed" and "db down" in sent[0]["message"]


async def test_imported_functions_do_not_become_routes(make_app, workdir, call):
    (workdir / "helpers.py").write_text("def get():\n    return 'leaked'\n")
    (workdir / "routes").mkdir()
    (workdir / "routes" / "page.py").write_text(
        "from helpers import get  # noqa\n\n\ndef post():\n    return 'mine'\n"
    )
    import sys

    sys.path.insert(0, str(workdir))
    try:
        app = make_app()
        assert (await call(app, "POST", "/page"))["body"] == "mine"
        assert (await call(app, "GET", "/page"))["status"] == 405
    finally:
        sys.path.remove(str(workdir))
        sys.modules.pop("helpers", None)


async def test_templates_are_loaded_from_the_app_directory(make_app, workdir, call, tmp_path_factory):
    from ushka.templating import render

    (workdir / "templates").mkdir()
    (workdir / "templates" / "hi.html").write_text("<p>{{ who }}</p>")
    app = make_app()

    @app.get("/hi")
    async def hi(request):
        return await render(request, "hi.html", {"who": "app dir"})

    import os

    os.chdir(tmp_path_factory.mktemp("elsewhere"))  # cwd no longer matters
    assert (await call(app, "GET", "/hi"))["body"] == "<p>app dir</p>"


async def test_app_directory_wins_over_an_earlier_config(make_app, workdir, call, tmp_path_factory):
    from ushka.core.config import Config

    Config(tmp_path_factory.mktemp("cli_cwd")).load_from_file()  # what the CLI does first
    (workdir / "static").mkdir()
    (workdir / "static" / "a.css").write_text("body{}")
    (workdir / "ushka.toml").write_text("[static]\nenable = true\n")
    app = make_app()
    res = await call(app, "GET", "/static/a.css")
    assert res["status"] == 200
    assert res["headers"]["content-type"].startswith("text/css")
