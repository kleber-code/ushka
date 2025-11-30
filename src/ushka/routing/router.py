import importlib.util
import inspect
import re
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, Literal

from ushka.http.request import Request
from ushka.http.response import Response


def normalize_url_path(path: str) -> str:
    parts = [p for p in path.split("/") if p and p != "."]
    return "/" + "/".join(parts)


class Router:
    def __init__(self, app_path: Path, host="127.0.0.1"):
        self.app_path = app_path
        # static_routes: method -> { path -> (handler, dependencies) }
        self.static_routes: Dict[str, Dict[str, Tuple[Callable, Dict[str, Any]]]] = {}
        # dynamic_routes: method -> [ (compiled_regex, param_names, handler, dependencies, raw_path) ]
        self.dynamic_routes: Dict[
            str, list[Tuple[re.Pattern, list[str], Callable, Dict[str, Any], str]]
        ] = {}
        self.host = host
        self.HTTPMethod = Literal["GET", "POST", "PUT", "UPDATE", "DELETE", "HEAD"]

    def _function_extractor(self, func: Callable) -> Dict[str, Callable]:
        sig = inspect.signature(func)

        args = {}
        for name, param in sig.parameters.items():
            ann = param.annotation
            # Mark parameters that should receive Request or Response instances
            if name == "request" or ann is Request:
                args[name] = Request
            elif name == "response" or ann is Response:
                args[name] = Response

        return args

    def _resolver_depends(self, request, args):
        loaded = {}
        for name, param in args.items():
            if param is Request:
                loaded[name] = request
            elif param is Response:
                # instantiate a fresh Response for the handler
                loaded[name] = Response()
        return loaded

    def add_route(self, method: str, path: str, func: Callable):
        path = normalize_url_path(path)
        args = self._function_extractor(func)

        # Static route (no dynamic parameters)
        if "[" not in path:
            self.static_routes.setdefault(method, {})[path] = (func, args)
            return

        # Dynamic route: build regex and capture parameter names
        # TODO: Find some usefull for param_names data
        param_names = []
        regex_parts = ["^"]

        for part in path.strip("/").split("/"):
            if part.startswith("[") and part.endswith("]"):
                name = part[1:-1]
                param_names.append(name)
                regex_parts.append(r"/(?P<{}>[^/]+)".format(name))
            else:
                regex_parts.append("/" + part)

        regex = re.compile("".join(regex_parts) + "$")
        self.dynamic_routes.setdefault(method, []).append(
            (regex, param_names, func, args, path)
        )

    def get_route(
        self, request: Request
    ) -> Tuple[Callable, Dict[str, Any]] | Tuple[None, None]:
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

    def autodiscover(self, folder="routes"):
        base = self.app_path
        root = base.joinpath(folder)

        for file in root.rglob("*.py"):
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
                if upper is self.HTTPMethod:
                    continue

                # Determine route path relative to the routes root
                # FIXME: Race condition when both /foo/index.py and /foo.py exist.
                # It does not pose a security risk but can cause routes to be overwritten,
                # making the behavior harder to debug.
                if file.name.lower() == "index.py":
                    rel = file.parent.relative_to(root)
                else:
                    rel = str(file.relative_to(root)).removesuffix(".py")

                self.add_route(upper, str(rel), obj)

    def get_urls(self, host="127.0,0.1", port=8000, with_host=True) -> list[str]:
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
