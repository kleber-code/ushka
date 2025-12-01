"""This module implements the Router for the Ushka framework.

It handles route registration, discovery, and matching for both static and
dynamic URL paths. The Router is a key component for mapping incoming HTTP
requests to the appropriate handler functions.
"""

import importlib.util
import inspect
import re
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Tuple

from ushka.core.config import Config
from ushka.core.log import LogSystem
from ushka.http.request import Request
from ushka.http.response import Response


def normalize_url_path(path: str) -> str:
    """Normalizes a URL path by removing empty segments.

    Ensures that the path starts with a leading slash and removes any redundant
    '/' or '.' characters.

    Args:
        path: The raw URL path string.

    Returns:
        The normalized URL path.
    """
    parts = [p for p in path.split("/") if p and p != "."]
    return "/" + "/".join(parts)


class Router:
    """Manages the application's routing logic.

    This class is responsible for route registration, automatic discovery of
    route handlers from files, and matching incoming requests to the correct
    handler. It supports static paths, dynamic paths with parameters, and
    dependency injection for handlers.

    Attributes:
        workdir (Path): The application's working directory.
        logsystem (LogSystem): The logging system instance.
        static_routes (dict): A dictionary to store static routes.
        dynamic_routes (dict): A dictionary to store dynamic routes.
        host (str): The host address.
    """

    def __init__(self, logsystem: LogSystem, workdir: Path, host: str = "127.0.0.1"):
        """Initializes the Router.

        Args:
            logsystem: The logging system instance.
            workdir: The application's working directory.
            host: The host address.
        """
        self.workdir = workdir
        self.logsystem = logsystem
        # static_routes: method -> { path -> (handler, dependencies) }
        self.static_routes: Dict[str, Dict[str, Tuple[Callable, Dict[str, Any]]]] = {}
        # dynamic_routes: method -> [
        # (compiled_regex, param_names, handler, dependencies, raw_path)
        # ]
        self.dynamic_routes: Dict[
            str,
            list[
                Tuple[
                    re.Pattern,
                    list[str],
                    Callable,
                    Dict[str, Any],
                    str,
                ]
            ],
        ] = {}
        self.host = host
        self.http_method = Literal[
            "GET",
            "POST",
            "PUT",
            "UPDATE",
            "DELETE",
            "HEAD",
        ]

    def _function_extractor(self, func: Callable) -> Dict[str, Any]:
        """Extracts function arguments and their types for dependency injection.

        This internal method inspects a route handler's signature to identify
        dependencies like `Request`, `Response`, or `Config` that need to be
        injected by the router.

        Args:
            func: The route handler function.

        Returns:
            A dictionary mapping argument names to their required types for
            injection.
        """
        sig = inspect.signature(func)

        args = {}
        for name, param in sig.parameters.items():
            ann = param.annotation
            # Mark parameters that should receive Request or Response instances
            if name == "request" or ann is Request:
                args[name] = Request
            elif name == "response" or ann is Response:
                args[name] = Response
            elif ann is Config:
                args[name] = Config

        return args

    def _resolver_depends(
        self, request: Request, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolves and injects dependencies for a route handler.

        Based on the arguments extracted by `_function_extractor`, this method
        creates instances of the required objects (`Request`, `Response`,
        `Config`) to be passed to the handler.

        Args:
            request: The incoming request object.
            args: A dictionary of dependencies required by the handler.

        Returns:
            A dictionary of resolved dependency instances.
        """
        loaded = {}
        for name, param in args.items():
            if param is Request:
                loaded[name] = request
            elif param is Response:
                # instantiate a fresh Response for the handler
                loaded[name] = Response()
            elif param is Config:
                loaded[name] = Config()

        return loaded

    def add_route(self, method: str, path: str, func: Callable) -> None:
        """Adds a new route to the router.

        This method registers a handler for a given HTTP method and path. It
        supports both static paths (e.g., '/users') and dynamic paths with
        parameter capturing (e.g., '/users/[user_id]').

        Args:
            method: The HTTP method (e.g., 'GET', 'POST').
            path: The URL path for the route.
            func: The handler function to execute for this route.
        """
        path = normalize_url_path(path)
        args = self._function_extractor(func)

        # Static route (no dynamic parameters)
        if "[" not in path:
            with suppress(KeyError):
                try:
                    old_function = self.static_routes[method][path][0]
                    self.logsystem.log.warning(
                        f"The static {path} is already defined by {repr(old_function)} "
                        f"and will be overwritten by {repr(func)}."
                    )
                finally:
                    self.static_routes.setdefault(method, {})[path] = (func, args)
            return

        # Dynamic route: build regex and capture parameter names
        # TODO: Lets make validate path params like int, float, uuid, path, any
        param_names = []
        regex_parts = ["^"]

        for part in path.strip("/").split("/"):
            if part.startswith("[") and part.endswith("]"):
                inner = part[1:-1]

                if inner.startswith("path:"):
                    name = inner[5:]
                    param_names.append(name)
                    regex_parts.append(f"/(?P<{name}>.+)")
                else:
                    name = inner
                    param_names.append(name)
                    regex_parts.append(f"/(?P<{name}>[^/]+)")
            else:
                regex_parts.append("/" + part)

        regex = re.compile("".join(regex_parts) + "$")
        self.dynamic_routes.setdefault(method, []).append(
            (regex, param_names, func, args, path)
        )

    def get_route(
        self, request: Request
    ) -> Tuple[Callable, Dict[str, Any]] | Tuple[None, None]:
        """Finds the appropriate route handler for a given request.

        It prioritizes static routes for performance, falling back to dynamic
        routes if no static match is found.

        Args:
            request: The incoming request object.

        Returns:
            A tuple containing the matched handler function and its resolved
            arguments, or `(None, None)` if no route is found.
        """
        method = request.method
        path = normalize_url_path(request.path)

        # Try static routes first
        func, args = self.static_routes.get(method, {}).get(path) or (None, None)
        if func:
            solved_args = self._resolver_depends(request, args)
            return func, solved_args

        # Then try dynamic routes and return the first matching handler
        for regex, _, func, args, _ in self.dynamic_routes.get(method, []):
            match = regex.match(path)
            if match:
                solved_args: Dict[str, Any] = self._resolver_depends(request, args)
                return func, (solved_args | match.groupdict())

        return None, None

    def autodiscover(self, folder: str = "routes") -> None:
        """Automatically discovers and registers routes from a specified folder.

        This method scans for Python files in the given folder, looking for
        functions named after HTTP methods (e.g., `get`, `post`). It then
        constructs a route path based on the file's location and registers it.

        Args:
            folder: The name of the folder to scan for route modules.
        """
        workdir_base = self.workdir
        routes_root = workdir_base.joinpath(folder)

        for file in routes_root.rglob("*.py"):
            if file.name.startswith("__"):
                continue

            spec = importlib.util.spec_from_file_location("mod", str(file))
            if not spec or not spec.loader:
                continue

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            for name, obj in inspect.getmembers(mod, inspect.isfunction):
                upper = name.upper()
                # Accept common HTTP method names
                if upper == self.http_method:
                    continue

                # Determine route path relative to the routes root
                if file.name.lower() == "index.py":
                    rel = file.parent.relative_to(routes_root)
                else:
                    rel = str(file.relative_to(routes_root)).removesuffix(".py")

                self.add_route(upper, str(rel), obj)

    def get_urls(
        self, host: str = "127.0.0.1", port: int = 8000, with_host: bool = True
    ) -> list[str]:
        """Generates a formatted list of all registered URL paths.

        Args:
            host: The server host, used for generating full URLs.
            port: The server port, used for generating full URLs.
            with_host: Whether to include the host and port in the output URLs.

        Returns:
            A sorted list of strings, each representing a registered route
            and its supported HTTP methods.
        """
        paths: Dict[str, list] = {}  # path:[methods]

        for method, static_routes_section in self.static_routes.items():
            for path in static_routes_section.keys():
                paths.setdefault(path, []).append(method)

        for method, dynamic_routes_section in self.dynamic_routes.items():
            for path_data in dynamic_routes_section:
                paths.setdefault(path_data[4], []).append(method)

        if with_host:
            printable_paths = [
                f"http://{host}:{port}{path} - " + ", ".join(methods).upper()
                for path, methods in paths.items()
            ]
        else:
            printable_paths = [
                f"{path} - " + ", ".join(methods).upper()
                for path, methods in paths.items()
            ]

        printable_paths.sort()

        return printable_paths
