"""BACKEND-MEMORY: a worker the running master retires (a `TTOU`, the tool for shedding workers
without a restart, or a `HUP`) shuts down as gracefully as a deploy's stop.

gunicorn's heartbeat is sent only from uvicorn's main loop (`Server.on_tick`), so through the
shutdown the arbiter heard nothing and aborted the worker after its `timeout` (120 s, the last
beat up to 60 s earlier): an open staff event stream holds the shutdown for 100 s, so the worker
was SIGABRTed mid-shutdown, before the lifespan shutdown let the inbox drains finish. The
heartbeat stays on the event loop, so a worker whose loop is wedged is still killed.
"""
import asyncio
import time

import uvicorn

# Before anything imports gunicorn: app.main reads "gunicorn in sys.modules" as a production
# entrypoint (app/services/dev_login.py running_under_gunicorn) and refuses a keyless env.
import app.main  # noqa: F401  isort:skip
from app import uvicorn_worker


def _server(notify=lambda: None, heartbeat_for=150.0):
    return uvicorn_worker.DrainingServer(uvicorn.Config(app=None), notify, heartbeat_for)


def test_the_heartbeat_keeps_going_through_the_drains_wait(monkeypatch):
    """The lifespan shutdown waits for the inbox drains off the event loop
    (`asyncio.to_thread(stop_inbox_queue)`, app/main.py shutdown_event), and the heartbeat
    keeps beating all through it, then stops with the shutdown."""
    monkeypatch.setattr(uvicorn_worker.DrainingServer, "HEARTBEAT_EVERY", 0.05, raising=False)
    beats: list[float] = []
    window: dict[str, float] = {}

    async def stock_shutdown(self, sockets=None):
        window["start"] = time.monotonic()
        await asyncio.to_thread(time.sleep, 0.4)
        window["end"] = time.monotonic()

    monkeypatch.setattr(uvicorn.Server, "shutdown", stock_shutdown)

    asyncio.run(_server(notify=lambda: beats.append(time.monotonic())).shutdown())
    time.sleep(0.15)

    during = [t for t in beats if window["start"] <= t <= window["end"]]
    assert len(during) >= 4, beats
    assert all(t <= window["end"] + 0.06 for t in beats), "the heartbeat outlived the shutdown"


def test_a_wedged_event_loop_gets_no_heartbeat(monkeypatch):
    """The heartbeat proves the event loop is alive: a shutdown that blocks the loop must not
    be shielded from the arbiter's timeout, which is what kills a genuinely hung worker."""
    monkeypatch.setattr(uvicorn_worker.DrainingServer, "HEARTBEAT_EVERY", 0.05, raising=False)
    beats: list[float] = []
    window: dict[str, float] = {}

    async def stock_shutdown(self, sockets=None):
        window["start"] = time.monotonic()
        time.sleep(0.4)
        window["end"] = time.monotonic()

    monkeypatch.setattr(uvicorn.Server, "shutdown", stock_shutdown)

    asyncio.run(_server(notify=lambda: beats.append(time.monotonic())).shutdown())

    wedged = [t for t in beats if window["start"] + 0.1 < t < window["end"]]
    assert wedged == [], f"{len(wedged)} beats while the event loop was blocked"


def test_the_heartbeat_stops_at_its_bound(monkeypatch):
    """A shutdown that never ends must not keep a hung worker alive: past `heartbeat_for`
    (gunicorn's graceful_timeout) the beats stop and the arbiter's timeout takes over."""
    monkeypatch.setattr(uvicorn_worker.DrainingServer, "HEARTBEAT_EVERY", 0.05, raising=False)
    beats: list[float] = []

    async def stock_shutdown(self, sockets=None):
        await asyncio.sleep(0.6)

    monkeypatch.setattr(uvicorn.Server, "shutdown", stock_shutdown)

    started = time.monotonic()
    asyncio.run(_server(notify=lambda: beats.append(time.monotonic()), heartbeat_for=0.2).shutdown())

    assert beats, "no heartbeat at all"
    assert max(beats) - started <= 0.2 + 0.08, [round(t - started, 3) for t in beats]


def test_the_worker_serves_through_the_draining_server(monkeypatch, tmp_path):
    """gunicorn's worker class, run the way gunicorn runs it (`run()`), serves through a
    DrainingServer with its own heartbeat and gunicorn's graceful_timeout as the bound. Driven
    through `run()` so a rename of uvicorn's `_serve` fails here instead of silently skipping
    the override."""
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

    monkeypatch.setattr(uvicorn.Server, "serve", serve)

    worker.run()

    assert len(served) == 1 and isinstance(served[0], uvicorn_worker.DrainingServer), served
    assert served[0]._notify == worker.notify
    assert served[0]._heartbeat_for == 150


# ---- BACKEND-MEM-2 S3: a worker at its request limit drains like a signalled one
def test_the_request_limit_drains_without_a_reset_and_runs_the_lifespan_shutdown(monkeypatch):
    """The inbox drains stop in the app's lifespan shutdown (app/main.py shutdown_event -> stop_inbox_queue ->
    begin_shutdown); a request-limit exit reaches it like a signal does. A request on a connection accepted just
    before the limit closed the listener is still answered (the accept settle), not reset."""
    import socket
    import threading
    import urllib.request

    monkeypatch.setattr(uvicorn_worker.DrainingServer, "ACCEPT_SETTLE_SECONDS", 0.3)
    events: list[str] = []

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif msg["type"] == "lifespan.shutdown":
                    events.append("shutdown")
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    config = uvicorn.Config(app=app, port=0, limit_max_requests=1, log_level="warning")
    server = uvicorn_worker.DrainingServer(config, lambda: None, 5.0)
    t = threading.Thread(target=server.run)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    late = socket.create_connection(("127.0.0.1", port))  # accepted, request not sent yet
    assert urllib.request.urlopen(f"http://127.0.0.1:{port}/").read() == b"ok"  # reaches the limit
    time.sleep(0.15)  # the limit is seen and the listener closes; the late client sends now
    late.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    assert late.recv(100).startswith(b"HTTP/1.1 200")
    late.close()
    t.join(10)
    assert not t.is_alive() and events == ["shutdown"]
