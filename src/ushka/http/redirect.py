"""
This module provides a helper function for generating HTTP redirection responses.

It simplifies the creation of `Response` objects that instruct clients
to navigate to a different URL, supporting various HTTP status codes
for redirection.
"""

from typing import TYPE_CHECKING, Optional

from ushka.http.response import Response

if TYPE_CHECKING:
    from ushka.http.request import Request


def redirect(
    to: str, status_code: int = 302, request: Optional["Request"] = None
) -> Response:
    """Returns a Response that forces an HTTP redirection.

    This function creates a Response object with the 'Location' header set to the
    target URL. It defaults to a 302 Found status code, which converts the HTTP
    method to GET in most cases.

    Parameters
    ----------
    to : str
        The target URL. It can be an absolute path (e.g., "https://example.com")
        or a relative path (e.g., "/login").
    status_code : int, optional
        The HTTP status code for the redirection. Defaults to 302 (Found).
        Use 307 (Temporary Redirect) or 308 (Permanent Redirect) if you need
        to preserve the original HTTP method (e.g., POST redirects to POST).
    request : Request, optional
        The current request object. This is required if you need to persist
        pending session data or cookies before redirecting, as the `Response`
        object uses the `Request` to check for these changes. Defaults to `None`.

    Returns
    -------
    Response
        A response object configured for redirection with the specified
        'Location' header and status code.
    """  # The 'Location' header is what actually triggers the browser redirect.
    headers = {"Location": to}

    return Response(
        body=b"",  # Redirects typically do not have a visible body.
        status_code=status_code,
        headers=headers,
        request=request,
    )
