"""The Coverage Timeline HTTP contract: ``GET /api/v1/scm/coverage`` (UAC Group B).

TEST-FIRST. The route does not exist yet; every test here is expected to be red on the
route's absence and to go green only when the endpoint serves the shape the frontend has
already been built against.

**The contract is `reorder/types/coverage.types.ts`, not this suite's judgement.** Field
names, nullability and the two deliberate omissions (no ids, no stored timeline) come from
there. Where the type file and the mock store disagree with what ``CoverageService``
currently produces, the type file wins and the gap is the implementer's work.

What this suite is NOT. ``tests/scm/test_coverage_service.py`` already proves the maths and
the pool resolution against real tables. Nothing here re-derives a balance for its own sake:
the figures are repeated only where the WIRE has to carry them (the ADR-0011 worked example
reaching the browser as four balances and a shortfall is a different claim from the service
computing them).

Seeding. Every product, warehouse, customer, supplier, SO, PO, shipment, role and permission
is created by the test under the ``ZZT`` marker, inside the ``scm_app`` savepoint. Nothing is
borrowed with ``LIMIT 1`` and nothing asserts about a row the environment happened to hold:
CI's database is empty, so a borrowed lookup is the difference between green locally and a
NOT NULL violation in CI. That includes the RBAC chain - the existing SCM route tests attach
the shipped ``purchasing`` role, which on a freshly migrated database may not carry
``scm.dashboard.view`` at all, so this suite seeds its own role and links the permission.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi.testclient import TestClient
from zoneinfo import ZoneInfo

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import (
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from tests._pg_fixture import unique_code
from tests.scm.conftest import requires_pg
from tests.scm.test_coverage_service import _po_line, _so_line, _stock
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

URL = "/api/v1/scm/coverage"

# The permission the route is gated on. A constant of the CODE, not of the environment, so
# the row is created when the database does not already carry it.
VIEW_PERMISSION = "scm.dashboard.view"

MALAYSIA = ZoneInfo("Asia/Kuala_Lumpur")

# Every field in `CoverageTimeline` (coverage.types.ts). Asserted as an exact set: a missing
# field breaks the screen, and an extra one is a field the contract was never reviewed for.
TIMELINE_FIELDS = {
    "product_code",
    "product_name",
    "pool_code",
    "locations",
    "floor",
    "opening_balance",
    "rows",
    "closing_balance",
    "shortfall",
    "peak_deficit",
    "availability",
    "allocations",
    "buy_qty",
    "use_stock",
    "undated_demand",
    "transfer_proposals",
    "horizon_months",
    "horizon_end",
    "excluded_event_count",
    "unattributed_in_transit_qty",
    # Placed on a PO and NOT counted in the balance, reported so a shortfall does not read
    # as "nobody has done anything about this".
    "qty_ordered_not_incoming",
    "unplaceable_demand_qty",
    "unplaceable_on_order_qty",
    "computed_at",
}
EVENT_FIELDS = {"at", "qty", "kind", "ref", "label", "location", "supply_stage"}
AVAILABILITY_FIELDS = {"own", "pool", "other", "pool_location", "other_locations"}
SHORTFALL_FIELDS = {"at", "qty", "ref", "label"}
ALLOCATION_FIELDS = {"source_type", "qty", "location", "needs_claim"}
UNDATED_FIELDS = {"so_number", "item_code", "qty", "location"}
PROPOSAL_FIELDS = {
    "proposal_ref",
    "from_pool_code",
    "available_qty",
    "qty",
    "transfer_cost",
    "lead_time_days",
    "arrives_at",
}


def _u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# principal
# --------------------------------------------------------------------------- #

def _grant_view(db, uid: str) -> None:
    """Give ``uid`` ``scm.dashboard.view`` through a role this test owns.

    The role is created rather than borrowed because "whatever roles hold the permission" is
    an assertion about the environment. The PERMISSION row is get-or-create: its slug is
    fixed by the route's own decorator, so on a migrated database it already exists and on a
    bare one it must be seeded, and either way the grant resolves.
    """
    role = UserRole(id=_u(), slug=unique_code("scmrole"), name=unique_code("SCM role"))
    db.add(role)
    db.flush()

    perm = (
        db.query(UserPermission)
        .filter(UserPermission.slug == VIEW_PERMISSION)
        .one_or_none()
    )
    if perm is None:
        perm = UserPermission(id=_u(), slug=VIEW_PERMISSION, name="View SCM dashboard")
        db.add(perm)
        db.flush()

    db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role.id))
    db.flush()


def _client(scm_app, *, granted: bool = True) -> TestClient:
    """An authenticated client carrying a company of this test's own making.

    Reuses ``as_company_user`` (the owned tables fail closed without an active company, so
    the dependency override has to supply one) and then attaches the view permission to the
    user it seeded. The uid is read back off the installed override because that IS where the
    principal lives - inventing a second user here would authenticate one and authorise the
    other, and the route would 403 for a reason that has nothing to do with the test.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    if granted:
        _grant_view(db, app.dependency_overrides[gcu]()["id"])
    return TestClient(app)


# --------------------------------------------------------------------------- #
# seeding
# --------------------------------------------------------------------------- #

def _chain(db) -> dict:
    """A product, a pool, and two customer bins pointing at it. The whole FK chain.

    Mirrors the ``chain`` fixture in ``test_coverage_service`` deliberately: Postgres
    enforces the NOT NULLs the ORM defaults do not cover (category_code, uom_code/uom_name,
    products.base_uom_id, list_price), so an approximation aborts the transaction.
    """
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    product = Product(
        id=_u(),
        product_code=unique_code("SKU"),
        product_name="Wall hung WC 7408",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=0,
    )
    pool = Warehouse(
        id=_u(), warehouse_code=unique_code("POOL"), warehouse_name="pool", is_active=True
    )
    db.add_all([product, pool])
    db.flush()

    bin_a = Warehouse(
        id=_u(), warehouse_code=unique_code("BINA"), warehouse_name="bin a",
        is_active=True, pool_warehouse_id=pool.id,
    )
    bin_b = Warehouse(
        id=_u(), warehouse_code=unique_code("BINB"), warehouse_name="bin b",
        is_active=True, pool_warehouse_id=pool.id,
    )
    pool.pool_warehouse_id = pool.id  # a pool is its own pool
    db.add_all([bin_a, bin_b])
    db.flush()
    return {"product": product, "pool": pool, "bin_a": bin_a, "bin_b": bin_b}


def _shipment_line(db, product, qty, arrival, *, status="in_transit", destination=None):
    """One inbound shipment line: supply at stage ``in_transit``.

    ``destination`` writes the ``spo_allocations`` row that says WHERE the container is
    going. It is not optional decoration: nothing on `inbound_shipments` or its lines names
    a warehouse, so an unallocated container belongs to no pool and is deliberately counted
    for none of them (see ``test_coverage_in_transit_destination``). Pass the bin whose pool
    the test is asking about, or the supply will correctly not appear.
    """
    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="GUANGDONG SW")
    db.add(sup)
    db.flush()
    ship = InboundShipment(
        id=_u(),
        shipment_number=unique_code("SH")[:50],
        supplier_id=sup.id,
        shipment_date=date(2026, 7, 20),
        estimated_arrival_date=arrival,
        shipment_status=status,
    )
    db.add(ship)
    db.flush()
    db.add(InboundShipmentLine(
        id=_u(), shipment_id=ship.id, product_id=product.id,
        quantity_shipped=qty, quantity_received=0, cartons_count=1,
        spo_allocated_quantity=(qty if destination is not None else 0),
        line_status="in_transit",
    ))
    db.flush()
    if destination is not None:
        db.add(SPOAllocation(
            id=_u(), spo_number=unique_code("SPO")[:50], inbound_shipment_id=ship.id,
            product_id=product.id, warehouse_id=destination.id, allocated_quantity=qty,
        ))
        db.flush()
    return ship


def _adr_worked_example(db, chain) -> dict:
    """Opening 140; demand 135 due 1 Jul 2026; demand 72 due 3 Aug 2026; 200 arriving 25 Aug.

    Verbatim from ADR-0011 and the Group B acceptance criteria, not invented figures. The
    arriving 200 is now an ALLOCATED SHIPMENT rather than a purchase order: the figures and
    the point of the example are unchanged, but a purchase order is an order placed, and
    only the SPO allocation against it is stock on its way in.
    """
    _stock(db, chain["product"], chain["pool"], 140)
    first = _so_line(db, chain["product"], chain["bin_a"], 135, date(2026, 7, 1),
                     customer_name="MARYAM TUJU RESIDENCE")
    second = _so_line(db, chain["product"], chain["bin_a"], 72, date(2026, 8, 3),
                      customer_name="MARYAM TUJU RESIDENCE")
    ship = _shipment_line(db, chain["product"], 200, date(2026, 8, 25),
                          destination=chain["bin_a"])
    return {"first_so": first, "second_so": second, "shipment": ship}


def _get(client, *, product_code=None, pool_code=None, floor=None):
    params = {}
    if product_code is not None:
        params["product_code"] = product_code
    if pool_code is not None:
        params["pool_code"] = pool_code
    if floor is not None:
        params["floor"] = floor
    return client.get(URL, params=params)


# --------------------------------------------------------------------------- #
# id / UUID leak detection
# --------------------------------------------------------------------------- #

def _iter_nodes(node, path="$"):
    """Every (path, key, value) in the payload, however deeply nested."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key, value
            yield from _iter_nodes(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_nodes(value, f"{path}[{index}]")


def _is_uuid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# =========================================================================== #
# 1. the shape
# =========================================================================== #

def test_the_payload_carries_every_contract_field_and_no_identifier_anywhere(scm_app):
    """A UUID on this screen is unusable and a missing field is a blank panel.

    Both halves are asserted structurally rather than by spot-checking the fields a reviewer
    happens to remember. The frontend is already built against this exact interface, so an
    omission is a runtime undefined in the browser rather than a type error anyone catches,
    and an id that leaks in is something a planner is expected to read aloud to a supplier.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    _adr_worked_example(db, chain)

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    assert set(body) == TIMELINE_FIELDS
    assert body["rows"], "the worked example must produce rows"
    for row in body["rows"]:
        assert set(row) == {"event", "balance"}
        assert set(row["event"]) == EVENT_FIELDS
    assert set(body["availability"]) == AVAILABILITY_FIELDS
    assert set(body["shortfall"]) == SHORTFALL_FIELDS
    for allocation in body["allocations"]:
        assert set(allocation) == ALLOCATION_FIELDS
    for undated in body["undated_demand"]:
        assert set(undated) == UNDATED_FIELDS
    for proposal in body["transfer_proposals"]:
        assert set(proposal) == PROPOSAL_FIELDS

    offenders = [
        (path, value)
        for path, key, value in _iter_nodes(body)
        if key == "id" or key.endswith("_id") or _is_uuid(value)
    ]
    assert offenders == [], f"identifier leaked to the wire: {offenders}"


# =========================================================================== #
# 2. the worked example
# =========================================================================== #

def test_a_positive_closing_balance_is_reported_alongside_a_real_shortfall(scm_app):
    """Supply dated after a demand event does not cover it (AC-B4), and this is the case
    that proves the whole date axis was worth building.

    A dateless net position for this product reads +133 and reports nothing wrong, while the
    order due 3 August is 67 units short and the container that would have covered it lands
    22 days late. Reporting only the closing balance is the error that makes a planning tool
    worthless in week one, so the payload has to carry BOTH numbers at once.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    seeded = _adr_worked_example(db, chain)

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    assert body["opening_balance"] == 140
    assert [row["balance"] for row in body["rows"]] == [140, 5, -67, 133]
    assert [row["event"]["at"] for row in body["rows"]] == [
        None, "2026-07-01", "2026-08-03", "2026-08-25",
    ]
    assert body["shortfall"]["qty"] == 67
    assert body["shortfall"]["at"] == "2026-08-03"
    assert body["shortfall"]["ref"] == seeded["second_so"].so_number
    assert body["peak_deficit"] == 67
    assert body["closing_balance"] == 133
    assert body["floor"] == 0


# =========================================================================== #
# 3. the pool regression
# =========================================================================== #

def test_demand_of_67_against_a_pool_holding_4397_answers_use_stock_not_a_buy(scm_app):
    """Item SRTWT7408, and the defect this module exists to fix.

    Netting per warehouse sees 67 committed against a customer bin holding nothing, reports a
    shortfall and recommends buying 67 units of an item with 4,397 sitting in the shared pool
    one row above. That was the first line of the first report anyone read, so a green suite
    that does not contain this case proves nothing.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    _stock(db, chain["product"], chain["pool"], 4397)
    _so_line(db, chain["product"], chain["bin_a"], 67, date(2026, 8, 14),
             customer_name="BANDAR BARU DEVELOPMENT")

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    assert body["use_stock"] is True
    assert body["buy_qty"] == 0, "a buy on an item holding 4,397 is the original defect"
    assert body["availability"]["pool"] == 4397
    assert body["availability"]["pool_location"] == chain["pool"].warehouse_code
    assert [(a["source_type"], a["qty"]) for a in body["allocations"]] == [("brw", 67)]
    assert body["shortfall"] is None


# =========================================================================== #
# 4. supply stages
# =========================================================================== #

def test_a_purchase_order_does_not_reach_the_payload_but_its_shipment_does(scm_app):
    """PO -> SPO -> GRN: the payload carries the middle link only.

    A purchase order is an order PLACED, and the supplier may have shipped nothing against
    it; sending it as supply had the planner reading cover that does not exist. Both halves
    are asserted together, because "the PO is gone" alone would also pass if supply had been
    dropped entirely, and every product would then read short.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    _po_line(db, chain["product"], chain["bin_a"], 200, date(2026, 8, 10))
    _shipment_line(db, chain["product"], 60, date(2026, 8, 12),
                   destination=chain["bin_a"])

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    assert [row["event"]["supply_stage"] for row in body["rows"]] == [None, "in_transit"]
    assert [row["balance"] for row in body["rows"]] == [0, 60]
    assert body["closing_balance"] == 60


# =========================================================================== #
# 5. undated demand
# =========================================================================== #

def test_demand_with_no_date_anywhere_is_reported_not_dated_today_and_not_dropped(scm_app):
    """An undated commitment cannot be planned, and both ways of pretending otherwise lie.

    Dating it today fabricates a shortfall that sends someone to buy stock nobody asked for
    by that date; dropping it hides a real commitment. It is therefore carried out of band,
    where the screen can ask a human for the date instead of guessing one.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    so = _so_line(db, chain["product"], chain["bin_a"], 40, None)

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    assert body["undated_demand"] == [{
        "so_number": so.so_number,
        "item_code": chain["product"].product_code,
        "qty": 40,
        "location": chain["bin_a"].warehouse_code,
    }]
    # Not dated today: no dated row at all, and the balance is untouched.
    dated = [row["event"]["at"] for row in body["rows"] if row["event"]["at"]]
    assert date.today().isoformat() not in dated
    assert dated == []
    assert body["closing_balance"] == 0
    assert body["shortfall"] is None


# =========================================================================== #
# 6. cross-site stock
# =========================================================================== #

def test_cross_site_stock_is_offered_as_a_transfer_proposal_never_netted(scm_app):
    """Stock at another site is real, but reaching it costs money and takes days.

    Netting it silently produces a plan that is only true if a lorry nobody has booked
    arrives, so it stays out of the balance and surfaces as a proposal carrying its cost and
    lead time for a person to accept (AC-B1d). Both halves are asserted together because
    each alone is satisfiable the wrong way: suppressing the proposal, or quietly netting it.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    other_pool = Warehouse(
        id=_u(), warehouse_code=unique_code("OTHR"), warehouse_name="other site",
        is_active=True,
    )
    db.add(other_pool)
    db.flush()
    other_pool.pool_warehouse_id = other_pool.id
    _stock(db, chain["product"], other_pool, 500)
    _so_line(db, chain["product"], chain["bin_a"], 50, date(2026, 9, 5),
             customer_name="SETIA MUTIARA CITY")

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    # Never netted: the shortfall is the full 50 despite 500 sitting at the other site.
    assert body["closing_balance"] == -50
    assert body["shortfall"]["qty"] == 50
    assert other_pool.warehouse_code not in body["locations"]

    proposals = body["transfer_proposals"]
    assert len(proposals) == 1, "the other site's 500 must be offered, not hidden"
    proposal = proposals[0]
    assert proposal["from_pool_code"] == other_pool.warehouse_code
    assert proposal["available_qty"] == 500
    assert proposal["qty"] == 50
    # Cost and lead time are what make it a judgement rather than a free win, so the keys
    # are part of the contract even before a tenant has configured a figure.
    assert "transfer_cost" in proposal
    assert "lead_time_days" in proposal
    assert "arrives_at" in proposal


# =========================================================================== #
# 7. floor
# =========================================================================== #

def test_a_non_zero_floor_moves_the_shortfall_earlier(scm_app):
    """The floor is what makes a reorder point the one-bucket case of this timeline.

    A continuous SKU is short the moment it dips below its reorder point, not when it hits
    zero, and the difference is a whole month of lead time. If the floor were ignored the
    same product would be planned as though running to zero were acceptable, which is a
    stockout dressed up as a healthy balance.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    _adr_worked_example(db, chain)
    code, pool = chain["product"].product_code, chain["pool"].warehouse_code

    at_zero = _get(client, product_code=code, pool_code=pool, floor=0)
    at_fifty = _get(client, product_code=code, pool_code=pool, floor=50)

    assert at_zero.status_code == 200, at_zero.text
    assert at_fifty.status_code == 200, at_fifty.text

    assert at_zero.json()["shortfall"]["at"] == "2026-08-03"
    # Balance 5 after 1 July is already below a floor of 50, five weeks earlier.
    assert at_fifty.json()["floor"] == 50
    assert at_fifty.json()["shortfall"]["at"] == "2026-07-01"
    assert at_fifty.json()["shortfall"]["qty"] == 45
    assert at_fifty.json()["peak_deficit"] == 117


# =========================================================================== #
# 8. horizon
# =========================================================================== #

def test_the_horizon_bounds_the_timeline_and_states_how_many_events_it_dropped(scm_app):
    """An omission a screen does not mention is indistinguishable from data that is not there.

    A planner who cannot see that nine years of demand was excluded reads the visible
    shortfall as the whole picture. Bounding the axis is necessary (a ten-year tail makes the
    report unreadable), so the count of what was dropped is what keeps the bound honest
    (AC-B5).
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    near = _so_line(db, chain["product"], chain["bin_a"], 10, date(2026, 9, 1))
    far = _so_line(db, chain["product"], chain["bin_a"], 900, date(2035, 9, 1))

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    refs = [row["event"]["ref"] for row in body["rows"]]
    assert near.so_number in refs
    assert far.so_number not in refs
    assert body["excluded_event_count"] == 1
    assert body["closing_balance"] == -10

    assert isinstance(body["horizon_months"], int) and body["horizon_months"] > 0
    horizon_end = date.fromisoformat(body["horizon_end"])
    assert date(2026, 9, 1) <= horizon_end < date(2035, 9, 1)


# =========================================================================== #
# 9. computed_at
# =========================================================================== #

def test_computed_at_is_a_naive_malaysia_wall_clock_timestamp(scm_app):
    """An offset-aware timestamp gets re-converted downstream and displays eight hours out.

    This repo has already shipped that bug once: ``+08:00`` is technically correct and every
    consumer that re-normalises to UTC then renders 09:28 as 01:28. The timeline is computed
    per request and never stored (AC-B6), so this field is the only thing telling a planner
    how fresh the numbers are - a value that reads as the middle of the night makes them
    distrust a report that is in fact seconds old.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    _adr_worked_example(db, chain)

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    raw = r.json()["computed_at"]

    assert isinstance(raw, str) and raw
    assert not raw.endswith("Z")
    time_part = raw.split("T", 1)[1]
    assert "+" not in time_part and "-" not in time_part, f"offset on the wire: {raw}"

    parsed = datetime.fromisoformat(raw)
    assert parsed.tzinfo is None
    now = datetime.now(MALAYSIA).replace(tzinfo=None)
    assert abs((now - parsed).total_seconds()) < 600, (
        f"{raw} is not Malaysia wall-clock (now {now.isoformat()})"
    )


# =========================================================================== #
# 10. what is not supply
# =========================================================================== #

def test_a_closed_po_line_and_a_draft_po_contribute_nothing_to_supply(scm_app):
    """Both are stock that is not coming, and counting either suppresses the buy that fixes it.

    A draft PO is a recommendation nobody has committed to, so treating it as supply cancels
    the very shortfall that produced it. A CLOSED line is worse, because it looks committed:
    the outstanding-orders importer closes a line the supplier has dropped, ``scm.on_order_v``
    stops counting it, and a timeline that still shows it arriving disagrees with the
    dashboard while hiding a real shortfall.
    """
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)

    _po_line(db, chain["product"], chain["bin_a"], 100, date(2026, 8, 1), status="draft")

    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="KAILU")
    db.add(sup)
    db.flush()
    placed = PurchaseOrder(
        id=_u(), po_number=unique_code("PO"), supplier_id=sup.id, status="active"
    )
    db.add(placed)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=placed.id, product_id=chain["product"].id,
        warehouse_id=chain["bin_a"].id, qty_ordered=500, qty_received=0,
        expected_date=date(2026, 8, 10), line_status="closed",
    ))
    db.flush()

    r = _get(client, product_code=chain["product"].product_code,
             pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 200, r.text
    body = r.json()

    assert body["closing_balance"] == 0
    # Absent from the timeline, not netted to zero inside it: a row a planner can see is a
    # delivery a planner will count on.
    assert len(body["rows"]) == 1
    assert body["rows"][0]["event"]["kind"] == "opening"


# =========================================================================== #
# 11. auth and resolution failures
# =========================================================================== #

def test_a_principal_without_the_view_permission_is_denied_before_any_work(scm_app):
    """The timeline is the whole purchasing position for a product, priced and dated.

    Nothing is seeded here on purpose: the denial has to come from the permission check
    rather than from the query finding no rows, so a 404 or a 500 would both be the wrong
    answer even though neither leaks data. 403 before any work is also what keeps an
    unauthorised caller from using response timing to probe which products exist.
    """
    client = _client(scm_app, granted=False)

    r = _get(client, product_code="ZZT-DOES-NOT-EXIST", pool_code="ZZT-NO-POOL")

    assert r.status_code == 403, r.text
    assert VIEW_PERMISSION in r.text


def test_an_unknown_product_code_is_a_404_naming_the_product(scm_app):
    """A planner typing a code that is not in the catalogue needs to be told WHICH of the two
    codes failed, or the only way forward is to try both."""
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    missing = unique_code("NOSUCHSKU")

    r = _get(client, product_code=missing, pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 404, r.text
    assert missing in r.text
    assert "product" in r.text.lower()


def test_an_unknown_pool_code_is_a_404_naming_the_pool(scm_app):
    """The other half of the same message, asserted separately: one 404 covering both codes
    would let the route answer "not found" without ever saying what it looked for."""
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)
    missing = unique_code("NOSUCHPOOL")

    r = _get(client, product_code=chain["product"].product_code, pool_code=missing)

    assert r.status_code == 404, r.text
    assert missing in r.text
    assert "pool" in r.text.lower()


def test_a_request_with_no_product_code_is_a_422(scm_app):
    """Defaulting an absent product to something would answer a question nobody asked, and
    the answer would look like a real coverage position for a real SKU."""
    app, db, gcu, gcuk = scm_app
    client = _client(scm_app)
    chain = _chain(db)

    r = _get(client, pool_code=chain["pool"].warehouse_code)

    assert r.status_code == 422, r.text
    assert "product_code" in r.text
