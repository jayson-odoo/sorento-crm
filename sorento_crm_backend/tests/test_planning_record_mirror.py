"""Planning record mirrors every core line on its own - no Re-sync click (issue #969).

Contract: `documentation/plans/scm/PLAN-scm-planning-record-mirror.md` section 3-4 and
`documentation/plans/scm/scm-planning-record-mirror-acceptance-criteria.md` AC-PR1..PR7.

TEST-FIRST. Today neither confirm path (`POST .../sales-orders/{pso_id}/confirm`,
`POST .../fulfilment-planning/confirm-all`) nor the line ingest
(`app/services/scm/sales_order_service.py::_upsert_lines`) calls
`ProjectSOAdoptionService.mirror_missing_lines` - a core line inserted after an order was
adopted has no `projects.sales_order_lines` mirror, is invisible to
`ProjectSupplyService.lines_of()`, and cannot be confirmed at all (the frontend reads its
board contribution's `project_line_id: null` as the `no_mirror` reason,
`app/(protected)/project-sales/_shared/lib/fulfilmentBoard.ts`). That label is FE-derived
from the board contribution; the backend-observable equivalent this file asserts is: (a) the
mirror row itself exists after the write, and (b) `ConfirmResult.lines_undecided` - computed
as `len(lines_of(order.id)) - decided` at the end of `confirm()` - counts the line, which it
cannot do until the self-heal makes `lines_of()` return it.

Two halves, two seams:
- AC-PR1/PR2/PR6 drive the confirm route/confirm-all HTTP surface (reusing the fixture chain
  from `tests/test_so_supply_confirmation.py`, Postgres via `tests/_pg_fixture.py::blank_session`).
- AC-PR3/PR4/PR5/PR7 drive `SalesOrderService.update` -> `_upsert_lines` directly (reusing the
  fixture chain from `tests/scm/test_sales_order_line_upsert.py`, Postgres via
  `tests/_pg_fixture.py::pg_session`, rolled back).

Every test seeds its own full chain - company, product(s), warehouse, core order and lines,
adoption mirror - nothing borrowed from an existing row (CI's database is empty).
"""
from __future__ import annotations

import uuid

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_ADOPTED,
    SO_STATUS_DRAFT,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
)
from app.schemas.scm_orders import SalesOrderUpdate
from app.services.scm.sales_order_service import SalesOrderService

import pytest

from tests._pg_fixture import pg_session, unique_code

from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    _client,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _restore,
    _stock,
    api,
)

MARKER = "ZZTPRM"


def _u() -> str:
    return str(uuid.uuid4())


# =============================================================================================
# AC-PR1 / AC-PR2 / AC-PR6 - the confirm route and confirm-all self-heal before posting
# =============================================================================================


def test_confirm_mirrors_missing_line_then_posts(api):
    """AC-PR1: an adopted order, plus a core line inserted after adoption (no mirror). CS
    confirms the already-mirrored line; the response must not be blind to the late line -
    a mirror row for it must exist, and the confirm's own accounting (`lines_undecided`)
    must count it, which only happens once `lines_of()` can see it."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=10)

    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _project_so(db, world.project, status=SO_STATUS_ADOPTED, so_id=core_so.id)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    # Arrived after adoption - nobody has mirrored it.
    late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The late line is on the record now - undecided, but no longer missing from it.
    assert body["lines_undecided"] == 1, body

    db.expire_all()
    mirror = (
        db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == order.id,
            ProjectSalesOrderLine.core_sales_order_line_id == late_core_line.id,
        )
        .first()
    )
    assert mirror is not None, (
        "the late core line must gain a mirror on confirm (self-heal before the line index "
        "is built)"
    )


def test_confirm_all_mirrors_for_every_order(api):
    """AC-PR2: two adopted orders, each with one late core line - confirm-all posts both,
    and both gain their mirror, each in its own per-order transaction."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=20)

    seeded = []
    for _ in range(2):
        core_so = _core_so(db, world.company_id)
        core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
        order = _project_so(db, world.project, status=SO_STATUS_ADOPTED, so_id=core_so.id)
        line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
        late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
        seeded.append((order, line, late_core_line))
    db.commit()

    payload = {
        "orders": [
            {
                "pso_id": order.id,
                "lines": [
                    _line_payload(
                        line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]
                    )
                ],
            }
            for order, line, _late in seeded
        ]
    }
    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json=payload)
    assert response.status_code == 200, response.text
    results = {row["pso_id"]: row for row in response.json()["results"]}

    db.expire_all()
    for order, _line, late_core_line in seeded:
        result = results[order.id]
        assert result["ok"] is True, result

        mirror = (
            db.query(ProjectSalesOrderLine)
            .filter(
                ProjectSalesOrderLine.project_sales_order_id == order.id,
                ProjectSalesOrderLine.core_sales_order_line_id == late_core_line.id,
            )
            .first()
        )
        assert mirror is not None, f"order {order.id}'s late line must be mirrored too"


def test_mirror_is_idempotent_on_confirm(api):
    """AC-PR6: confirm the same order twice - exactly one mirror line per core line, never
    a duplicate, on the second self-heal finding nothing missing."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=10)

    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _project_so(db, world.project, status=SO_STATUS_ADOPTED, so_id=core_so.id)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
    db.commit()

    payload = {
        "lines": [
            _line_payload(line_1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}])
        ]
    }
    first = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert first.status_code == 200, first.text
    second = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert second.status_code == 200, second.text

    db.expire_all()
    mirrors = (
        db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == order.id,
            ProjectSalesOrderLine.core_sales_order_line_id == late_core_line.id,
        )
        .all()
    )
    assert len(mirrors) == 1, "confirming twice must not duplicate the mirror line"


# =============================================================================================
# AC-PR3 / AC-PR4 / AC-PR5 / AC-PR7 - the line ingest self-heals an adopted order's mirror
# =============================================================================================


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(
        id=_u(), category_code=unique_code(MARKER), category_name=f"{MARKER} cat"
    )
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product_a = Product(
        id=_u(), product_code=unique_code("SKUA"), product_name=f"{MARKER} a",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    product_b = Product(
        id=_u(), product_code=unique_code("SKUB"), product_name=f"{MARKER} b",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    product_c = Product(
        id=_u(), product_code=unique_code("SKUC"), product_name=f"{MARKER} c",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    customer = Customer(id=_u(), customer_code=unique_code("C"), customer_name=f"{MARKER} Acme")
    warehouse = Warehouse(
        id=_u(), warehouse_code=unique_code("WH")[:50], warehouse_name=f"{MARKER} wh"
    )
    db.add_all([product_a, product_b, product_c, customer, warehouse])
    db.flush()
    return {
        "product_a": product_a, "product_b": product_b, "product_c": product_c,
        "customer": customer, "warehouse": warehouse,
    }


def _uploaded_order(db, world, *, qty_ordered=10, qty_delivered=3) -> tuple[SalesOrder, SalesOrderLine]:
    so = SalesOrder(
        id=_u(), so_number=unique_code(MARKER), status="open",
        customer_id=world["customer"].id, source_system="scm_upload",
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_a"].id,
        qty_ordered=qty_ordered, qty_delivered=qty_delivered, line_status="open",
        source_system="scm_upload",
    )
    db.add(line)
    db.flush()
    return so, line


def _adopted_mirror(db, so, *, project_id=None, status=SO_STATUS_ADOPTED):
    project_so = ProjectSalesOrder(
        id=_u(), project_id=project_id, provisional_ref=unique_code(MARKER),
        status=status, so_id=so.id,
    )
    db.add(project_so)
    db.flush()
    return project_so


def test_ingest_new_line_on_adopted_order_mirrors_it(db, world):
    """AC-PR3: `_upsert_lines` receives a payload adding a new SKU on an adopted order - a
    mirror line for the new core line must exist in the same transaction, with `line_no` =
    the previous max + 1."""
    so, line = _uploaded_order(db, world)
    project_so = _adopted_mirror(db, so)
    mirror_line = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=line.id,
        line_no=1, product_id=world["product_a"].id, qty=10,
    )
    db.add(mirror_line)
    db.flush()

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[
            {"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""},
            {"sku": world["product_b"].product_code, "qty_ordered": 5, "uom": ""},
        ]),
        user_id=None,
    )

    assert len(out["lines"]) == 2
    new_core_id = next(ln["id"] for ln in out["lines"] if ln["id"] != line.id)

    db.expire_all()
    new_mirror = (
        db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == project_so.id,
            ProjectSalesOrderLine.core_sales_order_line_id == new_core_id,
        )
        .first()
    )
    assert new_mirror is not None, "the new core line must gain a mirror in the same transaction"
    assert new_mirror.line_no == 2, "line_no must be the previous max (1) + 1"


def test_ingest_on_unadopted_order_adds_no_mirror(db, world):
    """AC-PR4 (guard - existing behaviour, may already be green): an order with no planning
    record gains no `projects.sales_order_lines` row when a new SKU is ingested."""
    so, line = _uploaded_order(db, world)

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[
            {"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""},
            {"sku": world["product_b"].product_code, "qty_ordered": 5, "uom": ""},
        ]),
        user_id=None,
    )

    new_core_id = next(ln["id"] for ln in out["lines"] if ln["id"] != line.id)
    db.expire_all()
    assert (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id == new_core_id)
        .count()
        == 0
    )


def test_ingest_prune_and_mirror_in_one_pass(db, world):
    """AC-PR5: one payload removes a line and adds another - the removed line's empty
    mirror is pruned (existing behaviour), the added line is mirrored, and the surviving
    mirror keeps its `line_no`."""
    so, line = _uploaded_order(db, world)
    second = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_b"].id,
        qty_ordered=5, qty_delivered=0, line_status="open",
    )
    db.add(second)
    db.flush()
    project_so = _adopted_mirror(db, so)
    mirror_kept = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=line.id,
        line_no=1, product_id=world["product_a"].id, qty=10,
    )
    mirror_removed = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=second.id,
        line_no=2, product_id=world["product_b"].id, qty=5,
    )
    db.add_all([mirror_kept, mirror_removed])
    db.flush()

    # Keeps product_a (matched), drops product_b (removed), adds product_c (new).
    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[
            {"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""},
            {"sku": world["product_c"].product_code, "qty_ordered": 7, "uom": ""},
        ]),
        user_id=None,
    )

    assert len(out["lines"]) == 2
    new_core_id = next(ln["id"] for ln in out["lines"] if ln["id"] != line.id)

    db.expire_all()
    assert db.get(SalesOrderLine, second.id) is None, "the removed core line must go"
    assert db.get(ProjectSalesOrderLine, mirror_removed.id) is None, (
        "its empty adoption mirror line must be pruned"
    )
    kept = db.get(ProjectSalesOrderLine, mirror_kept.id)
    assert kept is not None and kept.line_no == 1, "the surviving mirror keeps its line_no"

    new_mirror = (
        db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == project_so.id,
            ProjectSalesOrderLine.core_sales_order_line_id == new_core_id,
        )
        .first()
    )
    assert new_mirror is not None, "the newly added core line must be mirrored too"


def test_ingest_leaves_a_mirror_with_a_decision_or_link_untouched(db, world):
    """AC-PR7 (guard - existing behaviour, may already be green): a mirror line that
    already carries a decision or a link (here, an `SOLineAllocation`) is left exactly as
    the existing prune rules leave it - cancelled in place, never pruned - when the same
    ingest that adds this self-heal also drops its core line."""
    so, line = _uploaded_order(db, world)
    second = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_b"].id,
        qty_ordered=5, qty_delivered=0, line_status="open",
    )
    db.add(second)
    db.flush()
    project_so = _adopted_mirror(db, so)
    mirror_kept = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=line.id,
        line_no=1, product_id=world["product_a"].id, qty=10,
    )
    mirror_linked = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=second.id,
        line_no=2, product_id=world["product_b"].id, qty=5,
    )
    db.add_all([mirror_kept, mirror_linked])
    db.flush()
    allocation = SOLineAllocation(
        id=_u(), so_line_id=mirror_linked.id, source_type="order", qty=5,
    )
    db.add(allocation)
    db.flush()

    # Drops product_b (carries an allocation -> cancelled, not pruned) and adds product_c.
    SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[
            {"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""},
            {"sku": world["product_c"].product_code, "qty_ordered": 7, "uom": ""},
        ]),
        user_id=None,
    )

    db.expire_all()
    reloaded_second = db.get(SalesOrderLine, second.id)
    assert reloaded_second is not None and reloaded_second.line_status == "cancelled"
    reloaded_mirror = db.get(ProjectSalesOrderLine, mirror_linked.id)
    assert reloaded_mirror is not None, "a mirror carrying an allocation is untouched, not pruned"
    assert db.get(SOLineAllocation, allocation.id) is not None
