"""BACKEND-MEM-2 S2: at most HEAVY_HANDLER_CONCURRENCY (default 1) heavy handlers run at once in a worker.

Since API-NONBLOCKING (#1951) a `def` handler runs in anyio's 40-thread pool, so a worker can build several exports
or reports at once, and it keeps the memory of the busiest moment until it exits (+160 MB kept one at a time, +528
MB eight at once, +900-1,170 MB 24 at once, with no speed gained: documentation/plans/deploy/PLAN-backend-mem-2-30oct.md).
No database, no network."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils import heavy_work


@pytest.fixture(autouse=True)
def one_at_a_time(monkeypatch):
    monkeypatch.setattr(heavy_work, "_semaphore", threading.BoundedSemaphore(1))


def _overlap(fn, n=4):
    """Run `fn` on n threads at once; return the most calls seen inside it at the same moment."""
    inside = [0]
    most = [0]
    lock = threading.Lock()

    def body():
        with lock:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with lock:
            inside[0] -= 1

    wrapped = fn(body)
    threads = [threading.Thread(target=wrapped) for _ in range(n)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    return most[0]


def test_heavy_handlers_run_one_at_a_time_by_default():
    assert _overlap(heavy_work.heavy) == 1


def test_the_knob_allows_more_at_once(monkeypatch):
    monkeypatch.setattr(heavy_work, "_semaphore", threading.BoundedSemaphore(2))
    assert _overlap(heavy_work.heavy) == 2


def test_zero_turns_the_limit_off(monkeypatch):
    monkeypatch.setattr(heavy_work, "_semaphore", None)
    assert _overlap(heavy_work.heavy) == 4


def test_the_knob_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "3")
    assert heavy_work._from_env()._value == 3  # noqa: SLF001 - BoundedSemaphore's own counter
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "0")
    assert heavy_work._from_env() is None
    monkeypatch.delenv("HEAVY_HANDLER_CONCURRENCY")
    assert heavy_work._from_env()._value == 1  # noqa: SLF001


def test_a_heavy_handler_calling_another_does_not_deadlock():
    @heavy_work.heavy
    def inner():
        return "inner"

    @heavy_work.heavy
    def outer():
        return inner()

    done: list[str] = []
    t = threading.Thread(target=lambda: done.append(outer()))
    t.start()
    t.join(5)
    assert done == ["inner"]


def test_the_slot_is_released_when_the_handler_raises():
    @heavy_work.heavy
    def boom():
        raise ValueError("zz")

    with pytest.raises(ValueError):
        boom()
    assert heavy_work._semaphore.acquire(blocking=False)  # noqa: SLF001
    heavy_work._semaphore.release()  # noqa: SLF001


def test_an_async_handler_is_refused():
    """An `async def` runs on the event loop: waiting on the semaphore there would stall every request."""
    with pytest.raises(TypeError):

        @heavy_work.heavy
        async def handler():
            return 1


def test_fastapi_still_sees_the_handler_signature():
    app = FastAPI()

    @app.get("/zz/{item}")
    @heavy_work.heavy
    def handler(item: str, limit: int = 5):
        return {"item": item, "limit": limit}

    assert TestClient(app).get("/zz/a?limit=7").json() == {"item": "a", "limit": 7}


# ---- the handlers that wear it (PLAN-backend-mem-2-30oct.md S2): exports, reports and upload parsers that build or
# parse a large file or result in the request. Not LLM-bound handlers (chat turn, AI extract): they wait, not allocate.
WRAPPED = {
    "app.api.v1.sales.targets.dealer_targets_template",
    "app.api.v1.sales.targets.import_dealer_targets",
    "app.api.v1.projects.sample_requests.print_request",
    "app.api.v1.projects.order_inquiries.export_order_inquiry_worklist",
    "app.api.v1.projects.order_inquiries.export_order_inquiry",
    "app.api.v1.projects.sales_orders.export_autocount_change_list",
    "app.api.v1.projects.divergences.ingest_sales_order_file",
    "app.api.v1.public.portal_sample_request.portal_pdf",
    "app.api.v1.order_management.report_ask.report_ask",
    "app.api.v1.order_management.orders.bulk_import_orders",
    "app.api.v1.order_management.orders.import_order_tracking",
    "app.api.v1.order_management.orders.import_delivery_order_detail",
    "app.api.v1.order_management.orders.get_outstanding_report",
    "app.api.v1.order_management.orders.get_sales_report",
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
