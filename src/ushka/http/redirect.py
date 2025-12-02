from typing import TYPE_CHECKING, Optional

from ushka.http.response import Response

if TYPE_CHECKING:
    from ushka.http.request import Request


def redirect(
    to: str, status_code: int = 302, request: Optional["Request"] = None
) -> Response:
    """
    Returns a Response that forces an HTTP redirection.

    This function creates a Response object with the 'Location' header set to the
    target URL. It defaults to a 302 Found status code, which converts the HTTP
    method to GET in most cases.

    Args:
        to (str): The target URL. It can be an absolute path (e.g., "https://example.com")
                  or a relative path (e.g., "/login").
        status_code (int, optional): The HTTP status code. Defaults to 302.
                                     Use 307 if you need to preserve the HTTP method
                                     (e.g., POST redirects to POST).
        request (Request, optional): The current request object. Required if you need
                                     to persist pending session data or cookies
                                     before redirecting.

    Returns:
        Response: A response object configured for redirection.
    """
    # The 'Location' header is what actually triggers the browser redirect.
    headers = {"Location": to}

    return Response(
        body=b"",  # Redirects typically do not have a visible body.
        status_code=status_code,
        headers=headers,
        request=request,
    )
