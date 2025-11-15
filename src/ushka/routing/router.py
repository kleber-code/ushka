import re
from typing import Dict, Callable, Tuple

from ..http.request import Request


def normalize_url_path(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p == "."]
    return "/" + "/".join(parts)


class Router:
    def __init__(self, app_path: str):
        self.app_path = app_path
        self.static_routes: Dict[str, Dict[str, Callable]] = {}
        self.dynamic_routes: Dict[
            str, list[Tuple[re.Pattern, list[str], Callable]]
        ] = {}

    def add_route(self, method: str, path: str, func: Callable):
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
            # TODO: Add Resolve Route to injects depends like func(request)
            match = regex.match(path)
            if match:
                return dynamic_func, match.groupdict()

        return None, {}

    def autodiscover(self, folder="routes"):
        from pathlib import Path
        import importlib.util
        import inspect

        base_path = Path(self.app_path).parent
        target_path = base_path.joinpath(folder)
        for file in target_path.rglob("*.py"):
            if not file.name.startswith("__"):
                spec = importlib.util.spec_from_file_location("mod", str(file))
                if spec is None or spec.loader is None:
                    continue

                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                for name, obj in inspect.getmembers(mod):
                    if inspect.isfunction(obj):
                        # TODO: Add ANY method mode
                        if name.upper() in [
                            "GET",
                            "POST",
                            "PUT",
                            "UPDATE",
                            "DELETE",
                            "HEAD",
                        ]:
                            # FIXME: Race condition caused by /foo/index.py and /foo.py It doesn't pose a danger, but it can cause overwriting and make a "bug" difficult to spot.

                            if file.name.lower() == "index.py":
                                relative_path = file.parent.relative_to(target_path)

                            else:
                                relative_path = str(
                                    file.relative_to(target_path)
                                ).removesuffix(".py")

                            self.add_route(name.upper(), str(relative_path), obj)
