"""AC-1..AC-15 (chatbot-last-purchase-cost): the last purchase-order line per product per
location, and its route.

`documentation/plans/chatbot/PLAN-chatbot-last-purchase-cost.md`;
`documentation/plans/chatbot/chatbot-last-purchase-cost-acceptance-criteria.md`.

Mirrors `tests/test_spo_last_receipt.py`'s own shape (same fixtures, same seeding style,
same route-test pattern) for the sibling service `app.services.po_last_cost_service.
last_cost_rows`, which does not exist yet - every test in this file is RED until it does.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope

from tests._mc_lookup_seed import product, warehouse
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/procurement/purchase-orders"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _po(
    db,
    *,
    issue_date=None,
    status="active",
    po_number=None,
    currency="CNY",
    company_id=DEFAULT_COMPANY_ID,
):
    row = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=po_number or unique_code("PO")[:50],
        issue_date=issue_date,
        status=status,
        currency=currency,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _line(
    db,
    *,
    po,
    product_id,
    warehouse_id=None,
    qty_ordered=1,
    unit_cost=None,
    discount=None,
    line_total=None,
    line_status="open",
    currency="CNY",
    created_at=None,
    company_id=DEFAULT_COMPANY_ID,
):
    row = PurchaseOrderLine(
        id=str(uuid.uuid4()),
        purchase_order_id=po.id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        qty_ordered=qty_ordered,
        qty_received=0,
        unit_cost=unit_cost,
        discount=discount,
        line_total=line_total,
        line_status=line_status,
        currency=currency,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    if created_at is not None:
        db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == row.id).update(
            {"created_at": created_at}
        )
        db.flush()
    return row


def _import_last_cost_rows():
    """A single import point so every test raises the SAME ImportError/AttributeError
    until `app.services.po_last_cost_service.last_cost_rows` exists."""
    from app.services.po_last_cost_service import last_cost_rows

    return last_cost_rows


# --------------------------------------------------------------------- service


def test_ac1_latest_line_per_location(db):
    """P at W1 (1 Aug, 1 Sep) and W2 (15 Aug) -> exactly two rows, W1 from the 1 Sep PO,
    W2 from the 15 Aug PO."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    w1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="W1")
    w2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="W2")

    po_aug1 = _po(db, issue_date=date(2026, 8, 1), po_number="PO-AUG1")
    _line(db, po=po_aug1, product_id=prod.id, warehouse_id=w1.id, unit_cost=10)
    po_sep1 = _po(db, issue_date=date(2026, 9, 1), po_number="PO-SEP1")
    _line(db, po=po_sep1, product_id=prod.id, warehouse_id=w1.id, unit_cost=11)
    po_aug15 = _po(db, issue_date=date(2026, 8, 15), po_number="PO-AUG15")
    _line(db, po=po_aug15, product_id=prod.id, warehouse_id=w2.id, unit_cost=12)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert len(rows) == 2
    by_wh = {r["warehouse"]: r for r in rows}
    assert by_wh["W1"]["po_number"] == "PO-SEP1"
    assert by_wh["W2"]["po_number"] == "PO-AUG15"


def test_ac2_null_warehouse_is_its_own_bucket(db):
    """A NULL-warehouse cost line answers its own row with warehouse None, alongside the
    W1 row - it never displaces, and is never displaced by, a warehouse row."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    w1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="W1")

    po1 = _po(db, issue_date=date(2026, 8, 1), po_number="PO-W1")
    _line(db, po=po1, product_id=prod.id, warehouse_id=w1.id, unit_cost=10)
    po2 = _po(db, issue_date=date(2026, 8, 2), po_number="PO-NOWH")
    _line(db, po=po2, product_id=prod.id, warehouse_id=None, unit_cost=20)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert len(rows) == 2
    none_rows = [r for r in rows if r["warehouse"] is None]
    assert len(none_rows) == 1
    assert none_rows[0]["po_number"] == "PO-NOWH"
    w1_rows = [r for r in rows if r["warehouse"] == "W1"]
    assert len(w1_rows) == 1
    assert w1_rows[0]["po_number"] == "PO-W1"


def test_ac3_cancelled_line_and_cancelled_po_excluded(db):
    """A newer cancelled line, and a newer line on a cancelled PO, are both skipped; the
    answer is the newest non-cancelled line."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")

    older = _po(db, issue_date=date(2026, 8, 1), po_number="PO-OLD")
    _line(db, po=older, product_id=prod.id, unit_cost=10)
    cancelled_line_po = _po(db, issue_date=date(2026, 8, 20), po_number="PO-CANCELLED-LINE")
    _line(db, po=cancelled_line_po, product_id=prod.id, unit_cost=99, line_status="cancelled")
    cancelled_po = _po(
        db, issue_date=date(2026, 8, 25), po_number="PO-CANCELLED-PO", status="cancelled"
    )
    _line(db, po=cancelled_po, product_id=prod.id, unit_cost=88)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["po_number"] == "PO-OLD"


def test_ac4_null_unit_cost_never_picked(db):
    """A line with `unit_cost` NULL is never picked, even when it is the newest."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")

    older = _po(db, issue_date=date(2026, 8, 1), po_number="PO-OLD")
    _line(db, po=older, product_id=prod.id, unit_cost=10)
    newer = _po(db, issue_date=date(2026, 8, 30), po_number="PO-NO-COST")
    _line(db, po=newer, product_id=prod.id, unit_cost=None)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["po_number"] == "PO-OLD"


def test_ac5_ordering_issue_date_then_created_at(db):
    """Two lines on the same (product, warehouse): the one whose PO `issue_date` is
    later answers; on the same date the later `created_at` answers."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    same_date = date(2026, 8, 10)

    po_a = _po(db, issue_date=same_date, po_number="PO-A")
    _line(db, po=po_a, product_id=prod.id, unit_cost=10, created_at=datetime(2026, 8, 10, 8, 0, 0))
    po_b = _po(db, issue_date=same_date, po_number="PO-B")
    _line(db, po=po_b, product_id=prod.id, unit_cost=20, created_at=datetime(2026, 8, 10, 9, 0, 0))
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["po_number"] == "PO-B"


def test_ac6_per_unit_discount_m218_shape(db):
    """qty 19, unit_cost 110.00, discount 1254.00, line_total 836.00 answers
    unit_cost == 110.0, discount_per_unit == 66.0, unit_cost_after_discount == 44.0."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="M218")

    po = _po(db, issue_date=date(2026, 5, 1), po_number="PO-M218")
    _line(db, po=po, product_id=prod.id, qty_ordered=19, unit_cost=110, discount=1254, line_total=836)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert rows[0]["unit_cost"] == 110.0
    assert rows[0]["discount_per_unit"] == 66.0
    assert rows[0]["unit_cost_after_discount"] == 44.0


def test_ac7_zero_or_null_discount_absent(db):
    """discount 0 or NULL answers discount_per_unit is None and
    unit_cost_after_discount == unit_cost, on both branches."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    w_zero = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="W-ZERO")

    po_null = _po(db, issue_date=date(2026, 8, 1), po_number="PO-NULL-DISC")
    _line(db, po=po_null, product_id=prod.id, qty_ordered=10, unit_cost=5, discount=None, line_total=50)
    po_zero = _po(db, issue_date=date(2026, 8, 2), po_number="PO-ZERO-DISC")
    _line(
        db, po=po_zero, product_id=prod.id, warehouse_id=w_zero.id, qty_ordered=10,
        unit_cost=5, discount=0, line_total=50,
    )
    db.commit()

    by_wh = {r["warehouse"]: r for r in last_cost_rows(db, product_ids=[prod.id])}
    assert by_wh[None]["discount_per_unit"] is None
    assert by_wh[None]["unit_cost_after_discount"] == by_wh[None]["unit_cost"]
    assert by_wh["W-ZERO"]["discount_per_unit"] is None
    assert by_wh["W-ZERO"]["unit_cost_after_discount"] == by_wh["W-ZERO"]["unit_cost"]


def test_ac8_no_line_total_falls_back_to_unit_cost(db):
    """`line_total` NULL answers unit_cost_after_discount == unit_cost and
    discount_per_unit is None."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")

    po = _po(db, issue_date=date(2026, 8, 1), po_number="PO-NO-TOTAL")
    _line(db, po=po, product_id=prod.id, qty_ordered=10, unit_cost=7, discount=None, line_total=None)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert rows[0]["unit_cost_after_discount"] == 7.0
    assert rows[0]["discount_per_unit"] is None


def test_ac9_currency_is_the_lines(db):
    """`row["currency"]` is the LINE's own `currency`, not the header's."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")

    po = _po(db, issue_date=date(2026, 8, 1), po_number="PO-CUR", currency="MYR")
    _line(db, po=po, product_id=prod.id, unit_cost=5, currency="USD")
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id])
    assert rows[0]["currency"] == "USD"


def test_ac10_warehouse_ids_narrows_before_pick(db):
    """`warehouse_ids=[W2]` on AC-1-shaped data returns only the W2 row, even though W1
    has the newer line overall."""
    last_cost_rows = _import_last_cost_rows()
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    w1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="W1")
    w2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="W2")

    po1 = _po(db, issue_date=date(2026, 9, 1), po_number="PO-W1-NEW")
    _line(db, po=po1, product_id=prod.id, warehouse_id=w1.id, unit_cost=10)
    po2 = _po(db, issue_date=date(2026, 8, 15), po_number="PO-W2-OLD")
    _line(db, po=po2, product_id=prod.id, warehouse_id=w2.id, unit_cost=12)
    db.commit()

    rows = last_cost_rows(db, product_ids=[prod.id], warehouse_ids=[w2.id])
    assert len(rows) == 1
    assert rows[0]["po_number"] == "PO-W2-OLD"


def test_ac11_family_one_row_per_member_top_n_per_group(db):
    """Three products named in product_ids with top_n=1 return three rows (one per
    member); top_n=2 returns up to two per (product, warehouse), never two overall."""
    last_cost_rows = _import_last_cost_rows()
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="FAM1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="FAM2")
    p3 = product(db, company_id=DEFAULT_COMPANY_ID, code="FAM3")
    for i, p in enumerate((p1, p2, p3)):
        po_old = _po(db, issue_date=date(2026, 6, 1), po_number=f"PO-{p.product_code}-OLD")
        _line(db, po=po_old, product_id=p.id, unit_cost=1 + i)
        po_new = _po(db, issue_date=date(2026, 6, 10), po_number=f"PO-{p.product_code}-NEW")
        _line(db, po=po_new, product_id=p.id, unit_cost=10 + i)
    db.commit()

    rows1 = last_cost_rows(db, product_ids=[p1.id, p2.id, p3.id], top_n=1)
    assert len(rows1) == 3
    assert {r["po_number"] for r in rows1} == {"PO-FAM1-NEW", "PO-FAM2-NEW", "PO-FAM3-NEW"}

    rows2 = last_cost_rows(db, product_ids=[p1.id, p2.id, p3.id], top_n=2)
    assert len(rows2) == 6
    counts = Counter((r["product_id"], r["warehouse"]) for r in rows2)
    assert set(counts.values()) == {2}, "top_n must cap PER (product, warehouse), never overall"


def test_ac12_unscoped_top_n_is_a_plain_cap(db):
    """No product_ids, top_n=2 returns exactly two rows, newest first, across every
    product."""
    last_cost_rows = _import_last_cost_rows()
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="UNSC1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="UNSC2")
    p3 = product(db, company_id=DEFAULT_COMPANY_ID, code="UNSC3")

    po1 = _po(db, issue_date=date(2026, 6, 1), po_number="PO-UNSC-OLD")
    _line(db, po=po1, product_id=p1.id, unit_cost=1)
    po2 = _po(db, issue_date=date(2026, 6, 20), po_number="PO-UNSC-NEWEST")
    _line(db, po=po2, product_id=p2.id, unit_cost=2)
    po3 = _po(db, issue_date=date(2026, 6, 15), po_number="PO-UNSC-2ND")
    _line(db, po=po3, product_id=p3.id, unit_cost=3)
    db.commit()

    rows = last_cost_rows(db, top_n=2)
    assert [r["po_number"] for r in rows] == ["PO-UNSC-NEWEST", "PO-UNSC-2ND"]


def test_ac13_company_scope_other_company_line_never_answers(db):
    """Under a session scoped to company A, a cost line owned by company B on the SAME
    product never answers, on both the scoped (product_ids given) and unscoped branch."""
    last_cost_rows = _import_last_cost_rows()
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    sorento_product = product(db, company_id=DEFAULT_COMPANY_ID, code="SCOPE-P1")
    po = _po(db, issue_date=date(2026, 8, 1), po_number="PO-SCOPE-SORENTO")
    _line(db, po=po, product_id=sorento_product.id, unit_cost=5)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert [
        r["po_number"] for r in last_cost_rows(db, product_ids=[sorento_product.id], top_n=10)
    ] == ["PO-SCOPE-SORENTO"]
    assert any(
        r["po_number"] == "PO-SCOPE-SORENTO" for r in last_cost_rows(db, top_n=50)
    )

    set_company_scope(db, frozenset({MOCHA_ID}))
    assert last_cost_rows(db, product_ids=[sorento_product.id], top_n=10) == []
    assert all(r["po_number"] != "PO-SCOPE-SORENTO" for r in last_cost_rows(db, top_n=50))


def test_ac13b_company_scope_subquery_hazard_product_and_line_split(db):
    """The harder shape a `.subquery()` can hide (same hazard `test_spo_last_receipt.py`
    pins for the sibling tool): the PRODUCT belongs to Mocha, the LINE belongs to Sorento.
    Only an explicit company predicate on the windowed subquery keeps this hidden from
    both scopes."""
    last_cost_rows = _import_last_cost_rows()
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    mocha_product = product(db, company_id=MOCHA_ID, code="SCOPE-PP")
    po = _po(db, issue_date=date(2026, 8, 1), po_number="PO-SCOPE-PP")
    _line(db, po=po, product_id=mocha_product.id, unit_cost=5)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert last_cost_rows(db, product_ids=[str(mocha_product.id)], top_n=10) == []

    set_company_scope(db, frozenset({MOCHA_ID}))
    assert last_cost_rows(db, product_ids=[str(mocha_product.id)], top_n=10) == []


# --------------------------------------------------------------------- route


@pytest.fixture
def client(db):
    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-po-last-cost@test.com"}
    app.dependency_overrides[get_db] = _override_db
    # Deliberately NOT overriding `get_current_user` - AC-14 needs the route reachable
    # through the DUAL-auth dependency specifically, and overriding only this one proves
    # the route depends on it rather than on JWT-only `get_current_user`.
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


def test_ac14_route_envelope_and_bounds(client, db):
    """GET .../last-cost?product_ids=P returns {data, pagination, empty} with the AC-1
    rows; top_n=0 and top_n=51 are 422; the route is reachable with the dual-auth
    dependency (X-API-Key capable)."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="ROUTE-P1")
    po = _po(db, issue_date=date(2026, 8, 1), po_number="PO-ROUTE")
    _line(db, po=po, product_id=prod.id, unit_cost=5)
    db.commit()

    resp = client.get(f"{BASE}/last-cost", params={"product_ids": prod.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) >= {"data", "pagination", "empty"}
    assert body["empty"] is False
    assert body["data"][0]["po_number"] == "PO-ROUTE"

    assert (
        client.get(f"{BASE}/last-cost", params={"product_ids": prod.id, "top_n": 0}).status_code
        == 422
    )
    assert (
        client.get(f"{BASE}/last-cost", params={"product_ids": prod.id, "top_n": 51}).status_code
        == 422
    )
