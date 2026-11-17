"""This module defines the `Request` class for handling incoming HTTP requests."""

import json
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine, Dict
from urllib.parse import parse_qs

from ushka.guard import Untrusted, taint_deep
from ushka.http.cookies import Cookies
from ushka.http.exceptions import HTTPBadRequest, HTTPPayloadTooLarge
import ushka.http.proxy as proxy
from ushka.http.multipart import parse_multipart_asgi
from ushka.http.sessions import Session
from ushka.http.uploads import UploadFile

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
        #: Values captured from the URL (``[item_id]``); set by the router.
        self.path_params: Dict[str, Any] = {}
        self._cached_data: Dict[str, Any] = {}

        # Configs
        self.max_body_size_in_KB = int(
            self.app.config.get("limits_max_request_body_size_in_KB") or 2048
        )
        self.max_body_multipart_size_in_KB = int(
            self.app.config.get("limits_max_request_body_multipart_size_in_KB") or 51200
        )
        self._is_debug = bool(self.app.config.get("app_debug"))
        #: Whether client-supplied values are wrapped in `Untrusted` (Ushka Guard).
        self.taint_enabled = self.app.config.get("security_taint", True) is not False

    def _mark(self, value: Any, source: str) -> Any:
        """Wraps client-supplied data in `Untrusted` when the guard is on."""
        return taint_deep(value, source) if self.taint_enabled else value

    def _mark_mapping(self, data: Dict[str, Any], kind: str) -> Dict[str, Any]:
        if not self.taint_enabled:
            return data
        return {
            Untrusted(k, kind): taint_deep(v, f"{kind}:{k}") for k, v in data.items()
        }

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
            headers = {}
            for k, v in self.scope["headers"]:
                name = k.decode("latin-1")
                headers[name] = self._mark(v.decode("latin-1"), f"header:{name}")
            self._cached_data["headers"] = headers
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
            try:
                parsed = parse_qs(raw.decode(), max_num_fields=1000)
            except (UnicodeDecodeError, ValueError) as exc:
                raise HTTPBadRequest(message="Invalid query string") from exc
            self._cached_data["query"] = self._mark_mapping(
                {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}, "query"
            )
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
                header_value=cookie_header,
                secure_default=not self._is_debug,
                taint_values=self.taint_enabled,
            )
        return self._cached_data["cookies"]

    @property
    def session(self) -> Session:
        """Session is a property as it depends on the Cookie (Header), not the Body."""
        if "session" not in self._cached_data:
            # In debug mode Config generates a per-process key when none is set.
            secret = self.app.config.get("APP_SECRET_KEY")
            if not secret:
                raise RuntimeError(
                    "Sessions need a secret key. Set USHKA_APP_SECRET_KEY in the "
                    "environment or in .env (generate one with: "
                    'python -c "import secrets; print(secrets.token_urlsafe(48))").'
                )

            raw_session_value = self.cookies.get(Session.COOKIE_NAME)
            self._cached_data["session"] = Session(
                secret_key=secret,
                raw_cookie_value=raw_session_value,
                secure=not self._is_debug,
            )
        return self._cached_data["session"]

    # --- WHO IS CALLING (behind a reverse proxy) ---
    # `X-Forwarded-*` is believed only when the direct peer is listed in
    # `[security] trusted_proxies`; see `ushka.http.proxy` for the rules.

    @property
    def _proxies(self) -> "tuple[proxy.Network, ...]":
        return proxy.networks_from_config(self.app.config.get("security_trusted_proxies"))

    @property
    def client_ip(self) -> str | None:
        """The visitor's IP address, or ``None`` when it is unknown.

        Without ``[security] trusted_proxies`` this is the address of whoever
        connected, and ``X-Forwarded-For`` is ignored. When the connection
        comes from a trusted proxy, the header is read from the right and the
        first address that is not a trusted proxy is returned, so a forged
        left-most entry never wins. A malformed header falls back to the peer.

        It is a plain ``str`` (validated with ``ipaddress``), not ``Untrusted``:
        it can only be an IP address and never carries markup or SQL.
        """
        if "client_ip" not in self._cached_data:
            self._cached_data["client_ip"] = proxy.client_ip(self.scope, self._proxies)
        return self._cached_data["client_ip"]

    @property
    def scheme(self) -> str:
        """``"https"`` or ``"http"``, honouring ``X-Forwarded-Proto`` from a trusted proxy."""
        return proxy.forwarded_scheme(self.scope, self._proxies)

    @property
    def is_secure(self) -> bool:
        """True when the visitor reached the site over https (see `scheme`)."""
        return self.scheme == "https"

    @property
    def host(self) -> str:
        """The host the visitor asked for: ``X-Forwarded-Host`` from a trusted
        proxy, else the ``Host`` header (still `Untrusted`: the client wrote it)."""
        forwarded = proxy.forwarded_host(self.scope, self._proxies)
        return forwarded if forwarded is not None else self.headers.get("host", "")

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
                raise HTTPPayloadTooLarge(message="Request body too large")
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
        HTTPPayloadTooLarge
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

        total = 0
        limit = max(self.max_body_size_in_KB, self.max_body_multipart_size_in_KB) * 1024
        while True:
            message = await self._receive()
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                raise HTTPPayloadTooLarge(message="Request body too large")
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
        HTTPPayloadTooLarge
            If the request body size exceeds `max_body_size_in_KB`.
        UnicodeDecodeError
            If the request body cannot be decoded as UTF-8.
        """
        if "text" not in self._cached_data:
            body_bytes = await self.body()
            try:
                decoded = body_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPBadRequest(message="Request body is not valid UTF-8") from exc
            self._cached_data["text"] = self._mark(decoded, "body")
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
        HTTPPayloadTooLarge
            If the request body size exceeds `max_body_size_in_KB`.
        json.JSONDecodeError
            If the request body contains invalid JSON.
        """
        if "json" not in self._cached_data:
            body_data = await self.body()
            try:
                parsed = json.loads(body_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise HTTPBadRequest(message="Request body is not valid JSON") from exc
            self._cached_data["json"] = self._mark(parsed, "json")
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
        HTTPPayloadTooLarge
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
                self._cached_data["form"] = self._mark_mapping(form_data, "form")
                self._cached_data["files"] = files_data
            else:
                body = await self.body()
                try:
                    parsed = parse_qs(body.decode("utf-8"), max_num_fields=1000)
                except (UnicodeDecodeError, ValueError) as exc:
                    raise HTTPBadRequest(message="Invalid form data") from exc
                self._cached_data["form"] = self._mark_mapping(
                    {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}, "form"
                )
                self._cached_data["files"] = {}
        return self._cached_data["form"]

    async def files(self) -> Dict[str, UploadFile]:
        """Reads and returns the uploaded files, by form field name.

        This method implicitly calls `request.form()` if the body has not been
        parsed yet. (`form()` itself holds only the text fields.)

        Returns
        -------
        Dict[str, UploadFile]
            Field name to `UploadFile`. When a field was sent more than once
            (``<input type="file" multiple>``) this holds the last file; use
            `uploads` to get all of them. For code written against the old
            dictionaries, ``upload["filename"]`` still works.

        Raises
        ------
        HTTPPayloadTooLarge
            If the request body size exceeds `max_body_size_in_KB`.
        HTTPBadRequest
            If parsing multipart data fails (e.g., missing boundary).
        HTTPPayloadTooLarge
            If any uploaded file exceeds its configured size limit.
        """
        if "files" not in self._cached_data:
            await self.form()
        return self._cached_data["files"]

    async def uploads(self) -> Dict[str, list[UploadFile]]:
        """Like `files`, but every field maps to the list of all its files."""
        if "files" not in self._cached_data:
            await self.form()
        return self._cached_data.get("uploads", {})

    def _close_uploads(self) -> None:
        """Releases the temporary files of the request (the app calls this when done)."""
        for group in self._cached_data.get("uploads", {}).values():
            for upload in group:
                upload.close()
