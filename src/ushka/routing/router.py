import re
from typing import Dict, Callable, Tuple

from ushka.http.request import Request


def normalize_url_path(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    return "/" + "/".join(parts)


class Router:
    def __init__(self):
        self.static_routes: Dict[str, Dict[str, Callable]] = {}
        self.dynamic_routes: Dict[str, list[Tuple[re.Pattern, list[str], Callable]]] = (
            {}
        )

    def add_route(self, method, path, func):
        path = normalize_url_path(path)

        if "[" not in path:
            self.static_routes.setdefault(method, {})[path] = func

        else:
            param_names = []
            regex_pattern = "^"
            for part in path.strip("/").split("/"):
                if part.startswith("[") and part.endswith("]"):
                    param = part[1:-1]
                    param_names.append(param)
                    regex_pattern += r"/(?P<%s>[^/]+)" % param
                else:
                    regex_pattern += "/" + part

            regex_pattern += "$"
            compiled = re.compile(regex_pattern)
            self.dynamic_routes.setdefault(method, []).append(
                (compiled, param_names, func)
            )

    def get_route(self, request: Request) -> Tuple[Callable, Dict] | Tuple[None, Dict]:
        method = request.method
        path = normalize_url_path(request.path)

        func = self.static_routes.get(method, {}).get(path)
        if func:
            return func, {}

        for regex, param_names, dynamic_func in self.dynamic_routes.get(method, []):
            match = regex.match(path)
            if match:
                return dynamic_func, match.groupdict()

        return None, {}
