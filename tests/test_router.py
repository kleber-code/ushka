"""Tests for `ushka.core.router.Router`."""

import logging
from pathlib import Path

import pytest

from ushka.core.router import Router
from ushka.http.request import Request


class _FakeApp:
    """Minimal stand-in for `Ushka`, enough to build a `Request`."""

    def __init__(self):
        self.config = _FakeConfig()


class _FakeConfig:
    def get(self, key, default=None, required=False):
        return default


def _request(method, path):
    scope = {"type": "http", "method": method, "path": path, "headers": []}
    return Request(_FakeApp(), scope, None)


@pytest.fixture
def router(tmp_path):
    return Router(logging.getLogger("ushka.test"), Path(tmp_path))


def test_normalizes_paths(router):
    assert router._normalize_path("/") == "/"
    assert router._normalize_path("users") == "/users"
    assert router._normalize_path("//api//users//") == "/api/users"


def test_static_route_lookup(router):
    def handler():
        return "ok"

    router.add_route("get", "/ping", handler)

    found, params = router.get_route(_request("GET", "/ping"))
    assert found is handler
    assert params == {}


def test_unknown_method_is_ignored(router):
    def handler():
        return "ok"

    router.add_route("BREW", "/coffee", handler)

    assert router.static_routes == {}
    assert router.dynamic_routes == {}


def test_method_mismatch_does_not_match(router):
    def handler():
        return "ok"

    router.add_route("GET", "/ping", handler)

    found, _ = router.get_route(_request("POST", "/ping"))
    assert found is None


def test_dynamic_route_captures_parameters(router):
    def handler(slug):
        return slug

    router.add_route("GET", "/posts/[slug]", handler)

    found, params = router.get_route(_request("GET", "/posts/hello-world"))
    assert found is handler
    assert params == {"slug": "hello-world"}


def test_int_converter_only_matches_digits(router):
    def handler(uid):
        return uid

    router.add_route("GET", "/users/[int:uid]", handler)

    found, params = router.get_route(_request("GET", "/users/42"))
    assert found is handler
    assert params == {"uid": "42"}

    missing, _ = router.get_route(_request("GET", "/users/abc"))
    assert missing is None


def test_path_converter_matches_slashes(router):
    def handler(filename):
        return filename

    router.add_route("GET", "/static/[path:filename]", handler)

    found, params = router.get_route(_request("GET", "/static/css/app.css"))
    assert found is handler
    assert params == {"filename": "css/app.css"}


def test_dependencies_are_injected_by_name_and_annotation(router):
    def handler(request: Request, uid=None):
        return uid

    router.add_route("GET", "/deps/[uid]", handler)

    found, params = router.get_route(_request("GET", "/deps/7"))
    assert found is handler
    assert isinstance(params["request"], Request)
    assert params["uid"] == "7"


def test_autodiscover_skips_a_missing_routes_folder(router):
    router.autodiscover()

    assert router.static_routes == {}
    assert router.dynamic_routes == {}


def test_autodiscover_registers_route_modules(tmp_path):
    routes_dir = tmp_path / "routes"
    routes_dir.mkdir()
    (routes_dir / "index.py").write_text(
        "async def get():\n    return 'root'\n", encoding="utf-8"
    )
    (routes_dir / "about.py").write_text(
        "async def get():\n    return 'about'\n", encoding="utf-8"
    )

    router = Router(logging.getLogger("ushka.test"), Path(tmp_path))
    router.autodiscover()

    assert "/about" in router.static_routes["GET"]
    assert "/" in router.static_routes["GET"]
