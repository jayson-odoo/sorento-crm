"""A5 - PO placed (AC-907, AC-909).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.purchase_order_service import (
    PO_GROUP_BY_AXES,
    group_rows,
    purchase_orders_placed_rows,
    purchase_orders_placed_summary,
)

from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/procurement/purchase-orders"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _supplier(db, *, name="Acme Supplies"):
    row = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("SUP")[:50],
        supplier_name=name,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _po_line(
    db,
    *,
    supplier_id=None,
    product_id,
    ordered,
    received,
    status="open",
    line_expected=None,
    header_expected=None,
    po_number=None,
    header_issue=None,
    warehouse_id=None,
):
    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=po_number or unique_code("PO"),
        supplier_id=supplier_id,
        issue_date=header_issue,
        expected_date=header_expected,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=str(uuid.uuid4()),
            purchase_order_id=po.id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty_ordered=ordered,
            qty_received=received,
            line_status=status,
            expected_date=line_expected,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return po


def _warehouse(db, *, code="KL-WH"):
    from app.models.inventory import Warehouse

    row = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=code,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------- service


def test_placed_rows_only_open_positive_delta(db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=10, received=3,
             line_expected=date(2026, 6, 1))
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=5, received=5)  # fully received
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=8, received=0, status="closed")
    db.commit()

    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["outstanding_qty"] == 7
    assert rows[0]["supplier"] == "Acme Supplies"
    assert rows[0]["expected_date"] == "2026-06-01"


def test_placed_rows_never_nets_against_incoming(db):
    """AC-907: PO and SPO are never netted - a PO row's `outstanding_qty` is
    `qty_ordered - qty_received` of the PO LINE, and an SPO receipt booked against that
    line (a different table) never reduces it. Was pinned by "the SPO class is never
    imported"; item 5 (8 Sep 2026) reads the SPO table for its OWN unshipped rows, so
    the contract is now pinned on behaviour: the receipt below changes nothing."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=10, received=0, po_number="PO-NET")
    _spo(db, product_id=prod.id, allocated=10, received=6, status="fully_received",
         number="SPO-RECEIVED-AGAINST-IT", po_line_id=_po_line_id(db, "PO-NET"))
    db.commit()
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert [(r["po_number"], r["outstanding_qty"]) for r in rows] == [("PO-NET", 10)]


def test_placed_rows_uses_header_expected_date_when_line_has_none(db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=5, received=0,
             header_expected=date(2026, 7, 1))
    db.commit()

    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert rows[0]["expected_date"] == "2026-07-01"


def test_placed_summary_scoped_by_product(db):
    sup = _supplier(db)
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="P2")
    _po_line(db, supplier_id=sup.id, product_id=p1.id, ordered=10, received=4)  # +6
    _po_line(db, supplier_id=sup.id, product_id=p2.id, ordered=5, received=0)  # +5, other product
    db.commit()

    summary = purchase_orders_placed_summary(db, product_ids=[p1.id])
    assert summary == {"po_placed_qty": 6, "po_placed_count": 1}


def test_group_rows_by_supplier():
    rows = [{"supplier": "A"}, {"supplier": "A"}, {"supplier": "B"}]
    groups = group_rows(rows, group_by="supplier")
    assert {g["key"] for g in groups} == {"A", "B"}


# --------------------------------------------------------------------- route


@pytest.fixture
def client(db, monkeypatch):
    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-po-placed@test.com"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_route_lists_placed_lines(client, db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=10, received=3)
    db.commit()

    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"][0]["outstanding_qty"] == 7
    assert body["data"][0]["supplier"] == "Acme Supplies"


def test_route_group_by_unknown_axis_422(client, db):
    resp = client.get(f"{BASE}/placed", params={"group_by": "not-a-real-axis"})
    assert resp.status_code == 422
    body = resp.json()
    for axis in PO_GROUP_BY_AXES:
        assert axis in body["detail"]


def test_route_group_by_supplier(client, db):
    s1 = _supplier(db, name="Acme")
    s2 = _supplier(db, name="Beta")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _po_line(db, supplier_id=s1.id, product_id=prod.id, ordered=5, received=0)
    _po_line(db, supplier_id=s2.id, product_id=prod.id, ordered=3, received=0)
    db.commit()

    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id, "group_by": "supplier"})
    assert resp.status_code == 200, resp.text
    groups = resp.json()["groups"]
    assert {g["key"] for g in groups} == {"Acme", "Beta"}


def test_route_include_summary(client, db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=10, received=4)
    db.commit()

    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id, "include_summary": "true"})
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary["po_placed_qty"] == 6
    assert summary["po_placed_count"] == 1


# ------------------------------------------- should-fix 6: the summary takes the window


def test_placed_summary_honours_the_expected_date_window(db):
    """The summary counted the whole open book while the LIST showed one month, so "PO for
    X arriving in June" answered with two contradictory numbers in one message."""
    from datetime import date

    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P-WINDOW")
    _po_line(db, product_id=prod.id, ordered=10, received=0, line_expected=date(2026, 6, 1))
    _po_line(db, product_id=prod.id, ordered=25, received=0, line_expected=date(2026, 9, 1))
    db.commit()

    everything = purchase_orders_placed_summary(db, product_ids=[prod.id])
    assert everything == {"po_placed_qty": 35, "po_placed_count": 2}

    june = purchase_orders_placed_summary(
        db,
        product_ids=[prod.id],
        expected_date_from="2026-06-01",
        expected_date_to="2026-06-30",
    )
    assert june == {"po_placed_qty": 10, "po_placed_count": 1}


def test_placed_summary_window_reads_the_header_date_when_the_line_has_none(db):
    """Same COALESCE the rows use, through the shared `_apply_expected_date_window` - a
    second hand-written window is how the two drift again."""
    from datetime import date

    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P-HEADER")
    _po_line(db, product_id=prod.id, ordered=8, received=0, header_expected=date(2026, 6, 15))
    db.commit()

    assert purchase_orders_placed_summary(
        db, product_ids=[prod.id], expected_date_from="2026-06-01", expected_date_to="2026-06-30"
    ) == {"po_placed_qty": 8, "po_placed_count": 1}
    assert purchase_orders_placed_summary(
        db, product_ids=[prod.id], expected_date_from="2026-07-01"
    ) == {"po_placed_qty": 0, "po_placed_count": 0}


def test_route_summary_matches_the_rows_it_sits_under(client, db):
    from datetime import date

    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P-ROUTE-WINDOW")
    _po_line(db, product_id=prod.id, ordered=10, received=0, line_expected=date(2026, 6, 1))
    _po_line(db, product_id=prod.id, ordered=25, received=0, line_expected=date(2026, 9, 1))
    db.commit()

    resp = client.get(
        f"{BASE}/placed",
        params={
            "product_ids": prod.id,
            "include_summary": "true",
            "expected_date_from": "2026-06-01",
            "expected_date_to": "2026-06-30",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["summary"]["po_placed_count"] == len(body["data"])
    assert body["summary"]["po_placed_qty"] == 10


# ------------------------------------- blocker 3: the company scope actually narrows


def test_a_mocha_scoped_read_returns_no_sorento_po_lines(db):
    """AC-F7 for the new tool, backend half. See the SPO twin of this test for why the
    defect was MCP-side: `purchase_order_lines` is `CompanyScopedMixin` and narrows
    correctly, but the ToolSpec never declared `contact_id` / `space_id`, so the params
    never reached the request the scope resolver reads."""
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    sup = _supplier(db)
    sorento_product = product(db, company_id=DEFAULT_COMPANY_ID, code="SRT-PO-SCOPE")
    _po_line(
        db,
        supplier_id=sup.id,
        product_id=sorento_product.id,
        ordered=10,
        received=0,
        po_number="PO-SORENTO",
    )
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert [r["po_number"] for r in purchase_orders_placed_rows(db)] == ["PO-SORENTO"]

    set_company_scope(db, frozenset({MOCHA_ID}))
    assert purchase_orders_placed_rows(db) == []


def test_rows_carry_the_po_document_date(db):
    """Owner ruling (8 Sep 2026): the chatbot's PO rung shows the PO DOCUMENT date -
    `purchase_orders.issue_date` - beside the expected date, so each row carries it as
    `po_date` (ISO, None when the header has none). Every existing field is untouched."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=5, received=0, po_number="PO-DATED",
             header_issue=date(2026, 5, 1), header_expected=date(2026, 7, 1))
    _po_line(db, product_id=prod.id, ordered=3, received=0, po_number="PO-UNDATED")
    db.commit()

    rows = {r["po_number"]: r for r in purchase_orders_placed_rows(db, product_ids=[prod.id])}
    assert rows["PO-DATED"]["po_date"] == "2026-05-01"
    assert rows["PO-DATED"]["expected_date"] == "2026-07-01"
    assert rows["PO-UNDATED"]["po_date"] is None
    assert set(rows["PO-DATED"]) == {
        "po_number", "product_id", "product_code", "product_name", "outstanding_qty",
        "expected_date", "supplier", "po_date", "kind", "ordered_qty", "location",
    }


def test_po_row_carries_ordered_qty_and_the_lines_warehouse_as_location(db):
    """The 11 Sep 2026 ruling: every row carries `ordered_qty` (the line's `qty_ordered`)
    and `location` (the line's warehouse code, None when the line has no warehouse)."""
    wh = _warehouse(db, code="KL-WH")
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=10, received=3, po_number="PO-WH", warehouse_id=wh.id)
    _po_line(db, product_id=prod.id, ordered=8, received=0, po_number="PO-NO-WH")
    db.commit()

    rows = {r["po_number"]: r for r in purchase_orders_placed_rows(db, product_ids=[prod.id])}
    assert rows["PO-WH"]["ordered_qty"] == 10
    assert rows["PO-WH"]["location"] == "KL-WH"
    assert rows["PO-NO-WH"]["ordered_qty"] == 8
    assert rows["PO-NO-WH"]["location"] is None


# --------------------------------------- item 5: unshipped SPO allocations are on order

def _spo(db, *, product_id, allocated, received=0, status="pending", shipment=None, number=None,
         issue=None, expected=None, supplier_id=None, po_line_id=None, warehouse_id=None,
         location_code=None):
    row = SPOAllocation(
        id=str(uuid.uuid4()),
        company_id=DEFAULT_COMPANY_ID,
        spo_number=number or unique_code("SPO")[:50],
        product_id=product_id,
        allocated_quantity=allocated,
        quantity_received=received,
        receipt_status=status,
        inbound_shipment_id=shipment,
        issue_date=issue,
        expected_date=expected,
        supplier_id=supplier_id,
        po_line_id=po_line_id,
        warehouse_id=warehouse_id,
        location_code=location_code,
    )
    db.add(row)
    db.flush()
    return row


def _po_line_id(db, po_number: str) -> str:
    return (
        db.query(PurchaseOrderLine.id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(PurchaseOrder.po_number == po_number)
        .scalar()
    )


def test_po_only_rows_carry_kind_po_and_nothing_else_moves(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=5, received=0, po_number="PO-ONLY")
    db.commit()
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert [(r["po_number"], r["kind"]) for r in rows] == [("PO-ONLY", "po")]
    assert set(rows[0]) == {
        "po_number", "product_id", "product_code", "product_name", "outstanding_qty",
        "expected_date", "supplier", "po_date", "kind", "ordered_qty", "location",
    }


def test_spo_only_rows_are_on_order_from_the_supplier(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    sup = _supplier(db, name="Foshan Works")
    _spo(db, product_id=prod.id, allocated=10, received=3, number="SPO-2026/09-0001",
         issue=date(2026, 8, 20), expected=date(2026, 10, 5), supplier_id=sup.id)
    _spo(db, product_id=prod.id, allocated=4, received=4, number="SPO-DONE")          # nothing left
    _spo(db, product_id=prod.id, allocated=9, status="fully_received", number="SPO-RECEIVED")
    db.commit()
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    by_no = {r["po_number"]: r for r in rows}
    assert "SPO-DONE" not in by_no and "SPO-RECEIVED" not in by_no
    r = by_no["SPO-2026/09-0001"]
    assert r["kind"] == "spo"
    assert r["outstanding_qty"] == 7
    assert r["po_date"] == "2026-08-20" and r["expected_date"] == "2026-10-05"
    assert r["supplier"] == "Foshan Works"
    assert r["product_code"] == prod.product_code


def test_spo_row_carries_ordered_qty_and_location_from_its_warehouse(db):
    """The 11 Sep 2026 ruling: an SPO row's `ordered_qty` is `allocated_quantity`, and
    `location` is the allocation's warehouse code when it has one."""
    wh = _warehouse(db, code="BRW")
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _spo(db, product_id=prod.id, allocated=15, number="SPO-WH", warehouse_id=wh.id)
    db.commit()
    rows = {r["po_number"]: r for r in purchase_orders_placed_rows(db, product_ids=[prod.id])}
    assert rows["SPO-WH"]["ordered_qty"] == 15
    assert rows["SPO-WH"]["location"] == "BRW"


def test_spo_row_without_a_warehouse_falls_back_to_the_books_location_code(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _spo(db, product_id=prod.id, allocated=6, number="SPO-RAW-LOC", location_code="RAW-CODE-9")
    db.commit()
    rows = {r["po_number"]: r for r in purchase_orders_placed_rows(db, product_ids=[prod.id])}
    assert rows["SPO-RAW-LOC"]["ordered_qty"] == 6
    assert rows["SPO-RAW-LOC"]["location"] == "RAW-CODE-9"


def test_spo_row_without_warehouse_or_location_code_has_location_none(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _spo(db, product_id=prod.id, allocated=9, number="SPO-NOWHERE")
    db.commit()
    rows = {r["po_number"]: r for r in purchase_orders_placed_rows(db, product_ids=[prod.id])}
    assert rows["SPO-NOWHERE"]["location"] is None


def test_an_spo_already_on_a_shipment_is_incoming_not_on_order(db):
    from app.models.procurement import InboundShipment

    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    ship = InboundShipment(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, shipment_date=date(2026, 9, 1))
    db.add(ship)
    db.flush()
    _spo(db, product_id=prod.id, allocated=10, number="SPO-ON-SHIP", shipment=ship.id)
    _spo(db, product_id=prod.id, allocated=6, number="SPO-UNSHIPPED")
    db.commit()
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert [r["po_number"] for r in rows] == ["SPO-UNSHIPPED"]


def test_mixed_rows_sort_together_by_the_effective_expected_date(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=5, received=0, po_number="PO-SEP", line_expected=date(2026, 9, 15))
    _spo(db, product_id=prod.id, allocated=3, number="SPO-AUG", expected=date(2026, 8, 30))
    _spo(db, product_id=prod.id, allocated=2, number="SPO-NODATE")
    _po_line(db, product_id=prod.id, ordered=1, received=0, po_number="PO-NODATE")
    db.commit()
    asc = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert [(r["po_number"], r["kind"]) for r in asc] == [
        ("SPO-AUG", "spo"), ("PO-SEP", "po"), ("PO-NODATE", "po"), ("SPO-NODATE", "spo"),
    ]
    desc = purchase_orders_placed_rows(db, product_ids=[prod.id], dir="desc")
    assert [r["po_number"] for r in desc] == ["PO-SEP", "SPO-AUG", "PO-NODATE", "SPO-NODATE"]
    by_qty = purchase_orders_placed_rows(db, product_ids=[prod.id], sort="outstanding_qty", dir="desc")
    assert [r["po_number"] for r in by_qty] == ["PO-SEP", "SPO-AUG", "SPO-NODATE", "PO-NODATE"]


def test_an_spo_row_pointing_at_a_po_line_is_its_own_on_order_fact(db):
    """Review round 2, S3: no `po_line_id` dedupe - 0 of 80,468 allocations carry one, and
    the SELECT it took was column-only and unscoped. A row that points at a PO line counts
    like any other pending, unshipped allocation; the trigger for re-adding the dedupe is
    named in the PLAN's as-built section."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=10, received=0, po_number="PO-PARENT")
    _spo(db, product_id=prod.id, allocated=10, number="SPO-CHILD", po_line_id=_po_line_id(db, "PO-PARENT"))
    _po_line(db, product_id=prod.id, ordered=4, received=4, po_number="PO-CLOSED-PARENT")
    _spo(db, product_id=prod.id, allocated=4, number="SPO-ORPHAN", po_line_id=_po_line_id(db, "PO-CLOSED-PARENT"))
    db.commit()
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert sorted(r["po_number"] for r in rows) == ["PO-PARENT", "SPO-CHILD", "SPO-ORPHAN"]
    assert purchase_orders_placed_summary(db, product_ids=[prod.id]) == {"po_placed_qty": 24, "po_placed_count": 3}

def test_spo_rows_take_the_same_product_scope_and_window(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    other = product(db, company_id=DEFAULT_COMPANY_ID)
    _spo(db, product_id=prod.id, allocated=5, number="SPO-JUN", expected=date(2026, 6, 10))
    _spo(db, product_id=prod.id, allocated=6, number="SPO-SEP", expected=date(2026, 9, 10))
    _spo(db, product_id=prod.id, allocated=7, number="SPO-NODATE")
    _spo(db, product_id=other.id, allocated=8, number="SPO-OTHER", expected=date(2026, 6, 12))
    db.commit()
    everything = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert sorted(r["po_number"] for r in everything) == ["SPO-JUN", "SPO-NODATE", "SPO-SEP"]
    june = purchase_orders_placed_rows(db, product_ids=[prod.id],
                                       expected_date_from=date(2026, 6, 1), expected_date_to=date(2026, 6, 30))
    assert [r["po_number"] for r in june] == ["SPO-JUN"]  # a null date fails a window, as PO rows do
    assert purchase_orders_placed_summary(db, product_ids=[prod.id]) == {"po_placed_qty": 18, "po_placed_count": 3}
    assert purchase_orders_placed_summary(db, product_ids=[prod.id], expected_date_from="2026-06-01",
                                          expected_date_to="2026-06-30") == {"po_placed_qty": 5, "po_placed_count": 1}


def test_summary_counts_both_kinds_and_group_by_spans_both(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    sup = _supplier(db, name="Acme Supplies")
    _po_line(db, product_id=prod.id, ordered=5, received=0, po_number="PO-A", supplier_id=sup.id)
    _spo(db, product_id=prod.id, allocated=3, number="SPO-A", supplier_id=sup.id)
    _spo(db, product_id=prod.id, allocated=2, number="SPO-B")
    db.commit()
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert purchase_orders_placed_summary(db, product_ids=[prod.id]) == {"po_placed_qty": 10, "po_placed_count": 3}
    groups = group_rows(rows, group_by="supplier")
    assert {g["label"]: sorted(r["po_number"] for r in g["rows"]) for g in groups} == {
        "Acme Supplies": ["PO-A", "SPO-A"], "Not specified": ["SPO-B"],
    }


def test_a_mocha_spo_never_reaches_a_sorento_read(db):
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    row = _spo(db, product_id=prod.id, allocated=5, number="SPO-MOCHA")
    row.company_id = MOCHA_ID
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert purchase_orders_placed_rows(db, product_ids=[prod.id]) == []
    assert purchase_orders_placed_summary(db, product_ids=[prod.id]) == {"po_placed_qty": 0, "po_placed_count": 0}


def test_b1_both_summary_legs_apply_the_company_scope_by_hand(db):
    """Review round 2, B1: the summary's legs are column-only aggregates, and a column-only
    query is exactly where the session listener's scope is lost (order_service.
    stamp_order_summary documents the measurement). A Sorento-only read must not count a
    Mocha PO line or a Mocha SPO allocation - in the rows OR in the summary."""
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=5, received=0, po_number="PO-SRT")
    _spo(db, product_id=prod.id, allocated=3, number="SPO-SRT")
    m_po = _po_line(db, product_id=prod.id, ordered=70, received=0, po_number="PO-MCH")
    m_line = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == m_po.id).one()
    m_po.company_id = MOCHA_ID
    m_line.company_id = MOCHA_ID
    m_spo = _spo(db, product_id=prod.id, allocated=90, number="SPO-MCH")
    m_spo.company_id = MOCHA_ID
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert sorted(r["po_number"] for r in rows) == ["PO-SRT", "SPO-SRT"]
    assert purchase_orders_placed_summary(db, product_ids=[prod.id]) == {"po_placed_qty": 8, "po_placed_count": 2}

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    assert purchase_orders_placed_summary(db, product_ids=[prod.id]) == {"po_placed_qty": 168, "po_placed_count": 4}
