"""BACKEND-MEM-2 S2: at most HEAVY_HANDLER_CONCURRENCY (default 1) heavy requests run at once in a worker.

Since API-NONBLOCKING (#1951) a `def` handler runs in anyio's 40-thread pool, so a worker can build several exports
or reports at once, and it keeps the memory of the busiest moment until it exits (+160 MB kept one at a time, +528
MB eight at once, +900-1,170 MB 24 at once, with no speed gained: documentation/plans/deploy/PLAN-backend-mem-2-30oct.md).
The turn covers the whole request, the response's serialization included. No database, no network."""
from __future__ import annotations

import asyncio
import threading
import time

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils import heavy_work


def _app(seen):
    """Two heavy routes and a light one; `seen` records the most heavy requests inside at once, counting the
    response's serialization (a value that is slow to encode)."""
    app = FastAPI()
    state = {"inside": 0}
    lock = threading.Lock()

    class Slow:
        def __init__(self):
            with lock:
                state["inside"] += 1
                seen["most"] = max(seen.get("most", 0), state["inside"])

    def leave():
        with lock:
            state["inside"] -= 1

    @app.get("/heavy/{n}")
    @heavy_work.heavy
    def heavy_route(n: int):
        Slow()
        time.sleep(0.05)
        return {"n": n}

    @app.post("/heavy-upload")
    @heavy_work.heavy
    def heavy_upload(payload: dict):
        Slow()
        time.sleep(0.05)
        return payload

    @app.get("/light")
    def light():
        return {"ok": True}

    @app.middleware("http")
    async def out(request, call_next):  # leaves after the body is sent: the turn must still be held
        response = await call_next(request)
        if request.url.path.startswith("/heavy"):
            leave()
        return response

    app.add_middleware(heavy_work.HeavyRouteLimit, routes=app.router.routes)
    return app


def _overlap(app, paths):
    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            rs = await asyncio.gather(
                *[c.post(p, json={"x": 1}) if p.endswith("upload") else c.get(p) for p in paths]
            )
        assert all(r.status_code == 200 for r in rs), [r.status_code for r in rs]

    asyncio.run(go())


def test_heavy_requests_run_one_at_a_time_by_default(monkeypatch):
    monkeypatch.delenv("HEAVY_HANDLER_CONCURRENCY", raising=False)
    seen: dict = {}
    _overlap(_app(seen), ["/heavy/1", "/heavy/2", "/heavy-upload", "/heavy/3"])
    assert seen["most"] == 1


def test_the_knob_allows_more_at_once(monkeypatch):
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "2")
    seen: dict = {}
    _overlap(_app(seen), [f"/heavy/{i}" for i in range(6)])
    assert seen["most"] == 2


def test_zero_turns_the_limit_off(monkeypatch):
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "0")
    seen: dict = {}
    _overlap(_app(seen), [f"/heavy/{i}" for i in range(4)])
    assert seen["most"] == 4


def test_a_light_route_never_waits_behind_a_heavy_one(monkeypatch):
    monkeypatch.delenv("HEAVY_HANDLER_CONCURRENCY", raising=False)
    seen: dict = {}
    app = _app(seen)

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            slow = asyncio.ensure_future(asyncio.gather(*[c.get(f"/heavy/{i}") for i in range(5)]))
            await asyncio.sleep(0.02)
            t = time.monotonic()
            r = await c.get("/light")
            light_took = time.monotonic() - t
            await slow
            return r.status_code, light_took

    code, took = asyncio.run(go())
    assert code == 200 and took < 0.2  # five heavy ones take 0.25 s one after another


def test_a_request_that_waits_too_long_gets_503_and_the_rest_still_run(monkeypatch):
    """Security review, 30 Oct: one slow request must not queue every other heavy request forever."""
    monkeypatch.delenv("HEAVY_HANDLER_CONCURRENCY", raising=False)
    monkeypatch.setenv("HEAVY_WAIT_SECONDS", "0")
    app = FastAPI()

    @app.get("/slow")
    @heavy_work.heavy
    def slow():
        time.sleep(0.3)
        return {"ok": True}

    app.add_middleware(heavy_work.HeavyRouteLimit, routes=app.router.routes)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            first = asyncio.ensure_future(c.get("/slow"))
            await asyncio.sleep(0.05)
            second = await c.get("/slow")
            return (await first).status_code, second

    first, second = asyncio.run(go())
    assert first == 200
    assert second.status_code == 503 and second.headers["retry-after"] == "5"


def test_the_turn_is_given_back_when_a_handler_raises(monkeypatch):
    monkeypatch.delenv("HEAVY_HANDLER_CONCURRENCY", raising=False)
    monkeypatch.setenv("HEAVY_WAIT_SECONDS", "1")
    app = FastAPI()

    @app.get("/boom")
    @heavy_work.heavy
    def boom():
        raise RuntimeError("zz")

    @app.get("/fine")
    @heavy_work.heavy
    def fine():
        return {"ok": True}

    app.add_middleware(heavy_work.HeavyRouteLimit, routes=app.router.routes)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/boom").status_code == 500
    assert client.get("/fine").status_code == 200


def test_a_bad_knob_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "x")
    monkeypatch.setenv("HEAVY_WAIT_SECONDS", "soon")
    assert heavy_work.concurrency() == 1 and heavy_work.wait_seconds() == 60


def test_the_marker_keeps_the_handler_as_it_is():
    def handler(item: str, limit: int = 5):
        return {"item": item, "limit": limit}

    assert heavy_work.heavy(handler) is handler and handler.heavy is True
    app = FastAPI()
    app.get("/zz/{item}")(handler)
    assert TestClient(app).get("/zz/a?limit=7").json() == {"item": "a", "limit": 7}


# ---- the handlers that wear it (PLAN-backend-mem-2-30oct.md S2): exports, reports and upload parsers that build or
# parse a large file or result in the request. Not LLM-bound handlers (chat turn, AI extract): they wait, not allocate.
# Not the reports the chatbot calls as MCP tools (report-ask, sales-report, outstanding-report): they are part of a
# chat turn with a 10 s budget, and must not queue behind an export. Not public portal routes: an outside caller
# must not be able to hold the staff's slot (security review, 30 Oct).
WRAPPED = {
    "app.api.v1.sales.targets.dealer_targets_template",
    "app.api.v1.sales.targets.import_dealer_targets",
    "app.api.v1.projects.sample_requests.print_request",
    "app.api.v1.projects.order_inquiries.export_order_inquiry_worklist",
    "app.api.v1.projects.order_inquiries.export_order_inquiry",
    "app.api.v1.projects.sales_orders.export_autocount_change_list",
    "app.api.v1.projects.quotation_documents.download_quotation_issue_pdf",
    "app.api.v1.projects.divergences.ingest_sales_order_file",
    "app.api.v1.order_management.orders.bulk_import_orders",
    "app.api.v1.order_management.orders.import_order_tracking",
    "app.api.v1.order_management.orders.import_delivery_order_detail",
    "app.api.v1.order_management.orders.get_top_selling",
    "app.api.v1.order_management.customers.import_customers",
    "app.api.v1.master_data.products.bulk_import_products",
    "app.api.v1.scm.reorder_levels.preview_level_import",
    "app.api.v1.scm.reorder_levels.apply_level_import",
    "app.api.v1.scm.fulfilment.export_consolidated_packing_list",
    "app.api.v1.scm.fulfilment.export_spo_worksheet",
    "app.api.v1.scm.fulfilment.preview_supplier_inventory",
    "app.api.v1.scm.fulfilment.apply_supplier_inventory",
    "app.api.v1.scm.outstanding_import.preview_outstanding_import",
    "app.api.v1.scm.purchase_history.preview_order_inquiry",
    "app.api.v1.scm.purchase_history.apply_order_inquiry",
    "app.api.v1.procurement.grn.import_grn_listing",
    "app.api.v1.procurement.grn.import_grn_lines",
    "app.api.v1.procurement.spo_allocations.import_spo_allocations",
    "app.api.v1.procurement.packing_lists.import_container_status",
    "app.api.v1.procurement.cost_price_changes.probe_price_list",
    "app.api.v1.procurement.cost_price_changes.upload_price_list",
    "app.api.v1.integrations.autocount_pull.download_pull",
    "app.api.v1.inventory.stock_position.export_stock_position",
    "app.api.v1.inventory.stock.export_stock_balance",
    "app.api.v1.inventory.stock.bulk_import_stock",
    "app.api.v1.system.modules_runtime.upload_module_zip",
    "app.api.v1.system.modules_runtime.export_module",
    "app.api.v1.user_management.contacts.import_contact_access_sheet",
    "app.api.v1.reports.reports.run_report",
    "app.api.v1.connector.query",
    "app.api.v1.list_query.export_rows",
}


def test_exactly_the_listed_handlers_are_heavy():
    from fastapi.routing import APIRoute

    import app.main

    found = {
        f"{r.endpoint.__module__}.{r.endpoint.__name__}"
        for r in app.main.app.routes
        if isinstance(r, APIRoute) and getattr(r.endpoint, "heavy", False)
    }
    assert found == WRAPPED
