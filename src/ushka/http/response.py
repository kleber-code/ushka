"""This module defines the `Response` class for handling HTTP responses.

The `Response` class ensures correct formatting for ASGI compatibility and
automatically handles Cookie and Session persistence if a Request object is provided.
"""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

from ushka.guard import check_html, is_template
from ushka.guard.templates import html as render_template_html
from ushka.http.exceptions import ContentToJsonParserFailed

if TYPE_CHECKING:
    from ushka.http.request import Request

_MARKUP_TYPES = {"text/html", "application/xhtml+xml", "image/svg+xml", "text/xml"}


class Response:
    """Represents an outgoing HTTP response."""

    def __init__(
        self,
        body: str | int | dict | list | bytes = "",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
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
        #: Set for HEAD requests: headers are sent, the body is not.
        self.head_only = False
        #: When False, cookie and session changes made during the request are
        #: not sent. Unexpected errors (500) set it: a crash saves nothing.
        self.persist = True

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
        # A Content-Type set in `headers` replaces media_type (never two headers).
        custom_type = next(
            (v for k, v in self.headers.items() if k.lower() == "content-type"), None
        )
        media_type = custom_type or self.media_type
        if (media_type.startswith("text/") or media_type == "application/json") and "charset" not in media_type:
            media_type += "; charset=utf-8"
        asgi_headers = [[b"content-type", media_type.encode("latin-1")]]

        # 2. User-defined Custom Headers
        for key, value in self.headers.items():
            if key.lower() == "content-type":
                continue
            # Header names are case-insensitive, values are NOT: lowercasing
            # them corrupted Location URLs, tokens and signed values.
            # CR/LF would allow response splitting / header injection.
            if any(c in key + value for c in "\r\n\x00"):
                raise ValueError(f"Invalid character in header {key!r}")
            key_bytes = key.lower().encode("latin-1")
            value_bytes = value.encode("latin-1")
            asgi_headers.append([key_bytes, value_bytes])

        # A known size lets the server skip chunked encoding, and lets clients,
        # proxies and HEAD requests know the length. Not for bodies that
        # cannot have one (1xx, 204, 304) or that stream.
        length = self._content_length()
        if (
            length is not None
            and self.status_code >= 200
            and self.status_code not in (204, 304)
            and not any(k.lower() == "content-length" for k in self.headers)
        ):
            asgi_headers.append([b"content-length", str(length).encode()])

        # 3. Infrastructure Headers (Cookies & Session)
        # The Response asks the Request if something has changed and needs to be saved.
        # Only what the handler actually touched: reading `request.session`
        # here would demand a secret key from apps that never use sessions.
        if self.request and self.persist:
            touched = self.request._cached_data
            cookies = touched.get("cookies")
            if cookies is not None and cookies.should_save:
                asgi_headers.extend(cookies.get_response_headers())

            session = touched.get("session")
            commit = getattr(session, "commit", None)
            if commit is not None:
                await commit()  # server-side sessions are written to their store
            if session is not None and session.should_save:
                asgi_headers.extend(session.get_response_headers())

        # 4. Send Start
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": asgi_headers,
            }
        )

        await self._send_body(send)

    def _content_length(self) -> int | None:
        """Size of the body in bytes, or None when it is not known up front."""
        return len(self._body_bytes if self._body_bytes else self._body.encode("utf-8"))

    async def _send_body(self, send: Callable) -> None:
        body_to_send = (
            self._body_bytes if self._body_bytes else self._body.encode("utf-8")
        )
        await send(
            {"type": "http.response.body", "body": b"" if self.head_only else body_to_send}
        )

    @property
    def body(self) -> str:
        """The response body as a string for inspection."""
        if self._body:
            return self._body
        return self._body_bytes.decode("latin-1")

    @body.setter
    def body(self, value: str | int | dict[Any, Any] | list[Any] | bytes):
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

        # t-string (Python 3.14+): HTML safe by construction.
        if is_template(value):
            value = render_template_html(value)
            if self.media_type == "text/plain":
                self.media_type = "text/html"

        if isinstance(value, bytes):
            self._body_bytes = value
            # If the user has not defined media_type, do we keep the default or assume octet-stream?
            # For now, we keep the constructor's logic or text/plain if it's not HTML/JSON.

        elif isinstance(value, str):
            if self.media_type == "text/plain":  # Only infers if it's still the default
                if "<!DOCTYPE html>" in value or "<html" in value:
                    self.media_type = "text/html"
            # Ushka Guard: untrusted text must not be served as markup.
            if self.media_type.split(";")[0].strip() in _MARKUP_TYPES:
                check_html(value)
            self._body = value

        elif isinstance(value, (dict, list)):
            self.media_type = "application/json"
            try:
                self._body = json.dumps(value)
            except Exception as e:
                raise ContentToJsonParserFailed(str(e)) from e

        elif isinstance(value, (bool, float)) or value is None:
            # JSON scalars: `true`, `1.5`, `null`.
            self.media_type = "application/json"
            self._body = json.dumps(value)

        elif isinstance(value, int):
            self._body = str(value)

        else:
            raise TypeError(
                f"Cannot use {type(value).__name__} as a response body. Return str, "
                "bytes, int, float, bool, None, dict, list, a t-string or a Response; "
                "for a status code return (body, status)."
            )
