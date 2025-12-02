"""This module defines custom HTTP exception classes for the Ushka framework.

These exceptions correspond to specific HTTP status codes and are used to
interrupt the normal request flow and return an appropriate error response
to the client.
"""


class HTTPError(Exception):
    """Base class for all HTTP-related exceptions in Ushka.

    Attributes:
        status_code (int): The HTTP status code associated with the error.
        template (str): The name of the template to use for rendering the
            error page.
        message (str): A descriptive error message.
    """

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 400,
        message: str = "Bad Request",
    ) -> None:
        """Initializes the HTTPError.

        Args:
            template: The template file to render for the error page.
            status_code: The HTTP status code.
            message: The error message.
        """
        super().__init__(message)
        self.status_code = status_code
        self.template = template
        self.message = message


class HttpNotFound(HTTPError):
    """Raised when a requested resource could not be found (HTTP 404)."""

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 404,
        message: str = "Not Found",
    ) -> None:
        """Initializes the HttpNotFound error.

        Args:
            template: The template file to render for the error page.
            status_code: The HTTP status code (defaults to 404).
            message: The error message.
        """
        super().__init__(template, status_code, message)


class HTTPBadRequest(HTTPError):
    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 400,
        message: str = "Bad Request",
    ) -> None:
        super().__init__(template, status_code, message)


class HTTPStaticServerNotFound(HttpNotFound):
    """Raised when a requested static file could not be found (HTTP 404).

    This is a specialized version of `HttpNotFound` for use in the static
    file server.
    """

    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 404,
        message: str = "Static File Not Found",
    ) -> None:
        """Initializes the HttpStaticServerNotFound error.

        Args:
            template: The template file to render for the error page.
            status_code: The HTTP status code (defaults to 404).
            message: The error message.
        """
        super().__init__(template, status_code, message)


class HTTPPayloadTooLarge(HTTPError):
    def __init__(
        self,
        template: str = "error.html",
        status_code: int = 413,
        message: str = "Payload Too Large",
    ) -> None:
        super().__init__(template, status_code, message)
