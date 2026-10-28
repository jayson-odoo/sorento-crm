"""BACKEND-MEMORY: a worker that retires on its own (gunicorn `max_requests`, which is uvicorn's
request limit, or a `TTOU`) shuts down as gracefully as a deploy's stop.

Two gaps in uvicorn's stock shutdown, both read from the installed code:
- the request limit ends the main loop with no signal, so the chatbot inbox drains, which stop
  taking rows AT the signal (IQ-28, app/tasks/chat_turns.py), kept taking rows for the whole
  connection wait (up to 100 s);
- gunicorn's heartbeat is sent only from uvicorn's main loop (`Server.on_tick`), so through the
  shutdown the arbiter heard nothing and aborted the worker after its `timeout` (120 s, the last
  beat up to 60 s earlier), mid-row, before the lifespan shutdown let the drains finish.
"""
import asyncio
import time

import uvicorn

# Before anything imports gunicorn: app.main reads "gunicorn in sys.modules" as a production
# entrypoint (app/services/dev_login.py running_under_gunicorn) and refuses a keyless env.
import app.main  # noqa: F401  isort:skip
from app import uvicorn_worker
from app.tasks import chat_turns


def _server(notify=lambda: None, heartbeat_for=150.0):
    return uvicorn_worker.DrainingServer(uvicorn.Config(app=None), notify, heartbeat_for)


def test_shutdown_stops_the_inbox_before_waiting_on_connections(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(chat_turns, "begin_inbox_shutdown", lambda: calls.append("inbox stops"), raising=False)

    async def stock_shutdown(self, sockets=None):
        calls.append("connection wait + lifespan shutdown")

    monkeypatch.setattr(uvicorn.Server, "shutdown", stock_shutdown)

    asyncio.run(_server().shutdown())

    assert calls == ["inbox stops", "connection wait + lifespan shutdown"]


def test_the_heartbeat_keeps_going_while_the_shutdown_blocks_the_loop(monkeypatch):
    """The lifespan shutdown blocks the event loop (stop_inbox_queue waits on the drains), so
    the heartbeat cannot be an asyncio task: it must still beat while the loop is blocked."""
    monkeypatch.setattr(chat_turns, "begin_inbox_shutdown", lambda: None, raising=False)
    monkeypatch.setattr(uvicorn_worker.DrainingServer, "HEARTBEAT_EVERY", 0.05, raising=False)
    beats: list[float] = []
    window: dict[str, float] = {}

    async def stock_shutdown(self, sockets=None):
        window["start"] = time.monotonic()
        time.sleep(0.4)
        window["end"] = time.monotonic()

    monkeypatch.setattr(uvicorn.Server, "shutdown", stock_shutdown)

    asyncio.run(_server(notify=lambda: beats.append(time.monotonic())).shutdown())
    time.sleep(0.15)

    during = [t for t in beats if window["start"] <= t <= window["end"]]
    assert len(during) >= 4, beats
    assert all(t <= window["end"] + 0.06 for t in beats), "the heartbeat outlived the shutdown"


def test_the_heartbeat_stops_at_its_bound(monkeypatch):
    """A shutdown that never ends must not keep a hung worker alive: past `heartbeat_for`
    (gunicorn's graceful_timeout) the beats stop and the arbiter's timeout takes over."""
    monkeypatch.setattr(chat_turns, "begin_inbox_shutdown", lambda: None, raising=False)
    monkeypatch.setattr(uvicorn_worker.DrainingServer, "HEARTBEAT_EVERY", 0.05, raising=False)
    beats: list[float] = []

    async def stock_shutdown(self, sockets=None):
        time.sleep(0.6)

    monkeypatch.setattr(uvicorn.Server, "shutdown", stock_shutdown)

    started = time.monotonic()
    asyncio.run(_server(notify=lambda: beats.append(time.monotonic()), heartbeat_for=0.2).shutdown())

    assert beats, "no heartbeat at all"
    assert max(beats) - started <= 0.2 + 0.08, [round(t - started, 3) for t in beats]


def test_the_worker_serves_through_the_draining_server(monkeypatch, tmp_path):
    """gunicorn's worker class builds a DrainingServer with its own heartbeat and gunicorn's
    graceful_timeout as the bound."""
    from gunicorn.config import Config
    from gunicorn.glogging import Logger

    cfg = Config()
    cfg.set("graceful_timeout", 150)
    cfg.set("worker_tmp_dir", str(tmp_path))
    worker = uvicorn_worker.InboxUvicornWorker(1, 0, [], None, 60, cfg, Logger(cfg))
    worker.wsgi = object()
    served = []

    async def serve(self, sockets=None):
        served.append(self)
        self.started = True

    monkeypatch.setattr(uvicorn_worker.DrainingServer, "serve", serve, raising=False)

    asyncio.run(worker._serve())

    assert len(served) == 1 and isinstance(served[0], uvicorn_worker.DrainingServer)
    assert served[0]._notify == worker.notify
    assert served[0]._heartbeat_for == 150
