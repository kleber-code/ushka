"""WebSockets. A handler named ``websocket`` in ``routes/``, or ``@app.websocket``::

    # routes/chat.py
    async def websocket(ws):
        await ws.accept()
        async for text in ws.iter_text():        # Untrusted, like any client data
            await ws.send_text(f"echo: {text}")

The handshake is checked before your code runs: a browser on another site
cannot open the socket (the cross-site WebSocket hijacking attack), and
``allowed_hosts`` applies. Everything the client sends is marked `Untrusted`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from ushka.http.jsonenc import dumps
from ushka.http.request import Request


class WebSocketDisconnect(Exception):
    """The connection ended: the client left, or sent something unacceptable."""

    def __init__(self, code: int = 1005, reason: str = "") -> None:
        super().__init__(code, reason)
        self.code = code
        self.reason = reason


class WebSocket:
    """One WebSocket connection. `request` gives headers, query, cookies and session."""

    def __init__(self, request: Request, receive, send) -> None:
        self.request = request
        self.path_params = request.path_params
        self._receive, self._send = receive, send
        #: "connecting", "connected" or "closed"
        self.state = "connecting"
        self.max_message_bytes = int(request.app.config.get("limits_websocket_max_message_in_KB", 1024)) * 1024

    # -- handshake ---------------------------------------------------------------

    async def accept(self, subprotocol: str | None = None, headers: dict[str, str] | None = None) -> None:
        if self.state != "connecting":
            raise RuntimeError("accept() was already called")
        message = await self._receive()
        if message["type"] != "websocket.connect":
            self.state = "closed"
            raise WebSocketDisconnect(1006)
        reply: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            reply["subprotocol"] = subprotocol
        if headers:
            reply["headers"] = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
        await self._send(reply)
        self.state = "connected"

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.state == "closed":
            return
        if self.state == "connecting":  # refusing the handshake: consume the connect first
            await self._receive()
        self.state = "closed"
        await self._send({"type": "websocket.close", "code": code, "reason": reason})

    # -- receiving ---------------------------------------------------------------

    async def _next(self) -> dict:
        if self.state != "connected":
            raise RuntimeError("call accept() first")
        message = await self._receive()
        if message["type"] == "websocket.disconnect":
            self.state = "closed"
            raise WebSocketDisconnect(message.get("code", 1005), message.get("reason") or "")
        size = len(message.get("text") or "") + len(message.get("bytes") or b"")
        if size > self.max_message_bytes:
            await self.close(1009, "message too big")
            raise WebSocketDisconnect(1009, "message too big")
        return message

    async def receive_text(self) -> str:
        message = await self._next()
        text = message.get("text")
        if text is None:
            text = (message.get("bytes") or b"").decode("utf-8", "replace")
        return self.request._mark(text, "websocket")

    async def receive_bytes(self) -> bytes:
        message = await self._next()
        data = message.get("bytes")
        return data if data is not None else (message.get("text") or "").encode("utf-8")

    async def receive_json(self) -> Any:
        text = await self.receive_text()
        try:
            return self.request._mark(json.loads(text), "websocket")
        except ValueError:
            await self.close(1003, "invalid JSON")
            raise WebSocketDisconnect(1003, "invalid JSON") from None

    async def iter_text(self) -> AsyncIterator[str]:
        """Yields each text message until the client disconnects."""
        try:
            while True:
                yield await self.receive_text()
        except WebSocketDisconnect:
            return

    # -- sending -----------------------------------------------------------------

    async def send_text(self, data: str) -> None:
        await self._send_frame({"type": "websocket.send", "text": str(data)})

    async def send_bytes(self, data: bytes) -> None:
        await self._send_frame({"type": "websocket.send", "bytes": bytes(data)})

    async def send_json(self, data: Any) -> None:
        await self.send_text(dumps(data))

    async def _send_frame(self, message: dict) -> None:
        if self.state != "connected":
            raise RuntimeError("the connection is not open")
        await self._send(message)
