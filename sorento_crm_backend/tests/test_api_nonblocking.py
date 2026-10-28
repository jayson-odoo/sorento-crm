"""API-NONBLOCKING: a slow report / export / PDF request must not freeze its worker.

FastAPI runs an ``async def`` handler ON the worker's event loop and a plain ``def`` handler in
the threadpool. A report declared ``async def`` that never awaits holds the loop for its whole
run, so every other request on that worker (``/health`` included) waits behind it; with 4
gunicorn workers, 4 slow reports at once stall the API
(`documentation/plans/ops/PLAN-api-nonblocking-28oct.md`).

Each case drives the real route through the real app on ONE event loop (httpx's ASGI
transport, the same loop a uvicorn worker has), with every top-level dependency stubbed and the
database replaced by a stand-in that sleeps on first touch, the way a slow query does. While
that request is still running, ``GET /health`` on the same loop must answer.

Red on main for every case: the light request finishes only after the slow one.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid

import httpx
import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_db

SLOW_SECONDS = 1.5

# Set (from whatever thread runs the handler) the moment the slow part starts.
_entered = threading.Event()
_entered_at: dict[str, float] = {}


def _block() -> None:
    if not _entered.is_set():
        _entered_at["t"] = time.monotonic()
        _entered.set()
    time.sleep(SLOW_SECONDS)


class _SlowDB:
    """Every attribute touch costs SLOW_SECONDS of blocking time (a slow query), then fails.

    The failure is fine: the case measures the loop, not the response."""

    def __init__(self) -> None:
        self.touched = 0

    def __getattr__(self, name):
        self.touched += 1
        _block()
        raise RuntimeError("slow-db stand-in")


def _superadmin() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "email": "zzt-nonblocking@test.com",
        "name": "ZZT Nonblocking",
        "roles": ["superadmin"],
        "role": "superadmin",
        "permissions": [],
        "status": "ACTIVE",
    }


def _route(module: str, name: str):
    for r in app.routes:
        ep = getattr(r, "endpoint", None)
        if ep is not None and ep.__module__ == module and ep.__name__ == name:
            return r
    raise AssertionError(f"route {module}.{name} not mounted")


def _xlsx() -> bytes:
    """A real one-cell workbook: the upload routes read and macro-strip it before any query."""
    import io

    from openpyxl import Workbook

    buf = io.BytesIO()
    wb = Workbook()
    wb.active["A1"] = "zzt"
    wb.save(buf)
    return buf.getvalue()


def _upload() -> dict:
    return {"files": {"file": ("zzt.xlsx", _xlsx(), "application/octet-stream")}}


# (module, endpoint, query string or None, request kwargs, path params, slow hook)
# A slow hook names a callable to replace with a blocking sleep, for a handler whose slow part
# is not the database.
CASES = [
    (
        "app.api.v1.order_management.orders",
        "get_sales_report",
        "product_code=ZZT-SKU&date_from=2026-01-01&date_to=2026-01-31",
        {},
        {},
        None,
    ),
    ("app.api.v1.order_management.orders", "get_outstanding_report", "product_code=ZZT-SKU", {}, {}, None),
    ("app.api.v1.projects.quotation_documents", "download_quotation_issue_xlsx", None, {}, {}, None),
    ("app.api.v1.projects.sales_orders", "export_autocount_change_list", None, {}, {}, None),
    ("app.api.v1.system.jobs", "export_job_rows", None, {}, {}, None),
    (
        "app.api.v1.system.modules_runtime",
        "export_module",
        None,
        {},
        {"module_key": "zzt"},
        ("app.services.module_export_service", "build_export_zip"),
    ),
    ("app.api.v1.complaints.complaints", "export_complaint_pdf", None, {}, {}, None),
    (
        "app.api.v1.marketing.promotions",
        "export_promotions_pdf",
        None,
        {"json": {"promotion_ids": [str(uuid.uuid4())]}},
        {},
        None,
    ),
    ("app.api.v1.procurement.stock_inquiries", "export_stock_inquiry_pdf", None, {}, {}, None),
    # Slowest on prod (owner, 28 Oct 14:35 MYT): the audit log listing (36.7 s, a COUNT over
    # all of audit_logs) and the activity timeline (the same table, COUNT plus two DISTINCTs).
    ("app.api.v1.audit.audit_logs", "get_audit_logs", None, {}, {}, None),
    ("app.api.v1.audit.activity", "get_activity", None, {}, {}, None),
    # Crew's prod trace: the order-inquiry read walks the goods chain (an spo_allocations UNION).
    ("app.api.v1.projects.order_inquiries", "get_sales_order_inquiry", None, {}, {}, None),
    # AN-2: uploads that awaited the file, then parsed and wrote on the loop. Order tracking
    # was 77.1 s on prod: validate_only runs the whole tracking import in the request.
    (
        "app.api.v1.order_management.orders",
        "import_order_tracking",
        "validate_only=true",
        _upload(),
        {},
        ("app.api.v1.order_management.orders", "OrderService"),
    ),
    ("app.api.v1.order_management.customers", "import_customers", None, _upload(), {}, None),
    ("app.api.v1.procurement.grn", "import_grn_lines", None, _upload(), {}, None),
    (
        "app.api.v1.scm.outstanding_import",
        "preview_outstanding_import",
        None,
        _upload(),
        {"kind": "sales-orders"},
        None,
    ),
]


def _url(route, query, params) -> str:
    path = route.path
    for p in route.param_convertors:
        path = path.replace("{" + p + "}", params.get(p) or str(uuid.uuid4()))
    return path + (f"?{query}" if query else "")


@pytest.fixture
def stubbed():
    """Stubs every top-level dependency of the route under test; restores the overrides."""
    saved = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


async def _race(method: str, url: str, kwargs: dict, light_path: str = "/health"):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        warm = await client.get("/health")  # first call pays the probes' cold start
        assert warm.status_code == 200, warm.text
        done: dict[str, float] = {}

        async def slow():
            await client.request(method, url, **kwargs)
            done["slow"] = time.monotonic()

        async def light():
            # Only once the slow request is inside its slow part. If that part holds the
            # loop, this poll itself cannot run until it is over.
            while not _entered.is_set():
                await asyncio.sleep(0.005)
            r = await client.get(light_path)
            done["light"] = time.monotonic()
            assert r.status_code == 200, r.text

        _entered.clear()
        _entered_at.clear()
        await asyncio.wait_for(asyncio.gather(slow(), light()), timeout=30)
        return _entered_at["t"], done


@pytest.mark.parametrize("module,name,query,kwargs,params,hook", CASES, ids=[c[1] for c in CASES])
def test_a_slow_report_does_not_freeze_the_worker(
    stubbed, monkeypatch, module, name, query, kwargs, params, hook
):
    route = _route(module, name)
    slow_db = _SlowDB()
    for dep in route.dependant.dependencies:
        if dep.call is get_db:
            app.dependency_overrides[get_db] = lambda: slow_db
        else:
            app.dependency_overrides[dep.call] = _superadmin
    hooked = {"calls": 0}
    if hook is not None:
        import importlib

        def _slow(*_a, **_k):
            hooked["calls"] += 1
            _block()
            raise RuntimeError("slow stand-in")

        monkeypatch.setattr(importlib.import_module(hook[0]), hook[1], _slow)

    method = sorted(route.methods)[0]
    started, done = asyncio.run(_race(method, _url(route, query, params), kwargs))

    # Not vacuous: the slow part really ran, and really took its time.
    assert slow_db.touched + hooked["calls"] >= 1, "the request never reached its slow part"
    assert done["slow"] - started >= SLOW_SECONDS
    # The property: measured from the moment the slow part began, the light request on the
    # same loop answered while the slow one still ran.
    light = done["light"] - started
    assert light < SLOW_SECONDS / 2, (
        f"/health answered {light:.2f}s after {name} entered its slow part "
        f"(which took {done['slow'] - started:.2f}s): {name} holds the event loop"
    )
    assert done["light"] < done["slow"]


def test_a_slow_database_check_in_health_does_not_freeze_the_worker(monkeypatch):
    """AN-3: `/health`'s own DB check ran on the loop before its one await, so a starved
    connection checkout froze the worker it was meant to vouch for."""
    import app.database as database

    slow_db = _SlowDB()
    real = database.SessionLocal

    async def _go():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Warm the probe cache with the real database, so /health/deep reads it from memory.
            assert (await client.get("/health")).status_code == 200
            monkeypatch.setattr(database, "SessionLocal", lambda: slow_db)
            done: dict[str, float] = {}

            async def slow():
                await client.get("/health")
                done["slow"] = time.monotonic()

            async def light():
                while not _entered.is_set():
                    await asyncio.sleep(0.005)
                await client.get("/health/deep")
                done["light"] = time.monotonic()

            _entered.clear()
            _entered_at.clear()
            await asyncio.wait_for(asyncio.gather(slow(), light()), timeout=30)
            monkeypatch.setattr(database, "SessionLocal", real)
            return _entered_at["t"], done

    started, done = asyncio.run(_go())
    assert slow_db.touched >= 1
    assert done["light"] - started < SLOW_SECONDS / 2, (
        f"/health/deep answered {done['light'] - started:.2f}s after /health's DB check began"
    )
    assert done["light"] < done["slow"]
