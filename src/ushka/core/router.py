"""
This module defines the `Router` class, which acts as the central route manager
for the Ushka framework.

It is responsible for mapping incoming URL requests to their corresponding
Python handler functions, managing both static and dynamic routes, and
handling dependency injection for route handlers.
"""

import importlib.util
import inspect
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from ushka.core.config import Config
from ushka.http.request import Request
from ushka.http.response import Response

# Types for readability
RouteHandler = Callable[..., Union[Response, Any]]
DependencyMap = Dict[str, Any]


class Router:
    """Central route manager.

    Responsible for linking URLs to Python functions (handlers) and managing
    dependency injection for those handlers.

    Parameters
    ----------
    log : logging.Logger
        The application logger instance.
    workdir : Path
        The root working directory of the application, used for route discovery.
    host : str, optional
        The default host address (e.g., '127.0.0.1'). Defaults to "127.0.0.1".

    Attributes
    ----------
    HTTP_METHODS : Set[str]
        A set of valid HTTP verbs supported by the router.
    static_routes : Dict[str, Dict[str, Tuple[RouteHandler, DependencyMap]]]
        Storage for routes without path parameters (method -> path -> (handler, deps)).
    dynamic_routes : Dict[str, List[Tuple[re.Pattern, List[str], RouteHandler, DependencyMap, str]]]
        Storage for routes with path parameters, requiring regex matching.
    """

    # Valid HTTP verbs (Set is O(1) for lookup)
    HTTP_METHODS: Set[str] = {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    }

    def __init__(self, log: logging.Logger, workdir: Path, host: str = "127.0.0.1"):
        """Initializes the Router with a logger, working directory, and host.

        Sets up internal data structures for storing static and dynamic routes.

        Parameters
        ----------
        log : logging.Logger
            The application logger instance.
        workdir : Path
            The root working directory of the application, used for route discovery.
        host : str, optional
            The default host address (e.g., '127.0.0.1'). Defaults to "127.0.0.1".
        """
        self.log = log
        self.workdir = workdir
        self.host = host

        # Structure: method -> path -> (handler, dependencies)
        self.static_routes: Dict[
            str, Dict[str, Tuple[RouteHandler, DependencyMap]]
        ] = {}

        # Structure: method -> list of dynamic route tuples
        self.dynamic_routes: Dict[
            str, List[Tuple[re.Pattern, List[str], RouteHandler, DependencyMap, str]]
        ] = {}

    def _normalize_path(self, path: str) -> str:
        """Ensures the path always starts with / and has no double slashes.

        Parameters
        ----------
        path : str
            The raw path string to normalize.

        Returns
        -------
        str
            The normalized path string (e.g., '/api/users').
        """
        if path == "/":
            return path
        parts = [p for p in path.split("/") if p and p != "."]
        return "/" + "/".join(parts)

    def _extract_dependencies(self, func: RouteHandler) -> DependencyMap:
        """Analyzes the function signature for simple Dependency Injection.

        Identifies if the function requests Request, Response or Config, either
        by parameter name or type annotation.

        Parameters
        ----------
        func : RouteHandler
            The function handler whose signature is to be inspected.

        Returns
        -------
        DependencyMap
            A dictionary mapping parameter names to the required dependency type (class).
        """
        sig = inspect.signature(func)
        deps = {}

        for name, param in sig.parameters.items():
            ann = param.annotation
            if name == "request" or ann is Request:
                deps[name] = Request
            elif name == "response" or ann is Response:
                deps[name] = Response
            elif ann is Config:
                deps[name] = Config

        return deps

    def _resolve_dependencies(
        self, request: Request, required_deps: DependencyMap
    ) -> Dict[str, Any]:
        """Instantiates the necessary objects for the route handler.

        Parameters
        ----------
        request : Request
            The current incoming HTTP request object.
        required_deps : DependencyMap
            A map of dependency names and their required types, usually generated
            by `_extract_dependencies`.

        Returns
        -------
        Dict[str, Any]
            A dictionary of instantiated dependencies ready to be passed as kwargs
            to the route handler.
        """
        injected = {}
        for name, type_cls in required_deps.items():
            if type_cls is Request:
                injected[name] = request
            elif type_cls is Response:
                injected[name] = Response()
            elif type_cls is Config:
                # Note: Config() instantiation might need context in a real app
                injected[name] = Config()
        return injected

    def add_route(self, method: str, path: str, func: RouteHandler) -> None:
        """Registers a manual or discovered route.

        Parameters
        ----------
        method : str
            The HTTP method (e.g., 'GET', 'POST'). Case-insensitive.
        path : str
            The URL path (e.g., '/users', '/users/[id]').
        func : RouteHandler
            The Python function to execute when the route is matched.

        Returns
        -------
        None
        """
        method = method.upper()
        if method not in self.HTTP_METHODS:
            self.log.warning(f"Attempted to register invalid HTTP method: {method}")
            return

        path = self._normalize_path(path)
        deps = self._extract_dependencies(func)

        # Static Route (O(1) Performance)
        if "[" not in path:
            if method not in self.static_routes:
                self.static_routes[method] = {}

            # Overwrite log (good for debugging)
            if path in self.static_routes[method]:
                old = self.static_routes[method][path][0].__name__
                self.log.warning(
                    f"Overwriting route {method} {path} (old: {old}, new: {func.__name__})"
                )

            self.static_routes[method][path] = (func, deps)
            return

        # Dynamic Route (O(N) search performance)
        self._add_dynamic_route(method, path, func, deps)

    def _add_dynamic_route(
        self, method: str, path: str, func: RouteHandler, deps: DependencyMap
    ):
        """Compiles regex for routes with parameters like /user/[id].

        Parameters
        ----------
        method : str
            The HTTP method.
        path : str
            The dynamic URL path containing bracketed parameters (e.g., '/items/[int:id]').
        func : RouteHandler
            The handler function.
        deps : DependencyMap
            The dependencies required by the handler function.

        Returns
        -------
        None
        """
        param_names = []
        regex_parts = ["^"]

        for part in path.strip("/").split("/"):
            # Ex: [id] or [int:id]
            if part.startswith("[") and part.endswith("]"):
                content = part[1:-1]
                if ":" in content:
                    # Future support for types: [int:id]
                    type_hint, name = content.split(":", 1)
                    if type_hint == "path":
                        # Matches anything including slashes (greedy)
                        regex_parts.append(f"/(?P<{name}>.+)")
                    elif type_hint == "int":
                        # Matches digits
                        regex_parts.append(f"/(?P<{name}>\\d+)")
                    else:
                        # Default: Matches non-slash characters
                        regex_parts.append(f"/(?P<{name}>[^/]+)")
                else:
                    name = content
                    # Default: Matches non-slash characters
                    regex_parts.append(f"/(?P<{name}>[^/]+)")
                param_names.append(name)
            else:
                regex_parts.append("/" + part)

        regex = re.compile("".join(regex_parts) + "$")

        if method not in self.dynamic_routes:
            self.dynamic_routes[method] = []

        # Store (compiled regex, param names, handler, dependencies, raw path)
        self.dynamic_routes[method].append((regex, param_names, func, deps, path))

    def get_route(
        self, request: Request
    ) -> Tuple[Optional[RouteHandler], Dict[str, Any]]:
        """Searches for the route matching the request method and path.

        It prioritizes static routes over dynamic routes.

        Parameters
        ----------
        request : Request
            The incoming HTTP request object.

        Returns
        -------
        Tuple[Optional[RouteHandler], Dict[str, Any]]
            A tuple containing:
            1. The matching handler function (or None if not found).
            2. A dictionary of keyword arguments, including injected dependencies
               and path parameters.
        """
        method = request.method
        path = self._normalize_path(request.path)

        # 1. Try Static (Fast)
        if method in self.static_routes and path in self.static_routes[method]:
            func, deps = self.static_routes[method][path]
            injected_args = self._resolve_dependencies(request, deps)
            return func, injected_args

        # 2. Try Dynamic (Slow)
        if method in self.dynamic_routes:
            for regex, _, func, deps, _ in self.dynamic_routes[method]:
                match = regex.match(path)
                if match:
                    path_params = match.groupdict()
                    injected_args = self._resolve_dependencies(request, deps)
                    # Joins dependencies (request, config) with URL params (id, slug)
                    return func, {**injected_args, **path_params}

        return None, {}

    def autodiscover(self, folder: str = "routes") -> None:
        """Filesystem-based routing discovery.

        Reads files in the specified folder (relative to `workdir`) and maps
        functions named after HTTP methods (e.g., `get`, `post`) to URLs
        derived from the file path.

        Parameters
        ----------
        folder : str, optional
            The subdirectory name containing route files. Defaults to "routes".

        Returns
        -------
        None
        """
        routes_root = self.workdir.joinpath(folder)
        if not routes_root.exists():
            self.log.warning(f"Routes folder not found: {routes_root}")
            return

        for file_path in routes_root.rglob("*.py"):
            if file_path.name.startswith("__"):
                continue

            # Dynamic module import
            module_name = f"{folder}.{file_path.stem}"  # For reference only
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))

            if not spec or not spec.loader:
                continue

            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception as e:
                self.log.error(f"Failed to load route module {file_path}: {e}")
                continue

            # Calculates the route based on the file path
            # routes/api/users.py -> /api/users
            # routes/index.py -> /
            if file_path.name.lower() == "index.py":
                # If it's index.py, get the parent directory. Ex: routes/api/index.py -> /api
                rel_path = file_path.parent.relative_to(routes_root)
                route_base = str(rel_path)
            else:
                rel_path = file_path.relative_to(routes_root)
                route_base = str(rel_path.with_suffix(""))  # remove .py

            # On Windows, paths come with \\, we need / for URL
            route_base = route_base.replace("\\", "/")
            if route_base == ".":
                route_base = ""

            # Inspects functions within the file
            for name, func in inspect.getmembers(mod, inspect.isfunction):
                method_name = name.upper()
                if method_name in self.HTTP_METHODS:
                    # If the file is users.py and the func is get(), the route is GET /users
                    full_path = f"/{route_base}"
                    self.add_route(method_name, full_path, func)

    def get_urls(
        self, host: str = "127.0.0.1", port: int = 8000, with_host: bool = True
    ) -> List[str]:
        """Generates a list of registered routes for display in the terminal.

        Parameters
        ----------
        host : str, optional
            The host address to prepend to the URLs. Defaults to "127.0.0.1".
        port : int, optional
            The port number to prepend to the URLs. Defaults to 8000.
        with_host : bool, optional
            If True, includes the 'http://host:port' prefix. Defaults to True.

        Returns
        -------
        List[str]
            A sorted list of strings, where each string represents a route
            and its supported methods (e.g., 'http://127.0.0.1:8000/users - GET, POST').
        """
        url_map: Dict[str, List[str]] = {}

        # Collect static
        for method, routes in self.static_routes.items():
            for path in routes:
                url_map.setdefault(path, []).append(method)

        # Collect dynamic
        for method, routes_list in self.dynamic_routes.items():
            for _, _, _, _, raw_path in routes_list:
                url_map.setdefault(raw_path, []).append(method)

        output = []
        base = f"http://{host}:{port}" if with_host else ""

        for path, methods in sorted(url_map.items()):
            methods_str = ", ".join(sorted(methods))
            output.append(f"{base}{path} - {methods_str}")

        return output
