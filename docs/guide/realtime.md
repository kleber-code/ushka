# WebSockets and Server-Sent Events

## WebSockets

In `routes/`, a function named `websocket` handles the socket, next to the
`get` and `post` of the same file:

```python
# routes/chat/[room].py
async def websocket(ws, room: int):
    await ws.accept()
    async for text in ws.iter_text():          # Untrusted, like all client data
        await ws.send_json({"room": room, "said": text})
```

Without files: `@app.websocket("/ws")`.

| Method | |
| --- | --- |
| `await ws.accept(subprotocol=None)` | Open the connection. Call it first. |
| `await ws.receive_text()`, `receive_bytes()`, `receive_json()` | One message. |
| `async for text in ws.iter_text()` | Messages until the client leaves. |
| `await ws.send_text()`, `send_bytes()`, `send_json()` | Send. |
| `await ws.close(code=1000)` | Close. It also happens when the handler returns. |
| `ws.request` | Headers, query, cookies and session of the handshake. |

The handler takes the same [typed parameters and `Depends`](validation.md) as
an HTTP route, so authentication is a dependency that raises. A refused
handshake is answered with HTTP 403.

**Secured by default**

- **Cross-site hijacking.** A page on another site can make a visitor's browser
  open a socket to yours, cookies included. Ushka refuses a handshake whose
  `Origin` is another site (the same rule as [CSRF](security.md#csrf)).
  `csrf_trusted_origins` and `cors_origins` allow others. Clients that send no
  `Origin` (not browsers) pass, so authenticate them as you would any API.
- **Trusted hosts** apply to the handshake.
- **Message size** is limited: `[limits] websocket_max_message_in_KB` (1024). A bigger message closes the socket with 1009.
- Text and JSON received are `Untrusted`.
- An error in your handler closes with 1011 and is logged, without leaking details to the client.

## Server-Sent Events

One-way updates from the server to the browser, over plain HTTP:

```python
# routes/clock.py
import asyncio, datetime
from ushka import EventSourceResponse

async def get():
    async def ticks():
        while True:
            yield {"now": datetime.datetime.now().isoformat()}   # dict: sent as JSON
            await asyncio.sleep(1)
    return EventSourceResponse(ticks())
```

```js
new EventSource("/clock").onmessage = (e) => console.log(JSON.parse(e.data));
```

Yield text, a dict or list (JSON), or a `ServerSentEvent(data, event=, id=, retry=)`.
A `: ping` comment is sent every 15 seconds (`ping=`, or `None`) so proxies keep
the connection open. When the browser closes the page, the generator is
cancelled and its `finally` runs, so release resources there. `Last-Event-ID`
is in `request.headers`.

`event` and `id` cannot contain line breaks (`ValueError`), and line breaks
inside `data` are split into separate `data:` lines: a value cannot forge fields
or events.

For any other stream use `StreamingResponse(iterator, media_type=...)`.
