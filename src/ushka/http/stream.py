"""Streaming responses and Server-Sent Events (SSE).

``StreamingResponse`` sends chunks as an async (or sync) iterator produces
them, and stops the iterator when the client goes away. ``EventSourceResponse``
speaks SSE on top of it::

    async def get(request):
        async def events():
            for n in range(5):
                yield {"count": n}              # a dict is sent as JSON
                await asyncio.sleep(1)
        return EventSourceResponse(events())
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import re
from collections.abc import AsyncIterable, Callable, Iterable
from typing import Any

from ushka.http.response import Response

_LINES = re.compile(r"\r\n|\r|\n")
_FIELD_FORBIDDEN = re.compile(r"[\r\n\x00]")


class StreamingResponse(Response):
    """A response whose body is produced chunk by chunk.

    `content` is an async or sync iterable of ``bytes`` or ``str``. Cookies and
    the session are saved with the headers, so set them before the first chunk
    is produced (they are, when you return the response from the handler).
    Cleanup in the iterator (``finally``) runs when the client disconnects.
    """

    def __init__(
        self,
        content: AsyncIterable[bytes | str] | Iterable[bytes | str],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str = "application/octet-stream",
    ) -> None:
        super().__init__(b"", status_code, headers, media_type)
        self.content = content

    def _content_length(self):
        return None  # the size is not known until the iterator ends

    async def _chunks(self):
        if hasattr(self.content, "__aiter__"):
            async for chunk in self.content:
                yield chunk
        else:
            for chunk in self.content:
                yield chunk
                await asyncio.sleep(0)  # let a sync iterator not starve the loop

    async def _send_body(self, send: Callable) -> None:
        if self.head_only:
            await send({"type": "http.response.body", "body": b""})
            return

        async def pump() -> None:
            async for chunk in self._chunks():
                data = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                await send({"type": "http.response.body", "body": data, "more_body": True})

        pumping = asyncio.ensure_future(pump())
        watching = asyncio.ensure_future(self._client_gone())
        try:
            done, _ = await asyncio.wait({pumping, watching}, return_when=asyncio.FIRST_COMPLETED)
            if pumping in done:
                pumping.result()  # a failure in the iterator surfaces here
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            # else: the client left; cancelling below lets the iterator's `finally` run
        finally:
            for task in (watching, pumping):
                if not task.done():
                    task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def _client_gone(self) -> None:
        receive = getattr(self.request, "_receive", None)
        if receive is None:
            await asyncio.Event().wait()  # no way to know: never fires
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            await asyncio.sleep(0)


@dataclasses.dataclass
class ServerSentEvent:
    """One SSE message. `data` may be text (multi-line is fine) or a dict/list sent as JSON."""

    data: Any = ""
    event: str | None = None
    id: str | None = None
    retry: int | None = None
    comment: str | None = None

    def encode(self) -> bytes:
        for name in ("event", "id"):
            value = getattr(self, name)
            if value is not None and _FIELD_FORBIDDEN.search(str(value)):
                # A newline here would let a value forge new fields or events.
                raise ValueError(f"SSE {name} must not contain line breaks")
        out: list[str] = []
        if self.comment is not None:
            out += [f": {line}" for line in _LINES.split(str(self.comment))]
        if self.event is not None:
            out.append(f"event: {self.event}")
        if self.id is not None:
            out.append(f"id: {self.id}")
        if self.retry is not None:
            out.append(f"retry: {int(self.retry)}")
        if self.data != "" or self.comment is None:
            text = self.data if isinstance(self.data, str) else json.dumps(self.data)
            out += [f"data: {line}" for line in _LINES.split(text)]
        return ("\n".join(out) + "\n\n").encode("utf-8")


class EventSourceResponse(StreamingResponse):
    """Server-Sent Events. `events` yields `ServerSentEvent`, text, or dict/list (JSON).

    A comment line is sent every `ping` seconds (``None`` to disable) so proxies
    keep the connection open.
    """

    def __init__(self, events: AsyncIterable | Iterable, ping: float | None = 15, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        merged = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **(headers or {})}
        super().__init__(self._frames(events, ping), status_code, merged, "text/event-stream")

    @staticmethod
    def _frame(item: Any) -> bytes:
        return (item if isinstance(item, ServerSentEvent) else ServerSentEvent(item)).encode()

    async def _frames(self, events, ping):
        source = events if hasattr(events, "__aiter__") else _as_async(events)
        if not ping:
            async for item in source:
                yield self._frame(item)
            return
        queue: asyncio.Queue = asyncio.Queue()
        done = object()

        async def produce() -> None:
            try:
                async for item in source:
                    await queue.put(item)
            except BaseException as exc:  # noqa: BLE001 - handed to the consumer
                await queue.put(exc)
            finally:
                await queue.put(done)

        task = asyncio.ensure_future(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), ping)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    continue
                if item is done:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield self._frame(item)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def _as_async(iterable):
    for item in iterable:
        yield item
        await asyncio.sleep(0)
