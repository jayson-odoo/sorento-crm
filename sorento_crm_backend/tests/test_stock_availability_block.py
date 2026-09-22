"""Dealer stock verdict - S1, the server availability block (AC-1740 to AC-1752).

UAC `documentation/plans/chatbot/chatbot-dealer-stock-verdict-acceptance-criteria.md`
"Phase 2 - server availability block". PLAN
`documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md` "The server block (S1)".
Rulings D1, D2, D3, D8, D9, D10, D11, D20.

`_apply_stock_visibility`'s `availability` branch gains four reads, all filtered by the
SAME `warehouse_criterion(policy, <table>.warehouse_id)` as `on hand`:

* open SO (`sales_order_lines`, `qty_ordered - qty_delivered`, `line_status = 'open'`) - D2
* incoming (`spo_allocations`, the `scm.on_order_v` predicate verbatim) - D9, D10, D11
* purchase (`purchase_order_lines`, the PO-book status set) - D8

and each entry gains `verdict` / `running_low` / `disclaimer` from `stock_verdict.verdict()`
(S0). `requested_quantities` (JSON object, product UUID -> int) joins `requested_qty` on the
route and the service - the map wins per product, the scalar fills the rest (D20).

None of this exists yet: `StockService.list_stock` has no `requested_quantities` parameter,
so every service-level call below raises `TypeError: unexpected keyword argument` - that IS
the expected red state. The route silently ignores an unknown `requested_quantities` query
param today, so the 400-rejection tests get a 200 instead. The two settings-dependent tests
(AC-1748, and the threshold read implicitly used by every `running_low`) construct a
`SystemSetting` row with `chatbot_stock_low_threshold_pct=...`, which raises `TypeError` at
seed time until S0 adds the column - also an expected red reason, not a fixture bug.

Postgres only, blank schema, every row seeded here (CI's database has none).

NOTE for the coder (AC-1740): the UAC's own worked example ("on hand BRW 60, MWH 40, DC1 500
and open SO BRW 10, ask 90 -> available false (90 > 100 - 10)") does not check out arithmetically
- 100 - 10 = 90, and 90 is not greater than 90. `verdict()`'s own inclusive boundary (S0,
AC-1741/AC-1720 row 4: ask == available -> "available", pinned by the owner's 18-row matrix)
says ask 90 against a net of 90 is `available`. The test below uses ask 91, the smallest ask
that keeps the doc's "subtract open SO, exclude DC1" scenario intact while actually landing on
`not_available`, and flags the discrepancy here rather than encoding a backwards boundary.
Worth a ruling upstream if the UAC's literal 90 was intentional.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact, StockVisibilityPolicy
from app.models.base import set_company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import InboundShipment, PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.models.user import SystemSetting
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.inventory_service import StockService
from app.services.user_service import UserPermissionService

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha, stock, warehouse
from tests._pg_fixture import blank_session, unique_code

READ_PERM = "inventory.stock.view"
WRITE_PERM = "inventory.stock.edit"


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


@pytest.fixture
def client(db, monkeypatch):
    """A staff caller holding both stock permissions, on the SAME session the
    assertions read - copied from `tests/test_stock_visibility_policy.py`."""

    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-dsv-block@test.com"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in {READ_PERM, WRITE_PERM},
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------- seeding


def _wh(db, code: str):
    return warehouse(db, company_id=DEFAULT_COMPANY_ID, code=code)


def _contact(db) -> RespondContact:
    row = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT DSV Contact",
    )
    db.add(row)
    db.flush()
    return row


def _policy_row(db, *, mode: str, warehouse_ids=None, contact=None) -> StockVisibilityPolicy:
    row = StockVisibilityPolicy(
        id=str(uuid.uuid4()),
        contact_id=contact.id if contact else None,
        mode=mode,
        warehouse_ids=warehouse_ids,
    )
    db.add(row)
    db.flush()
    return row


def _so_line(
    db,
    *,
    product_id,
    warehouse_id,
    ordered,
    delivered=0,
    status="open",
    company_id=DEFAULT_COMPANY_ID,
):
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=unique_code("SO")[:100],
        company_id=company_id,
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=str(uuid.uuid4()),
        sales_order_id=so.id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        qty_ordered=ordered,
        qty_delivered=delivered,
        line_status=status,
        company_id=company_id,
    )
    db.add(line)
    db.flush()
    return line


def _allocation(
    db,
    *,
    product_id,
    warehouse_id,
    allocated,
    received=0,
    expected_date=None,
    line_status="open",
    receipt_status="pending",
    inbound_shipment_id=None,
    company_id=DEFAULT_COMPANY_ID,
) -> SPOAllocation:
    row = SPOAllocation(
        id=str(uuid.uuid4()),
        product_id=product_id,
        warehouse_id=warehouse_id,
        allocated_quantity=allocated,
        quantity_received=received,
        expected_date=expected_date,
        line_status=line_status,
        receipt_status=receipt_status,
        inbound_shipment_id=inbound_shipment_id,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _shipment(db, *, status="in_transit") -> InboundShipment:
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_date=date(2026, 1, 1),
        shipment_status=status,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _po_line(
    db,
    *,
    product_id,
    warehouse_id,
    ordered,
    received=0,
    line_status="open",
    po_status="active",
    company_id=DEFAULT_COMPANY_ID,
) -> PurchaseOrderLine:
    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=unique_code("PO")[:100],
        status=po_status,
        company_id=company_id,
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=str(uuid.uuid4()),
        purchase_order_id=po.id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        qty_ordered=ordered,
        qty_received=received,
        line_status=line_status,
        company_id=company_id,
    )
    db.add(line)
    db.flush()
    return line


def _settings_row(db, *, threshold=None, lead_time=None) -> SystemSetting:
    """AC-1748 / the threshold every `running_low` read depends on. `dsv_0001`
    (S0) has not landed on this branch, so passing `threshold` raises `TypeError`
    at construction - the expected red reason, not a fixture bug."""
    kwargs = {"id": str(uuid.uuid4()), "name": "ZZTDSV Co"}
    if threshold is not None:
        kwargs["chatbot_stock_low_threshold_pct"] = threshold
    if lead_time is not None:
        kwargs["default_product_standard_lead_time_days"] = lead_time
    row = SystemSetting(**kwargs)
    db.add(row)
    db.flush()
    return row


def _entry(result, product_id):
    for row in result["stock_availability"]:
        if row["product_id"] == product_id:
            return row
    raise AssertionError(f"no stock_availability entry for {product_id}")


#: Keys allowed to carry a number on an `availability` answer, mirroring
#: `tests/test_stock_visibility_policy.py`'s leak sweep.
_ALLOWED_NUMERIC_KEYS = {"requested_qty", "needs_quantity", "purchase_eta_days"}
_QUANTITY_WORDS = ("quantity", "on_hand", "qty")


def _walk(node, path="$"):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _assert_no_quantity_anywhere(body, forbidden_numbers):
    offending_keys = [
        path
        for path, key, _ in _walk(body)
        if key not in _ALLOWED_NUMERIC_KEYS and any(word in key for word in _QUANTITY_WORDS)
    ]
    assert not offending_keys, f"quantity-shaped keys leaked: {offending_keys}"

    leaked_values = [
        path
        for path, key, value in _walk(body)
        if key not in _ALLOWED_NUMERIC_KEYS
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value in forbidden_numbers
    ]
    assert not leaked_values, f"stock quantities leaked as values: {leaked_values}"


# ============================================================ AC-1740 to AC-1751


def test_availability_subtracts_open_so_inside_policy_only(db):
    """AC-1740. On hand BRW 60, MWH 40 (both allowed), DC1 500 (excluded, D1); open SO
    BRW 10 subtracted (D2). Net = 100 - 10 = 90. Ask 91 (see module docstring: the UAC's
    literal ask 90 lands on the verdict's own inclusive boundary and would be `available`,
    not `not_available`) -> not available, and DC1's 500 never enters the arithmetic."""
    brw = _wh(db, "ZZTBRW")
    mwh = _wh(db, "ZZTMWH")
    dc1 = _wh(db, "ZZTDC1")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=60)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=mwh.id, on_hand=40)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=dc1.id, on_hand=500)
    _so_line(db, product_id=p.id, warehouse_id=brw.id, ordered=10, delivered=0)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id, mwh.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 91}
    )

    entry = _entry(result, p.id)
    assert entry == {
        "product_id": p.id,
        "product_code": p.product_code,
        "product_name": p.product_name,
        "needs_quantity": False,
        "requested_qty": 91,
        "available": False,
        "verdict": "not_available",
        "running_low": False,
        "disclaimer": None,
    }
    _assert_no_quantity_anywhere(result, {60, 40, 500, 10})


def test_availability_running_low_at_threshold(db):
    """AC-1741. On hand 100, no open SO, default threshold 50: ask 50 running_low true,
    ask 49 false, ask 100 still available (and low), ask 101 not available (and
    `running_low` is false for a not-available answer - S0's own contract)."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    cases = [
        (49, True, False),
        (50, True, True),
        (100, True, True),
        (101, False, False),
    ]
    for ask, expected_available, expected_low in cases:
        result = StockService(db).list_stock(
            product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: ask}
        )
        entry = _entry(result, p.id)
        assert entry["available"] is expected_available, ask
        assert entry["running_low"] is expected_low, ask
        assert entry["verdict"] == ("available" if expected_available else "not_available"), ask
        assert entry["disclaimer"] is None, ask
    _assert_no_quantity_anywhere(result, {100})


def test_availability_incoming_covers_deficit_po_ignored(db):
    """AC-1742. On hand 100, ask 110 (deficit 10); an open allocation of 10 to BRW dated
    2026-10-12 covers the whole deficit, so PO is not consulted at all (D6) even though a
    PO line of 25 also sits at BRW.

    SEC-N2 (security review, round 1): `purchase_eta_days` is attached only when
    "purchase" is one of the named sources, the mirror of `incoming_eta`'s own guard -
    a lead time printed beside an incoming-only disclaimer is a promise about a purchase
    nothing consulted. This case is exactly that shape, so it reads null here."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(
        db,
        product_id=p.id,
        warehouse_id=brw.id,
        allocated=10,
        expected_date=date(2026, 10, 12),
    )
    _po_line(db, product_id=p.id, warehouse_id=brw.id, ordered=25)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["available"] is False
    assert entry["verdict"] == "not_available"
    assert entry["disclaimer"] == {
        "sources": ["incoming"],
        "limited": True,
        "incoming_eta": "2026-10-12",
        "purchase_eta_days": None,
    }
    _assert_no_quantity_anywhere(result, {100, 10, 25})


def test_availability_incoming_plus_po_both_limited(db):
    """AC-1743. On hand 100, ask 110 (deficit 10); incoming 5 (short of the deficit alone)
    plus PO 10 covers it jointly -> both sources named, limited (deficit 10 >= 50% of the
    combined 15), purchase_eta_days falls back to the 90-day default (no settings row)."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(db, product_id=p.id, warehouse_id=brw.id, allocated=5)
    _po_line(db, product_id=p.id, warehouse_id=brw.id, ordered=10)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["disclaimer"] == {
        "sources": ["incoming", "purchase"],
        "limited": True,
        "incoming_eta": None,
        "purchase_eta_days": 90,
    }
    _assert_no_quantity_anywhere(result, {100, 5, 10})


def test_availability_po_only_not_limited(db):
    """AC-1744. On hand 100, ask 110 (deficit 10), no allocation, PO 25 at BRW covers the
    deficit comfortably -> sources purchase only, not limited (10 < 50% of 25)."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _po_line(db, product_id=p.id, warehouse_id=brw.id, ordered=25)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["disclaimer"] == {
        "sources": ["purchase"],
        "limited": False,
        "incoming_eta": None,
        "purchase_eta_days": 90,
    }
    _assert_no_quantity_anywhere(result, {100, 25})


def test_availability_supply_outside_policy_not_named(db):
    """AC-1745. Ask 110 against on hand 100 at the one allowed warehouse; an allocation of
    55 and a PO of 55 both sit at DC1, outside the policy, so neither counts and there is
    no disclaimer at all."""
    brw = _wh(db, "ZZTBRW")
    dc1 = _wh(db, "ZZTDC1")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(db, product_id=p.id, warehouse_id=dc1.id, allocated=55)
    _po_line(db, product_id=p.id, warehouse_id=dc1.id, ordered=55)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["available"] is False
    assert entry["disclaimer"] is None
    # 55, not 50 - the page-size default (`pagination.limit`) is also 50, and the leak
    # sweep below walks the WHOLE payload, `pagination` included by design (never
    # excluded, however tempting - a real leak could as easily land there).
    _assert_no_quantity_anywhere(result, {100, 55})


def test_availability_null_destination_not_counted(db):
    """AC-1746. An open PO line of 500 and an open allocation of 500, both with
    `warehouse_id NULL`, are counted nowhere (D8, D9) even though the product's own
    allowed-warehouse stock leaves a deficit."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(db, product_id=p.id, warehouse_id=None, allocated=500)
    _po_line(db, product_id=p.id, warehouse_id=None, ordered=500)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["available"] is False
    assert entry["disclaimer"] is None
    _assert_no_quantity_anywhere(result, {100, 500})


def test_availability_incoming_eta_is_earliest_or_null(db):
    """AC-1747. `incoming_eta` is the earliest `expected_date` among the counted
    allocations (D10); with none dated it is null, not the earliest of nothing."""
    brw = _wh(db, "ZZTBRW")
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)

    dated = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("DSVA"))
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=dated.id, warehouse_id=brw.id, on_hand=100)
    _allocation(db, product_id=dated.id, warehouse_id=brw.id, allocated=6, expected_date=date(2026, 11, 1))
    _allocation(db, product_id=dated.id, warehouse_id=brw.id, allocated=6, expected_date=date(2026, 10, 5))

    undated = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("DSVB"))
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=undated.id, warehouse_id=brw.id, on_hand=100)
    _allocation(db, product_id=undated.id, warehouse_id=brw.id, allocated=6, expected_date=None)
    _allocation(db, product_id=undated.id, warehouse_id=brw.id, allocated=6, expected_date=None)
    db.flush()

    dated_result = StockService(db).list_stock(
        product_ids=[dated.id], contact_id=contact.id, requested_quantities={dated.id: 110}
    )
    undated_result = StockService(db).list_stock(
        product_ids=[undated.id], contact_id=contact.id, requested_quantities={undated.id: 110}
    )

    assert _entry(dated_result, dated.id)["disclaimer"]["incoming_eta"] == "2026-10-05"
    assert _entry(undated_result, undated.id)["disclaimer"]["incoming_eta"] is None


def test_availability_reads_lead_time_and_threshold_settings(db):
    """AC-1748. `chatbot_stock_low_threshold_pct = 30` moves the running_low boundary
    down from the 50 default (ask 30 of 100 is now low); `default_product_standard_
    lead_time_days = 120` is what `purchase_eta_days` reads instead of the 90 default."""
    _settings_row(db, threshold=30, lead_time=120)
    brw = _wh(db, "ZZTBRW")
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)

    low = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("DSVC"))
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=low.id, warehouse_id=brw.id, on_hand=100)

    po_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("DSVD"))
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=po_product.id, warehouse_id=brw.id, on_hand=100)
    _po_line(db, product_id=po_product.id, warehouse_id=brw.id, ordered=25)
    db.flush()

    low_result = StockService(db).list_stock(
        product_ids=[low.id], contact_id=contact.id, requested_quantities={low.id: 30}
    )
    entry = _entry(low_result, low.id)
    assert entry["available"] is True
    assert entry["running_low"] is True

    po_result = StockService(db).list_stock(
        product_ids=[po_product.id],
        contact_id=contact.id,
        requested_quantities={po_product.id: 110},
    )
    po_entry = _entry(po_result, po_product.id)
    assert po_entry["disclaimer"]["purchase_eta_days"] == 120
    # Threshold 30 applied to the deficit/purchase ratio: 10 >= 30% * 25 = 7.5 -> limited,
    # where the AC-1744 default of 50% left the same numbers NOT limited.
    assert po_entry["disclaimer"]["limited"] is True


def test_availability_per_product_map_wins_scalar_fills(db):
    """AC-1749. `requested_quantities` names A only; B stays unanswered (`needs_quantity`
    true, `available` null, no verdict). Adding `requested_qty = 7` as the scalar fallback
    then judges B at 7, while A still reads from the map (5), not the scalar."""
    brw = _wh(db, "ZZTBRW")
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    a = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("DSVA2"))
    b = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("DSVB2"))
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=a.id, warehouse_id=brw.id, on_hand=100)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=b.id, warehouse_id=brw.id, on_hand=100)
    db.flush()

    map_only = StockService(db).list_stock(
        product_ids=[a.id, b.id], contact_id=contact.id, requested_quantities={a.id: 5}
    )
    a_entry = _entry(map_only, a.id)
    b_entry = _entry(map_only, b.id)
    assert a_entry["requested_qty"] == 5
    assert a_entry["available"] is True
    assert b_entry == {
        "product_id": b.id,
        "product_code": b.product_code,
        "product_name": b.product_name,
        "needs_quantity": True,
        "requested_qty": None,
        "available": None,
        "verdict": None,
        "running_low": None,
        "disclaimer": None,
    }

    with_scalar = StockService(db).list_stock(
        product_ids=[a.id, b.id],
        contact_id=contact.id,
        requested_quantities={a.id: 5},
        requested_qty=7,
    )
    a_entry2 = _entry(with_scalar, a.id)
    b_entry2 = _entry(with_scalar, b.id)
    assert a_entry2["requested_qty"] == 5, "the map wins over the scalar for A"
    assert b_entry2["requested_qty"] == 7, "the scalar fills B, which the map did not name"
    assert b_entry2["needs_quantity"] is False
    assert b_entry2["available"] is True


def test_detailed_and_compact_ignore_requested_quantities(db):
    """AC-1750. `requested_quantities` is only read under `availability`; a `detailed` or
    `compact` policy, or no `contact_id` at all (the staff grid), returns byte-identical
    responses with and without it."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=42)
    contact = _contact(db)
    db.flush()

    for mode in ("detailed", "compact"):
        db.query(StockVisibilityPolicy).filter(
            StockVisibilityPolicy.contact_id == contact.id
        ).delete()
        _policy_row(db, mode=mode, contact=contact)
        db.flush()

        without = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)
        with_qty = StockService(db).list_stock(
            product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 5}
        )
        assert with_qty == without, mode
        assert "stock_availability" not in with_qty, mode

    staff_without = StockService(db).list_stock(product_ids=[p.id])
    staff_with_qty = StockService(db).list_stock(
        product_ids=[p.id], requested_quantities={p.id: 5}
    )
    assert staff_with_qty == staff_without


def test_availability_received_or_closed_supply_not_counted(db):
    """AC-1751. A fully-received allocation, a closed allocation line, an allocation on a
    shipment that has already landed, and a closed PO line are none of them counted."""
    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(
        db, product_id=p.id, warehouse_id=brw.id, allocated=65, receipt_status="fully_received"
    )
    _allocation(db, product_id=p.id, warehouse_id=brw.id, allocated=65, line_status="closed")
    landed = _shipment(db, status="fully_received")
    _allocation(
        db,
        product_id=p.id,
        warehouse_id=brw.id,
        allocated=65,
        inbound_shipment_id=landed.id,
    )
    _po_line(db, product_id=p.id, warehouse_id=brw.id, ordered=65, line_status="closed")
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["available"] is False
    assert entry["disclaimer"] is None
    # 65, not 50 - the page-size default (`pagination.limit`) is also 50, and the leak
    # sweep below walks the WHOLE payload, `pagination` included by design.
    _assert_no_quantity_anywhere(result, {100, 65})


# =================================================== review round 1, SEC-S1 (added)


def test_availability_supply_at_an_inactive_warehouse_is_not_counted(db):
    """SEC-S1 (security review, round 1). `warehouse_criterion` is only HALF of what the
    ON HAND read filters by: that query also carries `Warehouse.is_active`, so a retired
    location is not somewhere this contact can be supplied from. An allocation and a PO
    line bound for an INACTIVE warehouse that is nonetheless named in the policy's own
    include list were counted towards the verdict, and the dealer read a promise the
    warehouse cannot keep.

    RED before the fix: `disclaimer` came back
    `{"sources": ["incoming", "purchase"], ...}` off the retired location's 10 + 25."""
    brw = _wh(db, "ZZTBRW")
    retired = _wh(db, "ZZTOLD")
    retired.is_active = False
    db.flush()
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(
        db,
        product_id=p.id,
        warehouse_id=retired.id,
        allocated=10,
        expected_date=date(2026, 10, 12),
    )
    _po_line(db, product_id=p.id, warehouse_id=retired.id, ordered=25)
    contact = _contact(db)
    _policy_row(
        db, mode="availability", warehouse_ids=[brw.id, retired.id], contact=contact
    )
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_quantities={p.id: 110}
    )

    entry = _entry(result, p.id)
    assert entry["verdict"] == "not_available"
    assert entry["disclaimer"] is None, (
        "supply at a retired warehouse must not be named: the on-hand read this verdict "
        "is judged against never counts it either"
    )


def test_availability_supply_outside_the_asked_warehouse_is_not_counted(db):
    """SEC-S1, the second half: the caller's OWN `warehouse_ids=` narrowing ("stock at
    BRW") narrows the on-hand read, so it has to narrow the supply reads too - otherwise
    "do you have 110 at BRW?" was answered with an allocation bound for MWH."""
    brw = _wh(db, "ZZTBRW")
    mwh = _wh(db, "ZZTMWH")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(
        db,
        product_id=p.id,
        warehouse_id=mwh.id,
        allocated=10,
        expected_date=date(2026, 10, 12),
    )
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id, mwh.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id],
        contact_id=contact.id,
        warehouse_ids=[brw.id],
        requested_quantities={p.id: 110},
    )

    entry = _entry(result, p.id)
    assert entry["disclaimer"] is None


def test_availability_supply_outside_the_singular_warehouse_id_is_not_counted(db):
    """Review round 2: the SAME narrowing as the test above, but through the singular
    `warehouse_id` query param ("stock at BRW", not the plural `warehouse_ids=[...]`
    list). `list_stock` resolves it to `resolved_wh_ids` and uses it to narrow the
    on-hand read, but before this fix `_apply_stock_visibility` was only ever handed
    the plural `warehouse_ids` argument - so a caller asking with the singular param
    left the three supply reads unscoped and an allocation parked at MWH still leaked
    into a verdict about BRW."""
    brw = _wh(db, "ZZTBRW")
    mwh = _wh(db, "ZZTMWH")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100)
    _allocation(
        db,
        product_id=p.id,
        warehouse_id=mwh.id,
        allocated=10,
        expected_date=date(2026, 10, 12),
    )
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id, mwh.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id],
        contact_id=contact.id,
        warehouse_id=brw.id,
        requested_quantities={p.id: 110},
    )

    entry = _entry(result, p.id)
    assert entry["disclaimer"] is None


# ============================================================ AC-1752, route level


def test_route_rejects_bad_requested_quantities_and_declares_keys(client, db):
    """AC-1752. A non-object, a non-UUID key, or a non-int value in `requested_quantities`
    is a 400 - today the route does not declare the param at all, so it is silently
    ignored and the call succeeds with 200 instead. The `response_model`'s per-item shape
    (`StockAvailabilityEntry`) must declare `verdict` / `running_low` / `disclaimer` or
    `response_model` drops them off the wire even once the service computes them."""
    from app.schemas.inventory import StockAvailabilityEntry

    declared = set(StockAvailabilityEntry.model_fields)
    assert {"verdict", "running_low", "disclaimer"} <= declared

    brw = _wh(db, "ZZTBRW")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=10)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    not_an_object = client.get(
        "/api/v1/inventory/stock/balance",
        params={
            "product_ids": p.id,
            "contact_id": contact.id,
            "space_id": "364817",
            "requested_quantities": json.dumps([1, 2, 3]),
        },
    )
    assert not_an_object.status_code == 400, not_an_object.text

    non_uuid_key = client.get(
        "/api/v1/inventory/stock/balance",
        params={
            "product_ids": p.id,
            "contact_id": contact.id,
            "space_id": "364817",
            "requested_quantities": json.dumps({"not-a-uuid": 5}),
        },
    )
    assert non_uuid_key.status_code == 400, non_uuid_key.text

    non_int_value = client.get(
        "/api/v1/inventory/stock/balance",
        params={
            "product_ids": p.id,
            "contact_id": contact.id,
            "space_id": "364817",
            "requested_quantities": json.dumps({str(uuid.uuid4()): "abc"}),
        },
    )
    assert non_int_value.status_code == 400, non_int_value.text


def test_route_answers_a_bad_product_or_warehouse_uuid_with_400_not_500(client, db):
    """Review round 1 nit. `parse_uuid_list` raises `HTTPException(400)`, but both of
    its calls sat INSIDE the handler's `except Exception as e: raise
    handle_internal_error(str(e))` block, which turns every exception alike into a 500 -
    `HTTPException` included, since it does not look at the type. A caller's malformed
    UUID is the caller's mistake, and the reply has to say so. Hoisted out of the try
    the same way `requested_quantities` already was (AC-1752).

    RED before the fix: both calls came back 500."""
    bad_product = client.get(
        "/api/v1/inventory/stock/balance",
        params={"product_ids": "not-a-uuid"},
    )
    assert bad_product.status_code == 400, bad_product.text

    bad_warehouse = client.get(
        "/api/v1/inventory/stock/balance",
        params={"warehouse_ids": "not-a-uuid"},
    )
    assert bad_warehouse.status_code == 400, bad_warehouse.text


# ============================== review round 5, one entry per product code (added)
#
# Live evidence (`tests/chatbot/journeys/dealer-stock-verdict.EVIDENCE.md`, Run 2, case D
# turn 1): the dealer contact spans two companies that both carry product code MHS1028, so
# the block returned two entries for the one code and the question read "How many units do
# you need for MHS1028, MHS1028 and MSK11A-QT?". A full answer would then print two verdict
# lines for one code, and the task would hold two slots the dealer sees as one product.
#
# Ruling (owner, review round 5): a dealer sees ONE product per code. The merge happens in
# the backend block, where the figures live - entries whose `product_code` matches
# case-insensitively inside the one response collapse into one, summing on hand, open SO,
# incoming and purchase BEFORE `verdict()` runs, taking the earliest incoming ETA, keeping
# the first row's `product_id` in page order, and honouring `requested_quantities` keyed on
# ANY of the merged ids. `detailed` and `compact` are untouched.


def test_same_product_code_in_two_companies_is_one_entry_judged_on_the_sum(db):
    """The ruling's own scenario. Sorento holds 10 with 4 on open SO (net 6), Mocha holds 9
    with 3 on open SO (net 6). Ask 10.

    Merged, the dealer is judged on 12 and the answer is yes. Unmerged, each company's own
    6 is short of 10 and BOTH entries answer no - which is the defect, twice over: two
    lines for one code, and both of them wrong. `product_id` is the first id in page order
    (review round 6: the CALLER's `product_ids` order, so the first of the two named
    here), which is the id the task's slot then carries and the next fetch sends a
    quantity back for."""
    seed_mocha(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    sorento_wh = _wh(db, unique_code("ZZTSRW")[:50])
    mocha_wh = warehouse(db, company_id=MOCHA_ID, code=unique_code("ZZTMCW")[:50])
    code = unique_code("ZZTDUP")[:50]
    sorento_p = product(db, company_id=DEFAULT_COMPANY_ID, code=code)
    mocha_p = product(db, company_id=MOCHA_ID, code=code)
    stock(
        db,
        company_id=DEFAULT_COMPANY_ID,
        product_id=sorento_p.id,
        warehouse_id=sorento_wh.id,
        on_hand=10,
    )
    stock(
        db, company_id=MOCHA_ID, product_id=mocha_p.id, warehouse_id=mocha_wh.id, on_hand=9
    )
    _so_line(db, product_id=sorento_p.id, warehouse_id=sorento_wh.id, ordered=4)
    _so_line(
        db,
        product_id=mocha_p.id,
        warehouse_id=mocha_wh.id,
        ordered=3,
        company_id=MOCHA_ID,
    )
    contact = _contact(db)
    _policy_row(
        db,
        mode="availability",
        warehouse_ids=[sorento_wh.id, mocha_wh.id],
        contact=contact,
    )
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[sorento_p.id, mocha_p.id],
        contact_id=contact.id,
        requested_quantities={sorento_p.id: 10},
    )

    assert len(result["stock_availability"]) == 1, result["stock_availability"]
    assert result["stock_availability"][0] == {
        "product_id": sorento_p.id,
        "product_code": code,
        "product_name": code,
        "needs_quantity": False,
        "requested_qty": 10,
        "available": True,
        "verdict": "available",
        # 10 of 12 is at or over the 50% default threshold, so the yes still says
        # "running low" - the same rule a single-company entry follows.
        "running_low": True,
        "disclaimer": None,
    }
    # `pagination.total` still counts PRODUCTS (2 here) - the merge is about what the
    # dealer is told, not about how the page was walked - so 2 is not a forbidden number.
    _assert_no_quantity_anywhere(result, {10, 9, 4, 3, 12, 6})


def test_merged_entry_sums_supply_takes_the_earliest_eta_and_matches_code_case_blind(db):
    """The rest of the ruling, in one scenario. The two codes differ only in CASE, so a
    case-sensitive match would leave them apart. Nothing on hand anywhere; incoming 3 (ETA
    March) in Sorento and 4 (ETA February) in Mocha; open PO 5 and 4.

    Merged: deficit 10, incoming 7, purchase 9 - both sources named, earliest ETA
    February. Unmerged, neither side can cover its own 10 from 3 + 5 or 4 + 4, so the
    entry would carry NO disclaimer at all. The ask is keyed on the MOCHA id here, the
    one that is not necessarily first in page order, because a quantity given for any of
    the merged ids is a quantity for the merged entry."""
    seed_mocha(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    sorento_wh = _wh(db, unique_code("ZZTSRW")[:50])
    mocha_wh = warehouse(db, company_id=MOCHA_ID, code=unique_code("ZZTMCW")[:50])
    stem = unique_code("ZZTCASE")[:50]
    sorento_p = product(db, company_id=DEFAULT_COMPANY_ID, code=stem.upper())
    mocha_p = product(db, company_id=MOCHA_ID, code=stem.lower())
    stock(
        db,
        company_id=DEFAULT_COMPANY_ID,
        product_id=sorento_p.id,
        warehouse_id=sorento_wh.id,
        on_hand=0,
    )
    stock(
        db, company_id=MOCHA_ID, product_id=mocha_p.id, warehouse_id=mocha_wh.id, on_hand=0
    )
    _allocation(
        db,
        product_id=sorento_p.id,
        warehouse_id=sorento_wh.id,
        allocated=3,
        expected_date=date(2026, 3, 1),
    )
    _allocation(
        db,
        product_id=mocha_p.id,
        warehouse_id=mocha_wh.id,
        allocated=4,
        expected_date=date(2026, 2, 1),
        company_id=MOCHA_ID,
    )
    _po_line(db, product_id=sorento_p.id, warehouse_id=sorento_wh.id, ordered=5)
    _po_line(
        db,
        product_id=mocha_p.id,
        warehouse_id=mocha_wh.id,
        ordered=4,
        company_id=MOCHA_ID,
    )
    contact = _contact(db)
    _policy_row(
        db,
        mode="availability",
        warehouse_ids=[sorento_wh.id, mocha_wh.id],
        contact=contact,
    )
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[sorento_p.id, mocha_p.id],
        contact_id=contact.id,
        requested_quantities={mocha_p.id: 10},
    )

    assert len(result["stock_availability"]) == 1, result["stock_availability"]
    entry = result["stock_availability"][0]
    assert entry["product_code"] in {stem.upper(), stem.lower()}
    assert entry["requested_qty"] == 10
    assert entry["verdict"] == "not_available"
    assert entry["disclaimer"] == {
        "sources": ["incoming", "purchase"],
        # 10 of the 16 both sources together can find is at or over the 50% default.
        "limited": True,
        "incoming_eta": "2026-02-01",
        "purchase_eta_days": 90,
    }
    _assert_no_quantity_anywhere(result, {3, 4, 5, 7, 9, 16})


# ================================ review round 6, the asked order (finding B)
#
# Live evidence Run 3, finding B: asked "stock for MWT5727SS-CR 5, MHS1028 60, ...",
# answered "Noted: MHS1028 x 60, MWT5727SS-CR x 5." - the reply reordered the dealer's
# own products. `ordered_ids` above pages the candidates by `product_code` asc, which is
# the right order for the catalogue case ("what stock do you have?") and the wrong one
# whenever the caller named the products: then the list IS the order, and the task's
# slots and every later reply follow the block.


def test_availability_entries_follow_the_callers_product_ids_order(db):
    """The caller's order wins over product_code order. Both products here are named,
    and they are named in the order that is NOT alphabetical, so a page-ordered answer
    and an ask-ordered one cannot be confused."""
    brw = _wh(db, unique_code("ZZTORD")[:50])
    first = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("ZZTZED")[:50])
    second = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("ZZTALP")[:50])
    for p in (first, second):
        stock(
            db,
            company_id=DEFAULT_COMPANY_ID,
            product_id=p.id,
            warehouse_id=brw.id,
            on_hand=100,
        )
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[first.id, second.id],
        contact_id=contact.id,
        requested_quantities={first.id: 5, second.id: 60},
    )

    assert [e["product_code"] for e in result["stock_availability"]] == [
        first.product_code,
        second.product_code,
    ]


def test_availability_with_no_products_named_stays_in_page_order(db):
    """The catalogue case is untouched: nothing was named, so there is no asked order
    to keep and the page's own `product_code` order is the answer's."""
    brw = _wh(db, unique_code("ZZTORD")[:50])
    zed = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("ZZTZED")[:50])
    alpha = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("ZZTALP")[:50])
    for p in (zed, alpha):
        stock(
            db,
            company_id=DEFAULT_COMPANY_ID,
            product_id=p.id,
            warehouse_id=brw.id,
            on_hand=100,
        )
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(contact_id=contact.id, requested_qty=5)

    codes = [e["product_code"] for e in result["stock_availability"]]
    assert codes == sorted(codes)
