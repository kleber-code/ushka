"""The production server: Uvicorn with an idle loop that does not burn CPU.

Stock Uvicorn wakes every worker 10 times a second (``main_loop`` sleeps
0.1 s) and, with several workers, wakes the supervisor twice a second to ping
each worker through a pipe. An idle app then costs about 1 s of CPU per minute.
Here:

- the worker ticks once a second (that is all the ``Date`` header needs);
- the supervisor sleeps until a worker dies (its process sentinel), a signal
  arrives, or the next health check, every ``HEALTHCHECK_EVERY`` seconds;
- a worker that is still starting (importing the app) is judged by its process
  being alive, not by the ping, for ``STARTUP_GRACE`` seconds, so a slow start
  is no longer mistaken for a hang and killed in a loop.

This module imports Uvicorn, so only ``ushka run`` imports it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from multiprocessing.connection import wait

from uvicorn.config import STARTUP_FAILURE, Config
from uvicorn.server import Server
from uvicorn.supervisors import multiprocess as _mp
from uvicorn.supervisors.multiprocess import SIGNALS, Multiprocess, Process

logger = logging.getLogger("uvicorn.error")

TICK = 1.0  # seconds between wake-ups of an idle worker
HEALTHCHECK_EVERY = 10.0  # seconds between pings of each worker
HEALTHCHECK_TIMEOUT = 30  # seconds a worker may take to answer a ping
STARTUP_GRACE = 90.0  # seconds a new worker is exempt from pings


class QuietServer(Server):
    """A Uvicorn server that wakes once a second instead of ten times."""

    async def main_loop(self) -> None:
        counter = 0
        should_exit = await self.on_tick(counter)
        while not should_exit:
            # on_tick refreshes the Date header when counter % 10 == 0.
            counter = (counter + 10) % 864000
            await asyncio.sleep(TICK)
            should_exit = await self.on_tick(counter)


class Worker(Process):
    """A worker process that runs a ``QuietServer`` and remembers when it started."""

    started_at: float = 0.0

    @property
    def server(self) -> Server:
        if self._server is None:
            self._server = QuietServer(config=self.config)
        return self._server

    def start(self) -> None:
        self.started_at = time.monotonic()
        super().start()

    def starting(self) -> bool:
        return time.monotonic() - self.started_at < STARTUP_GRACE


class Supervisor(Multiprocess):
    """Keeps the workers alive without polling them."""

    def __init__(self, config: Config, sockets: list[socket.socket]) -> None:
        super().__init__(config, sockets)
        self._wake_r, self._wake_w = socket.socketpair()
        self._wake_r.setblocking(False)
        self._wake_w.setblocking(False)
        for sig in SIGNALS:
            signal.signal(sig, self._on_signal)

    def _on_signal(self, sig: int, _frame: object) -> None:
        self.signal_queue.append(sig)
        try:
            self._wake_w.send(b"\0")
        except OSError:  # a full buffer already means "wake up"
            pass

    def _drain_wake(self) -> None:
        try:
            while self._wake_r.recv(4096):
                pass
        except OSError:
            pass

    def run(self) -> None:
        # Multiprocess builds workers through this module-level name (also for
        # SIGHUP restarts and SIGTTIN), so point it at ours while we run.
        original, _mp.Process = _mp.Process, Worker
        try:
            self._run()
        finally:
            _mp.Process = original
            self._wake_r.close()
            self._wake_w.close()

    def _run(self) -> None:
        logger.info("Started parent process [%s]", os.getpid())
        self.init_processes()
        last_check = time.monotonic()
        while not self.should_exit.is_set():
            sentinels = [p.process.sentinel for p in self.processes]
            wait([self._wake_r, *sentinels], timeout=HEALTHCHECK_EVERY)
            self._drain_wake()
            self.handle_signals()
            if self.should_exit.is_set():
                break
            now = time.monotonic()
            due = now - last_check >= HEALTHCHECK_EVERY
            if due:
                last_check = now
            self.keep_subprocess_alive(check_health=due)
        self.terminate_all()
        self.join_all()
        logger.info("Stopping parent process [%s]", os.getpid())

    def keep_subprocess_alive(self, check_health: bool = True) -> None:  # type: ignore[override]
        if self.should_exit.is_set():
            return
        for idx, process in enumerate(self.processes):
            alive = process.process.is_alive()
            if alive and check_health and not (isinstance(process, Worker) and process.starting()):
                alive = process.ping(self.config.timeout_worker_healthcheck)
            if alive:
                continue

            process.kill()  # dead or hung
            process.join()
            if process.exitcode == STARTUP_FAILURE:
                logger.error("Child process [%s] failed to start, stopping the parent process.", process.pid)
                self.should_exit.set()
                return
            if self.should_exit.is_set():
                return
            logger.info("Child process [%s] died", process.pid)
            replacement = Worker(self.config, self.sockets)
            replacement.start()
            self.processes[idx] = replacement


def run_server(app: str, *, host: str, port: int, workers: int, log_config: dict) -> None:
    """Serves `app` (``module:attribute``) until stopped. Several workers get a ``Supervisor``."""
    config = Config(
        app,
        host=host,
        port=port,
        workers=workers if workers > 1 else None,
        lifespan="on",
        log_config=log_config,
        # One reading of X-Forwarded-*: Ushka's own (`[security] trusted_proxies`,
        # see ushka.http.proxy). Uvicorn trusting 127.0.0.1 on its own as well
        # would rewrite scope["client"] and scope["scheme"] behind our back.
        proxy_headers=False,
        timeout_worker_healthcheck=HEALTHCHECK_TIMEOUT,
    )
    server = QuietServer(config)
    try:
        if config.workers > 1:
            Supervisor(config, [config.bind_socket()]).run()
        else:
            server.run()
    except KeyboardInterrupt:
        pass
    if config.workers == 1 and not server.started:
        sys.exit(STARTUP_FAILURE)


__all__ = ["QuietServer", "Supervisor", "Worker", "run_server"]
