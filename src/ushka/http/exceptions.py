"""This module defines custom HTTP exception classes for the Ushka framework.

These exceptions correspond to specific HTTP status codes and are used to
interrupt the normal request flow and return an appropriate error response
to the client.
"""


class ContentToJsonParserFailed(Exception):
    """Raised when a response body cannot be converted to JSON."""


class HTTPError(Exception):
    """Base class for all HTTP-related exceptions in Ushka."""

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 400,
        message: str = "Bad Request",
    ) -> None:
        """Initializes the HTTPError.

        Parameters
        ----------
        template : str, optional
            The template file to render for the error page. Defaults to "error.html".
        status_code : int, optional
            The HTTP status code. Defaults to 400.
        message : str, optional
            The error message. Defaults to "Bad Request".
        """
        super().__init__(message)
        self.status_code = status_code
        self.template = template
        self.message = message


class HttpNotFound(HTTPError):
    """Exception raised for HTTP 404 Not Found errors."""

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 404,
        message: str = "Not Found",
    ) -> None:
        """Initializes the HttpNotFound error.

        Parameters
        ----------
        template : str, optional
            The template file to render for the error page. Defaults to "error.html".
        status_code : int, optional
            The HTTP status code. Defaults to 404.
        message : str, optional
            The error message. Defaults to "Not Found".
        """
        super().__init__(template, status_code, message)


class HTTPBadRequest(HTTPError):
    """Exception raised for HTTP 400 Bad Request errors."""

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 400,
        message: str = "Bad Request",
    ) -> None:
        """Initializes the HTTPBadRequest error.

        Parameters
        ----------
        template : str, optional
            The template file to render for the error page. Defaults to "error.html".
        status_code : int, optional
            The HTTP status code. Defaults to 400.
        message : str, optional
            The error message. Defaults to "Bad Request".
        """
        super().__init__(template, status_code, message)


class HTTPStaticServerNotFound(HttpNotFound):
    """Exception raised when a static file is not found or cannot be served.

    This is a specialized version of `HttpNotFound` for issues related
    to the static file server, such as file not found, path traversal
    attempts, or file access errors.
    """

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 404,
        message: str = "Static File Not Found",
    ) -> None:
        """Initializes the HTTPStaticServerNotFound error.

        Parameters
        ----------
        template : str, optional
            The template file to render for the error page. Defaults to "error.html".
        status_code : int, optional
            The HTTP status code. Defaults to 404.
        message : str, optional
            The error message. Defaults to "Static File Not Found".
        """
        super().__init__(template, status_code, message)


class HTTPPayloadTooLarge(HTTPError):
    """Exception raised for HTTP 413 Payload Too Large errors."""

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 413,
        message: str = "Payload Too Large",
    ) -> None:
        """Initializes the HTTPPayloadTooLarge error.

        Parameters
        ----------
        template : str, optional
            The template file to render for the error page. Defaults to "error.html".
        status_code : int, optional
            The HTTP status code. Defaults to 413.
        message : str, optional
            The error message. Defaults to "Payload Too Large".
        """
        super().__init__(template, status_code, message)


class HTTPMethodNotAllowed(HTTPError):
    """Exception raised for HTTP 405 Method Not Allowed errors."""

    def __init__(
        self,
        allowed: list[str] | None = None,
        template: str = "error.html",
        status_code: int = 405,
        message: str = "Method Not Allowed",
    ) -> None:
        """Initializes the HTTPMethodNotAllowed error.

        Parameters
        ----------
        allowed : list of str, optional
            Methods the path does accept; sent back in the `Allow` header.
        """
        super().__init__(template, status_code, message)
        self.allowed = sorted(allowed or [])


class HTTPForbidden(HTTPError):
    """Exception raised for HTTP 403 Forbidden errors."""

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 403,
        message: str = "Forbidden",
    ) -> None:
        super().__init__(template, status_code, message)


class HTTPRedirect(HTTPError):
    """Raised to redirect from anywhere, even deep inside a helper or dependency.

    Equivalent to ``return redirect(url, status_code, request)``, with one
    difference that matters: the redirect is built by the framework, which
    already knows the request, so cookies, session values and flash messages
    set before the ``raise`` are saved. Nothing else is saved on the way out:
    only what the handler explicitly changed.

    Raises `UnsafeValueError` straight away when `url` is `Untrusted` (validate
    it first with ``safe.url(url, allow=["/"], default="/")``).
    """

    def __init__(self, url: str, status_code: int = 302, *, query: dict | None = None, **params) -> None:
        from ushka.guard import check_redirect
        from ushka.http.urls import build_url

        if params or query:  # `{name}` slots and a query string, percent-encoded (see `redirect`)
            url = build_url(url, params, query)
        check_redirect(url)
        super().__init__("error.html", status_code, f"Redirect to {url}")
        self.url = url


class HTTPResponse(Exception):
    """Interrupts the request and answers with `response`, as it is.

    Raise it from a `Depends` function (or the handler) to stop early with any
    response, for example a JSON 401 for an API client::

        async def api_key(request: Request):
            if request.headers.get("x-api-key") != KEY:
                raise HTTPResponse(Response({"error": "no key"}, status_code=401))

    To redirect, raise `HTTPRedirect` instead: it also saves the session and
    flash messages. Unlike `HTTPError`, no error page is rendered.
    """

    def __init__(self, response) -> None:
        super().__init__(f"HTTP {getattr(response, 'status_code', '?')} response")
        self.response = response


def reject_nul(value):
    """Refuses a NUL byte (``\\x00``) anywhere in client text, with a 400.

    No form, query, JSON document or header has a legitimate use for it, and it
    breaks things later: PostgreSQL refuses it in text, C-based file APIs stop at
    it. Stopping it at the door is a 400 here instead of a 500 from the database.
    Returns `value` unchanged, so it can wrap an expression.
    """
    if isinstance(value, str):
        if "\x00" in value:
            raise HTTPBadRequest(message="Invalid character in request data")
    elif isinstance(value, dict):
        for k, v in value.items():
            reject_nul(k)
            reject_nul(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            reject_nul(v)
    return value
