"""
This module contains the core Ushka application class, responsible for handling HTTP requests,
managing routes, configuration, and running the ASGI server.
"""
# ushka/application.py

import inspect
import time
from asyncio import iscoroutinefunction
from datetime import datetime
from pathlib import Path
from types import FrameType
from urllib.parse import urlparse

import uvicorn
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ushka.core.config import Config
from ushka.core.error_handle import extract_frames, get_copy_paste_traceback
from ushka.http.exceptions import HttpNotFound, HTTPError
from ushka.http.request import Request
from ushka.http.response import Response
from ushka.core.log import LogLevelType, LogSystem
from ushka.routing.router import Router
from ushka.features.template import render
from ushka.features.static import server_static_files

# Global Rich Console
console = Console()


class Ushka:
    """
    The core Ushka application class.

    This class handles application setup, request routing, middleware integration,
    and server management. It acts as the central hub for the Ushka framework.
    """

    def __init__(self) -> None:
        """
        Initializes the Ushka application.

        Discovers the application path, initializes the router, loads configuration
        from 'ushka.toml', and sets up the application logger.
        """
        # Get the path of the file that instantiated Ushka
        frame: FrameType = inspect.currentframe().f_back  # noqa
        try:
            caller_file = frame.f_globals["__file__"]
            workdir = Path(caller_file).resolve().parent
        except (AttributeError, KeyError):
            # fallback
            workdir = Path.cwd()

        self.workdir = Path(workdir)

        self.logsystem = LogSystem()

        self.router = Router(self.logsystem, workdir)
        self.router.autodiscover()

        self.config = Config()
        self.config.load_from_file(self.workdir.joinpath("ushka.toml"))

        if self.config.get("STATIC_ENABLE"):
            static_url = self.config.get("STATIC_URL") + "/[path:filename]"
            self.router.add_route("GET", static_url, server_static_files)

    async def _process_request(self, request: Request):
        func, params = self.router.get_route(request)

        if callable(func) and params is not None:
            if iscoroutinefunction(func):
                result = await func(**params)
            else:
                result = func(**params)

            if isinstance(result, Response):
                return result
            return Response(result)

        is_router_empty = (
            not self.router.static_routes and not self.router.dynamic_routes
        )
        if is_router_empty:
            return Response(render("startup.html", {}), status_code=200)
        raise HttpNotFound()

    def _handle_http_error(self, exc: HTTPError):
        if self.config.get("APP_DEBUG"):
            app_route_urls = self.router.get_urls(with_host=False)
            # Quick parsing for debug page (splitting by " - ")
            available_urls = [tuple(url.split(" - ")) for url in app_route_urls]
        else:
            available_urls = []

        template = render(
            exc.template,
            {
                "message": exc.message,
                "status_code": exc.status_code,
                "available_urls": available_urls,
                "timestamp": datetime.now(),
            },
        )
        return Response(template, exc.status_code)

    def _handle_generic_error(self, exc: Exception):  # pylint: disable=broad-except
        frame_blocks = extract_frames(exc)
        copy_past_error = get_copy_paste_traceback(exc)
        self.logsystem.log.error(copy_past_error)
        if self.config.get("APP_DEBUG"):
            response = Response(
                render(
                    "debug_error.html",
                    {
                        "exception_type": repr(type(exc)),
                        "exception_message": str(exc),
                        "frames": frame_blocks,
                        "traceback_text": copy_past_error,
                        "framework_version": self.config.get("USHKA_VERSION"),
                    },
                ),
                500,
            )
        else:
            response = Response("Server Error", 500)
        return response

    async def handle_http_request(self, scope, receive, send):  # pylint: disable=unused-argument,unused-variable
        """
        Handles an incoming HTTP request, routes it to the appropriate function,
        and sends back the response.
        """
        request = Request(scope, receive)
        start_time = time.time()

        try:
            response = await self._process_request(request)

        except HTTPError as exc:
            response = self._handle_http_error(exc)

        except Exception as exc:  # pylint: disable=broad-except
            response = self._handle_generic_error(exc)

        process_time = (time.time() - start_time) * 1000
        self.logsystem.log_http(request, response, process_time)
        await response(send)

    async def handle_lifespan(self, receive, send):
        """
        Handles ASGI lifespan events (startup and shutdown).
        """
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
            return

    async def handle_asgi_call(self, scope, receive, send):
        """
        Dispatches incoming ASGI calls to the appropriate handler based on the scope type.
        """
        if scope["type"] == "http":
            await self.handle_http_request(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self.handle_lifespan(receive, send)
        else:
            response = Response("Not Supported", 501)
            await response(send)

    async def __call__(self, scope, receive, send):
        """
        The main entry point for the ASGI application.
        """
        await self.handle_asgi_call(scope, receive, send)

    def run(self, host="127.0.0.1", port=8000, log_level: LogLevelType = "INFO"):
        """
        Runs the Ushka application using Uvicorn.

        Displays a startup banner, mapped routes, and then starts the ASGI server.
        """
        version = self.config.get("USHKA_VERSION", "testing")

        banner_text = Text()
        banner_text.append("🐱 Ushka Framework ", style="bold orange3")
        banner_text.append(f"v{version}\n", style="dim white")
        banner_text.append("🚀 Server running at ", style="bold white")
        banner_text.append(f"http://{host}:{port}", style="underline bold blue")

        console.print(
            Panel(
                banner_text,
                border_style="orange3",
                expand=False,
                padding=(1, 2),
                style="on black",
            )
        )

        # 2. Beautiful Routes Table
        table = Table(
            title="Mapped Routes",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold blue",
            border_style="dim white",
            title_style="bold white",
        )
        table.add_column("Methods", style="bold orange3", width=15)
        table.add_column("Path", style="white")
        table.add_column("Url", style="blue")

        # 3. Parse and Display Routes
        # Expected format from router: "http://host:port/foo/bar - GET, POST"
        route_list = self.router.get_urls(host, port)

        if not route_list:
            table.add_row("No routes", "Check your routes/ folder")
        else:
            for url_str in route_list:
                parts = url_str.split(" - ")
                full_url = parts[0]
                methods = parts[1]

                parsed = urlparse(full_url)
                path = parsed.path if parsed.path else "/"

                full_url = full_url.replace("[", "_").replace("]", "_")

                table.add_row(methods, escape(path), escape(full_url))

        console.print(table)
        console.print("\n[dim italic white]Press Ctrl+C to stop me...[/]\n")

        if self.config.get("SERVER_USHKA_SUPPRESS_UVICORN"):
            uvicorn.run(
                self,
                host=host,
                port=port,
                log_config=self.logsystem.get_silent_uvicorn_config(level=log_level),
                lifespan="on",
            )
        else:
            uvicorn.run(
                self,
                host=host,
                port=port,
                lifespan="on",
            )

    def get(self, path: str):
        """
        Decorator to register a function as a GET route handler.
        """

        def wrapper(function):
            self.router.add_route("GET", path, function)
            return function

        return wrapper

    def post(self, path: str):
        """
        Decorator to register a function as a POST route handler.
        """

        def wrapper(function):
            self.router.add_route("POST", path, function)
            return function

        return wrapper

    def put(self, path: str):
        """Decorator to register a function as a PUT route handler.

        Args:
            path: The URL path for the route.

        Returns:
            The decorated function.
        """

        def wrapper(function):
            self.router.add_route("PUT", path, function)
            return function

        return wrapper

    def update(self, path: str):
        """
        Decorator to register a function as an UPDATE route handler.
        """

        def wrapper(function):
            self.router.add_route("UPDATE", path, function)
            return function

        return wrapper

    def head(self, path: str):
        """
        Decorator to register a function as a HEAD route handler.
        """

        def wrapper(function):
            self.router.add_route("HEAD", path, function)
            return function

        return wrapper

    def delete(self, path: str):
        """
        Decorator to register a function as a DELETE route handler.
        """

        def wrapper(function):
            self.router.add_route("DELETE", path, function)
            return function

        return wrapper
