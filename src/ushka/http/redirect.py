"""
This module provides a helper function for generating HTTP redirection responses.

It simplifies the creation of `Response` objects that instruct clients
to navigate to a different URL, supporting various HTTP status codes
for redirection.
"""

from typing import TYPE_CHECKING, Optional

from ushka.guard import check_redirect
from ushka.http.response import Response
from ushka.http.urls import build_url

if TYPE_CHECKING:
    from ushka.http.request import Request


def redirect(
    to: str,
    status_code: int = 302,
    request: Optional["Request"] = None,
    *,
    query: dict | None = None,
    **params,
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

    query : dict, optional
        Query string parameters, percent-encoded for you.
    **params
        Values for the ``{name}`` slots of `to`, percent-encoded for you:
        ``redirect("/projects/{id}/", id=project_id, query={"tab": "files"})``.
        This is the way to put request data in a redirect: `to` is your literal and
        the parts cannot change the host or the path.

    Returns
    -------
    Response
        A response object configured for redirection with the specified
        'Location' header and status code.

    Raises
    ------
    UnsafeValueError
        If `to` is `Untrusted` (e.g. straight from ``request.query``). Validate
        it first with ``safe.url(to, allow=["/"], default="/")``.
    """
    if params or query:
        to = build_url(to, params, query)
    check_redirect(to)
    # The 'Location' header is what actually triggers the browser redirect.
    headers = {"Location": to}

    return Response(
        body=b"",  # Redirects typically do not have a visible body.
        status_code=status_code,
        headers=headers,
        request=request,
    )
