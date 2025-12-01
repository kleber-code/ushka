"""This module defines custom exception classes for the Ushka framework.

These exceptions are used throughout the framework to indicate various
error conditions, from routing and response handling to server-side issues.
"""


# pylint: disable=W2301
class ServerError(Exception):
    """Base exception for all server-related errors in Ushka."""


# Router
class RouterError(ServerError):
    """Base exception for errors related to the routing system."""


class InvalidArgument(RouterError):
    """Raised when an invalid argument is provided to a router function."""


# Response
class ResponseError(ServerError):
    """Base exception for errors that occur during response handling."""


class ContentToTextParserFailed(ResponseError):
    """Raised when content cannot be parsed or converted to a text string."""


class ContentToJsonParserFailed(ResponseError):
    """Raised when content fails to be serialized into a JSON string."""


class StatictServerError(ServerError):
    """Base exception for errors related to the static file server."""


class CantCompleteResponse(StatictServerError):
    """Raised when the server is unable to complete or send a response."""
