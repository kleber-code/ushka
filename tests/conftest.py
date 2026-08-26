"""Shared fixtures for the Ushka test suite."""

from pathlib import Path

import pytest

from ushka.core.app import Ushka
from ushka.core.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Drops the `Config` singleton around every test.

    `Config` caches its instance on the class, so without this the first test
    that loads a configuration would leak its values into all the others.
    """
    Config._instance = None
    Config._initialized = False
    yield
    Config._instance = None
    Config._initialized = False


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """An empty directory that acts as the application root for a test."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def make_app(workdir, monkeypatch):
    """Builds `Ushka` instances rooted at the throwaway `workdir`.

    `Ushka._setup_workdir` walks the call stack to guess the project root,
    which resolves to pytest's own internals when the app is built from a test.
    Pinning it to the temporary directory keeps generated files out of the repo.
    """

    def _setup_workdir(self):
        self.workdir = Path.cwd()

    monkeypatch.setattr(Ushka, "_setup_workdir", _setup_workdir)

    def factory():
        return Ushka()

    return factory


@pytest.fixture
def app(make_app):
    """A ready-to-use application rooted at a throwaway directory."""
    return make_app()


@pytest.fixture
def call():
    """Returns an ASGI caller: `await call(app, "GET", "/path")`.

    Drives an application through the raw ASGI interface and collects the
    response, so the tests exercise the same path a real server would.
    """

    async def _call(app, method="GET", path="/", body=b"", headers=None, query=b""):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "root_path": "",
            "scheme": "http",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
            ],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)

        start = messages[0]
        payload = b"".join(m.get("body", b"") for m in messages[1:])
        return {
            "status": start["status"],
            "headers": {
                bytes(k).decode(): bytes(v).decode() for k, v in start["headers"]
            },
            "body": payload.decode("utf-8", "replace"),
        }

    return _call
