"""This module defines custom HTTP exception classes for the Ushka framework.

These exceptions correspond to specific HTTP status codes and are used to
interrupt the normal request flow and return an appropriate error response
to the client.
"""


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
