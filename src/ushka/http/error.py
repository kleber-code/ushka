"""
This module provides a convenient helper function for raising HTTP errors
within the Ushka framework.

It allows for uniform handling of HTTP exceptions by constructing and
raising an `HTTPError` instance with specified status code, message, and
template.
"""

from ushka.http.exceptions import HTTPError
from typing import Optional


def raise_error(
    status_code: int = 404,
    message: Optional[str] = None,
    template: Optional[str] = None,
):
    """Raises an HTTPError with the specified status code and optional details.

    This function provides a convenient way to immediately interrupt the request
    processing and return an HTTP error response to the client. It wraps the
    provided arguments into an `HTTPError` instance and raises it.

    Parameters
    ----------
    status_code : int, optional
        The HTTP status code for the error (e.g., 404 for Not Found, 400 for Bad Request).
        Defaults to 404.
    message : str, optional
        A custom error message to be included in the HTTP error response.
        If `None`, the default message for the status code will be used.
    template : str, optional
        The name of the template file to render for the error page.
        If `None`, the default error template for the status code will be used.

    Raises
    ------
    HTTPError
        An instance of `HTTPError` with the given `status_code`, `message`,
        and `template`.
    """
    error = HTTPError(status_code=404)
    if template:
        error.template = template
    if message:
        error.message = message
    raise error
