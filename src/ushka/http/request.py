"""This module defines the `Request` class for handling incoming HTTP requests."""

import json
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine, Dict
from urllib.parse import parse_qs

from ushka.http.cookies import Cookies
from ushka.http.multipart import parse_multipart_asgi
from ushka.http.sessions import Session

if TYPE_CHECKING:
    from ushka.core.app import Ushka


class Request:
    def __init__(
        self,
        app: "Ushka",
        scope: dict,
        receive: Callable[[], Coroutine],
    ):
        self.app = app
        self.scope = scope
        self.method = str(scope["method"]).upper()
        self.path = str(scope["path"])

        self._receive = receive
        self._cached_data: Dict[str, Any] = {}

        # Configs
        self.max_body_size_in_KB = int(
            self.app.config.get("limits_max_request_body_size_in_KB") or 2048
        )
        self.max_body_multipart_size_in_KB = int(
            self.app.config.get("limits_max_request_body_multipart_size_in_KB") or 51200
        )
        self._is_debug = bool(self.app.config.get("app_debug"))

    # --- SYNCHRONOUS DATA (PROPERTIES) ---
    # This data is already in the connection 'scope', no I/O needed.

    @property
    def headers(self) -> Dict[str, str]:
        if "headers" not in self._cached_data:
            self._cached_data["headers"] = {
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in self.scope["headers"]
            }
        return self._cached_data["headers"]

    @property
    def query(self) -> Dict[str, Any]:
        if "query" not in self._cached_data:
            raw = self.scope.get("query_string", b"")
            parsed = parse_qs(raw.decode())
            self._cached_data["query"] = {
                k: v[0] if len(v) == 1 else v for k, v in parsed.items()
            }
        return self._cached_data["query"]

    @property
    def cookies(self) -> Cookies:
        if "cookies" not in self._cached_data:
            cookie_header = self.headers.get("cookie", "")
            self._cached_data["cookies"] = Cookies(
                header_value=cookie_header, secure_default=not self._is_debug
            )
        return self._cached_data["cookies"]

    @property
    def session(self) -> Session:
        """Session is a property as it depends on the Cookie (Header), not the Body."""
        if "session" not in self._cached_data:
            secret = self.app.config.get("APP_SECRET_KEY")
            if not secret:
                if self._is_debug:
                    self.app.log.warning(
                        "⚠️ APP_SECRET_KEY not defined! Sessions insecure."
                    )
                    secret = "insecure-debug-key"
                else:
                    raise RuntimeError("APP_SECRET_KEY required in production.")

            raw_session_value = self.cookies.get(Session.COOKIE_NAME)
            self._cached_data["session"] = Session(
                secret_key=secret,
                raw_cookie_value=raw_session_value,
                secure=not self._is_debug,
            )
        return self._cached_data["session"]

    # --- ASYNCHRONOUS DATA (METHODS) ---
    # This data requires reading the network stream via 'await'.

    async def _load_body(self) -> bytes:
        """Internal helper to drain the stream."""
        chunks = []
        size = 0
        while True:
            msg = await self._receive()
            chunk = msg.get("body", b"")
            size += len(chunk)
            if size > (self.max_body_size_in_KB * 1024):
                raise ValueError("Request body too large")
            chunks.append(chunk)
            if not msg.get("more_body", False):
                break
        self._cached_data["body"] = b"".join(chunks)
        return self._cached_data["body"]

    async def body(self) -> bytes:
        """Returns raw bytes. Usage: await request.body()"""
        if "body" not in self._cached_data:
            return await self._load_body()
        return self._cached_data["body"]

    async def stream(self) -> AsyncGenerator[bytes, None]:
        if "body" in self._cached_data:
            yield self._cached_data["body"]
            return

        while True:
            message = await self._receive()
            chunk = message.get("body", b"")
            if chunk:
                yield chunk
            if not message.get("more_body", False):
                break

    async def text(self) -> str:
        """Usage: await request.text()"""
        if "text" not in self._cached_data:
            body_bytes = await self.body()
            self._cached_data["text"] = body_bytes.decode("utf-8")
        return self._cached_data["text"]

    async def json(self) -> Any:
        """Usage: await request.json()"""
        if "json" not in self._cached_data:
            body_data = await self.body()
            self._cached_data["json"] = json.loads(body_data)
        return self._cached_data["json"]

    async def form(self) -> Dict[str, Any]:
        """Usage: await request.form()"""
        if "form" not in self._cached_data:
            content_type = self.headers.get("content-type", "")

            if "multipart/form-data" in content_type:
                form_data, files_data = await parse_multipart_asgi(
                    self, self.max_body_size_in_KB, self.max_body_multipart_size_in_KB
                )
                self._cached_data["form"] = form_data
                self._cached_data["files"] = files_data
            else:
                body = await self.body()
                parsed = parse_qs(body.decode("utf-8"))
                self._cached_data["form"] = {
                    k: v[0] if len(v) == 1 else v for k, v in parsed.items()
                }
                self._cached_data["files"] = {}
        return self._cached_data["form"]

    async def files(self) -> Dict[str, Any]:
        """Usage: await request.files()"""
        if "files" not in self._cached_data:
            await self.form()
        return self._cached_data["files"]
