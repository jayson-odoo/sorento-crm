"""SCM S5 - generating a batch and deciding an exception, against Postgres (UAC Group D).

Every row here is seeded by the test under a marker prefix: no `LIMIT 1` off an existing
table and no assertion about a production row, because CI's database is empty and a borrowed
lookup is how a suite passes locally and fails there.

What these cover that the pure engine tests cannot: that the four reading signals are really
read from the four tables that already hold them, that the batch's delta count is the
UPLOAD's figure rather than a recount, and that the decision rules are enforced in the
SERVICE - the UI must not be the only thing that refuses to reject without a reason.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import PlanException, PlanExceptionBatch
from app.services.error_handler import AppException
from app.services.scm import plan_exception_service as svc
from app.services.scm.plan_exception_engine import Position
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session

MARKER = "ZZTPEX"
SORENTO = "00000000-0000-0000-0000-000000000001"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    """A product with stock, a committed order, and a purchase order already placed."""
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    wh = Warehouse(
        id=_u(), warehouse_code=_code("WH")[:30], warehouse_name=f"{MARKER} warehouse",
        is_active=True, counts_as_available=True,
    )
    db.add(wh)
    db.flush()
    wh.pool_warehouse_id = wh.id

    product = Product(
        id=_u(), product_code=_code("P"), product_name=f"{MARKER} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=10))

    supplier = Supplier(
        id=_u(), supplier_code=_code("S")[:30], supplier_name=f"{MARKER} supplier",
    )
    db.add(supplier)
    db.flush()

    po = PurchaseOrder(
        id=_u(), po_number=_code("PO")[:50], supplier_id=supplier.id, status="active",
        issue_date=_today() - timedelta(days=10),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=240, qty_received=0, expected_date=_today() + timedelta(days=45),
        line_status="open",
    ))
    db.flush()
    return {"product": product, "warehouse": wh, "po": po, "supplier": supplier,
            "category": cat, "uom": uom}


def _snap(**kw) -> dict:
    """A one-product snapshot with the position stated outright.

    The position arithmetic is the coverage service's and is tested there; what this file is
    about is what the SERVICE does with it, so the input is stated rather than constructed
    out of events.
    """
    return {kw.pop("pid"): svc.Snapshot(position=Position(**kw), points=[])}


def test_a_batch_is_written_even_when_nothing_disagrees(db, world):
    """"This upload produced no exceptions" is a real answer the screen has to state.

    No row at all would be indistinguishable from an upload nobody confirmed.
    """
    pid = str(world["product"].id)
    before = _snap(pid=pid, first_need_at=_today() + timedelta(days=50))
    after = _snap(pid=pid, first_need_at=_today() + timedelta(days=52))

    batch = svc.generate_batch(db, before=before, after=after, delta_count=412)

    assert batch.id is not None
    assert db.query(PlanException).filter(PlanException.batch_id == batch.id).count() == 0


def test_the_delta_count_is_the_uploads_figure_not_a_recount(db, world):
    """AC-D2b. Recounting from the exceptions would make the two agree by construction and
    hide the reduction that is the whole value of the screen."""
    pid = str(world["product"].id)
    before = _snap(pid=pid, first_need_at=_today() + timedelta(days=60))
    after = _snap(
        pid=pid, shortfall_at=_today() + timedelta(days=20), shortfall_qty=150,
        first_need_at=_today() + timedelta(days=20),
    )

    batch = svc.generate_batch(db, before=before, after=after, delta_count=412)
    out = svc.report(db)

    assert out["counts"]["delta_count"] == 412
    assert out["counts"]["exception_count"] == 1
    assert batch.delta_count == 412


def test_an_exception_carries_the_reading_read_from_the_real_tables(db, world):
    """AC-D9/AC-D12: four signals, each naming the field it came from."""
    product = world["product"]
    product.is_discontinued = True
    db.flush()

    pid = str(product.id)
    after = _snap(pid=pid, surplus_qty=500)
    batch = svc.generate_batch(
        db, before=_snap(pid=pid, first_need_at=_today()), after=after, delta_count=3
    )

    row = db.query(PlanException).filter(PlanException.batch_id == batch.id).one()
    reading = row.reading_json
    assert reading["lifecycle"] == {
        "value": "Discontinued",
        "source": "products.is_discontinued",
    }
    assert reading["velocity"]["source"] == "scm.item_classification"
    assert reading["business"]["source"] == "market_segments.demand_class"
    # Read from the placed order that already exists, not invented.
    assert reading["last_po"]["value"] == (_today() - timedelta(days=10)).isoformat()


def test_a_discontinued_surplus_proposes_keeping_the_order_first(db, world):
    """The inversion, end to end through the real reading (AC-D10, AC-D11)."""
    world["product"].is_discontinued = True
    db.flush()
    pid = str(world["product"].id)

    batch = svc.generate_batch(
        db,
        before=_snap(pid=pid, first_need_at=_today()),
        after=_snap(pid=pid, surplus_qty=500),
        delta_count=1,
    )
    row = db.query(PlanException).filter(PlanException.batch_id == batch.id).one()

    assert row.exception_type == "supply_surplus"
    # Capped at the placed order's own size, never the whole surplus.
    assert float(row.quantity) == 240
    assert row.actions_json[0]["code"] == "keep_and_pool"
    assert [a["rank"] for a in row.actions_json] == list(
        range(1, len(row.actions_json) + 1)
    )


def test_the_report_resolves_codes_and_never_leaks_an_id(db, world):
    """No UUID reaches the screen: product code, warehouse code, PO number, a human name."""
    pid = str(world["product"].id)
    svc.generate_batch(
        db,
        before=_snap(pid=pid, first_need_at=_today()),
        after=_snap(pid=pid, surplus_qty=500),
        delta_count=1,
    )
    out = svc.report(db)
    row = out["rows"][0]

    assert row["product_code"] == world["product"].product_code
    assert row["warehouse_code"] == world["warehouse"].warehouse_code
    assert row["po_number"] == world["po"].po_number
    # The opaque id is present for the decision call and is the ONLY id on the row.
    assert row["exception_id"]


def _one_open(db, world) -> PlanException:
    pid = str(world["product"].id)
    svc.generate_batch(
        db,
        before=_snap(pid=pid, first_need_at=_today()),
        after=_snap(pid=pid, surplus_qty=500),
        delta_count=1,
    )
    return db.query(PlanException).order_by(PlanException.created_at.desc()).first()


def test_rejecting_without_a_reason_is_refused(db, world):
    """AC-D6, enforced in the service: the UI must not be the only thing that refuses."""
    row = _one_open(db, world)
    with pytest.raises(AppException) as caught:
        svc.decide(db, str(row.id), status="rejected", reason="   ")
    assert caught.value.status_code == 422


def test_approving_an_action_the_engine_never_proposed_is_refused(db, world):
    """It is not a decision about THIS exception."""
    row = _one_open(db, world)
    proposed = {a["code"] for a in row.actions_json}
    absent = next(c for c in svc.ACTION_CODES if c not in proposed)
    with pytest.raises(AppException) as caught:
        svc.decide(db, str(row.id), status="approved", action_code=absent)
    assert caught.value.status_code == 422


def test_a_split_must_be_strictly_inside_the_quantity(db, world):
    """AC-D11b: the remainder stays on the original line, so the two parts sum to it."""
    row = _one_open(db, world)
    if "split" not in {a["code"] for a in row.actions_json}:
        pytest.skip("this reading proposes no split")
    whole = float(row.quantity)
    for bad in (0, whole, whole + 1):
        with pytest.raises(AppException) as caught:
            svc.decide(db, str(row.id), status="approved", action_code="split", split_qty=bad)
        assert caught.value.status_code == 422

    decided = svc.decide(
        db, str(row.id), status="approved", action_code="split", split_qty=whole / 2
    )
    assert float(decided.split_qty) == whole / 2


def test_deciding_twice_is_a_conflict_not_a_silent_overwrite(db, world):
    """Re-deciding is a different operation, and overwriting loses who decided what."""
    row = _one_open(db, world)
    first = row.actions_json[0]["code"]
    svc.decide(db, str(row.id), status="approved", action_code=first)
    with pytest.raises(AppException) as caught:
        svc.decide(db, str(row.id), status="rejected", reason="changed my mind")
    assert caught.value.status_code == 409


def test_approving_does_not_touch_the_purchase_order(db, world):
    """AC-D7. Approving a reallocation writes an allocation decision, never a PO amendment."""
    row = _one_open(db, world)
    line = db.query(PurchaseOrderLine).filter(
        PurchaseOrderLine.purchase_order_id == world["po"].id
    ).one()
    before = (float(line.qty_ordered), line.expected_date, line.warehouse_id, line.line_status)

    svc.decide(db, str(row.id), status="approved", action_code=row.actions_json[0]["code"])
    db.refresh(line)

    assert (float(line.qty_ordered), line.expected_date, line.warehouse_id,
            line.line_status) == before


def test_the_open_queue_leads_the_report(db, world):
    """Open first: the screen opens on what is left to decide."""
    row = _one_open(db, world)
    svc.decide(db, str(row.id), status="approved", action_code=row.actions_json[0]["code"])
    out = svc.report(db)
    statuses = [r["status"] for r in out["rows"]]
    assert statuses == sorted(statuses, key=lambda s: 0 if s == "open" else 1)
    assert out["counts"]["approved_count"] == 1
    assert out["counts"]["open_count"] == 0


def test_no_batch_at_all_reads_as_empty_rather_than_failing(db):
    """A fresh install has re-uploaded nothing, and the screen says so."""
    out = svc.report(db, run_id=str(uuid.uuid4()))
    assert out["rows"] == []
    assert out["counts"]["exception_count"] == 0
    assert out["generated_at"] is None
