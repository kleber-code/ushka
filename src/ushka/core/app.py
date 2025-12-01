# ushka/application.py

import inspect
import logging
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
from ushka.http.exceptions import HTTP_NotFound, HTTPError
from ushka.http.request import Request
from ushka.http.response import Response
from ushka.core.log import get_silent_uvicorn_config, AVAILABLE_LOG_LEVELS_TYPE
from ushka.routing.router import Router
from ushka.features.template import render

# Global Rich Console
console = Console()


class Ushka:
    def __init__(self) -> None:
        # Get the path of the file that instantiated Ushka
        frame: FrameType = inspect.currentframe().f_back  # noqa
        try:
            caller_file = frame.f_globals["__file__"]
            app_path = Path(caller_file).resolve().parent
        except (AttributeError, KeyError):
            # fallback
            app_path = Path.cwd()

        self.app_path = Path(app_path)
        self.router = Router(app_path)
        self.router.autodiscover()

        self.config = Config()
        self.config.load_from_file(self.app_path.joinpath("ushka.toml"))

        # Use the "ushka" logger defined in the silent config
        self.log = logging.getLogger("ushka")

    async def handle_http_request(self, scope, receive, send):
        request = Request(scope, receive)
        start_time = time.time()

        func, params = self.router.get_route(request)

        try:
            if callable(func) and params is not None:
                if iscoroutinefunction(func):
                    result = await func(**params)
                else:
                    result = func(**params)
                response = Response(result)
            else:
                # "I'm alive" page logic
                is_router_empty = (
                    not self.router.static_routes and not self.router.dynamic_routes
                )
                if is_router_empty:
                    response = Response(render("startup.html", {}), status_code=200)
                else:
                    raise HTTP_NotFound()

        except HTTPError as exc:
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
            response = Response(template, exc.status_code)

        except Exception as exc:
            frame_blocks = extract_frames(exc)
            copy_past_error = get_copy_paste_traceback(exc)
            self.log.error(copy_past_error)
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

        # --- CUSTOM USHKA LOGGING ---
        process_time = (time.time() - start_time) * 1000
        status_code = int(response.status_code)

        if status_code >= 500:
            status_color = "red"
            icon = "🔥"
            self.log.error(
                f"{icon} [bold blue]{escape(request.method)}[/] "
                f"[white]{escape(request.path)}[/] "
                f"[bold {status_color}]{status_code}[/] "
                f"[dim]in {process_time:.2f}ms[/]"
            )
        elif status_code >= 400:
            status_color = "yellow"
            icon = "⚠️"
            self.log.warning(
                f"{icon} [bold blue]{escape(request.method)}[/] "
                f"[white]{escape(request.path)}[/] "
                f"[bold {status_color}]{status_code}[/] "
                f"[dim]in {process_time:.2f}ms[/]"
            )
        elif status_code >= 300:
            status_color = "cyan"
            icon = "🚀"
            self.log.info(
                f"{icon} [bold blue]{escape(request.method)}[/] "
                f"[white]{escape(request.path)}[/] "
                f"[bold {status_color}]{status_code}[/] "
                f"[dim]in {process_time:.2f}ms[/]"
            )
        else:  # < 300
            status_color = "green"
            icon = "✅"
            self.log.info(
                f"{icon} [bold blue]{escape(request.method)}[/] "
                f"[white]{escape(request.path)}[/] "
                f"[bold {status_color}]{status_code}[/] "
                f"[dim]in {process_time:.2f}ms[/]"
            )
        await response(send)

    async def handle_lifespan(self, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
            return

    async def handle_asgi_call(self, scope, receive, send):
        if scope["type"] == "http":
            await self.handle_http_request(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self.handle_lifespan(receive, send)
        else:
            response = Response("Not Supported", 501)
            await response(send)

    async def __call__(self, scope, receive, send):
        await self.handle_asgi_call(scope, receive, send)

    def run(
        self, host="127.0.0.1", port=8000, log_level: AVAILABLE_LOG_LEVELS_TYPE = "INFO"
    ):
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
                log_config=get_silent_uvicorn_config(level=log_level),
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
        def wrapper(function):
            self.router.add_route("GET", path, function)
            return function

        return wrapper

    def post(self, path: str):
        def wrapper(function):
            self.router.add_route("POST", path, function)
            return function

        return wrapper

    def put(self, path: str):
        def wrapper(function):
            self.router.add_route("PUT", path, function)
            return function

        return wrapper

    def update(self, path: str):
        def wrapper(function):
            self.router.add_route("UPDATE", path, function)
            return function

        return wrapper

    def head(self, path: str):
        def wrapper(function):
            self.router.add_route("HEAD", path, function)
            return function

        return wrapper

    def delete(self, path: str):
        def wrapper(function):
            self.router.add_route("DELETE", path, function)
            return function

        return wrapper
