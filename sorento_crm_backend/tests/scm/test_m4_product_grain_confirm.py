"""Product-grain reorder runs also drive an internal draft PO (captain, 21 Aug).

Reverses the old doctrine recorded in `decision_service.py`'s original docstring: a
product-grain run used to hand Joey a worklist to key into AutoCount and NOTHING
ELSE (`summary_order_service.po_worklist` stays unchanged and untested here - it
already has its own coverage). This slice ADDS a second path off the SAME "decide
buy on the row" decision (`summary_order_service.record_decision`, writing
`OrderSummaryRow.chosen_qty` / `chosen_supplier_id`): **Confirm decisions**
(`decision_service.confirm_decisions`, dispatching to `_confirm_product_grain`)
now materialises it into a consolidated draft PO exactly the way a location-grain
Accept/Adjust does, and confirming THAT PO (`purchase_order_service.bulk_confirm`)
in turn triggers the order-inquiry auto-place cascade
(`project_order_inquiry_service.auto_place_for_products`).

Two fixture idioms, matching what each half needs:

* (a) the product-grain confirm/reconcile shape needs only `scm.*` tables plus
  `products` / `warehouses` / `suppliers` - the plain `pg_session()` ORM-model chain
  `tests/scm/test_plan_grain_policy.py` already established (marker `ZZTM4PG`).
* (b) the bulk-confirm -> auto-place cascade needs the `projects.*` order-inquiry
  tables too, so it reuses `tests/test_order_inquiry_place_on_po.py`'s
  `blank_session` fixture chain directly rather than re-deriving it (marker
  `zzt-oi-place`, inherited from that module's own helpers).

Every row is marker-prefixed and seeded fresh per test; nothing is borrowed with a
bare `LIMIT 1` off the shared prod-copy database (CI's is empty), per
PRINCIPLES.md / CLAUDE.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import INQUIRY_PLACED
from app.models.scm import OrderSummaryRow, ReorderRecommendation, ReorderRun
from app.services import project_seed_service
from app.services.scm import decision_service as dsvc
from app.services.scm import summary_order_service as svc
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import blank_session, pg_session
from tests.scm.conftest import requires_pg
from tests.test_order_inquiry_place_on_po import (
    _po_line as _oi_po_line,
    _row as _oi_row,
    _seed_world as _oi_seed_world,
    _sorento as _oi_sorento,
    _user as _oi_user,
)

pytestmark = requires_pg

MARKER = "ZZTM4PG"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str = "") -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


# =========================================================================== #
# (a) fixture chain - product, warehouse, one buy rec, one frozen order-summary
# row, stamped at PRODUCT grain (mirrors test_plan_grain_policy.py).
# =========================================================================== #


def _category_and_uom(db):
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    return cat, uom


def _product(db, cat, uom):
    p = Product(
        id=_u(), product_code=_code("SKU"), product_name="product grain confirm product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0, is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _warehouse(db):
    wh = Warehouse(id=_u(), warehouse_code=_code("WH")[:30], warehouse_name="wh",
                    is_active=True, counts_as_available=True)
    db.add(wh)
    db.flush()
    return wh


def _supplier(db, name="supplier"):
    s = Supplier(id=_u(), supplier_code=_code("S")[:30], supplier_name=name)
    db.add(s)
    db.flush()
    return s


def _run(db):
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse", decision_grain="product",
        front_planning_contract_version=1, started_at=datetime.utcnow(),
        source_system="scm", source_ref=_code("RUN"),
    )
    db.add(run)
    db.flush()
    return run


def _recommendation(db, run, product, wh, qty=50, supplier=None):
    rec = ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=qty, status="proposed",
        supplier_id=(supplier.id if supplier else None),
    )
    db.add(rec)
    db.flush()
    return rec


def _lines_for_product(db, product_id):
    """Every product-grain draft line for a product (B2, code review 21 Aug: a
    product-grain draft is split across its REAL member warehouses, so a product can
    hold more than one line - never a single NULL-warehouse one). Queried by the
    product itself, not by a single ``source_ref``, since the grid path keys each
    line by its own member recommendation id and the summary-fallback path keys each
    by ``"{row_id}:{warehouse_id}"`` - two different key shapes that both still name
    THIS product."""
    return db.execute(text(
        "SELECT purchase_order_id::text AS po_id, qty_ordered, warehouse_id::text AS warehouse_id "
        "FROM purchase_order_lines "
        "WHERE product_id = :p AND source_system = 'scm_order_summary_row' "
        "ORDER BY warehouse_id"
    ), {"p": product_id}).mappings().all()


def _line_for_product(db, product_id):
    """The single line, for a test scenario with exactly one real member warehouse."""
    lines = _lines_for_product(db, product_id)
    assert len(lines) <= 1, f"expected at most one line, got {len(lines)}"
    return lines[0] if lines else None


# =========================================================================== #
# (a) product-grain confirm: OrderSummaryRow.chosen_qty -> draft PO
# =========================================================================== #


def test_product_grain_confirm_drafts_a_line_with_the_right_supplier_and_qty(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    supplier = _supplier(db, f"{MARKER} Supplier A")
    run = _run(db)
    _recommendation(db, run, product, wh, qty=50)
    svc.write_rows(db, run.id)

    row = (
        db.query(OrderSummaryRow)
        .filter(OrderSummaryRow.run_id == run.id, OrderSummaryRow.product_id == product.id)
        .one()
    )

    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=40, supplier_code=supplier.supplier_code, actor="tester",
    )

    out = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out["confirmed_count"] == 1
    assert out["po_count"] == 1

    line = _line_for_product(db, product.id)
    assert line is not None, "product-grain confirm must draft a PO line"
    assert float(line["qty_ordered"]) == 40
    # the ONE real member warehouse this product's split names (B2) - never NULL,
    # or the line is invisible to the next run's on-order figures.
    assert line["warehouse_id"] == wh.id

    po = db.execute(text(
        "SELECT status, supplier_id::text AS supplier_id FROM purchase_orders WHERE id = :id"
    ), {"id": line["po_id"]}).mappings().first()
    assert po["status"] == "draft_recommendation"
    assert po["supplier_id"] == supplier.id


def test_product_grain_reconfirm_after_a_requalify_reconciles_the_same_line(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    supplier_a = _supplier(db, f"{MARKER} Supplier A")
    supplier_b = _supplier(db, f"{MARKER} Supplier B")
    run = _run(db)
    _recommendation(db, run, product, wh, qty=50)
    svc.write_rows(db, run.id)
    row = (
        db.query(OrderSummaryRow)
        .filter(OrderSummaryRow.run_id == run.id, OrderSummaryRow.product_id == product.id)
        .one()
    )

    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=40, supplier_code=supplier_a.supplier_code, actor="tester",
    )
    dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    first_po_id = _line_for_product(db, product.id)["po_id"]

    # a re-decision changing BOTH qty and supplier, then re-confirm - the SAME row
    # id is the line's key, so this reconciles a line, never duplicates one.
    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=70, supplier_code=supplier_b.supplier_code, actor="tester",
    )
    out2 = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out2["confirmed_count"] == 1
    assert out2["po_count"] == 1

    line_count = db.execute(text(
        "SELECT count(*) FROM purchase_order_lines "
        "WHERE product_id = :p AND source_system = 'scm_order_summary_row'"
    ), {"p": product.id}).scalar()
    assert line_count == 1, "a re-confirm must reconcile the existing line, not add one"

    line2 = _line_for_product(db, product.id)
    assert float(line2["qty_ordered"]) == 70
    assert line2["po_id"] != first_po_id, "a supplier switch drafts under the new supplier"

    # the old (supplier A) draft emptied out and was deleted with its last line
    old_po_gone = db.execute(text(
        "SELECT count(*) FROM purchase_orders WHERE id = :id"
    ), {"id": first_po_id}).scalar()
    assert old_po_gone == 0


def test_product_grain_chosen_qty_zero_pulls_the_line_and_is_not_confirmed(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    supplier = _supplier(db, f"{MARKER} Supplier A")
    run = _run(db)
    _recommendation(db, run, product, wh, qty=50)
    svc.write_rows(db, run.id)
    row = (
        db.query(OrderSummaryRow)
        .filter(OrderSummaryRow.run_id == run.id, OrderSummaryRow.product_id == product.id)
        .one()
    )

    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=40, supplier_code=supplier.supplier_code, actor="tester",
    )
    dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert _line_for_product(db, product.id) is not None

    # "use the pool, do not buy" - zero is a valid decision (record_decision's own
    # doctrine), and confirming it pulls the stale draft line back out.
    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=0, supplier_code=supplier.supplier_code, actor="tester",
    )
    out = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out["confirmed_count"] == 0
    assert out["po_count"] == 0
    assert _line_for_product(db, product.id) is None


def test_confirm_decisions_endpoint_reaches_product_grain(db):
    """The route dispatches by the run's own stamped grain (S16 follow-up, 21 Aug) - 
    a product-grain run is no longer refused by the blanket location-grain gate."""
    from app.database import get_db
    from app.dependencies import get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService
    from fastapi.testclient import TestClient

    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    supplier = _supplier(db, f"{MARKER} Supplier A")
    run = _run(db)
    _recommendation(db, run, product, wh, qty=50)
    svc.write_rows(db, run.id)
    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=40, supplier_code=supplier.supplier_code, actor="tester",
    )

    actor = {"id": "tester", "email": "tester@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = ["scm.reorder.run"]
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    try:
        with TestClient(app) as client:
            res = client.post(
                f"/api/v1/scm/reorder-runs/{run.id}/confirm-decisions", json={"ids": []}
            )
    finally:
        UserPermissionService.check_user_has_permission = originals[0]
        UserPermissionService.get_user_permission_slugs = originals[1]
        app.dependency_overrides.clear()

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["confirmed_count"] == 1
    assert body["po_count"] == 1


# =========================================================================== #
# (a2) grid-decided (PlanRowDecision on member recs) - the ACTUAL Reorder Planning
# results grid the captain meant ("I need the confirm decision to be in reorder
# planning, not in another page called order summary"). `usePlanLines.decide` fans
# the SAME decision out to every member rec of a grouped product row (never split),
# so confirming must consolidate ONCE per product, never once per member.
# =========================================================================== #


def test_grid_decided_group_confirm_drafts_once_with_the_right_qty(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh_a = _warehouse(db)
    wh_b = _warehouse(db)
    supplier = _supplier(db, f"{MARKER} Supplier A")
    run = _run(db)
    # TWO member recs for the SAME product (two warehouses), exactly what a grouped
    # product row fans a decision out to.
    rec_a = _recommendation(db, run, product, wh_a, qty=30, supplier=supplier)
    rec_b = _recommendation(db, run, product, wh_b, qty=20, supplier=supplier)

    # the FE fan-out: the IDENTICAL decision written onto EVERY member, never split.
    for rec in (rec_a, rec_b):
        dsvc.record_plan_row_decision(
            db, rec.id, kind="buy", buy_qty=298, stock_takes=None,
            po_qty=None, po_refs=None, reason_text=None, actor="tester",
        )

    out = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out["confirmed_count"] == 1, "one PRODUCT, not one per member"
    assert out["po_count"] == 1

    # the fanned 298 is split back across the group's REAL member warehouses (B2),
    # never once per member (894) and never on a NULL warehouse.
    lines = _lines_for_product(db, product.id)
    assert lines, "product-grain confirm must draft at least one PO line"
    assert len(lines) <= 2, "never more than the group's own member warehouses"
    total_qty = sum(float(l["qty_ordered"]) for l in lines)
    assert total_qty == 298, "the fanned qty, never summed/tripled across members"
    member_warehouse_ids = {wh_a.id, wh_b.id}
    for l in lines:
        assert l["warehouse_id"] is not None, "no line may carry a NULL warehouse"
        assert l["warehouse_id"] in member_warehouse_ids


def test_grid_decided_mixture_only_the_buy_portion_drafts(db):
    """A mixture like the captain's own example ('PO 1,191 + Buy 1,626') only drafts
    its buy portion - the po_qty leg is already-ordered stock, nothing to purchase."""
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    supplier = _supplier(db, f"{MARKER} Supplier A")
    run = _run(db)
    rec = _recommendation(db, run, product, wh, qty=50, supplier=supplier)

    dsvc.record_plan_row_decision(
        db, rec.id, kind="mixture", buy_qty=1626, stock_takes=None,
        po_qty=1191, po_refs=["PO-1"], reason_text="mixed cover", actor="tester",
    )

    out = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out["confirmed_count"] == 1
    line = _line_for_product(db, product.id)
    assert line is not None
    assert float(line["qty_ordered"]) == 1626, "only the buy leg drafts, never the PO leg"
    assert line["warehouse_id"] == wh.id


def test_grid_decision_wins_over_a_summary_screen_decision_no_double_line(db):
    """Both surfaces can hold a decision for the same product - the grid is
    AUTHORITATIVE (mirrors S16's row-decision-wins doctrine on the location side)."""
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    grid_supplier = _supplier(db, f"{MARKER} Grid Supplier")
    summary_supplier = _supplier(db, f"{MARKER} Summary Supplier")
    run = _run(db)
    rec = _recommendation(db, run, product, wh, qty=50, supplier=grid_supplier)
    svc.write_rows(db, run.id)

    # the OLDER surface decides first...
    svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=999, supplier_code=summary_supplier.supplier_code, actor="tester",
    )
    # ...then the grid decides too, on the member rec.
    dsvc.record_plan_row_decision(
        db, rec.id, kind="buy", buy_qty=40, stock_takes=None,
        po_qty=None, po_refs=None, reason_text=None, actor="tester",
    )

    out = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out["confirmed_count"] == 1, "one line, not one per decision surface"
    assert out["po_count"] == 1

    line_count = db.execute(text(
        "SELECT count(*) FROM purchase_order_lines "
        "WHERE product_id = :p AND source_system = 'scm_order_summary_row'"
    ), {"p": product.id}).scalar()
    assert line_count == 1

    line = _line_for_product(db, product.id)
    assert float(line["qty_ordered"]) == 40, "the grid's qty wins"
    assert line["warehouse_id"] == wh.id
    po = db.execute(text(
        "SELECT supplier_id::text AS supplier_id FROM purchase_orders WHERE id = :id"
    ), {"id": line["po_id"]}).mappings().first()
    assert po["supplier_id"] == grid_supplier.id, "the grid's supplier wins"


def test_clear_plan_row_decision_then_confirm_line_gone(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    supplier = _supplier(db, f"{MARKER} Supplier A")
    run = _run(db)
    rec = _recommendation(db, run, product, wh, qty=50, supplier=supplier)

    dsvc.record_plan_row_decision(
        db, rec.id, kind="buy", buy_qty=40, stock_takes=None,
        po_qty=None, po_refs=None, reason_text=None, actor="tester",
    )
    dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert _line_for_product(db, product.id) is not None

    dsvc.clear_plan_row_decision(db, rec.id, actor="tester")
    # clear retracts the line immediately - the next confirm has nothing left to undo,
    # and the "then confirm" in the name proves that re-running finds it already gone.
    assert _line_for_product(db, product.id) is None
    out = dsvc.confirm_decisions(db, run.id, ids=None, actor="tester")
    assert out["confirmed_count"] == 0
    assert out["po_count"] == 0
    assert _line_for_product(db, product.id) is None


# =========================================================================== #
# (b) bulk_confirm -> order-inquiry auto-place cascade (captain, 21 Aug)
# =========================================================================== #


def test_bulk_confirm_auto_places_a_raised_order_inquiry_buy_row():
    """Confirming a draft PO (either grain) is now a THIRD trigger of the same
    idempotent cascade `project_supply_service._auto_place_after_confirm` already
    runs on decision confirm - a RAISED buy row for the same product claims the
    line the confirm just opened, in the same run, best-effort."""
    with blank_session() as db:
        company_id = _oi_sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _oi_user(db, f"{MARKER} Buyer")
        world = _oi_seed_world(db, company_id, user_id)
        product = world["product"]
        warehouse = world["warehouse"]
        supplier = world["supplier"]

        row = _oi_row(db, company_id, world["inquiry"], qty="20", item_code=product.product_code)

        po = PurchaseOrder(
            id=_u(), company_id=company_id, po_number=_code("PO"),
            supplier_id=supplier.id, status="draft_recommendation",
            source_system="scm_order_summary_row", source_ref="scm",
        )
        db.add(po)
        db.flush()
        po_line = _oi_po_line(
            db, company_id, po, product, warehouse, qty_ordered="30",
        )
        db.commit()

        with company_scope(db, frozenset({company_id})):
            out = PurchaseOrderService(db).bulk_confirm([po.id], actor=user_id)

        assert out["confirmed_count"] == 1
        db.refresh(po)
        assert po.status == "active", "the confirm itself must still succeed"
        db.refresh(row)
        assert row.state == INQUIRY_PLACED, "the just-opened PO line must be auto-claimed"
        assert row.po_line_id == po_line.id
        assert "auto: po_confirm" in (row.note or "")


def test_bulk_confirm_still_succeeds_when_auto_place_blows_up(monkeypatch):
    """Post-commit side effects are best-effort (CLAUDE.md): a failure in the
    auto-place pass must not turn an already-successful PO confirm into a 500 the
    retry cannot repair, and must not roll the confirm back either."""
    with blank_session() as db:
        company_id = _oi_sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _oi_user(db, f"{MARKER} Buyer")
        world = _oi_seed_world(db, company_id, user_id)
        product = world["product"]
        warehouse = world["warehouse"]
        supplier = world["supplier"]

        po = PurchaseOrder(
            id=_u(), company_id=company_id, po_number=_code("PO"),
            supplier_id=supplier.id, status="draft_recommendation",
            source_system="scm_order_summary_row", source_ref="scm",
        )
        db.add(po)
        db.flush()
        _oi_po_line(db, company_id, po, product, warehouse, qty_ordered="30")
        db.commit()

        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        def _boom(self, *a, **kw):
            raise RuntimeError("auto-place exploded")

        monkeypatch.setattr(ProjectOrderInquiryService, "auto_place_for_products", _boom)

        with company_scope(db, frozenset({company_id})):
            out = PurchaseOrderService(db).bulk_confirm([po.id], actor=user_id)

        assert out["confirmed_count"] == 1, "the PO confirm itself must not raise"
        db.refresh(po)
        assert po.status == "active", "a failed auto-place must not roll the confirm back"
