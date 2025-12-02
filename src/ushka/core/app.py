# ushka/application.py
import inspect
import logging
from asyncio import iscoroutinefunction
from pathlib import Path
from types import FrameType

import uvicorn

from ushka.core.config import Config
from ushka.core.error_handler import ErrorHandler
from ushka.core.log import LogLevelType, get_log_config
from ushka.static import server_static_files
from ushka.templating import render
from ushka.http.exceptions import HttpNotFound
from ushka.http.request import Request
from ushka.http.response import Response
from .router import Router


class Ushka:
    """
    Core Application Class.
    Centralizes the ASGI lifecycle, routing, and execution.
    """

    def __init__(self) -> None:
        self._setup_workdir()
        self.log = logging.getLogger("ushka")

        self.config = Config()
        self.config.load_from_file(self.workdir.joinpath("ushka.toml"))

        self.router = Router(self.log, self.workdir)
        self.router.autodiscover()
        self.error_handler = ErrorHandler(self.config, self.log, self.router)

        if self.config.get("STATIC_ENABLE"):
            static_url = self.config.get("STATIC_URL", "/static") + "/[path:filename]"
            self.router.add_route("GET", static_url, server_static_files)

    def _setup_workdir(self):
        """Discovers the application's root directory safely."""
        try:
            frame: FrameType = inspect.currentframe().f_back.f_back  # type: ignore
            caller_file = frame.f_globals["__file__"]
            self.workdir = Path(caller_file).resolve().parent
        except (AttributeError, KeyError):
            self.workdir = Path.cwd()

    # --- ASGI Interface ---

    async def __call__(self, scope, receive, send):
        """Main entry point of the ASGI specification."""
        scope_type = scope["type"]

        if scope_type == "http":
            await self._handle_http(scope, receive, send)
        elif scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            # WebSocket or other protocols not yet supported
            response = Response("Not Supported", 501)
            await response(send)

    async def _handle_lifespan(self, scope, receive, send):
        """Manages startup and shutdown events."""
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                # Here you can add DB initialization logic, etc.
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                # Cleanup logic here
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _handle_http(self, scope, receive, send):
        """HTTP Request/Response cycle."""
        request = Request(self, scope, receive)
        try:
            response = await self._dispatch_request(request)
            response.request = request

        except Exception as e:
            response = await self.error_handler.handle_exception(e, request)

        await response(send)

    async def _dispatch_request(self, request: Request) -> Response:
        """Finds the route and executes the handler."""
        handler, params = self.router.get_route(request)

        if not handler:
            is_empty = not self.router.static_routes and not self.router.dynamic_routes
            if is_empty:
                return Response(await render(request, "startup.html", {}))
            raise HttpNotFound()

        if iscoroutinefunction(handler):
            result = await handler(**params)
        else:
            result = handler(**params)

        if isinstance(result, Response):
            return result
        return Response(result)

    # --- Server Helper ---

    def run(self, host="127.0.0.1", port=8000, log_level: LogLevelType = "INFO"):
        """Starts the Uvicorn server."""
        self._print_banner(host, port)

        uvicorn.run(
            self,
            host=host,
            port=port,
            log_config=get_log_config(level=log_level),
            lifespan="on",
        )

    def _print_banner(self, host, port):
        version = self.config.get("USHKA_VERSION", "dev")
        self.log.info(f"🐱 Ushka Framework v{version}")
        self.log.info(f"🚀 Server running at http://{host}:{port}")
        self.log.info("--- Mapped Routes ---")

        routes = self.router.get_urls(host, port)
        if not routes:
            self.log.info("  (No routes found)")
        else:
            for line in routes:
                self.log.info(f"  {line}")
        self.log.info("(Press Ctrl+C to stop)")

    # --- Public API Decorators ---

    def _add_route(self, method: str, path: str):
        """Helper to avoid code repetition in decorators."""

        def wrapper(func):
            self.router.add_route(method, path, func)
            return func

        return wrapper

    def get(self, path: str):
        return self._add_route("GET", path)

    def post(self, path: str):
        return self._add_route("POST", path)

    def put(self, path: str):
        return self._add_route("PUT", path)

    def patch(self, path: str):
        return self._add_route("PATCH", path)

    def delete(self, path: str):
        return self._add_route("DELETE", path)