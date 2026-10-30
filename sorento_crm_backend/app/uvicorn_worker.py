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
import os
import signal
import sys
import time
from typing import Callable, Optional

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
    ACCEPT_SETTLE_SECONDS = 1.0
    #: How long a worker at its request limit keeps serving while it waits to see its replacement forked.
    REPLACEMENT_WAIT_SECONDS = 30.0

    def __init__(
        self, config: Config, notify: Callable[[], None], heartbeat_for: float,
        ask_replacement: Optional[Callable[[], None]] = None,
        replacement_up: Callable[[], bool] = lambda: True,
    ) -> None:
        super().__init__(config=config)
        self._notify = notify
        self._heartbeat_for = heartbeat_for
        self._ask_replacement = ask_replacement
        self._replacement_up = replacement_up
        self._waiting_since: Optional[float] = None

    async def on_tick(self, counter: int) -> bool:
        """BACKEND-MEM-2 S3: a worker that reaches `max_requests` (not a signal: a deploy's stop or a `TTOU` retires
        it on purpose) asks the master for its replacement (SIGTTIN) and keeps serving until it sees that worker
        forked, at most `REPLACEMENT_WAIT_SECONDS`; only then does it drain, so the colour never runs a worker short.
        Waiting also orders the master's work: the TTIN is handled before this worker exits, so gunicorn.conf.py
        `child_exit` always sees the extra worker it takes back (draining at once let the exit win the race and left
        the count one high). The drain is a signal's: the lifespan shutdown stops the inbox (app/main.py)."""
        should_exit = await super().on_tick(counter)
        if self._waiting_since is not None:
            if self.should_exit:  # a signal while waiting
                return True
            return self._replacement_up() or time.monotonic() - self._waiting_since > self.REPLACEMENT_WAIT_SECONDS
        # uvicorn's request limit returns True without setting `should_exit`; a signal sets it.
        limit = self.config.limit_max_requests
        if (
            should_exit and not self.should_exit and self._ask_replacement is not None
            and limit is not None and self.server_state.total_requests >= limit
        ):
            self._waiting_since = time.monotonic()
            self.config.limit_max_requests = None  # this worker is past it; uvicorn need not log it every tick
            self._ask_replacement()
            return self._replacement_up()
        return should_exit

    async def shutdown(self, sockets=None) -> None:
        beat = asyncio.ensure_future(self._beat())
        try:
            # BACKEND-MEM-2 S3: stop accepting first and give a connection accepted just before that a moment to send
            # its request. uvicorn's shutdown closes every connection with no request in progress yet, so a client
            # whose bytes were still in flight got a connection reset (4 of 600 requests over 10 recycles, measured).
            servers = getattr(self, "servers", [])  # set by `startup`; a server that never started has none
            for server in servers:
                server.close()
            if servers:
                await asyncio.sleep(self.ACCEPT_SETTLE_SECONDS)
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
        server = DrainingServer(
            self.config, self.notify, self.cfg.graceful_timeout,
            ask_replacement=lambda: os.kill(self.ppid, signal.SIGTTIN), replacement_up=self._replacement_up,
        )
        self._install_sigquit_handler()
        await server.serve(sockets=self.sockets)
        if not server.started:
            sys.exit(Arbiter.WORKER_BOOT_ERROR)

    def _replacement_up(self) -> bool:
        """True once the master has as many other workers as it is configured for, i.e. this one's replacement has
        forked (BACKEND-MEM-2 S3). Reads /proc; where there is none, True (drain at once, as before)."""
        try:
            others = 0
            for entry in os.listdir("/proc"):
                if entry.isdigit() and int(entry) != self.pid:
                    try:
                        with open(f"/proc/{entry}/stat") as f:
                            ppid = int(f.read().rsplit(")", 1)[1].split()[1])
                    except (OSError, ValueError, IndexError):
                        continue
                    others += ppid == self.ppid
            return others >= self.cfg.workers
        except OSError:
            return True
