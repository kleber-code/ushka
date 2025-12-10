"""
This module provides centralized exception handling for the Ushka framework.

It includes an `ErrorHandler` class to manage both expected HTTP errors (4xx)
and unexpected server errors (5xx), rendering appropriate error pages.
Additionally, it features a `_TracebackInspector` utility for safe and
detailed stack trace extraction during debugging.
"""

# ushka/core/error_handler.py
import linecache
import logging
import traceback
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any, Dict, List, Optional, Tuple

from ushka.core.config import Config
from ushka.templating import render
from ushka.http.exceptions import HTTPError
from ushka.http.request import Request
from ushka.http.response import Response
from .router import Router

DEFAULT_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "key",
    "auth",
    "credential",
    "pass",
    "cookie",
}


class _TracebackInspector:
    """Internal utility class to inspect stack traces and extract
    safe context (redacting sensitive variables).
    """

    @staticmethod
    def safe_repr(obj: Any, limit: int = 200) -> str:
        """Safely generates a string representation of an object, truncating it if necessary.

        Parameters
        ----------
        obj : Any
            The object to represent.
        limit : int, optional
            The maximum length of the representation string. If exceeded, the string is truncated.
            Default is 200.

        Returns
        -------
        str
            The safe string representation of the object.
        """
        try:
            value = repr(obj)
            if len(value) > limit:
                return f"{value[:limit]}... <len={len(value)}>"
            return value
        except Exception as e:
            return f"<{type(obj).__name__} repr_failed: {e}>"

    @classmethod
    def get_safe_locals(cls, frame: FrameType) -> Dict[str, str]:
        """Extracts local variables from a frame, redacting sensitive keys.

        Sensitive keys are determined by `DEFAULT_SENSITIVE_KEYS`.

        Parameters
        ----------
        frame : FrameType
            The frame object containing local variables (`f_locals`).

        Returns
        -------
        Dict[str, str]
            A dictionary mapping variable names to their safe string representations.
        """
        safe_vars = {}
        try:
            for k, v in frame.f_locals.items():
                if any(s in k.lower() for s in DEFAULT_SENSITIVE_KEYS):
                    safe_vars[k] = "******** (Redacted)"
                else:
                    safe_vars[k] = cls.safe_repr(v)
        except Exception as e:
            return {"<error>": f"Inspection failed: {e}"}
        return safe_vars

    @staticmethod
    def get_context_lines(
        filename: str, lineno: int, context: int = 7
    ) -> List[Tuple[int, str]]:
        """Retrieves surrounding lines of code from a file based on line number.

        Uses `linecache` for efficient file reading.

        Parameters
        ----------
        filename : str
            The path to the source file.
        lineno : int
            The central line number.
        context : int, optional
            The number of lines to retrieve before and after the central line.
            Default is 7.

        Returns
        -------
        List[Tuple[int, str]]
            A list of tuples, where each tuple contains (line_number, line_content).
        """
        lines = []
        start = max(1, lineno - context)
        end = lineno + context

        for i in range(start, end + 1):
            line = linecache.getline(filename, i)
            if line:
                lines.append((i, line.rstrip("\n")))
        return lines

    @classmethod
    def extract_frames(cls, exc: Exception) -> List[Dict[str, Any]]:
        """Extracts detailed information from the traceback associated with an exception.

        This includes file paths, line numbers, function names, code context,
        and safe local variables for each frame.

        Parameters
        ----------
        exc : Exception
            The exception object containing the traceback (`__traceback__`).

        Returns
        -------
        List[Dict[str, Any]]
            A list of dictionaries, where each dictionary represents a stack frame.
        """
        frame_blocks = []
        tb = exc.__traceback__

        while tb:
            frame = tb.tb_frame
            lineno = tb.tb_lineno
            code = frame.f_code
            filename = code.co_filename

            try:
                display_filename = str(Path(filename).relative_to(Path.cwd()))
            except ValueError:
                display_filename = filename

            frame_blocks.append(
                {
                    "filepath": display_filename,
                    "line": lineno,
                    "function_name": code.co_name,
                    "context": cls.get_context_lines(filename, lineno),
                    "locals": cls.get_safe_locals(frame),
                }
            )
            tb = tb.tb_next

        return frame_blocks


class ErrorHandler:
    """Manages global exceptions within the application lifecycle.

    This handler supports asynchronous rendering and provides detailed context
    (including the Request object) to error templates.
    """

    def __init__(
        self, config: Config, log: logging.Logger, router: Optional[Router] = None
    ) -> None:
        """Initializes the ErrorHandler.

        Parameters
        ----------
        config : Config
            The application configuration object.
        log : logging.Logger
            The logger instance used for recording server errors.
        router : Optional[Router], optional
            The application router, used primarily for listing available routes
            in debug mode (e.g., on 404 pages). Default is None.
        """
        self.config = config
        self.log = log
        self.router = router

    async def handle_exception(self, exc: Exception, request: Request) -> Response:
        """Single entry point for error handling.

        Delegates handling based on whether the exception is an expected HTTPError
        or an unexpected server error.

        Parameters
        ----------
        exc : Exception
            The exception that occurred.
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Response
            The HTTP response object containing the error page content.
        """

        if isinstance(exc, HTTPError):
            return await self._handle_http_error(exc, request)

        return await self._handle_server_error(exc, request)

    async def _handle_http_error(self, exc: HTTPError, request: Request) -> Response:
        """Handles expected errors (4xx status codes, e.g., 404, 405).

        Parameters
        ----------
        exc : HTTPError
            The HTTP exception raised.
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Response
            The HTTP response object with the appropriate status code and error content.
        """
        context = {
            "message": exc.message,
            "status_code": exc.status_code,
            "timestamp": datetime.now(),
            "available_urls": self._get_debug_routes()
            if self.config.get("APP_DEBUG")
            else [],
        }

        content = await render(request, exc.template, context)
        return Response(content, status_code=exc.status_code)

    async def _handle_server_error(self, exc: Exception, request: Request) -> Response:
        """Handles unexpected errors (500 Internal Server Error).

        Logs the full traceback and renders either the debug page or the
        generic production error page based on configuration.

        Parameters
        ----------
        exc : Exception
            The unexpected exception that occurred.
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Response
            The HTTP response object with status code 500.
        """

        traceback_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        self.log.error(f"Internal Server Error: {exc}\n{traceback_text}")

        if self.config.get("APP_DEBUG"):
            return await self._render_debug_page(exc, traceback_text, request)

        return await self._render_production_page(request)

    async def _render_debug_page(
        self, exc: Exception, tb_text: str, request: Request
    ) -> Response:
        """Renders the detailed debug error page (500) showing stack trace and context.

        This is only called if APP_DEBUG is True.

        Parameters
        ----------
        exc : Exception
            The exception object.
        tb_text : str
            The raw formatted traceback text.
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Response
            The HTTP response object with status code 500 and debug content.
        """
        frames = _TracebackInspector.extract_frames(exc)
        context = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "frames": frames,
            "traceback_text": tb_text,
            "framework_version": self.config.get("USHKA_VERSION", "unknown"),
        }
        content = await render(request, "debug_error.html", context)
        return Response(content, status_code=500)

    async def _render_production_page(self, request: Request) -> Response:
        """Renders the generic production error page (500).

        Parameters
        ----------
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Response
            The HTTP response object with status code 500 and generic content.
        """
        context = {
            "message": "Internal Server Error",
            "status_code": 500,
            "timestamp": datetime.now(),
        }
        content = await render(request, "error.html", context)
        return Response(content, status_code=500)

    def _get_debug_routes(self) -> List[Tuple[str, str]]:
        """Helper to list available routes for display on debug error screens (e.g., 404).

        Returns
        -------
        List[Tuple[str, str]]
            A list of (method, path) tuples representing registered routes,
            or an empty list if the router is unavailable or an error occurs.
        """
        if not self.router:
            return []
        try:
            raw_urls = self.router.get_urls(with_host=False)
            return [tuple(url.split(" - ", 1)) for url in raw_urls]
        except Exception:
            return []
