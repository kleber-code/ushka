"""The production server must stay asleep when idle and still keep workers alive."""

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

pytest.importorskip("uvicorn")

from ushka.core import server as srv


def test_idle_worker_ticks_once_a_second(monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(srv.asyncio, "sleep", fake_sleep)
    s = srv.QuietServer(srv.Config("x:y"))
    ticks = []

    async def on_tick(counter):
        ticks.append(counter)
        return len(ticks) > 3

    monkeypatch.setattr(s, "on_tick", on_tick)
    asyncio.run(s.main_loop())
    assert sleeps and all(d >= 1.0 for d in sleeps), "an idle worker must not wake more than once a second"
    # Uvicorn refreshes the Date header when counter % 10 == 0: every tick must qualify.
    assert all(c % 10 == 0 for c in ticks)


def test_starting_worker_is_not_pinged_and_dead_one_is_replaced(monkeypatch):
    config = srv.Config("x:y", workers=2)
    sup = srv.Supervisor.__new__(srv.Supervisor)
    sup.config, sup.sockets, sup.should_exit = config, [], __import__("threading").Event()

    class Proc:
        def __init__(self, alive):
            self._alive, self.exitcode, self.pid = alive, 1, 1

        def is_alive(self):
            return self._alive

    class FakeWorker(srv.Worker):
        pinged = 0

        def __init__(self, alive=True, young=True):
            self.process = Proc(alive)
            self.started_at = time.monotonic() - (0 if young else srv.STARTUP_GRACE + 1)
            self.killed = False

        def ping(self, timeout=5):
            FakeWorker.pinged += 1
            return True

        def kill(self):
            self.killed = True

        def join(self):
            pass

    started = []
    monkeypatch.setattr(srv.Worker, "__init__", lambda self, c, s: setattr(self, "process", Proc(True)))
    monkeypatch.setattr(srv.Worker, "start", lambda self: started.append(self))

    young, old, dead = FakeWorker(young=True), FakeWorker(young=False), FakeWorker(alive=False)
    sup.processes = [young, old, dead]
    sup.keep_subprocess_alive(check_health=True)
    assert FakeWorker.pinged == 1, "only the worker past its startup grace is pinged"
    assert dead.killed and len(started) == 1 and sup.processes[2] is started[0]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(os.name != "posix", reason="signals")
def test_supervisor_replaces_a_killed_worker_and_stops_on_sigterm(tmp_path):
    (tmp_path / "idleapp.py").write_text(
        "from ushka import Ushka\napp = Ushka()\n@app.get('/healthz')\nasync def h(request):\n    return 'ok'\n"
    )
    (tmp_path / "ushka.toml").write_text("[app]\nauto_discover = false\n")
    port = _free_port()
    code = (
        "from ushka.core.server import run_server;"
        f"run_server('idleapp:app', host='127.0.0.1', port={port}, workers=2, log_config=None)"
    )
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(tmp_path)})
    url = f"http://127.0.0.1:{port}/healthz"

    def up():
        try:
            return urllib.request.urlopen(url, timeout=1).status == 200
        except OSError:
            return False

    def workers():
        out = subprocess.run(["ps", "-o", "pid=", "--ppid", str(proc.pid)], check=False, capture_output=True, text=True).stdout
        return [int(p) for p in out.split()]

    try:
        deadline = time.time() + 30
        while time.time() < deadline and not up():
            time.sleep(0.2)
        assert up()
        before = workers()
        victim = next(p for p in before if "spawn_main" in Path(f"/proc/{p}/cmdline").read_text())
        os.kill(victim, signal.SIGKILL)
        deadline = time.time() + 15
        while time.time() < deadline and victim in workers():
            time.sleep(0.2)
        deadline = time.time() + 30
        while time.time() < deadline and len(workers()) < len(before):
            time.sleep(0.2)
        assert victim not in workers() and up()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=15) in (0, -signal.SIGTERM)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_the_fast_loop_and_parser_are_the_default():
    pytest.importorskip("uvloop")
    pytest.importorskip("httptools")
    config = srv.Config("x:y")
    from uvicorn.config import HTTP_PROTOCOLS, LOOP_FACTORIES

    assert config.loop == "auto" and config.http == "auto"
    assert "uvloop" in LOOP_FACTORIES and "httptools" in HTTP_PROTOCOLS


def test_pyproject_declares_the_c_accelerators_with_platform_markers():
    from pathlib import Path

    deps = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())["project"]["dependencies"]
    uvloop = next(d for d in deps if d.startswith("uvloop"))
    assert "win32" in uvloop and "CPython" in uvloop, "uvloop has no Windows or PyPy build"
    assert any(d.startswith("httptools") for d in deps)
