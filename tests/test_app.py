"""End-to-end tests driving `Ushka` through the raw ASGI interface."""

import json

from ushka.http.response import Response


async def test_plain_text_route(app, call):
    @app.get("/hello")
    async def hello():
        return "hi"

    result = await call(app, "GET", "/hello")

    assert result["status"] == 200
    assert result["headers"]["content-type"] == "text/plain"
    assert result["body"] == "hi"


async def test_dict_return_becomes_json(app, call):
    @app.get("/payload")
    async def payload():
        return {"framework": "ushka"}

    result = await call(app, "GET", "/payload")

    assert result["headers"]["content-type"] == "application/json"
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
    assert result["headers"]["content-type"] == "text/html"


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


async def test_unsupported_scope_type_is_rejected(app):
    sent = []

    async def receive():
        return {}

    async def send(message):
        sent.append(message)

    await app({"type": "websocket"}, receive, send)

    assert sent[0]["status"] == 501
