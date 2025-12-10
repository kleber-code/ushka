"""This module defines the `Response` class for handling HTTP responses.

The `Response` class ensures correct formatting for ASGI compatibility and
automatically handles Cookie and Session persistence if a Request object is provided.
"""

import json
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ushka.core.exceptions import ContentToJsonParserFailed

if TYPE_CHECKING:
    from ushka.http.request import Request


class Response:
    """Represents an outgoing HTTP response."""

    def __init__(
        self,
        body: str | int | Dict | List | bytes = "",
        status_code: int = 200,
        headers: Dict[str, str] | None = None,
        media_type: str | None = None,
        request: Optional["Request"] = None,
    ) -> None:
        """Initializes a new Response object.

        Parameters
        ----------
        body : str, int, dict, list, or bytes, optional
            The content for the response body. Can be a string, integer,
            dictionary (will be JSON-encoded), list (will be JSON-encoded),
            or raw bytes. Defaults to an empty string.
        status_code : int, optional
            The HTTP status code for the response. Defaults to 200.
        headers : Dict[str, str], optional
            A dictionary of custom HTTP headers to include in the response.
            Defaults to `None`.
        media_type : str, optional
            The explicit MIME type for the response (e.g., "text/html", "application/json").
            If `None`, the media type is inferred from the `body` content.
        request : Request, optional
            An optional reference to the incoming `Request` object. If provided,
            it's used to automatically persist session data and cookies.
        """
        self.status_code = status_code
        self.headers = headers or {}
        self.media_type = media_type or "text/plain"
        self.request = request

        # Body Processing
        self._body = ""
        self._body_bytes = b""
        self.body = body  # Uses the setter to define the correct type

    async def __call__(self, send: Callable) -> None:
        """Makes the Response object an ASGI callable.

        This method is the entry point for ASGI servers to process the response.
        It constructs the HTTP response headers (including any modified cookies
        or session data) and sends the response body.

        Parameters
        ----------
        send : Callable
            The ASGI send channel callable, used to send response events
            (`http.response.start` and `http.response.body`) to the client.
        """

        # 1. Base Headers
        asgi_headers = [[b"content-type", self.media_type.encode("utf-8")]]

        # 2. User-defined Custom Headers
        for key, value in self.headers.items():
            key_bytes = key.lower().encode("latin-1")
            value_bytes = value.lower().encode("latin-1")
            asgi_headers.append([key_bytes, value_bytes])

        # 3. Infrastructure Headers (Cookies & Session)
        # The Response asks the Request if something has changed and needs to be saved.
        if self.request:
            # Normal Cookies
            if self.request.cookies.should_save:
                asgi_headers.extend(self.request.cookies.get_response_headers())

            # Session (which also generates Set-Cookie)
            if self.request.session.should_save:
                asgi_headers.extend(self.request.session.get_response_headers())

        # 4. Send Start
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": asgi_headers,
            }
        )

        # 5. Send Body
        body_to_send = (
            self._body_bytes if self._body_bytes else self._body.encode("utf-8")
        )
        await send({"type": "http.response.body", "body": body_to_send})

    @property
    def body(self) -> str:
        """The response body as a string for inspection."""
        if self._body:
            return self._body
        return self._body_bytes.decode("latin-1")

    @body.setter
    def body(self, value: str | int | Dict[Any, Any] | List[Any] | bytes):
        """Sets the response body content and attempts to infer the `media_type`.

        If the `media_type` has not been explicitly set, this setter will
        try to determine it based on the type of the `value` (e.g., "text/html"
        for strings containing HTML, "application/json" for dicts/lists).

        Parameters
        ----------
        value : str, int, dict, list, or bytes
            The content to set as the response body.

        Raises
        ------
        ContentToJsonParserFailed
            If `value` is a dictionary or list, and JSON serialization fails.
        """
        self._body = ""
        self._body_bytes = b""

        if isinstance(value, bytes):
            self._body_bytes = value
            # If the user has not defined media_type, do we keep the default or assume octet-stream?
            # For now, we keep the constructor's logic or text/plain if it's not HTML/JSON.

        elif isinstance(value, str):
            if self.media_type == "text/plain":  # Only infers if it's still the default
                if "<!DOCTYPE html>" in value or "<html" in value:
                    self.media_type = "text/html"
            self._body = value

        elif isinstance(value, (dict, list)):
            self.media_type = "application/json"
            try:
                self._body = json.dumps(value)
            except Exception as e:
                raise ContentToJsonParserFailed(str(e)) from e

        elif isinstance(value, int):
            self._body = str(value)
