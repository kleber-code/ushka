"""WebSockets and Server-Sent Events."""

import asyncio

import pytest

from ushka import EventSourceResponse, ServerSentEvent, StreamingResponse, WebSocket, Depends, Header
from ushka.guard import Untrusted


async def ws_client(app, path, client_messages=(), headers=None, query=b""):
    """Plays a browser: connect, send `client_messages` (str), then disconnect.
    Returns what the server sent."""
    scope = {
        "type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": path, "raw_path": path.encode(),
        "query_string": query, "root_path": "", "subprotocols": [],
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 1), "server": ("testserver", 80),
    }
    inbox = [{"type": "websocket.connect"}] + [{"type": "websocket.receive", "text": m} for m in client_messages]
    inbox.append({"type": "websocket.disconnect", "code": 1000})
    sent = []

    async def receive():
        return inbox.pop(0) if inbox else {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


async def test_echo_and_taint(app):
    seen = []

    @app.websocket("/ws")
    async def chat(ws: WebSocket):
        await ws.accept()
        async for text in ws.iter_text():
            seen.append(isinstance(text, Untrusted))
            await ws.send_text(f"echo: {text}")

    sent = await ws_client(app, "/ws", ["hi", "there"])
    assert sent[0]["type"] == "websocket.accept"
    assert [m["text"] for m in sent if m["type"] == "websocket.send"] == ["echo: hi", "echo: there"]
    assert seen == [True, True]


async def test_file_route_uses_function_named_websocket(make_app, workdir, call):
    (workdir / "routes").mkdir()
    (workdir / "routes" / "echo.py").write_text(
        "async def websocket(ws):\n    await ws.accept()\n    await ws.send_json({'ok': True})\n"
        "async def get():\n    return 'http'\n"
    )
    app = make_app()
    sent = await ws_client(app, "/echo")
    assert sent[1] == {"type": "websocket.send", "text": '{"ok": true}'}
    res = await call(app, "GET", "/echo")
    assert res["status"] == 200 and "WEBSOCKET" not in res["headers"].get("allow", "")


async def test_cross_site_handshake_is_refused(app):
    called = []

    @app.websocket("/ws")
    async def h(ws):
        called.append(1)
        await ws.accept()

    evil = await ws_client(app, "/ws", headers={"Origin": "https://evil.test", "Host": "app.test"})
    assert evil[-1]["type"] == "websocket.close" and not called
    same = await ws_client(app, "/ws", headers={"Origin": "http://app.test", "Host": "app.test"})
    assert same[0]["type"] == "websocket.accept" and called
    none = await ws_client(app, "/ws")  # not a browser
    assert none[0]["type"] == "websocket.accept"


async def test_unknown_path_and_typed_params_and_depends(app):
    @app.websocket("/room/[room_id]")
    async def room(ws, room_id: int, token: str = Header("")):
        await ws.accept()
        await ws.send_text(f"{room_id}:{token}")

    assert (await ws_client(app, "/nope"))[-1]["type"] == "websocket.close"
    ok = await ws_client(app, "/room/7", headers={"token": "t"})
    assert ok[1]["text"] == "7:t"
    assert (await ws_client(app, "/room/x"))[-1]["type"] == "websocket.close"  # 422 becomes a refused handshake


async def test_auth_dependency_can_refuse(app):
    from ushka.http.exceptions import HTTPForbidden

    def need_key(x_key: str = Header("")):
        if x_key != "k":
            raise HTTPForbidden()

    @app.websocket("/priv")
    async def priv(ws, _=Depends(need_key)):
        await ws.accept()

    assert (await ws_client(app, "/priv"))[-1]["type"] == "websocket.close"
    assert (await ws_client(app, "/priv", headers={"x-key": "k"}))[0]["type"] == "websocket.accept"


async def test_oversized_message_closes_with_1009(make_app, workdir):
    (workdir / "ushka.toml").write_text("[limits]\nwebsocket_max_message_in_KB = 1\n")
    app = make_app()

    @app.websocket("/ws")
    async def h(ws):
        await ws.accept()
        async for _ in ws.iter_text():
            pass

    sent = await ws_client(app, "/ws", ["x" * 5000])
    assert {"type": "websocket.close", "code": 1009, "reason": "message too big"} in sent


async def test_handler_error_closes_with_1011(app):
    @app.websocket("/ws")
    async def h(ws):
        await ws.accept()
        raise RuntimeError("boom")

    assert (await ws_client(app, "/ws"))[-1]["code"] == 1011


# -- SSE ---------------------------------------------------------------------------


async def test_sse_stream_format_and_headers(app, call):
    @app.get("/events")
    async def events():
        async def gen():
            yield {"n": 1}
            yield ServerSentEvent("line one\nline two", event="note", id="7", retry=3000)
            yield "plain"

        return EventSourceResponse(gen())

    res = await call(app, "GET", "/events")
    assert res["headers"]["content-type"].startswith("text/event-stream")
    assert res["headers"]["cache-control"] == "no-cache"
    assert res["headers"]["x-content-type-options"] == "nosniff"  # security middleware still applies
    assert res["body"] == 'data: {"n": 1}\n\nevent: note\nid: 7\nretry: 3000\ndata: line one\ndata: line two\n\ndata: plain\n\n'


def test_sse_fields_reject_line_breaks():
    with pytest.raises(ValueError):
        ServerSentEvent("x", event="a\ndata: forged").encode()
    with pytest.raises(ValueError):
        ServerSentEvent("x", id="1\r\nevent: x").encode()


def test_sse_data_newlines_cannot_forge_fields():
    out = ServerSentEvent("a\n\nevent: evil").encode().decode()
    assert out == "data: a\ndata: \ndata: event: evil\n\n"


async def test_sse_ping_and_sync_iterator(app, call):
    async def slow():
        yield "a"
        await asyncio.sleep(0.25)
        yield "b"

    @app.get("/p")
    async def p():
        return EventSourceResponse(slow(), ping=0.05)

    @app.get("/sync")
    async def s():
        return EventSourceResponse(iter(["x", "y"]), ping=None)

    assert ": ping" in (await call(app, "GET", "/p"))["body"]
    assert (await call(app, "GET", "/sync"))["body"] == "data: x\n\ndata: y\n\n"


async def test_stream_stops_and_cleans_up_when_client_disconnects(app):
    state = {"closed": False, "sent": 0}

    @app.get("/forever")
    async def forever():
        async def gen():
            try:
                while True:
                    yield "tick"
                    await asyncio.sleep(0.01)
            finally:
                state["closed"] = True

        return EventSourceResponse(gen(), ping=None)

    scope = {"type": "http", "method": "GET", "path": "/forever", "raw_path": b"/forever", "query_string": b"",
             "headers": [], "scheme": "http", "root_path": "", "client": ("c", 1), "server": ("s", 80),
             "asgi": {"version": "3.0"}, "http_version": "1.1"}
    gone = asyncio.Event()

    async def receive():
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            state["sent"] += 1
            if state["sent"] == 3:
                gone.set()  # the browser tab closes

    await asyncio.wait_for(app(scope, receive, send), 2)
    assert state["closed"] is True and state["sent"] < 20


async def test_plain_streaming_response(app, call):
    @app.get("/s")
    async def s():
        async def parts():
            yield b"ab"
            yield "cd"

        return StreamingResponse(parts(), media_type="text/plain")

    assert (await call(app, "GET", "/s"))["body"] == "abcd"
