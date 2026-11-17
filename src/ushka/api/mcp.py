"""Routes as agent tools, over MCP (Model Context Protocol).

Mark the routes an agent may use, declare what each one touches, and serve them::

    from ushka.api.mcp import tool

    @tool(reads=["orders"], description="Look up an order")
    async def get(order_id: int): ...                     # routes/orders/[order_id].py

    @tool(writes=["orders"], description="Refund an order")
    async def post(order_id: int, reason: str): ...

    app.enable_mcp("/mcp", approve=queue)                 # token from USHKA_MCP_TOKEN

Nothing is exposed unless you mark it. A tool call is an ordinary request to
your own app (with a service credential from ``internal_headers`` if your routes
need one), so the security middleware, validation and your `Depends`
(authentication included) all still apply. The agent's arguments are client
data like any other: strings arrive `Untrusted`.

Declared capabilities do two jobs: they become MCP tool annotations the client
can show, and they decide approval. A tool that writes, calls something
outside, or uses a method other than GET/HEAD needs a human to approve each
call; with no approver configured it is refused.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hmac
import json
import logging
import re
import typing
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote, urlencode

from ushka.api.openapi import _PATH_SEGMENT, _required, _Schemas, _specs
from ushka.http.params import Param

log = logging.getLogger("ushka.api.mcp")

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
SAFE_METHODS = {"GET", "HEAD"}
_SEGMENT = re.compile(r"\[(?:(?:path|int):)?([A-Za-z_][A-Za-z0-9_]*)\]")


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """What a route declares about itself as an agent tool."""

    name: str | None = None
    description: str = ""
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    approval: bool | None = None  # None: decided by the capabilities

    def needs_approval(self, method: str) -> bool:
        if self.approval is not None:
            return self.approval
        return bool(self.writes or self.calls) or method not in SAFE_METHODS


def tool(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str = "",
    reads: list[str] | tuple[str, ...] = (),
    writes: list[str] | tuple[str, ...] = (),
    calls: list[str] | tuple[str, ...] = (),
    approval: bool | None = None,
):
    """Marks a route handler as an agent tool and declares its capabilities.

    `reads` and `writes` name the data it touches (``"orders"``, ``"db:users"``),
    `calls` the outside services it reaches (``"stripe"``). `approval=True`
    forces a human approval, ``False`` waives it. By default writing, calling
    out, or a method other than GET requires it.
    """

    def mark(fn: Callable) -> Callable:
        fn.__ushka_tool__ = ToolSpec(name, description or (fn.__doc__ or "").strip().split("\n")[0], tuple(reads), tuple(writes), tuple(calls), approval)
        return fn

    return mark(func) if callable(func) else mark


@dataclasses.dataclass
class ToolCall:
    """What a human is asked to approve: exactly what is about to run."""

    id: str
    tool: str
    method: str
    path: str
    arguments: dict[str, Any]
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    calls: tuple[str, ...]


Approver = Callable[[ToolCall], Awaitable[bool]]


class ApprovalQueue:
    """In-memory approvals for apps that give humans a page or a chat to decide.

    ``enable_mcp(approve=queue)`` makes each sensitive call wait here. Your own
    route (behind your own login!) shows ``queue.pending()`` and calls
    ``queue.decide(id, True or False)``. No answer within `timeout` seconds is a no.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout
        self._waiting: dict[str, tuple[ToolCall, asyncio.Future]] = {}

    def pending(self) -> list[ToolCall]:
        return [call for call, _ in self._waiting.values()]

    def decide(self, call_id: str, approved: bool) -> bool:
        """Records the human's answer. False if there is no such pending call."""
        entry = self._waiting.get(call_id)
        if entry is None or entry[1].done():
            return False
        entry[1].set_result(bool(approved))
        return True

    async def __call__(self, call: ToolCall) -> bool:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiting[call.id] = (call, future)
        try:
            return await asyncio.wait_for(future, self.timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self._waiting.pop(call.id, None)


async def terminal_approver(call: ToolCall) -> bool:
    """For local development: asks in the terminal that runs the server."""
    summary = f"\n[ushka mcp] approve {call.method} {call.path}?\n  tool: {call.tool}\n  arguments: {json.dumps(call.arguments, default=str)}\n  writes: {list(call.writes)} calls: {list(call.calls)}\n  [y/N] "
    answer = await asyncio.to_thread(input, summary)
    return answer.strip().lower() in ("y", "yes")


@dataclasses.dataclass
class _Tool:
    name: str
    method: str
    raw_path: str
    func: Callable
    spec: ToolSpec


class MCPServer:
    """Serves the marked routes of `app` as MCP tools (JSON-RPC over HTTP POST)."""

    def __init__(self, app, path: str, token: str | bool | None, approve: Approver | None, name: str | None, instructions: str | None, internal_headers: dict | Callable | None = None, max_result_bytes: int = 65536) -> None:
        self.app, self.path = app, path
        self.internal_headers = internal_headers
        #: token=False: no shared secret, so each route's own auth decides, and sees the caller's Authorization.
        self.delegate_auth = token is False
        self.approve = approve
        self.server_name = name or app.config.get("app_name", "ushka")
        self.instructions = instructions
        self.max_result_bytes = max_result_bytes
        self.token = self._resolve_token(token)
        self.tools = self._collect()

    def _resolve_token(self, token) -> str | None:
        if token is False:
            self.app.log.warning("MCP endpoint at %s has NO authentication (token=False)", self.path)
            return None
        value = token or self.app.config.get("mcp_token")
        if value:
            return str(value)
        if self.app.config.get("app_debug"):
            self.app.log.warning("MCP endpoint at %s has no token: allowed because debug is on", self.path)
            return None
        raise ValueError(
            "enable_mcp needs a token: set USHKA_MCP_TOKEN (or pass token=...). "
            "An agent endpoint without authentication would let anyone call your tools."
        )

    def _collect(self) -> dict[str, _Tool]:
        tools: dict[str, _Tool] = {}
        for method, raw_path, func in self.app.router.iter_routes():
            spec: ToolSpec | None = getattr(func, "__ushka_tool__", None)
            if spec is None or method == "WEBSOCKET":
                continue
            if method in SAFE_METHODS and spec.writes:
                raise ValueError(f"{method} {raw_path} declares writes={list(spec.writes)}: a {method} route must be safe. Use POST/PUT/PATCH/DELETE.")
            slug = _SEGMENT.sub(r"\1", raw_path)
            name = spec.name or re.sub(r"[^a-z0-9]+", "_", f"{method}_{slug}".lower()).strip("_")
            if name in tools:
                raise ValueError(f"Two MCP tools are named {name!r}; give one a name=")
            tools[name] = _Tool(name, method, raw_path, func, spec)
        return tools

    # -- JSON-RPC ----------------------------------------------------------------

    async def handle(self, request) -> tuple[int, Any]:
        if self.token is not None:
            header = str(request.headers.get("authorization") or "")
            scheme, _, given = header.partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(given.encode(), self.token.encode()):
                return 401, {"error": "invalid or missing bearer token"}
        try:
            message = json.loads(await request.body())
        except ValueError:
            return 400, _error(None, -32700, "Parse error")
        if isinstance(message, list):
            replies = [r for r in [await self._one(request, m) for m in message] if r is not None]
            return (200, replies) if replies else (202, None)
        reply = await self._one(request, message)
        return (200, reply) if reply is not None else (202, None)

    async def _one(self, request, message: Any) -> dict | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
        mid, method, params = message.get("id"), message["method"], message.get("params") or {}
        if "id" not in message:
            return None  # a notification: nothing to answer
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                return _ok(mid, {
                    "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": str(self.server_name), "version": "1"},
                    **({"instructions": self.instructions} if self.instructions else {}),
                })
            if method == "ping":
                return _ok(mid, {})
            if method == "tools/list":
                return _ok(mid, {"tools": [self._describe(t) for t in self.tools.values()]})
            if method == "tools/call":
                return _ok(mid, await self._call(request, params))
        except _InvalidParams as exc:
            return _error(mid, -32602, str(exc))
        return _error(mid, -32601, f"Method not found: {method}")

    # -- tools/list --------------------------------------------------------------

    def _describe(self, t: _Tool) -> dict:
        schemas = _Schemas()
        properties: dict[str, Any] = {}
        required: list[str] = []
        names = frozenset(_PATH_SEGMENT.findall(t.raw_path))
        for s in _specs(t.func, names, t.method):
            if s.kind not in ("path", "query", "body", "form"):
                continue
            marker: Param | None = s.marker
            tp = typing.Annotated[s.annotation, marker] if marker else s.annotation
            properties[marker.alias if marker and marker.alias else s.name] = schemas.of(tp)
            if s.kind == "path" or s.default is _required():
                required.append(marker.alias if marker and marker.alias else s.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        if schemas.components:
            schema["$defs"] = schemas.components
            schema = json.loads(json.dumps(schema).replace("#/components/schemas/", "#/$defs/"))
        caps = t.spec
        facts = [f"{label}: {', '.join(items)}" for label, items in (("Reads", caps.reads), ("Writes", caps.writes), ("Calls", caps.calls)) if items]
        approval = " Needs human approval." if caps.needs_approval(t.method) else ""
        return {
            "name": t.name,
            "description": " ".join(x for x in [caps.description, ". ".join(facts) + ("." if facts else "") + approval] if x.strip()),
            "inputSchema": schema,
            "annotations": {
                "readOnlyHint": not (caps.writes or caps.calls) and t.method in SAFE_METHODS,
                "destructiveHint": bool(caps.writes),
                "openWorldHint": bool(caps.calls),
            },
        }

    # -- tools/call --------------------------------------------------------------

    async def _call(self, request, params: dict) -> dict:
        tool_ = self.tools.get(params.get("name"))
        if tool_ is None:
            raise _InvalidParams(f"Unknown tool: {params.get('name')!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise _InvalidParams("arguments must be an object")

        spec = tool_.spec
        call = ToolCall(uuid.uuid4().hex, tool_.name, tool_.method, tool_.raw_path, arguments, spec.reads, spec.writes, spec.calls)
        if spec.needs_approval(tool_.method):
            if self.approve is None:
                log.warning("mcp tool=%s DENIED: needs approval and no approver is configured", tool_.name)
                return _text("Refused: this action needs human approval and no approver is configured on the server.", error=True)
            if not await self.approve(call):
                log.warning("mcp tool=%s DENIED by approver id=%s", tool_.name, call.id)
                return _text("Refused: a human did not approve this action.", error=True)
            log.info("mcp tool=%s APPROVED id=%s", tool_.name, call.id)
        else:
            log.info("mcp tool=%s id=%s args=%s", tool_.name, call.id, sorted(arguments))

        status, body = await self._invoke(request, tool_, arguments)
        text = body.decode("utf-8", "replace")
        if len(body) > self.max_result_bytes:
            text = text[: self.max_result_bytes] + "\n[truncated]"
        return _text(text, error=status >= 400)

    async def _invoke(self, request, t: _Tool, arguments: dict) -> tuple[int, bytes]:
        """Runs the route through the whole app, as an ordinary request."""
        names = frozenset(_PATH_SEGMENT.findall(t.raw_path))
        specs = [s for s in _specs(t.func, names, t.method) if s.kind in ("path", "query", "body", "form")]
        used = {s.marker.alias if s.marker and s.marker.alias else s.name for s in specs}
        unknown = set(arguments) - used
        if unknown:
            raise _InvalidParams(f"Unknown argument(s): {', '.join(sorted(map(str, unknown)))}")

        def key(s) -> str:
            return s.marker.alias if s.marker and s.marker.alias else s.name

        def fill(match: re.Match) -> str:
            name = match.group(1)
            if name not in arguments:
                raise _InvalidParams(f"Missing argument: {name}")
            return str(arguments[name])

        path = _SEGMENT.sub(fill, t.raw_path)
        if re.search(r"[\x00-\x1f]", path):
            raise _InvalidParams("Invalid path argument")
        query = {key(s): arguments[key(s)] for s in specs if s.kind == "query" and key(s) in arguments}
        body_specs = [s for s in specs if s.kind == "body"]
        form_specs = [s for s in specs if s.kind == "form"]
        payload, content_type = b"", None
        if body_specs:
            single = len(body_specs) == 1 and not (body_specs[0].marker and body_specs[0].marker.embed)
            data = arguments.get(key(body_specs[0])) if single else {key(s): arguments[key(s)] for s in body_specs if key(s) in arguments}
            if data is not None:
                payload, content_type = json.dumps(data).encode(), "application/json"
        elif form_specs:
            payload = urlencode({key(s): arguments[key(s)] for s in form_specs if key(s) in arguments}).encode()
            content_type = "application/x-www-form-urlencoded"

        pairs = []
        for k, v in query.items():
            for item in (v if isinstance(v, list) else [v]):
                pairs.append((k, "true" if item is True else "false" if item is False else str(item)))
        headers = [(b"host", str(request.headers.get("host") or "localhost").encode("latin-1"))]
        extra = self.internal_headers(request) if callable(self.internal_headers) else (self.internal_headers or {})
        if self.delegate_auth and request.headers.get("authorization"):
            extra = {"authorization": str(request.headers["authorization"]), **extra}
        for k, v in extra.items():
            headers.append((str(k).lower().encode("latin-1"), str(v).encode("latin-1")))
        if content_type:
            headers.append((b"content-type", content_type.encode()))
        headers.append((b"content-length", str(len(payload)).encode()))
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": t.method, "scheme": request.scope.get("scheme", "http"),
            "path": path, "raw_path": quote(path).encode(), "query_string": urlencode(pairs).encode(), "root_path": "",
            "headers": headers, "client": request.scope.get("client"), "server": request.scope.get("server"),
        }
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            sent.append(message)

        await self.app(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        return start["status"], b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


class _InvalidParams(Exception):
    pass


def _ok(mid, result) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}
