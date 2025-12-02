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
    """
    Central route manager.
    Responsible for linking URLs to Python functions (handlers).
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
        """Ensures the path always starts with / and has no double slashes."""
        if path == "/":
            return path
        parts = [p for p in path.split("/") if p and p != "."]
        return "/" + "/".join(parts)

    def _extract_dependencies(self, func: RouteHandler) -> DependencyMap:
        """
        Analyzes the function signature for simple Dependency Injection.
        Identifies if the function requests Request, Response or Config.
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
        """Instantiates the necessary objects for the route."""
        injected = {}
        for name, type_cls in required_deps.items():
            if type_cls is Request:
                injected[name] = request
            elif type_cls is Response:
                injected[name] = Response()
            elif type_cls is Config:
                injected[name] = Config()
        return injected

    def add_route(self, method: str, path: str, func: RouteHandler) -> None:
        """Registers a manual or discovered route."""
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
        """Compiles regex for routes with parameters like /user/[id]."""
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
                        regex_parts.append(f"/(?P<{name}>.+)")
                    elif type_hint == "int":
                        regex_parts.append(f"/(?P<{name}>\\d+)")
                    else:
                        regex_parts.append(f"/(?P<{name}>[^/]+)")
                else:
                    name = content
                    regex_parts.append(f"/(?P<{name}>[^/]+)")
                param_names.append(name)
            else:
                regex_parts.append("/" + part)

        regex = re.compile("".join(regex_parts) + "$")

        if method not in self.dynamic_routes:
            self.dynamic_routes[method] = []

        self.dynamic_routes[method].append((regex, param_names, func, deps, path))

    def get_route(
        self, request: Request
    ) -> Tuple[Optional[RouteHandler], Dict[str, Any]]:
        """
        Searches for the route. Returns (Handler, Kwargs) or (None, {}).
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
        """
        Filesystem-based routing.
        Reads files in the /routes folder and maps functions (get, post) to URLs.
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
        """Generates a list of routes for display in the terminal."""
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
