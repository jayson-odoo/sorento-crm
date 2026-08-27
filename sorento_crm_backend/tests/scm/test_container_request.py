"""S13 - the container request, the demand-first stage in front of the Loading Plan's CBM fit.

`PLAN-scm-loading-plan-demand-first.md` section 6 is this file's contract. `build` is a pure
read over the supplier's current stock list crossed with the outstanding sales-order book,
ranked by the ACTIVE Fulfilment Priority policy - the same call the fulfilment board makes
(AC-H5), so this suite seeds its own `scm.priority_policy` row rather than assuming one is
active, exactly like `test_priority_demand_rows.py`'s policy tests. `send` is a thin wrapper
over `supplier_notice_service.request_and_notify`, the S8 machinery under a new
`notice_type`, so its render/storage side effects are stubbed the same way
`test_supplier_notice.py` stubs them - this suite is about the request, not WeasyPrint.

Every test seeds its own chain under a marker-prefixed tag (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.job import ImportJob, JobStatus
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.scm import PriorityPolicy
from app.models.supplier_notice import SupplierNoticeLine
from app.services.scm import supplier_notice_service
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_container_request_universe import _project_need as project_need
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZCR"

BUILD_URL = "/api/v1/scm/container-requests/build"
SEND_URL = "/api/v1/scm/container-requests"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    """This suite is about the notice record, not WeasyPrint - same stub as S8's own suite."""
    monkeypatch.setattr(
        supplier_notice_service, "render_document", lambda html: b"%PDF-1.4 stub"
    )
    monkeypatch.setattr(
        supplier_notice_service, "_store", lambda data, filename: ("s3", f"exports/test/{filename}")
    )


def _policy(db, factors: dict, class_weights: dict | None = None) -> str:
    """A policy owned by this test. Deactivates the incumbent rather than deleting it -
    same pattern as `test_priority_demand_rows.py`'s `_policy`."""
    db.query(PriorityPolicy).filter(PriorityPolicy.is_active.is_(True)).update(
        {"is_active": False}, synchronize_session=False
    )
    row = PriorityPolicy(
        id=str(uuid.uuid4()),
        name=f"{MARKER}-policy-{uuid.uuid4().hex[:6]}",
        is_active=True,
        factors=factors,
        demand_class_weights=class_weights or {},
    )
    db.add(row)
    db.flush()
    return str(row.id)


#: Sentinel meaning "derive demand_origin from demand_class" - a caller who wants to
#: exercise the S13b order-level gate explicitly still overrides it with a real value
#: (including `None`).
_AUTO_ORIGIN = object()


def _so(
    db,
    w: World,
    key: str,
    qty: float,
    *,
    demand_class: str | None = "retail",
    demand_origin: str | None = _AUTO_ORIGIN,
    required_date: date | None = None,
    order_date: date | None = None,
    delivered: float = 0,
    status: str = "open",
    line_status: str = "open",
    purchasing_status: str = "not_reviewed",
) -> SalesOrder:
    # S13b / `is_plan_demand_order()`: a project-class order counts as purchasing demand
    # only when the Order Inquiry named it. Every helper call in this file means "the
    # sheet named this" unless a test explicitly says otherwise (the auth/404/422 tests
    # below don't care), so default the stamp rather than making every project-class
    # `_so(...)` call in the file repeat it.
    if demand_origin is _AUTO_ORIGIN:
        demand_origin = "scm_order_inquiry" if demand_class == "project" else None
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status=status,
        demand_class=demand_class,
        demand_origin=demand_origin,
        order_date=order_date or date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=w.product(key).id,
            qty_ordered=qty,
            qty_delivered=delivered,
            line_status=line_status,
            purchasing_status=purchasing_status,
            required_date=required_date,
        )
    )
    db.flush()
    return so


def _row(rows: list[dict], key: str, w: World) -> dict:
    code = w.product(key).product_code
    return next(r for r in rows if r["item_code"] == code)


def _warehouse(db, *, segment: str | None = None, is_active: bool = True) -> Warehouse:
    """A location. `segment='project'` makes it a GROUP location - stock there is spoken for.

    The pool predicate is `COALESCE(segment, 'dealer') <> 'project'`, the reorder engine's own
    (`reorder_run_service`), so a warehouse with no segment stated is a site pool: a location
    nobody has classified is not assumed to be a project bin.

    `is_active=False` is a CLOSED location - eleven of them exist in the live book, and they
    are not a site anyone can ask stock from.
    """
    wh = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=f"{MARKER}-WH-{uuid.uuid4().hex[:8]}",
        warehouse_name=f"{MARKER} warehouse",
        segment=segment,
        is_active=is_active,
    )
    db.add(wh)
    db.flush()
    return wh


def _packing_list(
    db,
    w: World,
    key: str,
    qty: float,
    *,
    received: float = 0,
    eta: date | None = None,
    arrived: date | None = None,
    number: str | None = _AUTO_ORIGIN,
) -> InboundShipment:
    """A packing list carrying this product. `number=None` is a draft nobody has numbered."""
    ship = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=(
            f"{MARKER}-PL-{uuid.uuid4().hex[:8]}" if number is _AUTO_ORIGIN else number
        ),
        supplier_id=w.supplier.id,
        shipment_date=date(2026, 1, 1),
        estimated_arrival_date=eta,
        actual_arrival_date=arrived,
        shipment_status="fully_received" if arrived else "in_transit",
    )
    db.add(ship)
    db.flush()
    db.add(
        InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=ship.id,
            product_id=w.product(key).id,
            supplier_id=w.supplier.id,
            quantity_shipped=qty,
            quantity_received=received,
        )
    )
    db.flush()
    return ship


def _on_hand(db, w: World, key: str, wh: Warehouse, qty: float) -> None:
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=w.product(key).id,
            warehouse_id=wh.id,
            quantity_on_hand=qty,
        )
    )
    db.flush()


def _outstanding_po(db, w: World, key: str, wh: Warehouse, qty: float) -> None:
    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=f"{MARKER}-OPO-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        issue_date=date(2026, 1, 1),
        status="active",
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=str(uuid.uuid4()),
            purchase_order_id=po.id,
            product_id=w.product(key).id,
            warehouse_id=wh.id,
            qty_ordered=qty,
            qty_received=0,
            line_status="open",
        )
    )
    db.flush()


def _incoming_spo(db, w: World, key: str, wh: Warehouse, qty: float) -> None:
    ship = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        shipment_date=date(2026, 1, 1),
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    db.add(
        SPOAllocation(
            id=str(uuid.uuid4()),
            spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
            inbound_shipment_id=ship.id,
            product_id=w.product(key).id,
            warehouse_id=wh.id,
            allocated_quantity=qty,
            quantity_received=0,
        )
    )
    db.flush()


def _import_job(db, company_id: str, job_type: str) -> None:
    db.add(
        ImportJob(
            id=str(uuid.uuid4()),
            job_id=f"{MARKER}-JOB-{uuid.uuid4().hex[:8]}",
            job_type=job_type,
            status=JobStatus.FINISHED.value,
            user_id=str(uuid.uuid4()),
            company_id=company_id,
        )
    )
    db.flush()


def _foreign_product(db) -> str:
    """A product stamped with a DIFFERENT company - never the caller's own (BL-2)."""
    coid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": coid, "n": f"{MARKER} product co", "c": f"{MARKER}-PCO-{coid[:8]}"},
    )
    cat_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, "
            "created_at, updated_at) VALUES (:i, :c, :n, now(), now())"
        ),
        {"i": cat_id, "c": f"{MARKER}-FPC-{cat_id[:8]}", "n": f"{MARKER} foreign category"},
    )
    uom_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, created_at, updated_at) "
            "VALUES (:i, :c, :n, now(), now())"
        ),
        {"i": uom_id, "c": f"{MARKER}-FU-{uom_id[:8]}"[:20], "n": "pcs"},
    )
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, "
            "base_uom_id, list_price, is_active, is_discontinued, company_id, "
            "created_at, updated_at) "
            "VALUES (:i, :c, :n, :cat, :uom, 0, true, false, :co, now(), now())"
        ),
        {"i": pid, "c": f"{MARKER}-FP-{pid[:8]}", "n": f"{MARKER} Foreign Product",
         "cat": cat_id, "uom": uom_id, "co": coid},
    )
    db.flush()
    return pid


def _plan(db, w: World, *, plan_horizon_date=None) -> str:
    """The plan row the build and the send are now scoped to (part 4, R2).

    A container request belongs to a PLAN since part 4: supplier and cut-off are read off the
    row, and the typed quantities live on it. Every route call in this suite therefore needs
    one, so it is minted here rather than repeated per test.
    """
    from app.models.scm import LoadingPlan

    plan = LoadingPlan(
        id=str(uuid.uuid4()),
        supplier_id=str(w.supplier.id),
        status="planning",
        plan_horizon_date=plan_horizon_date,
        document_kind="stock_list",
        line_edits={},
    )
    db.add(plan)
    db.flush()
    return str(plan.id)


def _foreign_plan(db) -> str:
    """A plan stamped with a DIFFERENT company - never the caller's own."""
    supplier_id = _foreign_supplier(db)
    company_id = db.execute(
        text("SELECT company_id::text FROM suppliers WHERE id = CAST(:s AS uuid)"),
        {"s": supplier_id},
    ).scalar()
    plan_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO scm.loading_plan (id, supplier_id, container_count, status, "
            "document_kind, line_edits, company_id, computed_at, created_at, updated_at) "
            "VALUES (CAST(:i AS uuid), CAST(:s AS uuid), 1, 'planning', 'none', "
            "'{}'::jsonb, CAST(:c AS uuid), now(), now(), now())"
        ),
        {"i": plan_id, "s": supplier_id, "c": company_id},
    )
    db.flush()
    return plan_id


def _foreign_supplier(db) -> str:
    """A supplier stamped with a DIFFERENT company - never the caller's own."""
    coid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": coid, "n": f"{MARKER} other co", "c": f"{MARKER}-CO-{coid[:8]}"},
    )
    sid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active, "
            "company_id, created_at, updated_at) "
            "VALUES (:i, :c, :n, true, :co, now(), now())"
        ),
        {"i": sid, "c": f"{MARKER}-FS-{sid[:8]}", "n": f"{MARKER} Foreign Supplier", "co": coid},
    )
    db.flush()
    return sid


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


def test_build_scope_is_the_whole_stock_list_ranked_rows_then_no_demand_rows(scm_app):
    # CHANGE 1: row scope is the WHOLE stock list - a product on the list with no open need
    # still gets a row (has_demand false, rank null), sorted after the ranked demand rows.
    # A product with need that this supplier neither lists nor is sourced from is still
    # absent: since F1 the universe is the stock list UNION `product_suppliers`, and product
    # C is in neither.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=5, cbm=0.5)  # on the list, has open need
    w.stock("B", packed=5, cbm=0.5)  # on the list, no open need
    _so(db, w, "A", 20)
    _so(db, w, "C", 30)  # need exists, but neither on the list nor sourced from them

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    body = r.json()
    codes = {row["item_code"] for row in body["rows"]}
    assert codes == {w.product("A").product_code, w.product("B").product_code}
    row_a = _row(body["rows"], "A", w)
    row_b = _row(body["rows"], "B", w)
    assert row_a["has_demand"] is True
    assert row_a["rank"] == 1
    assert row_b["has_demand"] is False
    assert row_b["rank"] is None
    # Ranked rows keep total order first; the no-demand row sorts after them.
    assert [r["item_code"] for r in body["rows"]] == [
        row_a["item_code"],
        row_b["item_code"],
    ]


def test_build_no_demand_rows_with_stock_but_zero_quantity_are_left_out_entirely(scm_app):
    # The module docstring's own carve-out: a stock-list row with neither packed nor
    # unfinished quantity AND no open need names nothing worth asking about, so it never
    # appears at all (not even as a no-demand row).
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=5, cbm=0.5)  # has open need
    w.stock("B", packed=0, unfinished=0, cbm=0.5)  # no need, no quantity either

    _so(db, w, "A", 20)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    codes = {row["item_code"] for row in r.json()["rows"]}
    assert codes == {w.product("A").product_code}


def test_build_suggested_qty_nets_stock_and_incoming_spo_but_not_outstanding_po(scm_app):
    # CHANGE 4 (captain decision), amended 20 Aug follow-up (CWCY604 worked example):
    # suggested_qty = max(open_so_need - on_hand - incoming_spo, 0). outstanding_po is
    # deliberately NOT subtracted - a PO placed but not yet allocated is not supply this
    # container can count on (often the very demand this request is asking the supplier to
    # pack), whereas an SPO allocation is real incoming stock on the water. outstanding_po
    # still travels on the row as context. The gross figure stays on the row as open_so_need
    # so the arithmetic is visible.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 120)
    wh = _warehouse(db)
    _on_hand(db, w, "A", wh, 20)
    _outstanding_po(db, w, "A", wh, 30)
    _incoming_spo(db, w, "A", wh, 15)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["open_so_need"] == 120
    assert row["on_hand"] == 20
    assert row["outstanding_po"] == 30  # shown, not deducted
    assert row["incoming_spo"] == 15
    assert row["suggested_qty"] == 85  # 120 - 20 - 15 (outstanding_po not subtracted)
    assert row["qty_packed"] == 10


def test_build_suggested_qty_floors_at_zero_when_stock_and_incoming_cover_the_need(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 50)
    wh = _warehouse(db)
    _on_hand(db, w, "A", wh, 200)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["open_so_need"] == 50
    assert row["on_hand"] == 200
    assert row["suggested_qty"] == 0


# --------------------------------------------------------------------------- #
# F2 - the pool predicate, and the packing list as a reference
# --------------------------------------------------------------------------- #


def test_build_on_hand_counts_site_pools_only_and_reports_group_stock_beside_it(scm_app):
    # AC-B1. Stock in a group location is real and it is spoken for - a project bin holds it
    # for an order that is already promised - so it can neither be asked against nor netted
    # off the ask. Same predicate the reorder engine nets by.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 500, demand_class="retail")
    pool = _warehouse(db)
    group = _warehouse(db, segment="project")
    _on_hand(db, w, "A", pool, 200)
    _on_hand(db, w, "A", group, 50)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["on_hand"] == 200
    assert row["on_hand_group"] == 50
    assert row["suggested_qty"] == 300  # 500 - 200, the group 50 is NOT netted


def test_build_counts_active_locations_only(scm_app):
    # AC-B3. The On hand lightbox lists ACTIVE locations only
    # (`location_stock_service.location_stock_for_product`, and `_pool_warehouses` for the
    # zero rows), so a cell counting closed ones could not equal the total the reader lands
    # on. Worse than a cosmetic gap: 17,356 units sit in closed pool locations on the live
    # book (SPARE/P, REWORK, STAGING, PARTS, SHOWROOM...), and every one of them was
    # cancelling part of an ask for stock nobody can ship.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 500, demand_class="retail")
    pool = _warehouse(db)
    closed = _warehouse(db, is_active=False)
    _on_hand(db, w, "A", pool, 200)
    _on_hand(db, w, "A", closed, 60)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["on_hand"] == 200
    # Not muted into the group figure either: a closed location is neither a pool nor a bin.
    assert row["on_hand_group"] == 0
    assert closed.warehouse_code not in {s["warehouse_code"] for s in row["sites"]}
    assert closed.warehouse_code not in row["group_locations"]["warehouse_codes"]
    assert row["suggested_qty"] == 300  # 500 - 200, the closed 60 is NOT netted


def test_build_spo_counts_site_pools_only(scm_app):
    # AC-B2, review item 1: an allocation bound for a group location lands in a bin this
    # container cannot draw on, so it is out of the cell and muted in the breakdown.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 500, demand_class="retail")
    pool = _warehouse(db)
    group = _warehouse(db, segment="project")
    _incoming_spo(db, w, "A", pool, 30)
    _incoming_spo(db, w, "A", group, 70)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["incoming_spo"] == 30
    assert row["incoming_spo_group"] == 70
    assert row["suggested_qty"] == 470  # 500 - 30


def test_build_lists_every_site_pool_including_the_empty_ones(scm_app):
    # AC-B3: a site with nothing in it is a fact the reader needs ("we looked, there is
    # none"), not an absence to be inferred from a missing row.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100, demand_class="retail")
    held = _warehouse(db)
    empty = _warehouse(db)
    group = _warehouse(db, segment="project")
    _on_hand(db, w, "A", held, 40)
    _on_hand(db, w, "A", group, 15)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    sites = {s["warehouse_code"]: s for s in row["sites"]}
    assert sites[held.warehouse_code]["on_hand"] == 40
    assert empty.warehouse_code in sites
    assert sites[empty.warehouse_code]["on_hand"] == 0
    # The group location is never a site row - it has its own muted line.
    assert group.warehouse_code not in sites
    assert row["group_locations"]["on_hand"] == 15
    assert row["group_locations"]["count"] == 1
    assert group.warehouse_code in row["group_locations"]["warehouse_codes"]


def test_build_incoming_packing_list_is_shown_and_never_subtracted(scm_app):
    # AC-B4 / Q1: a packing list names no destination, so it cannot be netted against a pool
    # the way an SPO can. It travels as a reference, with the shipment and ETA behind it.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100, demand_class="retail")
    ship = _packing_list(db, w, "A", 60, received=10, eta=date(2026, 7, 27))

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["incoming_pl"] == 50  # 60 shipped - 10 already received
    assert row["suggested_qty"] == 100  # untouched
    assert row["incoming_pl_shipments"] == [
        {
            "shipment_id": str(ship.id),
            "shipment_number": ship.shipment_number,
            "estimated_arrival_date": "2026-07-27",
            "qty": 50,
        }
    ]


def test_build_incoming_packing_list_ignores_shipments_that_have_arrived(scm_app):
    # Arrived stock is already in `on_hand`; counting it here would show it twice.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100, demand_class="retail")
    _packing_list(db, w, "A", 60, arrived=date(2026, 7, 1))

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["incoming_pl"] == 0
    assert row["incoming_pl_shipments"] == []


def test_build_a_draft_packing_list_reads_as_a_draft_not_as_a_missing_number(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100, demand_class="retail")
    _packing_list(db, w, "A", 25, number=None)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["incoming_pl"] == 25
    assert row["incoming_pl_shipments"][0]["shipment_number"] is None
    assert row["incoming_pl_shipments"][0]["estimated_arrival_date"] is None


def test_build_outstanding_po_lines_foot_to_the_outstanding_po_figure(scm_app):
    # AC-H2: still shown, still not deducted - now with the POs named, so the reader can see
    # which order the figure is.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100, demand_class="retail")
    wh = _warehouse(db)
    _outstanding_po(db, w, "A", wh, 30)
    _outstanding_po(db, w, "A", wh, 12)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["outstanding_po"] == 42
    assert sum(line["qty"] for line in row["outstanding_po_lines"]) == 42
    assert all(line["po_number"] for line in row["outstanding_po_lines"])
    assert row["suggested_qty"] == 100  # never deducted


def test_build_a_no_demand_row_carries_the_same_breakdown_fields(scm_app):
    # The two row builders are one shape or the breakdown dialog breaks on half the grid.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("B", packed=5, cbm=0.5)  # stock, no open need
    pool = _warehouse(db)
    _on_hand(db, w, "B", pool, 7)
    _packing_list(db, w, "B", 3)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "B", w)
    assert row["has_demand"] is False
    assert row["on_hand"] == 7
    assert row["incoming_pl"] == 3
    assert row["on_hand_group"] == 0
    assert any(s["warehouse_code"] == pool.warehouse_code for s in row["sites"])


def test_build_returns_a_sources_block_naming_the_latest_ingest_per_family(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    company_id = next(iter(scope))
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    _so(db, w, "A", 10)
    _import_job(db, company_id, "outstanding_so_import")

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    body = r.json()
    sources = body["sources"]
    assert set(sources) == {
        "so_book_as_of",
        "po_book_as_of",
        "spo_as_of",
        "stock_list_as_of",
        "proforma_as_of",
        "proforma_pi_number",
    }
    assert sources["so_book_as_of"] is not None
    assert sources["stock_list_as_of"] == body["stock_list_as_of"]
    # Nothing seeded for these two families - honest absence, not a stale guess.
    assert sources["po_book_as_of"] is None
    assert sources["spo_as_of"] is None
    # A stock list exists, so the proforma stand-in is not consulted and does not name
    # itself (AC-A3).
    assert sources["proforma_as_of"] is None


def test_build_reads_the_spo_freshness_off_the_allocation_book(scm_app):
    """`spo_as_of` used to be read off `purchase_orders`, and migration 420 moved every
    SPO document out of that table into `spo_allocations` - so the strip has said nothing
    about the shipping-order book since, however recently one was uploaded. The freshness
    is read off the rows the SPO writers actually write."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    db.add(
        SPOAllocation(
            id=str(uuid.uuid4()),
            spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
            product_id=w.product("A").id,
            allocated_quantity=5,
            quantity_received=0,
            source_system="scm_upload",
        )
    )
    db.flush()

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    assert r.json()["sources"]["spo_as_of"] is not None


def test_build_include_lines_returns_flat_lines_summing_to_the_retail_need(scm_app):
    # CHANGE 2 + the invariant `build`'s docstring states, as P3 leaves it: sum(lines.qty per
    # product) == retail_qty. The flat lines are the sales-order BOOK, and the book speaks for
    # retail alone - project need lives on `projects.order_inquiry_rows` and has no book line
    # to list (`test_container_request_universe.py` covers that half).
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    so1 = _so(db, w, "A", 20)
    so2 = _so(db, w, "A", 15)

    r = TestClient(app).post(
        BUILD_URL,
        params={"include_lines": "true"},
        json={"plan_id": _plan(db, w)},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    row = _row(body["rows"], "A", w)
    lines = [ln for ln in body["lines"] if ln["product_id"] == row["product_id"]]
    assert len(lines) == 2
    assert sum(ln["qty"] for ln in lines) == row["retail_qty"] == row["open_so_need"] == 35
    assert {ln["so_number"] for ln in lines} == {so1.so_number, so2.so_number}


def test_build_without_include_lines_omits_the_lines_key(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    _so(db, w, "A", 10)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    assert "lines" not in r.json()


def test_build_for_another_companys_plan_is_a_404(scm_app):
    # The plan row is company-scoped, so a plan belonging to somebody else does not resolve
    # and its supplier's figures never reach this caller.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    foreign_plan = _foreign_plan(db)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": foreign_plan})

    assert r.status_code == 404, r.text


def test_build_with_a_malformed_plan_id_is_a_404_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": "not-a-uuid"})

    assert r.status_code == 404, r.text


def test_build_splits_project_and_retail_qty(scm_app):
    # The two channels, both off the sales-order book and told apart by `demand_class`
    # (R15, captain 27 Aug), the project half net of what CS already placed. `so_count`
    # counts the orders behind BOTH, which is what the "Open SOs" drill lists.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    project_need(db, w, "A", 80)
    _so(db, w, "A", 40, demand_class="retail")

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["suggested_qty"] == 120
    assert row["project_qty"] == 80
    assert row["retail_qty"] == 40
    assert row["unclassified_qty"] == 0
    assert row["so_count"] == 2


def test_build_a_project_row_outranks_a_retail_row_at_equal_dates(scm_app):
    # AC-H5, the ACTIVE policy - mirrors the seeded weighting (demand_class dominant).
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _policy(
        db,
        {"demand_class": 3.0, "need_by_date": 0.0, "document_age": 0.0, "po_document_sequence": 0.0},
        {"project": 1.0, "retail": 0.4},
    )
    w.stock("A", packed=1, cbm=0.5)
    w.stock("B", packed=1, cbm=0.5)
    same_date = date(2026, 9, 1)
    _so(db, w, "A", 10, demand_class="retail", required_date=same_date, order_date=same_date)
    project_need(db, w, "B", 10, required=same_date)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    project_row = _row(rows, "B", w)
    retail_row = _row(rows, "A", w)
    assert project_row["rank"] < retail_row["rank"]
    assert project_row["rank_score"] > retail_row["rank_score"]


def test_build_a_sooner_required_date_outranks_within_the_same_class(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _policy(
        db,
        {"need_by_date": 1.0, "demand_class": 0.0, "document_age": 0.0, "po_document_sequence": 0.0},
        {"project": 1.0},
    )
    w.stock("A", packed=1, cbm=0.5)
    w.stock("B", packed=1, cbm=0.5)
    # Both project, both dated off `sales_order_lines.required_date` - the same column the
    # retail half ranks on since R15, so the two classes cannot rank on different clocks.
    project_need(db, w, "A", 10, required=date(2026, 9, 4))
    project_need(db, w, "B", 10, required=date(2027, 5, 15))

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    soon = _row(rows, "A", w)
    late = _row(rows, "B", w)
    assert soon["rank"] < late["rank"]
    assert soon["rank_score"] > late["rank_score"]


def test_build_with_no_stock_list_reads_as_an_empty_result_not_an_error(scm_app):
    # The route docstring's own decision: empty-with-reason, not a 409. `stock_list_as_of`
    # null is the FE's cue for the "upload a stock list first" empty state.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _so(db, w, "A", 10, demand_class="project")  # demand exists, but no stock list at all

    r = TestClient(app).post(BUILD_URL, json={"plan_id": _plan(db, w)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == []
    assert body["stock_list_as_of"] is None


def test_build_requires_the_read_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(BUILD_URL, json={"plan_id": str(uuid.uuid4())})

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# send
# --------------------------------------------------------------------------- #


def test_send_creates_a_notice_with_a_copied_lines_snapshot_and_a_document(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.supplier.email = f"{MARKER}@example.test"
    db.flush()
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [{"product_id": str(product.id), "qty": 42}],
        },
    )

    assert r.status_code == 201, r.text
    body = r.json()
    # ONE row, on the channel the send chose - email by default (R9, AC-C6).
    assert [n["channel"] for n in body["notices"]] == ["email"]
    email = body["notices"][0]
    assert email["status"] == "sent"
    assert email["recipients"] == [f"{MARKER}@example.test"]
    assert email["has_document"] is True
    assert email["document_filename"].endswith(".pdf")

    lines = (
        db.query(SupplierNoticeLine)
        .filter(SupplierNoticeLine.notice_id == email["id"])
        .all()
    )
    assert len(lines) == 1
    assert lines[0].item_code == product.product_code
    assert lines[0].product_name == product.product_name
    assert float(lines[0].qty) == 42
    assert lines[0].kind == "pack"


def test_send_with_no_address_anywhere_is_refused(scm_app):
    # AC-C2, superseding the old "skipped, not a failure" behaviour: since R9 the sender
    # names the recipients in the send dialog, so a send with nobody on it is a mistake, not
    # an outcome. The document is still obtainable without sending anything
    # (`/container-requests/document`), which is what the old skipped row existed for.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    # No email set on the supplier - the default.
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [{"product_id": str(product.id), "qty": 5}],
        },
    )

    assert r.status_code == 422, r.text
    assert r.json()["code"] == "no_recipients"


def test_send_goes_to_every_address_the_sender_named(scm_app):
    # AC-C2. The supplier's own address is a default, not a limit.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.supplier.email = f"{MARKER}-default@example.test"
    db.flush()
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [{"product_id": str(product.id), "qty": 5}],
            "channel": "email",
            "recipients": [f"{MARKER}-one@example.com", f"{MARKER}-two@example.com"],
            "note": "Please confirm by Friday.",
        },
    )

    assert r.status_code == 201, r.text
    notice = r.json()["notices"][0]
    assert notice["recipients"] == [
        f"{MARKER}-one@example.com",
        f"{MARKER}-two@example.com",
    ]
    assert notice["open_count"] == 0 and notice["opened_at"] is None


def test_send_refuses_an_address_that_is_not_one(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [{"product_id": str(product.id), "qty": 5}],
            "recipients": ["not-an-address"],
        },
    )

    assert r.status_code == 422, r.text


def test_send_for_a_plan_that_does_not_exist_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": str(uuid.uuid4()),
            "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
    )

    assert r.status_code == 404, r.text


def test_send_for_another_companys_plan_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    foreign_plan = _foreign_plan(db)

    r = TestClient(app).post(
        SEND_URL,
        json={"plan_id": foreign_plan, "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}]},
    )

    assert r.status_code == 404, r.text


def test_send_with_a_malformed_plan_id_is_a_404_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        SEND_URL,
        json={"plan_id": "not-a-uuid", "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}]},
    )

    assert r.status_code == 404, r.text


def test_send_with_unknown_or_malformed_product_ids_is_a_422_naming_them(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    unknown_id = str(uuid.uuid4())

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [
                {"product_id": "not-a-uuid", "qty": 1},
                {"product_id": unknown_id, "qty": 1},
            ],
        },
    )

    assert r.status_code == 422, r.text
    body = r.json()
    assert "not-a-uuid" in body["message"]
    assert unknown_id in body["message"]


def test_send_with_a_foreign_product_id_is_a_422_naming_it(scm_app):
    # BL-2 (SECURITY): a well-formed id naming ANOTHER company's product must not resolve -
    # the catalogue lookup is company-scoped, so a foreign id lands in the same "unknown"
    # set as a made-up one, and the company's product_code/product_name never reach
    # `supplier_notice_lines` or the emailed PDF.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    foreign_pid = _foreign_product(db)

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [{"product_id": foreign_pid, "qty": 1}],
        },
    )

    assert r.status_code == 422, r.text
    body = r.json()
    assert foreign_pid in body["message"]

    lines = (
        db.query(SupplierNoticeLine)
        .filter(SupplierNoticeLine.product_id == foreign_pid)
        .all()
    )
    assert lines == [], "the foreign product must never be copied into a notice line"


def test_send_with_no_lines_is_a_422(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(
        SEND_URL, json={"plan_id": _plan(db, w), "lines": []}
    )

    assert r.status_code == 422, r.text


def test_send_with_a_non_positive_qty_is_a_422(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": _plan(db, w),
            "lines": [{"product_id": str(product.id), "qty": 0}],
        },
    )

    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# N-3: GET /supplier-notices?supplier_id= with a malformed id
# --------------------------------------------------------------------------- #
#
# No dedicated supplier-notice ROUTE test file is in this pass's edit scope
# (`tests/scm/test_supplier_notice.py` exists but is owned elsewhere), so this is a
# service-level test of `list_for_supplier` directly - cheap, and it exercises the exact
# function `GET /api/v1/scm/supplier-notices` calls.


def test_list_for_supplier_with_a_malformed_id_is_an_empty_list_not_a_500(scm_app):
    _, db, _, _ = scm_app

    out = supplier_notice_service.list_for_supplier(db, "not-a-uuid")

    assert out == []


def test_send_requires_the_write_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(
        SEND_URL,
        json={
            "plan_id": str(uuid.uuid4()),
            "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
    )

    assert r.status_code == 403, r.text
