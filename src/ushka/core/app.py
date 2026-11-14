"""
This module defines the core `Ushka` application class, which serves as the
central entry point for handling ASGI requests, managing routing,
configuration, and error handling within the framework.
"""

# ushka/application.py
import inspect
import logging
from pathlib import Path
from types import FrameType

import uvicorn

from ushka.core.config import Config
from ushka.core.error_handler import ErrorHandler
from ushka.core.log import LogLevelType, get_log_config, setup_logging
from ushka.http.exceptions import HTTPMethodNotAllowed, HttpNotFound
from ushka.http.request import Request
from ushka.http.response import Response
from ushka.http.redirect import redirect
from ushka.static import DEFAULT_CACHE_CONTROL, file_response, resolve_in, server_static_files
from ushka.templating import render
from ushka.templating.engine import engine as template_engine

from .router import Router


class Ushka:
    """Core Application Class.

    Centralizes the ASGI lifecycle, routing, and execution.

    Attributes
    ----------
    log : logging.Logger
        The main application logger.
    config : Config
        Application configuration object.
    router : Router
        The URL router responsible for dispatching requests.
    error_handler : ErrorHandler
        Handles exceptions raised during request processing.
    workdir : Path
        The root directory of the application.
    """

    def __init__(self) -> None:
        """Initializes the Ushka application.

        Sets up the application's working directory, loads configuration from
        `ushka.toml`, and initializes core components such as logging,
        routing, and error handling. It also registers static file serving
        routes if enabled in the application's configuration.

        Parameters
        ----------
        self : Ushka
            The instance of the Ushka application.
        """
        self._setup_workdir()
        self.log = logging.getLogger("ushka")

        self.config = Config(self.workdir).set_workdir(self.workdir)
        self.config.load_from_file()

        # Templates are looked up next to the app, not in whatever directory
        # the process happened to start in.
        template_engine.set_project_dir(self.workdir / "templates")

        self._startup: list = []
        self._shutdown: list = []

        self.router = Router(self.log, self.workdir)
        if self.config.get("APP_AUTO_DISCOVER", True):
            self.router.autodiscover()
        self.error_handler = ErrorHandler(self.config, self.log, self.router)

        if self.config.get("STATIC_ENABLE"):
            static_url = self.config.get("STATIC_URL", "/static") + "/[path:filename]"
            self.router.add_route("GET", static_url, server_static_files)

    def _setup_workdir(self):
        """Discovers the application's root directory safely.

        This attempts to find the directory where the Ushka instance was created.
        If detection fails (e.g., in interactive environments), it defaults to
        the current working directory.

        Sets
        ----
        self.workdir : Path
            The determined root directory of the application.
        """
        try:
            frame: FrameType = inspect.currentframe().f_back.f_back  # type: ignore
            caller_file = frame.f_globals["__file__"]
            self.workdir = Path(caller_file).resolve().parent
        except (AttributeError, KeyError):
            self.workdir = Path.cwd()

    # --- ASGI Interface ---

    async def __call__(self, scope, receive, send):
        """Main entry point of the ASGI specification.

        Delegates handling based on the scope type (http, lifespan, etc.).

        Parameters
        ----------
        scope : dict
            The ASGI scope dictionary.
        receive : callable
            The ASGI receive channel callable.
        send : callable
            The ASGI send channel callable.
        """
        scope_type = scope["type"]

        if scope_type == "http":
            await self._handle_http(scope, receive, send)
        elif scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        elif scope_type == "websocket":
            # Not supported yet: refuse the handshake the way the protocol expects.
            await receive()
            await send({"type": "websocket.close", "code": 1000})

    async def _handle_lifespan(self, scope, receive, send):
        """Manages startup and shutdown events according to the ASGI lifespan protocol.

        Parameters
        ----------
        scope : dict
            The ASGI scope dictionary.
        receive : callable
            The ASGI receive channel callable.
        send : callable
            The ASGI send channel callable.
        """
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    for hook in self._startup:
                        await _maybe_await(hook())
                except Exception as exc:  # report it instead of hanging the server
                    self.log.exception("Startup hook failed")
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                for hook in reversed(self._shutdown):
                    try:
                        await _maybe_await(hook())
                    except Exception:
                        self.log.exception("Shutdown hook failed")
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _handle_http(self, scope, receive, send):
        """Handles the full HTTP Request/Response cycle.

        This involves creating the Request object, dispatching it, handling
        any exceptions via the ErrorHandler, and sending the final Response.

        Parameters
        ----------
        scope : dict
            The ASGI scope dictionary for the HTTP request.
        receive : callable
            The ASGI receive channel callable.
        send : callable
            The ASGI send channel callable.
        """
        request = Request(self, scope, receive)
        try:
            response = await self._dispatch_request(request)
        except Exception as e:
            try:
                response = await self.error_handler.handle_exception(e, request)
            except Exception:
                # The error page itself failed: never leave the client hanging.
                self.log.exception("Error handler failed")
                response = Response("Internal Server Error", 500)
        # Lets the response persist cookie/session changes, even on errors.
        response.request = request

        if request.method == "HEAD":
            response.head_only = True
        await response(send)

    async def _dispatch_request(self, request: Request) -> Response:
        """Finds the appropriate route handler and executes it.

        If no handler is found, it raises HttpNotFound, unless the application
        is empty, in which case it returns a startup page.

        Parameters
        ----------
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Response
            The response generated by the route handler.

        Raises
        ------
        HttpNotFound
            If no matching route is found and the application is not empty.
        """
        handler, params = self.router.get_route(request)

        if not handler:
            is_empty = not self.router.static_routes and not self.router.dynamic_routes
            if is_empty:
                return Response(await render(request, "startup.html", {}))
            allowed = self.router.allowed_methods(request.path)
            if allowed:
                raise HTTPMethodNotAllowed(allowed)
            raise HttpNotFound()

        if inspect.iscoroutinefunction(handler):
            result = await handler(**params)
        else:
            result = handler(**params)

        return _to_response(result)

    # --- Server Helper ---

    def run(self, host: str = "", port: int = 0, log_level: LogLevelType = "INFO"):
        """Starts the Uvicorn server, running the Ushka application instance.

        Parameters
        ----------
        host : str, optional
            The host IP address to bind to. (Default is "127.0.0.1").
        port : int, optional
            The port number to listen on. (Default is 8000).
        log_level : LogLevelType, optional
            The logging level for the server (e.g., "INFO", "DEBUG").
            (Default is "INFO").
        """
        setup_logging(log_level)
        host = host or self.config.get("SERVER_HOST", "127.0.0.1")
        port = port or int(self.config.get("SERVER_PORT", 8000))
        self._print_banner(host, port)

        uvicorn.run(
            self,
            host=host,
            port=port,
            log_config=get_log_config(level=log_level),
            lifespan="on",
        )

    def _print_banner(self, host, port):
        """Prints the startup banner, version information, and mapped routes to the console.

        Parameters
        ----------
        host : str
            The host address the server is running on.
        port : int
            The port the server is listening on.
        """
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
        """Helper to avoid code repetition in HTTP method decorators.

        Parameters
        ----------
        method : str
            The HTTP method (e.g., 'GET', 'POST').
        path : str
            The URL path template.

        Returns
        -------
        callable
            A decorator function (`wrapper`) that registers the decorated
            function as a route handler.
        """

        def wrapper(func):
            """Registers the decorated function as a route handler.

            Parameters
            ----------
            func : callable
                The function to be registered as the handler.

            Returns
            -------
            callable
                The original function (for chaining decorators).
            """
            self.router.add_route(method, path, func)
            return func

        return wrapper

    def mount_static(
        self,
        url: str,
        directory: str | Path,
        *,
        html: bool = False,
        cache_control: str = DEFAULT_CACHE_CONTROL,
    ) -> None:
        """Serves the files in `directory` under `url`.

        Parameters
        ----------
        url : str
            URL prefix, e.g. ``"/docs"``.
        directory : str or Path
            Folder to serve; relative paths are resolved against the app directory.
        html : bool
            Serve ``index.html`` for directories and redirect ``/docs/guide`` to
            ``/docs/guide/`` so relative links work (static-site output).
        cache_control : str
            ``Cache-Control`` for every file, e.g.
            ``"public, max-age=31536000, immutable"`` for fingerprinted assets.

        Notes
        -----
        Every request path is validated with `ushka.guard.safe.path`; files get
        an ``ETag`` and revalidation answers ``304 Not Modified``.
        """
        root = Path(directory)
        if not root.is_absolute():
            root = self.workdir / root
        prefix = "/" + url.strip("/")

        async def serve(request: Request, filename: str = ""):
            target = resolve_in(root, filename, html=html)
            if target is None:
                raise HttpNotFound()
            if html and target.name == "index.html" and not request.path.endswith("/"):
                if (root / filename).resolve().is_dir() or not filename:
                    return redirect(request.path + "/", status_code=301)
            return file_response(target, request, cache_control)

        self.router.add_route("GET", prefix + "/[path:filename]", serve)
        if html:
            self.router.add_route("GET", prefix, serve)

    def on_startup(self, func):
        """Registers a function (sync or async) to run when the server starts.

        Use it to open connection pools, warm caches, etc. If it raises, the
        server refuses to start and logs the error.
        """
        self._startup.append(func)
        return func

    def on_shutdown(self, func):
        """Registers a function (sync or async) to run when the server stops."""
        self._shutdown.append(func)
        return func

    def get(self, path: str):
        """Decorator to register a function as a GET route handler.

        Parameters
        ----------
        path : str
            The URL path template.

        Returns
        -------
        callable
            The route registration decorator.
        """
        return self._add_route("GET", path)

    def post(self, path: str):
        """Decorator to register a function as a POST route handler.

        Parameters
        ----------
        path : str
            The URL path template.

        Returns
        -------
        callable
            The route registration decorator.
        """
        return self._add_route("POST", path)

    def put(self, path: str):
        """Decorator to register a function as a PUT route handler.

        Parameters
        ----------
        path : str
            The URL path template.

        Returns
        -------
        callable
            The route registration decorator.
        """
        return self._add_route("PUT", path)

    def patch(self, path: str):
        """Decorator to register a function as a PATCH route handler.

        Parameters
        ----------
        path : str
            The URL path template.

        Returns
        -------
        callable
            The route registration decorator.
        """
        return self._add_route("PATCH", path)

    def delete(self, path: str):
        """Decorator to register a function as a DELETE route handler.

        Parameters
        ----------
        path : str
            The URL path template.

        Returns
        -------
        callable
            The route registration decorator.
        """
        return self._add_route("DELETE", path)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _to_response(result) -> Response:
    """Turns a handler's return value into a `Response`.

    ``Response`` → as is; ``(body, status)`` / ``(body, status, headers)`` →
    that status (and headers); ``None`` → ``204 No Content``; anything else is
    the body (see `Response.body`).
    """
    if isinstance(result, Response):
        return result
    if isinstance(result, tuple) and 2 <= len(result) <= 3 and isinstance(result[1], int):
        body, status, *rest = result
        response = body if isinstance(body, Response) else Response(body)
        response.status_code = status
        if rest:
            response.headers.update(rest[0])
        return response
    if result is None:
        return Response(b"", status_code=204)
    return Response(result)
