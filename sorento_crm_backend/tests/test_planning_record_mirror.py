"""Planning record mirrors every core line on its own - no Re-sync click (issue #969).

Contract: `documentation/plans/scm/PLAN-scm-planning-record-mirror.md` section 3-4 and
`documentation/plans/scm/scm-planning-record-mirror-acceptance-criteria.md` AC-PR1..PR8.

Owner ruling 17 Sep 2026 (B2): the heal lives on the BOARD READ, not on confirm. A core
line inserted after an order was adopted has no `projects.sales_order_lines` mirror, is
invisible to `ProjectSupplyService.lines_of()`, and cannot be confirmed at all (the frontend
reads its board contribution's `project_line_id: null` as the `no_mirror` reason,
`app/(protected)/project-sales/_shared/lib/fulfilmentBoard.ts`). `FulfilmentBoardService
.build` - the one read that label is derived from, and the read the FE's confirm-all also
builds from - now runs `ProjectSOAdoptionService.mirror_missing_lines` for every adopted,
unauthored order it is asked about, before the line list is built, so the SAME response
already carries a `project_line_id` for the late line. `ProjectSupplyService.confirm` stays
a pure write and never mirrors on its own (AC-PR8 pins this).

Three more writers self-heal on their own, all bypassing `_upsert_lines`'s own self-heal
(review round 1: it has ONE caller, the manual FE edit) - the ESB push
(`document_ingest_service.py::_sync_lines`, AC-PR3b) and the Excel book upload
(`outstanding_import_service.py::apply`, AC-PR3c), each write core lines their own way and
each mirrors a new one in the same transaction, gated the same way the board read is: an
adopted, unauthored mirror only.

Two halves:
- AC-PR1/PR2/PR6/PR8 drive `GET /fulfilment-planning/board` then the confirm route/
  confirm-all HTTP surface (reusing the fixture chain from
  `tests/test_so_supply_confirmation.py`, Postgres via `tests/_pg_fixture.py::blank_session`).
- AC-PR3/PR3b/PR3c/PR4/PR5/PR7 drive `SalesOrderService.update` -> `_upsert_lines`, the ESB
  ingest route and `outstanding_import_service.apply` directly (reusing the fixture chains
  from `tests/scm/test_sales_order_line_upsert.py` and `tests/test_ingest_documents.py`,
  Postgres via `tests/_pg_fixture.py::pg_session`, rolled back).

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
# AC-PR1 / AC-PR2 / AC-PR6 / AC-PR8 - the BOARD READ self-heals; confirm never does
#
# Owner ruling 17 Sep 2026 (B2): heal on the board read, so the first Confirm posts every
# line; historical gaps heal when the board is opened. `GET /fulfilment-planning/board`
# (`FulfilmentBoardService.build`) is the one read the FE's `fulfilmentBoard.ts` derives
# `no_mirror` from (`!contribution.project_line_id`) and the list confirm-all reads too
# (`PlanningBoard.contributions`, never windowed). The confirm write stays a pure write.
# =============================================================================================


def _adopted_book_order(db, world, core_so):
    """The planning record the AutoCount book adoption leaves: `so_id` set, `adopted`, and
    NO project (`project_id IS NULL`), which is the heal's own gate. `_project_so` always
    stamps `world.project`, so it cannot build this shape."""
    from tests.test_so_supply_confirmation import _suffix

    order = ProjectSalesOrder(
        id=_u(), company_id=world.company_id, project_id=None,
        provisional_ref=f"ZZT-PSO-{_suffix()}", status=SO_STATUS_ADOPTED, so_id=core_so.id,
    )
    db.add(order)
    db.flush()
    return order


def _board(client, *so_numbers):
    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": ",".join(so_numbers), "granularity": "week"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _mirrors_of(db, order, core_line):
    return (
        db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == order.id,
            ProjectSalesOrderLine.core_sales_order_line_id == core_line.id,
        )
        .all()
    )


def _reserve_all(world, contributions):
    """One confirm line per board contribution, reserving its whole open qty at the pool."""
    return [
        _line_payload(
            c["project_line_id"],
            reserve=[{"warehouse_id": world.pool_wh.id, "qty": c["qty"]}],
        )
        for c in contributions
    ]


def test_board_read_mirrors_missing_line_then_confirm_posts(api):
    """AC-PR1: an adopted order plus a core line inserted after adoption (no mirror). Opening
    the board must come back with a `project_line_id` for the late line (no `no_mirror`-shaped
    null) and the mirror row must exist; confirming every line the board returned then posts
    with `lines_undecided == 0` and the decision covering the late line."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=15)

    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _adopted_book_order(db, world, core_so)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
    db.commit()

    board = _board(client, core_so.so_number)
    by_core = {c["line_id"]: c for c in board["contributions"]}
    assert late_core_line.id in by_core, "the late line must be on the board"
    late = by_core[late_core_line.id]
    assert late["project_line_id"] is not None, (
        "the board read must self-heal the late line's mirror so the FE never derives "
        "`no_mirror` for it"
    )
    db.expire_all()
    mirrors = _mirrors_of(db, order, late_core_line)
    assert len(mirrors) == 1
    assert mirrors[0].id == late["project_line_id"]

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": _reserve_all(world, board["contributions"])},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines_decided"] == 2, body
    assert body["lines_undecided"] == 0, body

    from app.models.project_so import SOLineAllocation, SOSupplyDecision

    active = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == "active",
        )
        .one()
    )
    covered = (
        db.query(SOLineAllocation)
        .filter(
            SOLineAllocation.decision_id == active.id,
            SOLineAllocation.so_line_id == mirrors[0].id,
        )
        .count()
    )
    assert covered == 1, "the decision must cover the late line"


def test_board_list_read_mirrors_for_every_order(api):
    """AC-PR2: two adopted orders, each with one late core line. The multi-order board read
    the FE's confirm-all builds from heals both (both mirrors exist, both lines carry a
    `project_line_id`); confirm-all then posts both."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=30)

    seeded = []
    for _ in range(2):
        core_so = _core_so(db, world.company_id)
        core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
        order = _adopted_book_order(db, world, core_so)
        _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
        late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
        seeded.append((core_so, order, late_core_line))
    db.commit()

    board = _board(client, *[core_so.so_number for core_so, _o, _l in seeded])
    by_core = {c["line_id"]: c for c in board["contributions"]}
    db.expire_all()
    for core_so, order, late_core_line in seeded:
        assert late_core_line.id in by_core, f"{core_so.so_number}'s late line must be on the board"
        assert by_core[late_core_line.id]["project_line_id"] is not None, (
            f"{core_so.so_number}'s late line must carry a project_line_id after the read"
        )
        assert len(_mirrors_of(db, order, late_core_line)) == 1

    by_so_number = {}
    for c in board["contributions"]:
        by_so_number.setdefault(c["so_number"], []).append(c)
    payload = {
        "orders": [
            {"pso_id": order.id, "lines": _reserve_all(world, by_so_number[core_so.so_number])}
            for core_so, order, _late in seeded
        ]
    }
    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json=payload)
    assert response.status_code == 200, response.text
    results = {row["pso_id"]: row for row in response.json()["results"]}
    for _so, order, _late in seeded:
        assert results[order.id]["ok"] is True, results[order.id]
        assert results[order.id]["lines_decided"] == 2, results[order.id]


def test_mirror_is_idempotent_on_board_read(api):
    """AC-PR6: read the board twice - exactly one mirror line per core line, never a
    duplicate, the second heal finding nothing missing."""
    client, world = api
    db = world.db

    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _adopted_book_order(db, world, core_so)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
    db.commit()

    _board(client, core_so.so_number)
    _board(client, core_so.so_number)

    db.expire_all()
    assert len(_mirrors_of(db, order, late_core_line)) == 1, (
        "reading the board twice must not duplicate the mirror line"
    )
    assert len(_mirrors_of(db, order, core_line_1)) == 1


def test_confirm_without_a_prior_board_read_does_not_mirror(api):
    """AC-PR8 (pins the seam): the heal lives on the READ, not the write. Confirming the
    existing lines directly, with no board read first, succeeds for the lines given and
    creates NO mirror for the late line - a future "helpful" confirm-side call is caught."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=10)

    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _adopted_book_order(db, world, core_so)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    late_core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line_1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}])
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["lines_decided"] == 1

    db.expire_all()
    assert _mirrors_of(db, order, late_core_line) == [], (
        "confirm is a pure write: it must not mirror the late line on its own"
    )


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


# =============================================================================================
# AC-PR3b / AC-PR3c - the two line writers that BYPASS `_upsert_lines`
#
# Lane B review (17 Sep 2026): `_upsert_lines` has ONE caller, the manual FE edit
# `PUT /sales-orders/{so_id}`. Every one of the 394 unmirrored lines on the 0915 copy is
# `source_system = autocount`, written by `document_ingest_service._sync_lines` (the ESB push,
# `POST /api/v1/external/ingest/sales_orders`), and the Excel book upload writes its own rows
# at `outstanding_import_service._write_change` (`db.add(bind.line(**fields))`). Neither
# passes through `_upsert_lines`, so the AC-PR3 self-heal there never sees them.
# =============================================================================================


def test_esb_ingest_new_line_on_adopted_order_mirrors_it():
    """AC-PR3b: the ESB push (`DocumentIngestService.ingest` -> `_sync_lines`) creates a
    core line on an adopted order - a mirror line for it must exist after the call with
    `line_no` = previous max + 1, and the core line is stamped `source_system = autocount`.

    Drives the real route exactly as `tests/test_ingest_documents.py` AC-A3-2 does: first
    push creates the header + one line; the order is then adopted (mirror header + one
    mirror line, the shape `adopt` leaves); the second push re-states the kept line by its
    own `source_ref` and adds one more.
    """
    from sqlalchemy import text

    from tests.test_ingest_documents import INGEST_SO, _so_line, _so_record, env as _env_fixture

    # The `env` fixture is a generator fixture; drive it by hand so this module keeps its
    # own `db`/`world` fixtures for the `_upsert_lines` half without a name clash.
    gen = _env_fixture.__wrapped__()
    env = next(gen)
    try:
        keep = _so_line(env, qty_ordered=10)
        record = _so_record(env, lines=[keep])
        first = env.post(INGEST_SO, [record])
        assert first.status_code == 200, first.text
        assert first.json()["records"][0]["outcome"] == "created", first.text

        header = env.header("sales_orders", record["source_ref"])
        kept_line_id = str(env.db.execute(
            text("SELECT id FROM sales_order_lines WHERE sales_order_id = :h AND source_ref = :r"),
            {"h": str(header["id"]), "r": keep["source_ref"]},
        ).scalar())

        # Adopted after the first push: mirror header + one mirror line, as `adopt` leaves it.
        project_so = ProjectSalesOrder(
            id=_u(), project_id=None, provisional_ref=unique_code(MARKER),
            status=SO_STATUS_ADOPTED, so_id=str(header["id"]), company_id=env.company_a,
        )
        env.db.add(project_so)
        env.db.flush()
        env.db.add(ProjectSalesOrderLine(
            id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=kept_line_id,
            line_no=1, qty=10, company_id=env.company_a,
        ))
        env.db.commit()

        # The late line arrives on the next weekly sync.
        added = _so_line(env, product_ref=env.product2_ref, qty_ordered=7)
        second = env.post(INGEST_SO, [dict(record, lines=[keep, added])])
        assert second.status_code == 200, second.text
        assert second.json()["records"][0]["outcome"] == "updated", second.text

        new_core = env.db.execute(
            text("SELECT id, source_system FROM sales_order_lines "
                 "WHERE sales_order_id = :h AND source_ref = :r"),
            {"h": str(header["id"]), "r": added["source_ref"]},
        ).mappings().first()
        assert new_core is not None, "the ESB push must have created the new core line"
        assert new_core["source_system"] == "autocount", dict(new_core)

        # Through the ORM, never a schema-qualified raw string: `blank_session` redirects
        # ORM constructs with `schema_translate_map` and unqualified raw SQL with
        # `search_path`, but an explicit `projects.` prefix escapes both and reads the
        # REAL schema, where this row can never be.
        env.db.expire_all()
        mirror = (
            env.db.query(ProjectSalesOrderLine)
            .filter(
                ProjectSalesOrderLine.project_sales_order_id == project_so.id,
                ProjectSalesOrderLine.core_sales_order_line_id == str(new_core["id"]),
            )
            .first()
        )
        assert mirror is not None, (
            "the core line the ESB push created on an adopted order must gain a mirror in "
            "the same transaction (document_ingest_service._sync_lines never calls "
            "mirror_missing_lines)"
        )
        assert mirror.line_no == 2, "line_no must be the previous max (1) + 1"
    finally:
        gen.close()


def test_outstanding_book_upload_new_line_on_adopted_order_mirrors_it(db):
    """AC-PR3c: the Excel book upload (`outstanding_import_service.apply` ->
    `_write_change`, `db.add(bind.line(**fields))`) creates a core line on an adopted
    order - a mirror line for it must exist after the call with `line_no` = previous
    max + 1.

    Seeded exactly as `tests/scm/test_outstanding_import_service.py` does (`make_codes` +
    `seed_catalogue`); book A lands one line, the order is adopted, book B re-states that
    line and adds `item_new` on the same order, the shape `week2` uses.
    """
    from datetime import date

    from sqlalchemy import text

    from app.services.scm import outstanding_import_service as svc
    from app.services.scm.outstanding_reader import SO
    from tests.scm._outstanding_workbooks import (
        PROJECT_LABEL,
        _row,
        make_codes,
        seed_catalogue,
        workbook,
    )

    codes = make_codes()
    seed_catalogue(db, codes)
    so_date = date(2026, 5, 4)
    kept_row = _row(PROJECT_LABEL, codes.project_so, so_date, "300-T012", codes.item_rl, 135,
                    date(2026, 7, 1), codes.loc_project)

    first = svc.apply(db, workbook([kept_row]), SO)
    assert first["ok"] and first["applied"]["added"] == 1, first

    so = db.query(SalesOrder).filter(SalesOrder.so_number == codes.project_so).one()
    kept_line = db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == so.id).one()

    project_so = _adopted_mirror(db, so)
    db.add(ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=kept_line.id,
        line_no=1, product_id=kept_line.product_id, qty=135,
    ))
    db.flush()

    new_row = _row(PROJECT_LABEL, codes.project_so, so_date, "300-T012", codes.item_new, 12,
                   date(2026, 9, 1), codes.loc_project, "new")
    second = svc.apply(db, workbook([kept_row, new_row]), SO)
    assert second["ok"] and second["applied"]["added"] == 1, second

    db.expire_all()
    new_core_id = db.execute(text(
        "SELECT sol.id FROM sales_order_lines sol JOIN products p ON p.id = sol.product_id "
        "WHERE sol.sales_order_id = :so AND p.product_code = :item"
    ), {"so": so.id, "item": codes.item_new}).scalar()
    assert new_core_id is not None, "the book upload must have created the new core line"

    mirror = (
        db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == project_so.id,
            ProjectSalesOrderLine.core_sales_order_line_id == str(new_core_id),
        )
        .first()
    )
    assert mirror is not None, (
        "the core line the book upload created on an adopted order must gain a mirror in "
        "the same transaction (outstanding_import_service._write_change never calls "
        "mirror_missing_lines)"
    )
    assert mirror.line_no == 2, "line_no must be the previous max (1) + 1"
