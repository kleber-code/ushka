# Testing

`ushka.testing.TestClient` calls your app in-process, with the standard
library only (no `httpx`, no socket, no new dependency).

```python
# tests/test_signup.py
import pytest
from ushka.testing import TestClient
from app import app

async def test_signup_flow():
    async with TestClient(app) as client:          # startup hooks run here
        res = await client.post("/signup", data={"email": "ada@example.com"})
        assert res.status_code == 200
        me = await client.get("/me")               # the session cookie came along
        assert me.json()["email"] == "ada@example.com"
```

With `pytest-asyncio` (`asyncio_mode = "auto"`, or `@pytest.mark.asyncio`) the
test above runs as written.

## What it does

- **Lifespan.** `async with TestClient(app)` runs your `on_startup` hooks on
  entry and `on_shutdown` on exit. A failing startup hook raises
  `RuntimeError`. Without `async with` call `await client.startup()` and
  `await client.shutdown()` yourself.
- **Cookies.** Cookies the app sets are sent back on the next request, like a
  browser, so sessions and flash messages work. They are in `client.cookies`
  (a dict you can edit or `.clear()`). A cookie the app deletes is dropped.
- **Requests.** `get`, `post`, `put`, `patch`, `delete`, `head`, `options`, or
  `request(method, url, ...)`, all `await`ed, with:
  `params={"q": "x"}`, `json={...}`, `data={...}` (an HTML form),
  `files={"doc": ("a.txt", b"...")}` (multipart; `data` fields go along),
  `headers={...}`, `cookies={...}` and `follow_redirects=True`.
- **Responses.** `status_code`, `headers` (lower-case names), `text`,
  `content` (bytes), `json()`, `cookies` (what this response set), `ok`, and
  `header_list("set-cookie")` for a header that repeats.

## CSRF: script or browser

The [CSRF check](security.md#csrf) lets through a request with neither
`Origin` nor `Sec-Fetch-Site`, because it cannot come from a victim's browser.
`TestClient` is such a client by default, so your `POST` tests pass without
tokens. To test what a browser does, or an attack:

```python
async with TestClient(app, browser=True) as browser:      # same-origin browser
    assert (await browser.post("/transfer")).status_code == 200
    evil = await browser.post("/transfer", headers={"Sec-Fetch-Site": "cross-site"})
    assert evil.status_code == 403
```

`browser=True` adds `Sec-Fetch-Site: same-origin` and, for non-`GET`
requests, an `Origin` that matches the host. Headers you pass win.

## Why not `httpx.ASGITransport`?

`httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` works for plain
requests, but it **does not send the ASGI lifespan events**, so `on_startup`
hooks never run (a pool you open there will be missing) and `on_shutdown`
never fires. `TestClient` runs them. If you prefer `httpx`, start the hooks
yourself with `TestClient(app).startup()`, or use `async with TestClient(app)`
around your `httpx` calls.

## Replacing dependencies

Combine it with `app.dependency_overrides` (see
[Validation](validation.md#depends)):

```python
app.dependency_overrides[get_db] = fake_db
```

!!! note
    Streaming responses that never end (SSE) are read until the app finishes,
    so test them with a handler that stops, or call the generator directly.
