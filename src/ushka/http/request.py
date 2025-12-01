"""This module defines the `Request` class for handling incoming HTTP requests.

The `Request` class encapsulates the ASGI scope and receive stream, providing a
convenient, high-level interface for accessing request details such as
headers, query parameters, and the request body in various formats (e.g.,
bytes, text, JSON, form data).
"""

import json
from typing import Any, Callable, Coroutine, Dict
from urllib.parse import parse_qs

MAX_BODY = int(2.5 * 1024 * 1024)  # 2.5 MB


class Request:
    """Represents an incoming HTTP request.

    This class provides convenient access to request attributes like headers,
    query parameters, and the body. It lazily loads and caches properties to
    avoid redundant processing.

    Attributes:
        scope (dict): The raw ASGI scope dictionary.
        method (str): The HTTP method of the request (e.g., 'GET', 'POST').
        path (str): The URL path of the request.
    """

    def __init__(self, scope: dict, receive: Callable[[], Coroutine]):
        """Initializes the Request object.

        Args:
            scope: The ASGI scope dictionary for the request.
            receive: The ASGI receive callable to read body data.
        """
        self.scope = scope
        self.method = str(scope["method"]).upper()
        self.path = str(scope["path"])

        self._receive = receive
        self._cached_data: Dict[str, Any] = {}

    @property
    def headers(self) -> Dict[str, str]:
        """The request headers as a case-insensitive dictionary."""
        if "headers" not in self._cached_data:
            self._cached_data["headers"] = {
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in self.scope["headers"]
            }
        return self._cached_data["headers"]

    @property
    def query(self) -> Dict[str, Any]:
        """The parsed query parameters from the URL as a dictionary."""
        if "query" not in self._cached_data:
            raw = self.scope.get("query_string", b"")
            parsed = parse_qs(raw.decode())
            self._cached_data["query"] = {
                k: v[0] if len(v) == 1 else v for k, v in parsed.items()
            }
        return self._cached_data["query"]

    async def _load_body(self) -> bytes:
        """Loads and caches the request body from the ASGI receive stream.

        Raises:
            ValueError: If the body size exceeds the `MAX_BODY` limit.
        """
        chunks = []
        size = 0
        while True:
            msg = await self._receive()
            chunk = msg.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY:
                raise ValueError("Request body too large")
            chunks.append(chunk)
            if not msg.get("more_body", False):
                break
        self._cached_data["body"] = b"".join(chunks)
        return self._cached_data["body"]

    @property
    async def body(self) -> bytes:
        """The raw request body as bytes.

        This property is loaded asynchronously from the request stream upon
        first access and then cached.
        """
        if "body" not in self._cached_data:
            return await self._load_body()
        return self._cached_data["body"]

    @property
    async def text(self) -> str:
        """The request body decoded as a string (using UTF-8)."""
        if "text" not in self._cached_data:
            self._cached_data["text"] = (await self.body).decode()
        return self._cached_data["text"]

    @property
    async def json(self) -> Any:
        """The request body parsed as JSON."""
        if "json" not in self._cached_data:
            body_data = await self.body
            self._cached_data["json"] = json.loads(body_data)
        return self._cached_data["json"]

    @property
    async def form(self) -> Dict[str, Any]:
        """The request body parsed as form data."""
        if "form" not in self._cached_data:
            body = await self.body
            parsed = parse_qs(body.decode())
            self._cached_data["form"] = {
                k: v[0] if len(v) == 1 else v for k, v in parsed.items()
            }
        return self._cached_data["form"]
