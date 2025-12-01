"""This package provides core HTTP components for the Ushka framework.

It exports the `Request` and `Response` classes, which are fundamental for
handling incoming requests and constructing outgoing responses in an Ushka
application.
"""

from ushka.http.request import Request
from ushka.http.response import Response

__all__ = ["Request", "Response"]
