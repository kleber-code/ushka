"""This module defines custom exception classes for the Ushka framework.

These exceptions are used throughout the framework to indicate various
error conditions, from routing and response handling to server-side issues.
"""


# pylint: disable=W2301
class ServerError(Exception):
    """
    Base exception for all server-related errors in Ushka.
    """


# Router
class RouterError(ServerError):
    """
    Base exception for errors related to the routing system.
    """


class InvalidArgument(RouterError):
    """
    Exception raised when an invalid argument is provided during routing or processing.
    """


# Response
class ResponseError(ServerError):
    """
    Base exception for errors that occur during response handling.
    """


class ContentToTextParserFailed(ResponseError):
    """
    Exception raised when content conversion to text format fails.
    """


class ContentToJsonParserFailed(ResponseError):
    """
    Exception raised when content conversion to JSON format fails.
    """


class StatictServerError(ServerError):
    """
    Base exception for errors related to the static file server.
    """


class CantCompleteResponse(StatictServerError):
    """
    Exception raised when the static server is unable to complete the response.
    """
