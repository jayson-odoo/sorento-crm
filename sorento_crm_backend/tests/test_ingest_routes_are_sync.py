"""The external ingest routes must run in the threadpool, not on the event loop.

Production, 2026-09-07: `ingest_masters` was `async def` and called the
synchronous ingest service inline, so each 14-31s batch blocked its gunicorn
worker's event loop; one batch past 120s missed the arbiter heartbeat, the
worker was killed (WORKER TIMEOUT), nginx answered 502 and the ESB re-offered
5,000 rows. A plain `def` route is the fix; this pins it.
"""
import inspect

from app.api.v1.external import ingest


def test_ingest_routes_are_plain_def():
    for name in ("ingest_masters", "delete_records", "read_current_state"):
        fn = getattr(ingest, name)
        assert not inspect.iscoroutinefunction(fn), (
            f"{name} is async def: its synchronous service call would block the "
            "worker event loop for the whole batch (WORKER TIMEOUT -> nginx 502)"
        )
