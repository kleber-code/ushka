"""This module defines the `Response` class for handling HTTP responses.

The `Response` class is a core component of the Ushka framework, providing a
flexible and easy-to-use interface for constructing HTTP responses. It supports
various content types, including HTML, JSON, and binary data, and ensures
correct formatting for ASGI compatibility.
"""

import json
from typing import Any, Dict, List, Callable

from ushka.core.exceptions import ContentToJsonParserFailed


class Response:
    """Represents an outgoing HTTP response.

    This class manages the response body, status code, headers, and media type.
    It can handle content as strings, bytes, dictionaries, or lists,
    automatically setting the appropriate `Content-Type` header and encoding
    the body for transmission.

    Attributes:
        status_code (int): The HTTP status code.
        headers (dict): A dictionary of response headers.
        media_type (str): The MIME type of the response.
    """

    def __init__(
        self,
        body: str | int | Dict | List | bytes = "",
        status_code: int = 200,
        media_type: str | None = None,
    ) -> None:
        """Initializes a new Response object.

        Args:
            body: The response body content. Can be a string, integer,
                dictionary, list, or bytes. Dictionaries and lists are
                automatically JSON-encoded.
            status_code: The HTTP status code for the response.
            media_type: The MIME type of the response (e.g., 'text/html').
                If `None`, it is inferred from the body type.
        """
        self._body = ""
        self._body_bytes = b""
        self.status_code = status_code
        self.headers = {}

        self.media_type = media_type if media_type is not None else "text/plain"
        self.body = body

    async def __call__(self, send: Callable) -> None:
        """Makes the Response object an ASGI callable.

        This method formats the response headers and body and sends them using
        the provided ASGI `send` function.

        Args:
            send: The ASGI send callable.
        """
        asgi_headers = [[b"content-type", self.media_type.encode("utf-8")]]

        for key, value in self.headers.items():
            key_bytes = key.lower().encode("latin-1")
            value_bytes = value.lower().encode("latin-1")

            asgi_headers.append([key_bytes, value_bytes])

        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": asgi_headers,
            }
        )
        body = self._body_bytes if self._body_bytes else self._body.encode("utf-8")
        await send({"type": "http.response.body", "body": body})

    @property
    def body(self) -> str:
        """The response body as a string.

        If the body was set as bytes, it is decoded using 'latin-1' for a
        string representation. This is primarily for inspection and debugging.
        The raw bytes are sent when the response is called.
        """
        if self._body:
            return self._body
        return self._body_bytes.decode("latin-1")

    @body.setter
    def body(self, value: str | int | Dict[Any, Any] | List[Any] | bytes):
        """Sets the response body.

        This setter handles different types of content:
        - `bytes`: Stored directly for binary responses.
        - `str`: Stored as a string. `media_type` is inferred.
        - `dict` or `list`: Serialized to a JSON string.

        Raises:
            ContentToJsonParserFailed: If serialization of a dict or list
                to JSON fails.
        """
        self._body = ""
        self._body_bytes = b""
        if isinstance(value, bytes):
            self._body_bytes = value

        elif isinstance(value, str):
            if "<!DOCTYPE html>" in value:
                self.media_type = "text/html"
            else:
                self.media_type = "text/plain"

            self._body = value

        elif isinstance(value, (Dict, List)):
            self.media_type = "application/json"
            try:
                self._body = json.dumps(value)
            except Exception as e:
                raise ContentToJsonParserFailed(str(e)) from e
