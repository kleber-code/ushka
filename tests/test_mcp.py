"""Routes as agent tools over MCP."""

import asyncio
import json

import pytest

from ushka import Depends, Header
from ushka.api.mcp import ApprovalQueue, tool

TOKEN = "s3cret"
AUTH = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def rpc(method, params=None, mid=1):
    return json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, **({"params": params} if params is not None else {})}).encode()


async def post(call, app, method, params=None, headers=AUTH, mid=1):
    res = await call(app, "POST", "/mcp", body=rpc(method, params, mid), headers=headers)
    return res, (json.loads(res["body"]) if res["body"] else None)


@pytest.fixture
def shop(app):
    calls = {"refund": 0}

    @app.get("/orders/[order_id]")
    @tool(reads=["orders"], description="Look up an order")
    async def get_order(order_id: int, verbose: bool = False):
        return {"id": order_id, "verbose": verbose}

    @app.post("/orders/[order_id]/refund")
    @tool(writes=["orders"], calls=["stripe"], description="Refund an order")
    async def refund(order_id: int, reason: str):
        calls["refund"] += 1
        return {"refunded": order_id, "reason": str(reason)}

    @app.get("/private")
    async def private():
        return "not a tool"

    app.calls = calls
    return app


async def test_only_marked_routes_are_listed_with_schema_and_annotations(shop, call):
    shop.enable_mcp(token=TOKEN)
    res, body = await post(call, shop, "tools/list")
    tools = {t["name"]: t for t in body["result"]["tools"]}
    assert set(tools) == {"get_orders_order_id", "post_orders_order_id_refund"}

    read = tools["get_orders_order_id"]
    assert read["inputSchema"] == {"type": "object", "properties": {"order_id": {"type": "integer"}, "verbose": {"type": "boolean"}}, "required": ["order_id"]}
    assert read["annotations"] == {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
    assert "Reads: orders" in read["description"] and "approval" not in read["description"]

    write = tools["post_orders_order_id_refund"]
    assert write["annotations"] == {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True}
    assert "Writes: orders" in write["description"] and "Calls: stripe" in write["description"] and "Needs human approval" in write["description"]


async def test_endpoint_requires_the_token(shop, call):
    shop.enable_mcp(token=TOKEN)
    for headers in ({"Content-Type": "application/json"}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}):
        res, _ = await post(call, shop, "tools/list", headers=headers)
        assert res["status"] == 401


def test_no_token_refuses_to_start_outside_debug(shop):
    with pytest.raises(ValueError, match="needs a token"):
        shop.enable_mcp()


async def test_env_token_is_used(make_app, workdir, call, monkeypatch):
    monkeypatch.setenv("USHKA_MCP_TOKEN", TOKEN)
    app = make_app()
    app.enable_mcp()
    res, _ = await post(call, app, "ping")
    assert res["status"] == 200


async def test_read_tool_runs_through_the_real_route_with_validation(shop, call):
    shop.enable_mcp(token=TOKEN)
    _, ok = await post(call, shop, "tools/call", {"name": "get_orders_order_id", "arguments": {"order_id": 7, "verbose": True}})
    assert ok["result"]["isError"] is False
    assert json.loads(ok["result"]["content"][0]["text"]) == {"id": 7, "verbose": True}

    _, bad = await post(call, shop, "tools/call", {"name": "get_orders_order_id", "arguments": {"order_id": "abc"}})
    assert bad["result"]["isError"] is True and "int_parsing" in bad["result"]["content"][0]["text"]


async def test_sensitive_tool_is_refused_without_an_approver(shop, call):
    shop.enable_mcp(token=TOKEN)
    _, body = await post(call, shop, "tools/call", {"name": "post_orders_order_id_refund", "arguments": {"order_id": 1, "reason": "x"}})
    assert body["result"]["isError"] and "needs human approval" in body["result"]["content"][0]["text"]
    assert shop.calls["refund"] == 0


async def test_approver_sees_exactly_what_will_run(shop, call):
    seen = []

    async def approve(c):
        seen.append(c)
        return True

    shop.enable_mcp(token=TOKEN, approve=approve)
    _, body = await post(call, shop, "tools/call", {"name": "post_orders_order_id_refund", "arguments": {"order_id": 9, "reason": "damaged"}})
    assert body["result"]["isError"] is False and shop.calls["refund"] == 1
    c = seen[0]
    assert (c.method, c.path, c.arguments, c.writes, c.calls) == ("POST", "/orders/[order_id]/refund", {"order_id": 9, "reason": "damaged"}, ("orders",), ("stripe",))


async def test_denied_approval_does_not_run_the_route(shop, call):
    async def no(_):
        return False

    shop.enable_mcp(token=TOKEN, approve=no)
    _, body = await post(call, shop, "tools/call", {"name": "post_orders_order_id_refund", "arguments": {"order_id": 1, "reason": "x"}})
    assert body["result"]["isError"] and shop.calls["refund"] == 0


async def test_approval_queue_with_a_human_deciding(shop, call):
    queue = ApprovalQueue(timeout=2)
    shop.enable_mcp(token=TOKEN, approve=queue)
    pending = asyncio.ensure_future(post(call, shop, "tools/call", {"name": "post_orders_order_id_refund", "arguments": {"order_id": 3, "reason": "r"}}))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if queue.pending():
            break
    (waiting,) = queue.pending()
    assert waiting.tool == "post_orders_order_id_refund" and shop.calls["refund"] == 0
    assert queue.decide(waiting.id, True) and not queue.decide("nope", True)
    _, body = await pending
    assert body["result"]["isError"] is False and shop.calls["refund"] == 1


async def test_approval_queue_timeout_is_a_no(shop, call):
    shop.enable_mcp(token=TOKEN, approve=ApprovalQueue(timeout=0.05))
    _, body = await post(call, shop, "tools/call", {"name": "post_orders_order_id_refund", "arguments": {"order_id": 1, "reason": "x"}})
    assert body["result"]["isError"] and shop.calls["refund"] == 0


def test_a_get_route_cannot_declare_writes(app):
    @app.get("/x")
    @tool(writes=["db"])
    async def x():
        pass

    with pytest.raises(ValueError, match="must be safe"):
        app.enable_mcp(token=TOKEN)


async def test_protocol_basics(shop, call):
    shop.enable_mcp(token=TOKEN, instructions="Be careful.")
    _, init = await post(call, shop, "initialize", {"protocolVersion": "2025-03-26"})
    assert init["result"]["protocolVersion"] == "2025-03-26" and init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert init["result"]["instructions"] == "Be careful."
    _, newest = await post(call, shop, "initialize", {"protocolVersion": "1999-01-01"})
    assert newest["result"]["protocolVersion"] == "2025-06-18"

    note = await call(shop, "POST", "/mcp", body=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(), headers=AUTH)
    assert note["status"] == 202 and note["body"] == ""

    _, unknown_tool = await post(call, shop, "tools/call", {"name": "nope"})
    assert unknown_tool["error"]["code"] == -32602
    _, unknown_arg = await post(call, shop, "tools/call", {"name": "get_orders_order_id", "arguments": {"order_id": 1, "admin": True}})
    assert unknown_arg["error"]["code"] == -32602
    _, no_method = await post(call, shop, "resources/list")
    assert no_method["error"]["code"] == -32601
    bad = await call(shop, "POST", "/mcp", body=b"{not json", headers=AUTH)
    assert bad["status"] == 400 and json.loads(bad["body"])["error"]["code"] == -32700

    batch = await call(shop, "POST", "/mcp", body=json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}]).encode(), headers=AUTH)
    assert [r["id"] for r in json.loads(batch["body"])] == [1, 2]


async def test_path_argument_cannot_escape_its_segment(shop, call):
    shop.enable_mcp(token=TOKEN)
    _, body = await post(call, shop, "tools/call", {"name": "get_orders_order_id", "arguments": {"order_id": "1/../../private"}})
    assert body["result"]["isError"] is True  # 404/422, never the other route


async def test_tool_route_auth_dependency_still_applies(app, call):
    from ushka.http.exceptions import HTTPForbidden

    def need_service_key(x_service_key: str = Header("")):
        if x_service_key != "svc":
            raise HTTPForbidden(message="no")

    @app.get("/secret")
    @tool(reads=["x"])
    async def secret(_=Depends(need_service_key)):
        return "classified"

    app.enable_mcp(token=TOKEN)
    _, blocked = await post(call, app, "tools/call", {"name": "get_secret", "arguments": {}})
    assert blocked["result"]["isError"] is True  # the MCP token does not unlock the route

    app2_headers = {"X-Service-Key": "svc"}
    app.mcp.internal_headers = app2_headers
    _, ok = await post(call, app, "tools/call", {"name": "get_secret", "arguments": {}})
    assert ok["result"]["isError"] is False and "classified" in ok["result"]["content"][0]["text"]


async def test_delegated_auth_forwards_authorization_to_the_route(app, call):
    from ushka.http.exceptions import HTTPForbidden

    def user(authorization: str = Header("")):
        if authorization != "Bearer user-1":
            raise HTTPForbidden()
        return "u1"

    @app.get("/me")
    @tool(reads=["users"])
    async def me(u=Depends(user)):
        return {"user": u}

    app.enable_mcp(token=False)
    _, ok = await post(call, app, "tools/call", {"name": "get_me", "arguments": {}}, headers={"Authorization": "Bearer user-1", "Content-Type": "application/json"})
    assert ok["result"]["isError"] is False
    _, no = await post(call, app, "tools/call", {"name": "get_me", "arguments": {}}, headers={"Authorization": "Bearer other", "Content-Type": "application/json"})
    assert no["result"]["isError"] is True


async def test_tool_arguments_arrive_untrusted(app, call):
    from ushka.guard import Untrusted

    seen = {}

    @app.post("/say")
    @tool(writes=["log"], approval=False)
    async def say(text: str):
        seen["t"] = isinstance(text, Untrusted)
        return "ok"

    app.enable_mcp(token=TOKEN)
    await post(call, app, "tools/call", {"name": "post_say", "arguments": {"text": "hello"}})
    assert seen["t"] is True


async def test_mcp_route_is_not_in_openapi_and_get_is_405(shop, call):
    shop.enable_mcp(token=TOKEN)
    assert "/mcp" not in shop.openapi()["paths"]
    assert (await call(shop, "GET", "/mcp"))["status"] == 405
