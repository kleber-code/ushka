"""A test client for Ushka apps, on the standard library only.

::

    from ushka.testing import TestClient

    async def test_signup():
        async with TestClient(app) as client:          # runs on_startup / on_shutdown
            res = await client.post("/signup", data={"email": "a@b.c"})
            assert res.status_code == 200
            assert (await client.get("/me")).json()["email"] == "a@b.c"   # the cookie stayed

It speaks ASGI to the app directly (no socket), keeps cookies between requests
like a browser would, and runs the ASGI *lifespan*, which ``httpx.ASGITransport``
does not: ``on_startup`` hooks never fire there.

By default requests look like they come from a script (no ``Origin`` or
``Sec-Fetch-Site``), which the CSRF check lets through. ``TestClient(app, browser=True)``
makes every request look like a same-origin browser request instead; pass
``headers={"Sec-Fetch-Site": "cross-site"}`` to simulate an attack.
"""

from __future__ import annotations

import asyncio
import json as jsonlib
import uuid
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

__all__ = ["TestClient", "TestResponse"]


class TestResponse:
    """What a `TestClient` call returns."""

    __test__ = False  # not a pytest test class

    def __init__(self, status_code: int, raw_headers: list[tuple[str, str]], content: bytes, url: str) -> None:
        self.status_code = status_code
        self.raw_headers = raw_headers
        self.content = content
        self.url = url
        self.headers: dict[str, str] = {}
        for key, value in raw_headers:
            self.headers.setdefault(key.lower(), value)
        self.cookies: dict[str, str] = {}
        for key, value in raw_headers:
            if key.lower() == "set-cookie":
                jar: SimpleCookie = SimpleCookie()
                jar.load(value)
                self.cookies.update({name: morsel.value for name, morsel in jar.items()})

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self) -> Any:
        return jsonlib.loads(self.content)

    def header_list(self, name: str) -> list[str]:
        """Every value of a header that may repeat (``set-cookie``)."""
        return [v for k, v in self.raw_headers if k.lower() == name.lower()]

    def __repr__(self) -> str:
        return f"<TestResponse {self.status_code} {self.url}>"


class TestClient:
    """Calls an ASGI app in-process. Use it as ``async with TestClient(app) as client``."""

    __test__ = False

    def __init__(self, app: Any, *, base_url: str = "http://testserver", browser: bool = False) -> None:
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.browser = browser
        self.cookies: dict[str, str] = {}
        self._lifespan: asyncio.Task | None = None
        self._to_app: asyncio.Queue = asyncio.Queue()
        self._from_app: asyncio.Queue = asyncio.Queue()

    # --- lifespan ---

    async def __aenter__(self) -> TestClient:
        await self.startup()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.shutdown()

    async def _next_lifespan_message(self) -> dict | None:
        getter = asyncio.ensure_future(self._from_app.get())
        done, _ = await asyncio.wait({getter, self._lifespan}, return_when=asyncio.FIRST_COMPLETED)  # type: ignore[arg-type]
        if getter in done:
            return getter.result()
        getter.cancel()
        self._lifespan.result()  # re-raises if the app crashed
        return None  # the app ignores lifespan

    async def startup(self) -> None:
        """Runs the app's startup hooks (done for you by ``async with``)."""
        if self._lifespan is not None:
            return
        scope = {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}}
        self._lifespan = asyncio.ensure_future(self.app(scope, self._to_app.get, self._from_app.put))
        await self._to_app.put({"type": "lifespan.startup"})
        message = await self._next_lifespan_message()
        if message and message["type"] == "lifespan.startup.failed":
            await self._lifespan
            raise RuntimeError(f"startup failed: {message.get('message', '')}")

    async def shutdown(self) -> None:
        """Runs the app's shutdown hooks (done for you by ``async with``)."""
        if self._lifespan is None:
            return
        await self._to_app.put({"type": "lifespan.shutdown"})
        try:
            await self._next_lifespan_message()
            await self._lifespan
        finally:
            self._lifespan = None

    # --- requests ---

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: Any = None,
        data: dict | bytes | str | None = None,
        files: dict | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        follow_redirects: bool = False,
    ) -> TestResponse:
        """Sends one request and returns a `TestResponse`.

        `json` sends a JSON body; `data` a form (a dict becomes urlencoded, or
        multipart when `files` is given); `files` maps a field name to
        ``(filename, bytes)`` or ``(filename, bytes, content_type)``.
        """
        full = urljoin(self.base_url + "/", url) if not url.startswith(("http://", "https://")) else url
        for _ in range(10):
            response = await self._send(method, full, params, json, data, files, headers or {}, cookies or {})
            location = response.headers.get("location")
            if not (follow_redirects and response.status_code in (301, 302, 303, 307, 308) and location):
                return response
            full = urljoin(full, location)
            params = None
            if response.status_code in (301, 302, 303) and method.upper() != "HEAD":
                method, json, data, files = "GET", None, None, None
        raise RuntimeError("too many redirects")

    async def get(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("GET", url, **kw)

    async def head(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("HEAD", url, **kw)

    async def options(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("OPTIONS", url, **kw)

    async def post(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("POST", url, **kw)

    async def put(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("PUT", url, **kw)

    async def patch(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("PATCH", url, **kw)

    async def delete(self, url: str, **kw: Any) -> TestResponse:
        return await self.request("DELETE", url, **kw)

    async def _send(self, method, full, params, json, data, files, headers, cookies) -> TestResponse:
        parts = urlsplit(full)
        query = parts.query
        if params:
            query = "&".join(x for x in (query, urlencode(params, doseq=True)) if x)
        hdrs = {k.lower(): v for k, v in headers.items()}
        body = b""
        if json is not None:
            body = jsonlib.dumps(json).encode()
            hdrs.setdefault("content-type", "application/json")
        elif files:
            body, ctype = _multipart(data if isinstance(data, dict) else {}, files)
            hdrs.setdefault("content-type", ctype)
        elif isinstance(data, dict):
            body = urlencode(data, doseq=True).encode()
            hdrs.setdefault("content-type", "application/x-www-form-urlencoded")
        elif data is not None:
            body = data.encode() if isinstance(data, str) else data
        origin = f"{parts.scheme}://{parts.netloc}"
        hdrs.setdefault("host", parts.netloc)
        if self.browser:
            hdrs.setdefault("sec-fetch-site", "same-origin")
            if method.upper() not in ("GET", "HEAD"):
                hdrs.setdefault("origin", origin)
        jar = {**self.cookies, **cookies}
        if jar and "cookie" not in hdrs:
            hdrs["cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
        hdrs["content-length"] = str(len(body))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "path": parts.path or "/",
            "raw_path": (parts.path or "/").encode(),
            "query_string": query.encode(),
            "root_path": "",
            "scheme": parts.scheme,
            "headers": [(k.encode(), v.encode()) for k, v in hdrs.items()],
            "client": ("127.0.0.1", 50000),
            "server": (parts.hostname or "testserver", parts.port or (443 if parts.scheme == "https" else 80)),
        }
        sent = False
        messages: list[dict] = []

        async def receive() -> dict:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            messages.append(message)

        await self.app(scope, receive, send)
        start = next(m for m in messages if m["type"] == "http.response.start")
        raw = [(bytes(k).decode("latin-1"), bytes(v).decode("latin-1")) for k, v in start["headers"]]
        content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        response = TestResponse(start["status"], raw, content, full)
        self._store_cookies(raw)
        return response

    def _store_cookies(self, raw_headers: list[tuple[str, str]]) -> None:
        for key, value in raw_headers:
            if key.lower() != "set-cookie":
                continue
            jar: SimpleCookie = SimpleCookie()
            jar.load(value)
            for name, morsel in jar.items():
                max_age = morsel["max-age"]
                expired = (max_age != "" and int(max_age) <= 0) or morsel.value == ""
                if expired:
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = morsel.value


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = "ushka" + uuid.uuid4().hex
    out = b""
    for name, value in fields.items():
        for item in value if isinstance(value, (list, tuple)) else [value]:
            out += (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{item}\r\n'
            ).encode()
    for name, spec in files.items():
        filename, content, *rest = spec if isinstance(spec, (tuple, list)) else (name, spec)
        ctype = rest[0] if rest else "application/octet-stream"
        if isinstance(content, str):
            content = content.encode()
        out += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode() + content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"
