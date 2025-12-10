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
    """Represents an incoming HTTP request within the Ushka framework.

    This class provides a comprehensive interface to access various aspects
    of the HTTP request, including headers, query parameters, cookies, session
    data, and the request body (as raw bytes, text, JSON, form data, or files).

    It handles asynchronous reading of the request body and lazy loading
    of parsed data for efficiency.
    """

    def __init__(
        self,
        app: "Ushka",
        scope: dict,
        receive: Callable[[], Coroutine],
    ):
        """Initializes a new Request object.

        Parameters
        ----------
        app : Ushka
            The instance of the Ushka application.
        scope : dict
            The ASGI scope dictionary for the incoming request.
        receive : callable
            The ASGI receive channel callable for receiving request body chunks.
        """
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
        """The request headers as a dictionary.

        Headers are lazily decoded from the ASGI scope and cached upon first access.

        Returns
        -------
        Dict[str, str]
            A dictionary where keys are header names (lowercase) and values are
            header values.
        """
        if "headers" not in self._cached_data:
            self._cached_data["headers"] = {
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in self.scope["headers"]
            }
        return self._cached_data["headers"]

    @property
    def query(self) -> Dict[str, Any]:
        """The parsed query parameters from the request URL.

        Query parameters are lazily parsed from the ASGI scope and cached upon first access.
        Values are automatically unwrapped from lists if there's only one value.

        Returns
        -------
        Dict[str, Any]
            A dictionary where keys are query parameter names and values are
            either single strings or lists of strings.
        """
        if "query" not in self._cached_data:
            raw = self.scope.get("query_string", b"")
            parsed = parse_qs(raw.decode())
            self._cached_data["query"] = {
                k: v[0] if len(v) == 1 else v for k, v in parsed.items()
            }
        return self._cached_data["query"]

    @property
    def cookies(self) -> Cookies:
        """The parsed cookies from the request headers.

        Cookies are lazily parsed from the 'Cookie' header and wrapped in
        a `Cookies` object which also tracks changes for setting `Set-Cookie`
        headers in the response.

        Returns
        -------
        Cookies
            A `Cookies` object representing the request's cookies.
        """
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
        """Reads and returns the raw request body as bytes.

        The body is read asynchronously from the ASGI stream. Once read,
        it is cached for subsequent access within the same request.

        Returns
        -------
        bytes
            The full request body as raw bytes.

        Raises
        ------
        ValueError
            If the request body size exceeds `max_body_size_in_KB`.
        """
        if "body" not in self._cached_data:
            return await self._load_body()
        return self._cached_data["body"]

    async def stream(self) -> AsyncGenerator[bytes, None]:
        """Streams the raw request body as an asynchronous generator of bytes chunks.

        This allows processing large request bodies without loading the entire
        content into memory at once. If the body has already been read and cached
        by a previous call to `body()`, it will yield the cached content.

        Yields
        ------
        bytes
            Chunks of the request body.
        """
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
        """Reads and returns the request body as decoded text.

        The body is first read as bytes (if not already cached) and then decoded
        using UTF-8.

        Returns
        -------
        str
            The full request body as a string.

        Raises
        ------
        ValueError
            If the request body size exceeds `max_body_size_in_KB`.
        UnicodeDecodeError
            If the request body cannot be decoded as UTF-8.
        """
        if "text" not in self._cached_data:
            body_bytes = await self.body()
            self._cached_data["text"] = body_bytes.decode("utf-8")
        return self._cached_data["text"]

    async def json(self) -> Any:
        """Reads and returns the request body as parsed JSON.

        The body is first read as bytes (if not already cached) and then parsed
        as a JSON object.

        Returns
        -------
        Any
            The parsed JSON content of the request body. The type depends on
            the JSON structure (e.g., dict, list, str, int, etc.).

        Raises
        ------
        ValueError
            If the request body size exceeds `max_body_size_in_KB`.
        json.JSONDecodeError
            If the request body contains invalid JSON.
        """
        if "json" not in self._cached_data:
            body_data = await self.body()
            self._cached_data["json"] = json.loads(body_data)
        return self._cached_data["json"]

    async def form(self) -> Dict[str, Any]:
        """Reads and returns the request body as parsed form data.

        This method handles both `application/x-www-form-urlencoded` and
        `multipart/form-data` content types. For multipart data, it uses
        `parse_multipart_asgi` to extract fields and files.
        Files are stored separately and can be accessed via `request.files()`.

        Returns
        -------
        Dict[str, Any]
            A dictionary of form fields. For `application/x-www-form-urlencoded`,
            values are automatically unwrapped from lists if there's only one.

        Raises
        ------
        ValueError
            If the request body size exceeds `max_body_size_in_KB`.
        HTTPBadRequest
            If parsing multipart data fails (e.g., missing boundary).
        HTTPPayloadTooLarge
            If any form field or file in multipart data exceeds size limits.
        """
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
        """Reads and returns any uploaded files from the request body.

        This method implicitly calls `request.form()` if form data (including files)
        has not yet been parsed. It extracts file-specific information and
        `SpooledTemporaryFile` objects.

        Returns
        -------
        Dict[str, Any]
            A dictionary where keys are file input names and values are dictionaries
            containing 'filename', 'content_type', and a `SpooledTemporaryFile` object.

        Raises
        ------
        ValueError
            If the request body size exceeds `max_body_size_in_KB`.
        HTTPBadRequest
            If parsing multipart data fails (e.g., missing boundary).
        HTTPPayloadTooLarge
            If any uploaded file exceeds its configured size limit.
        """
        if "files" not in self._cached_data:
            await self.form()
        return self._cached_data["files"]
