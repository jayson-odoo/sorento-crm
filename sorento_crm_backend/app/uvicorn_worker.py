"""The gunicorn worker class (gunicorn.conf.py `worker_class`): uvicorn's own, with a bounded
graceful shutdown.

CHAT-INBOX-QUEUE (IQ-28): without `timeout_graceful_shutdown` uvicorn waits for EVERY open
connection before the lifespan shutdown runs, and a staff event stream never closes, so the
app's shutdown handler (which lets the inbox drains finish their row) was never reached
before gunicorn's SIGKILL. 100 s lets a sync mode-off `/chat/turn` (n8n's 90 s budget)
finish; the budget against `graceful_timeout` is written out in
`app/tasks/chat_turns.py` (INBOX_SHUTDOWN_GRACE_SECONDS).

BACKEND-MEMORY: the master also retires single workers while it keeps running (`TTOU`, `HUP`),
and `DrainingServer` makes that shutdown as graceful as a deploy's stop.
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Callable

from gunicorn.arbiter import Arbiter
from uvicorn import Config, Server
from uvicorn.workers import UvicornWorker

TIMEOUT_GRACEFUL_SHUTDOWN_SECONDS = 100


class DrainingServer(Server):
    """uvicorn's server for a worker the running master retires (BACKEND-MEMORY): a `TTOU` or `HUP`
    sends the worker SIGTERM but gunicorn's master keeps checking its heartbeat against `timeout`
    (120 s), and uvicorn sends that heartbeat only from its main loop (`Server.on_tick`). An open
    staff event stream holds the shutdown for 100 s, so the master SIGABRTed the worker 60-100 s
    in, before the lifespan shutdown let the inbox drains finish. A task on the event loop keeps
    beating until the shutdown returns, never past `heartbeat_for` (gunicorn's graceful_timeout).
    On the loop on purpose: the drains wait runs off it (`asyncio.to_thread`, app/main.py), so the
    beats go on through it, while a wedged loop stops beating and the master still kills it. A
    deploy's stop is unaffected: the master does not check heartbeats while it stops."""

    HEARTBEAT_EVERY = 5.0

    def __init__(self, config: Config, notify: Callable[[], None], heartbeat_for: float) -> None:
        super().__init__(config=config)
        self._notify = notify
        self._heartbeat_for = heartbeat_for

    async def shutdown(self, sockets=None) -> None:
        beat = asyncio.ensure_future(self._beat())
        try:
            await super().shutdown(sockets)
        finally:
            beat.cancel()

    async def _beat(self) -> None:
        deadline = time.monotonic() + self._heartbeat_for
        while time.monotonic() < deadline:
            self._notify()
            await asyncio.sleep(min(self.HEARTBEAT_EVERY, max(0.0, deadline - time.monotonic())))


class InboxUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "timeout_graceful_shutdown": TIMEOUT_GRACEFUL_SHUTDOWN_SECONDS}

    async def _serve(self) -> None:
        # uvicorn's own `_serve`, with DrainingServer in place of Server.
        self.config.app = self.wsgi
        server = DrainingServer(self.config, self.notify, self.cfg.graceful_timeout)
        self._install_sigquit_handler()
        await server.serve(sockets=self.sockets)
        if not server.started:
            sys.exit(Arbiter.WORKER_BOOT_ERROR)
