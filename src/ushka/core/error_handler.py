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
    """
    Internal utility class to inspect stack traces and extract
    safe context (redacting sensitive variables).
    """

    @staticmethod
    def safe_repr(obj: Any, limit: int = 200) -> str:
        try:
            value = repr(obj)
            if len(value) > limit:
                return f"{value[:limit]}... <len={len(value)}>"
            return value
        except Exception as e:
            return f"<{type(obj).__name__} repr_failed: {e}>"

    @classmethod
    def get_safe_locals(cls, frame: FrameType) -> Dict[str, str]:
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
    """
    Manages global exceptions.
    Refactored to support Async Render and pass the Request to the Template.
    """

    def __init__(
        self, config: Config, log: logging.Logger, router: Optional[Router] = None
    ) -> None:
        self.config = config
        self.log = log
        self.router = router

    async def handle_exception(self, exc: Exception, request: Request) -> Response:
        """Single entry point for error handling."""

        if isinstance(exc, HTTPError):
            return await self._handle_http_error(exc, request)

        return await self._handle_server_error(exc, request)

    async def _handle_http_error(self, exc: HTTPError, request: Request) -> Response:
        """Handles expected errors (404, 405, etc)."""
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
        """Handles unexpected errors (500)."""

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
        context = {
            "message": "Internal Server Error",
            "status_code": 500,
            "timestamp": datetime.now(),
        }
        content = await render(request, "error.html", context)
        return Response(content, status_code=500)

    def _get_debug_routes(self) -> List[Tuple[str, str]]:
        """Helper to list routes on the 404 screen in debug mode."""
        if not self.router:
            return []
        try:
            raw_urls = self.router.get_urls(with_host=False)
            return [tuple(url.split(" - ", 1)) for url in raw_urls]
        except Exception:
            return []
