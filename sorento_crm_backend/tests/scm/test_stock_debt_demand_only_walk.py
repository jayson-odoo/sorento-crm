"""STOCKDEBT-PERF PR1 (AC-SDP-1..5): the default board walks only products that can owe.

WRITTEN BEFORE THE IMPLEMENTATION EXISTS (Phase 2 is test-first). Plan:
documentation/plans/scm/stockdebt-perf-acceptance-criteria.md, section PR1.

Five products at one flagged bin: P_DEBT (open SO line, no supply), P_COVERED (open SO line
and stock), P_STOCK (stock only), P_PO (open PO line only), P_SPO (open SPO allocation only).
Postgres only; every test seeds its own chain.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_routes import (
    _client,
    _demand,
    _months_ahead,
    _product,
    _spo,
    _stock,
    _u,
    _warehouse,
)

pytestmark = requires_pg

LOGGER = "app.services.scm.stock_debt_service"


def _seed(db):
    marker = f"ZZTDOW{_u()[:6]}".upper()
    bin_ = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    bin_.segment = "project"
    db.flush()
    due = _months_ahead(2)
    p = {
        "debt": _product(db, f"{marker}-DEBT"),
        "covered": _product(db, f"{marker}-COVERED"),
        "stock": _product(db, f"{marker}-STOCK"),
        "po": _product(db, f"{marker}-PO"),
        "spo": _product(db, f"{marker}-SPO"),
    }
    _demand(db, p["debt"], bin_, qty=5, required_date=due, so_number=f"{marker}-SO1")
    _demand(db, p["covered"], bin_, qty=3, required_date=due, so_number=f"{marker}-SO2")
    _stock(db, p["covered"], bin_, 10)
    _stock(db, p["stock"], bin_, 10)
    po = PurchaseOrder(
        id=_u(), po_number=f"{marker}-PO", supplier_id=None,
        issue_date=date(2026, 9, 1), status="active", company_id=SORENTO_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=_u(), purchase_order_id=po.id, product_id=p["po"].id,
            warehouse_id=bin_.id, qty_ordered=Decimal("7"), qty_received=Decimal("0"),
            line_status="open", company_id=SORENTO_COMPANY_ID,
        )
    )
    _spo(db, p["spo"], bin_, qty=9, arrives=_months_ahead(1))
    db.flush()
    return marker, bin_, p


def _svc(db):
    from app.services.scm.stock_debt_service import StockDebtService

    return StockDebtService(db)


def _spy_assign(monkeypatch):
    import app.services.scm.stock_debt_service as mod

    walked: list = []
    real = mod.assign

    def wrapper(product_id, *a, **k):
        walked.append(str(product_id))
        return real(product_id, *a, **k)

    monkeypatch.setattr(mod, "assign", wrapper)
    return walked


def _ids(p, *names):
    return {str(p[n].id) for n in names}


# --------------------------------------------------------------------------- AC-SDP-1


def test_default_view_walks_only_products_with_open_demand(scm_app, monkeypatch):
    """AC-SDP-1: only_debt=True, projected=False walks P_DEBT and P_COVERED, never the
    stock-only, PO-only or SPO-only product."""
    app, db = _client(scm_app)
    marker, _bin, p = _seed(db)
    walked = _spy_assign(monkeypatch)

    body = _svc(db).list(query=marker, only_debt=True, projected=False)

    assert set(walked) == _ids(p, "debt", "covered"), walked
    assert not set(walked) & _ids(p, "stock", "po", "spo")
    assert [r["product_code"] for r in body["data"]] == [p["debt"].product_code]


# --------------------------------------------------------------------------- AC-SDP-2


def test_per_product_reads_skip_the_products_the_walk_skips(scm_app, monkeypatch):
    """AC-SDP-2: supply, demand, holds, lead times, stand-in floors, last supplier and aux
    maps are never asked about P_STOCK, P_PO or P_SPO on the default view."""
    from app.services.project_supply_service import ProjectSupplyService
    from app.services.scm.stock_debt_service import StockDebtService

    app, db = _client(scm_app)
    marker, _bin, p = _seed(db)
    seen: dict = {}

    def wrap(cls, name):
        real = getattr(cls, name)

        def wrapper(self, product_ids, *a, **k):
            ids = [str(x) for x in product_ids]
            seen.setdefault(name, []).extend(ids)
            return real(self, ids, *a, **k)

        monkeypatch.setattr(cls, name, wrapper)

    for name in ("_supply", "_demand", "_holds", "_stand_in_floors",
                 "_last_supplier_map", "_aux_maps"):
        wrap(StockDebtService, name)
    wrap(ProjectSupplyService, "lead_times")

    _svc(db).list(query=marker, only_debt=True, projected=False)

    forbidden = _ids(p, "stock", "po", "spo")
    assert {"_supply", "_demand", "lead_times"} <= set(seen), sorted(seen)
    for name, ids in seen.items():
        assert not set(ids) & forbidden, f"{name} read {set(ids) & forbidden}"


# --------------------------------------------------------------------------- AC-SDP-3


def test_every_candidate_is_walked_with_only_debt_off_or_projected_on(scm_app, monkeypatch):
    """AC-SDP-3: today's behaviour is kept for only_debt=False and for projected=True."""
    app, db = _client(scm_app)
    marker, _bin, p = _seed(db)
    everyone = _ids(p, "debt", "covered", "stock", "po", "spo")
    walked = _spy_assign(monkeypatch)

    body = _svc(db).list(query=marker, only_debt=False, projected=False)
    assert set(walked) == everyone, walked
    assert {r["product_code"] for r in body["data"]} == {x.product_code for x in p.values()}

    walked.clear()
    _svc(db).list(query=marker, only_debt=True, projected=True)
    assert set(walked) == everyone, walked


# --------------------------------------------------------------------------- AC-SDP-4


def test_default_view_numbers_are_pinned(scm_app):
    """AC-SDP-4: the default board's rows, axis, totals, suppliers, sheet_counts and total,
    equal explicit values computed from the seed (passes before and after the change)."""
    from app.services.scm.supply_assignment import month_key

    app, db = _client(scm_app)
    marker, _bin, p = _seed(db)
    svc = _svc(db)

    body = svc.list(query=marker, only_debt=True, projected=False)
    assert body["pagination"] == {"total": 1, "page": 1, "limit": 50}
    assert body["suppliers"] == [], body["suppliers"]
    due_key = month_key(_months_ahead(2))
    assert body["months"][0] == month_key(date.today())
    assert body["months"][-1] == due_key

    (row,) = body["data"]
    assert row["product_id"] == str(p["debt"].id)
    assert row["product_code"] == p["debt"].product_code
    assert row["product_name"] == f"{p['debt'].product_code} basin"
    assert row["supplier_id"] is None and row["supplier_name"] is None
    assert row["tba"] == 0
    assert row["undated"] == 0
    assert row["unlocated"] == 0
    assert row["total"] == -5
    assert [m["key"] for m in row["months"]] == body["months"]
    balances = {m["key"]: m["balance"] for m in row["months"]}
    assert balances[due_key] == -5
    assert sum(v for k, v in balances.items() if k != due_key) == 0
    assert row["pool_on_hand"] == 0
    assert row["pool_po_qty"] == 0
    assert row["pool_incoming_qty"] == 0
    assert row["dealer_outstanding"] == 0

    totals = body["totals"]
    assert totals["total"] == -5
    assert totals["tba"] == 0
    assert totals["pool_on_hand"] == 0
    assert totals["pool_po_qty"] == 0
    assert totals["pool_incoming_qty"] == 0
    assert totals["dealer_outstanding"] == 0
    assert totals["unlocated"] == 0 and totals["undated"] == 0
    assert totals["months"][due_key] == -5
    assert sum(v for k, v in totals["months"].items() if k != due_key) == 0
    assert body["sheet_counts"] == {"supplier": 1, "category": 1, "supplier_category": 1}

    # the same product set with only_debt off: the other four are present and untouched
    everything = svc.list(query=marker, only_debt=False, projected=False)
    assert everything["pagination"]["total"] == 5
    by_code = {r["product_code"]: r for r in everything["data"]}
    assert set(by_code) == {x.product_code for x in p.values()}
    assert by_code[p["debt"].product_code]["total"] == -5
    assert by_code[p["covered"].product_code]["total"] >= 0
    for name in ("stock", "po", "spo"):
        assert by_code[p[name].product_code]["total"] >= 0, name
    assert everything["sheet_counts"] == {"supplier": 1, "category": 1, "supplier_category": 1}
    assert everything["totals"]["total"] == sum(r["total"] for r in everything["data"])
    assert everything["months"][0] == body["months"][0]


# --------------------------------------------------------------------------- AC-SDP-5


def test_one_timing_log_line_per_board_build(scm_app, caplog):
    """AC-SDP-5: ONE INFO line, counts and milliseconds only, no product id or code."""
    app, db = _client(scm_app)
    marker, _bin, p = _seed(db)
    svc = _svc(db)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        svc.list(query=marker, only_debt=True, projected=False)

    records = [r for r in caplog.records if r.name == LOGGER]
    lines = [r.getMessage() for r in records if r.getMessage().startswith("stock_debt.board")]
    assert len(lines) == 1, [r.getMessage() for r in records]
    assert len([r for r in records if r.levelno == logging.INFO]) == 1
    line = lines[0]
    assert "candidates=5 walked=2 rows=1" in line, line
    for field in ("products_ms", "assignments_ms", "total_ms"):
        assert re.search(rf"\b{field}=\d+\b", line), line
    for product in p.values():
        assert str(product.id) not in line
        assert product.product_code not in line
    assert marker not in line
