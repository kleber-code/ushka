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

import ushka.web.pwa as pwa_module
import ushka.web.seo as seo_module
from ushka.core.config import Config
from ushka.core.error_handler import ErrorHandler
from ushka.core.log import LogLevelType, get_log_config, setup_logging
from ushka.http.exceptions import (
    HTTPError,
    HTTPMethodNotAllowed,
    HttpNotFound,
    HTTPResponse,
)
from ushka.http.params import Resolver
from ushka.http.redirect import redirect
from ushka.http.request import Request
from ushka.http.response import Response
from ushka.http.validation import RequestValidationError
from ushka.http.websocket import WebSocket, WebSocketDisconnect
from ushka.security import SecurityMiddleware
from ushka.static import (
    DEFAULT_CACHE_CONTROL,
    file_response,
    resolve_in,
    server_static_files,
)
from ushka.templating import render
from ushka.templating.engine import engine as template_engine
from ushka.web.i18n import I18n

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
        template_engine.configure(self.config)
        #: Translation settings and language choice, from ``[i18n]``.
        self.i18n = I18n(self.config, self.workdir)

        self._startup: list = []
        self._shutdown: list = []
        #: ``{original: replacement}`` for `Depends`, handy in tests.
        self.dependency_overrides: dict = {}
        #: Your middleware, outermost first. See `add_middleware`.
        self._middleware: list = []

        self.router = Router(self.log, self.workdir)
        #: Routes every host serves (static files); see `_add_shared_route`.
        self._shared_routes: list = []
        if self.config.get("APP_AUTO_DISCOVER", True):
            # Hosts first: their folders are left out of the default routes.
            for pattern, folder in (self.config.get("ROUTES_HOSTS") or {}).items():
                self.router.add_host(pattern, folder)
            self.router.autodiscover()
        if self.config.get("SESSION_ENCRYPT"):
            # Fail at startup, not on the first request: the extra, the key.
            from ushka.crypto.fernet import validate_config

            validate_config(self.config)
        self.error_handler = ErrorHandler(self.config, self.log, self.router)
        #: Always outermost; configured in ``[security]``.
        self.security = SecurityMiddleware(self.config)
        #: A `ushka.sessions.stores.SessionStore` of your own (Redis, ...);
        #: when None, ``[session] store`` decides.
        self.session_store = None
        #: ``{path: handler}`` for GET pages Ushka ships (robots.txt, the PWA files...).
        #: They answer only when no route of yours matches, so yours always win.
        self._builtin_routes: dict = {}
        #: The pieces plugged in with `use`, by name (``app.pieces["docs"]``).
        self.pieces: dict = {}
        seo_module.install(self)
        pwa_module.install(self)
        if any(self.config.get(f"oauth_{n}_client_id") for n in ("google", "github")):
            # only apps that sign in with OAuth load the package
            from ushka.auth import install as install_auth

            install_auth(self)

        if self.config.get("STATIC_ENABLE"):
            static_url = self.config.get("STATIC_URL", "/static") + "/[path:filename]"
            self._add_shared_route("GET", static_url, server_static_files)

    def _add_shared_route(self, method: str, path: str, func) -> None:
        """A route every host serves (static files), not only the default one."""
        self._shared_routes.append((method, path, func))
        self.router.add_route(method, path, func)
        for _, sub in self.router.hosts:
            sub.add_route(method, path, func)

    def host(self, pattern: str):
        """The routes of a host: ``@app.host("api.*").get("/status")``.

        `pattern` is a host name or glob (``"api.example.com"``, ``"*.example.com"``).
        A request for a matching host is answered only by the routes of that host,
        so the routes of ``routes/`` do not leak onto it. The same can be set in
        ``[routes] hosts`` (a folder of route files per host). Returns a `Router`.
        """
        known = {p for p, _ in self.router.hosts}
        sub = self.router.add_host(pattern)
        if sub is not None and pattern.strip().lower() not in known:
            for method, path, func in self._shared_routes:
                sub.add_route(method, path, func)
        return sub

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
            await self._handle_websocket(scope, receive, send)

    async def _handle_websocket(self, scope, receive, send):
        """Routes a WebSocket handshake like a request, checks it, runs the handler."""
        request = Request(self, {**scope, "type": "http", "method": "WEBSOCKET"}, receive)
        ws = WebSocket(request, receive, send)
        resolver = Resolver(request)
        resolver.websocket = ws
        try:
            handler, params = self.router.get_route(request)
            if handler is None or not self.security.websocket_allowed(request):
                await ws.close(1008, "refused")  # before accept: the client sees HTTP 403
                return
            kwargs = await resolver.call(handler, params)
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                await result
        except WebSocketDisconnect:
            pass
        except (HTTPError, HTTPResponse):
            await ws.close(1008, "refused")
        except RequestValidationError:
            await ws.close(1008, "invalid request")
        except Exception:
            self.log.exception("WebSocket handler failed")
            await ws.close(1011, "server error")
        finally:
            await resolver.close()
        await ws.close(1000)

    def websocket(self, path: str):
        """Registers a WebSocket handler: ``@app.websocket("/ws")``."""
        return self._add_route("WEBSOCKET", path)

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
                store = self.session_store
                if store is not None:  # release the sessions database connections
                    try:
                        await store.close()
                    except Exception:
                        self.log.exception("Closing the session store failed")
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
        token = self.i18n.activate(request)
        try:
            await self._serve_http(request, send)
        finally:
            self.i18n.deactivate(token)

    async def _serve_http(self, request, send):
        """`_handle_http` with the request's language already set."""
        try:
            try:
                await request.load_session()
                response = await self._run_chain(request)
            except Exception as e:
                response = await self._error_response(e, request)
            # Lets the response persist cookie/session changes, also on 4xx errors
            # and redirects raised by the handler (not on 500s: see Response.persist).
            if response.persist:
                response.request = request

            if request.method == "HEAD":
                response.head_only = True

            started = False

            async def tracked_send(message):
                nonlocal started
                started = started or message["type"] == "http.response.start"
                await send(message)

            try:
                await response(tracked_send)
            except Exception:
                if started:
                    raise  # the status line is gone: only the server can abort now
                # Building the response failed (for example a header value with a
                # line break): answer with a clean 500 instead of leaking the error to the server.
                self.log.exception("Could not send the response")
                await Response("Internal Server Error", 500)(send)
        finally:
            request._close_uploads()  # temporary files of any uploads

    async def _error_response(self, exc: Exception, request: Request) -> Response:
        try:
            return await self.error_handler.handle_exception(exc, request)
        except Exception:
            # The error page itself failed: never leave the client hanging.
            self.log.exception("Error handler failed")
            failed = Response("Internal Server Error", 500)
            failed.persist = False
            return failed

    async def _dispatch_safely(self, request: Request) -> Response:
        """The route, with errors already turned into responses, so every
        middleware (security headers included) sees a `Response` and nothing else."""
        try:
            return await self._dispatch_request(request)
        except Exception as exc:
            return await self._error_response(exc, request)

    async def _run_chain(self, request: Request) -> Response:
        call = self._dispatch_safely
        for mw in reversed(self._middleware):
            call = _bind(mw, call)
        return await _bind(self.security, call)(request)

    def add_middleware(self, func):
        """Registers a middleware: ``async def mw(request, call_next) -> Response``.

        Middleware runs in the order added (the first one is outermost) and
        inside the built-in security middleware. ``await call_next(request)``
        gives the downstream `Response`, which you may change or replace. Raise
        nothing for expected errors: return a `Response` instead. Also usable as
        a decorator (``@app.middleware``).
        """
        self._middleware.append(func)
        return func

    middleware = add_middleware

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

        if not handler and request.method in ("GET", "HEAD"):
            handler = self._builtin_routes.get(self.router._normalize_path(request.path))

        if not handler:
            is_empty = not (self.router.static_routes or self.router.dynamic_routes or self.router.hosts)
            if is_empty:
                return Response(await render(request, "startup.html", {}))
            allowed = self.router.allowed_methods(request.path, request.host)
            if allowed:
                raise HTTPMethodNotAllowed(allowed)
            raise HttpNotFound()

        resolver = Resolver(request)
        try:
            try:
                kwargs = await resolver.call(handler, params)
            except RequestValidationError as exc:
                on_invalid = getattr(handler, "__ushka_on_invalid__", None)
                if on_invalid is None:
                    raise
                # the route's own answer (usually the form again, with the errors)
                resolver.errors, handler = exc, on_invalid
                kwargs = await resolver.call(on_invalid, params)
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        finally:
            await resolver.close()  # generator dependencies clean up here

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
        import uvicorn  # only needed to serve; importing it costs about half of `import ushka`

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
            proxy_headers=False,  # X-Forwarded-* is read by Ushka: [security] trusted_proxies
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

    def _add_route(self, method: str, path: str, on_invalid=None):
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
            if on_invalid is not None:
                func.__ushka_on_invalid__ = on_invalid
            self.router.add_route(method, path, func)
            return func

        return wrapper

    def add_builtin_route(self, path: str, handler) -> None:
        """Registers a page Ushka itself ships (``/robots.txt``, ``/sw.js``...).

        Unlike `Router.add_route` it never overwrites yours: a route you define
        for the same path is used instead, with no warning.
        """
        self._builtin_routes[self.router._normalize_path(path)] = handler

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

        self._add_shared_route("GET", prefix + "/[path:filename]", serve)
        if html:
            self._add_shared_route("GET", prefix, serve)

    def use(self, *pieces):
        """Plugs pieces into the app: ``app.use(Docs("docs"))``. The one verb for every feature.

        A piece is any object with an ``install(app)`` method, or a plain function that
        takes the app. It registers what it needs (routes, hooks, middleware) with the
        app's own methods. Ushka's batteries are pieces, and so is the one you write:

            def health(app):
                @app.get("/health")
                async def ok():
                    return "ok"

            app.use(health)

        Returns the piece, or a tuple when you pass several. A piece may have a ``name``
        (otherwise its class or function name, lower-case); it is kept in
        ``app.pieces[name]``, and using another piece with the same name replaces it.
        Using the same object twice installs it once.
        """
        done = []
        for piece in pieces:
            if any(piece is p for p in self.pieces.values()):
                done.append(piece)
                continue
            install = getattr(piece, "install", None)
            if callable(install):
                install(self)
            elif callable(piece):
                piece(self)
            else:
                raise TypeError(
                    f"app.use() takes an object with install(app) or a function(app), got {type(piece).__name__}"
                )
            name = getattr(piece, "name", None)
            if not isinstance(name, str) or not name:
                name = getattr(piece, "__name__", None) or type(piece).__name__
            self.pieces[name.lower()] = piece
            done.append(piece)
        return done[0] if len(done) == 1 else tuple(done)

    def openapi(self, title: str | None = None, version: str = "0.1.0") -> dict:
        """The OpenAPI 3.1 document describing this app's routes (a dict)."""
        from ushka.api import openapi

        skip = getattr(self, "_openapi_skip", set())
        return openapi.build(self.router, title or self.config.get("app_name", "Ushka API"), version, skip)

    def enable_openapi(self, path: str = "/openapi.json", title: str | None = None, version: str = "0.1.0") -> None:
        """Serves `openapi()` as JSON at `path`. Opt-in: an API description is
        a map of your routes, so you decide whether to publish it."""

        async def openapi_json():
            return self.openapi(title, version)

        self._openapi_skip = getattr(self, "_openapi_skip", set()) | {openapi_json}
        self.router.add_route("GET", path, openapi_json)

    def enable_mcp(self, path: str = "/mcp", token=None, approve=None, name: str | None = None, instructions: str | None = None, internal_headers=None) -> None:
        """Serves the routes marked with `ushka.api.mcp.tool` to AI agents over MCP.

        Call it after your routes are registered. `token` (or ``USHKA_MCP_TOKEN``)
        is the bearer token agents must send; without one it refuses to start
        unless debug is on. `approve` is an async callable (or
        `ushka.api.mcp.ApprovalQueue`) that a human answers for sensitive tools.
        `internal_headers` (a dict, or a function of the request) adds headers to
        the internal request, e.g. a service credential your routes check.
        With ``token=False`` the endpoint has no shared secret: the caller's
        ``Authorization`` is passed to the routes, which authenticate it.
        """
        from ushka.api.mcp import MCPServer

        server = MCPServer(self, path, token, approve, name, instructions, internal_headers)
        self.mcp = server

        async def mcp_endpoint(request):
            status, payload = await server.handle(request)
            return (payload, status) if payload is not None else Response(b"", status_code=status)

        server_endpoint = mcp_endpoint
        self._openapi_skip = getattr(self, "_openapi_skip", set()) | {server_endpoint}
        self.router.add_route("POST", path, server_endpoint)

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

    def get(self, path: str, *, on_invalid=None):
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
        return self._add_route("GET", path, on_invalid)

    def post(self, path: str, *, on_invalid=None):
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
        return self._add_route("POST", path, on_invalid)

    def put(self, path: str, *, on_invalid=None):
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
        return self._add_route("PUT", path, on_invalid)

    def patch(self, path: str, *, on_invalid=None):
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
        return self._add_route("PATCH", path, on_invalid)

    def delete(self, path: str, *, on_invalid=None):
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
        return self._add_route("DELETE", path, on_invalid)


def _bind(mw, call_next):
    async def run(request: Request) -> Response:
        return _to_response(await _maybe_await(mw(request, call_next)))

    return run


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
