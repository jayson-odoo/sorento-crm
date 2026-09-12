"""Slice A, diff parity (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`,
AC-A1 to AC-A4; AC-A5 is `test_outstanding_diff_line_identity.py` and
`test_planning_change_batch_kind_parity.py`). RED before the coder's slice lands - no
implementation exists yet.

Every manual-edit test below drives `SalesOrderService(db).update` directly, mirroring
`test_scm_sales_order_edit_propagation.py`'s own pattern (its docstring explains why the
helpers below are copied rather than imported: that file, and `test_planning_changes.py`
it in turn borrows from, are each free to evolve on their own schedule). Postgres only
(`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.

AC-A1's "removal accepted, no 409" needs an ADOPTED mirror order (`project_id=None`,
`SO_STATUS_ADOPTED`) rather than the registered-project world the other three ACs use:
`_upsert_lines`'s `is_authored` refusal (`referrer.project_id is not None or referrer
.status != SO_STATUS_ADOPTED`) fires unconditionally for a REGISTERED project's line,
before the `has_dependents` check the coder is changing ever runs - see
`tests/scm/test_sales_order_line_upsert.py::_adopted_mirror` for the same shape.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.planning_change import (
    PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    DECISION_CHALLENGED,
    SO_STATUS_ADOPTED,
    SO_STATUS_PUBLISHED,
    AllocationClaim,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.user import User
from app.schemas.scm_orders import SalesOrderUpdate
from app.services import project_seed_service
from app.services.error_handler import AppException
from app.services.scm.front_planning_engine import qty_text
from app.services.scm.sales_order_service import SalesOrderService
from tests._pg_fixture import blank_session

MARKER = "zzt-diffparity"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    from sqlalchemy import text

    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Set")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Basin",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("120.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, location="ZZT", is_active=True,
        fulfilment_planning=True,
    )
    db.add(row)
    db.flush()
    return row


def _core_so(db, company_id: str) -> SalesOrder:
    so = SalesOrder(
        id=_uid(), company_id=company_id, so_number=f"ZZT-CORE-{_uid()[:8]}",
        status="open", demand_class="project",
    )
    db.add(so)
    db.flush()
    return so


def _core_line(db, so, product: Product, warehouse: Warehouse, *, qty_ordered,
                required_date=date(2026, 8, 20)) -> SalesOrderLine:
    line = SalesOrderLine(
        id=_uid(), company_id=so.company_id, sales_order_id=so.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(str(qty_ordered)),
        qty_delivered=Decimal("0"), required_date=required_date, line_status="open",
    )
    db.add(line)
    db.flush()
    return line


def _project_so(db, project, *, so_id=None, autocount_doc_no=None) -> ProjectSalesOrder:
    order = ProjectSalesOrder(
        id=_uid(), company_id=project.company_id, project_id=project.id,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}", area_group="TOWER",
        status=SO_STATUS_PUBLISHED, so_id=so_id, autocount_doc_no=autocount_doc_no,
    )
    db.add(order)
    db.flush()
    return order


def _project_line(db, order, *, line_no, product: Product, core_line) -> ProjectSalesOrderLine:
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
        core_sales_order_line_id=core_line.id, line_no=line_no, product_id=product.id,
        description=f"{MARKER} line {line_no}", qty=core_line.qty_ordered, uom="SET",
        unit_price=Decimal("120.00"), amount=Decimal("0"),
        delivery_date=core_line.required_date,
    )
    db.add(line)
    db.flush()
    return line


class _World:
    def __init__(self, db, company_id, actor, own_wh):
        self.db = db
        self.company_id = company_id
        self.actor = actor
        self.own_wh = own_wh


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = _user(db, f"{MARKER} tester")
        project = register_project(
            db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
            title=f"{MARKER} Residences",
        )
        own_wh = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}")
        db.commit()
        world = _World(db, company_id, actor, own_wh)
        with company_scope(db, frozenset({company_id})):
            yield world, project


def _linked_line(world, project, *, qty_ordered, required_date=date(2026, 8, 20)):
    """A REGISTERED-project line (`project_id` set) - held/undecided AC-A2/A3/A4 scenarios
    only, never a removal (see the module docstring)."""
    db = world.db
    product = _product(db)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, product, world.own_wh, qty_ordered=qty_ordered, required_date=required_date,
    )
    order = _project_so(db, project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    mirror_line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
    db.commit()
    return core_so, core_line, product, order, mirror_line


def _adopted_line(world, *, qty_ordered, required_date=date(2026, 8, 20)):
    """An ADOPTED mirror order (`project_id=None`, `SO_STATUS_ADOPTED`) - AC-A1's removal
    scenarios only, exactly `test_sales_order_line_upsert.py::_adopted_mirror`'s shape."""
    db = world.db
    product = _product(db)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, product, world.own_wh, qty_ordered=qty_ordered, required_date=required_date,
    )
    order = ProjectSalesOrder(
        id=_uid(), company_id=world.company_id, project_id=None,
        provisional_ref=f"ZZT-ADOPT-{_uid()[:8]}", status=SO_STATUS_ADOPTED,
        so_id=core_so.id, autocount_doc_no=core_so.so_number,
    )
    db.add(order)
    db.flush()
    mirror_line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
    db.commit()
    return core_so, core_line, product, order, mirror_line


def _line_payload(project_line_id, *, timely_spo_qty="0", reserve=None, borrow=None,
                   buy_qty="0", buy_reason=None, amend_reason=None):
    body = {
        "project_line_id": project_line_id, "timely_spo_qty": timely_spo_qty,
        "reserve": reserve or [], "borrow": borrow or [], "buy_qty": buy_qty,
    }
    if buy_reason is not None:
        body["buy_reason"] = buy_reason
    if amend_reason is not None:
        body["amend_reason"] = amend_reason
    return body


def _api_client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = (
        lambda self, uid: ["projects.projects.view", "projects.projects.edit"]
    )
    return TestClient(app), originals


def _restore_api_client(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _freeze_with_a_full_buy(db, world, order, mirror_line):
    """Confirms a wholly-Buy decision for one line, freezing it in the order's ACTIVE
    decision - a full Buy needs no stock/warehouse setup beyond `world.own_wh`."""
    core_line = db.get(SalesOrderLine, mirror_line.core_sales_order_line_id)
    open_qty = str(core_line.qty_ordered - core_line.qty_delivered)
    client, originals = _api_client(db, world.actor)
    try:
        response = client.post(
            f"/api/v1/project-sales/sales-orders/{order.id}/confirm",
            json={"lines": [
                _line_payload(mirror_line.id, buy_qty=open_qty, buy_reason="ZZT no stock anywhere"),
            ]},
        )
        assert response.status_code == 200, response.text
    finally:
        _restore_api_client(originals)
    db.commit()


def _rows_for(db, batch_id: str) -> list[PlanningChangeRow]:
    return (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch_id)
        .order_by(PlanningChangeRow.created_at)
        .all()
    )


def _q(v) -> str:
    return qty_text(Decimal(str(v)))


# --------------------------------------------------------------------------- #
# AC-A1a: removing a line with an inquiry row (no active decision) is accepted
# --------------------------------------------------------------------------- #

def test_removing_a_line_with_an_inquiry_row_is_accepted_and_raises_cancelled(api):
    world, _project = api
    db = world.db
    core_so, core_line, _product, order, mirror_line = _adopted_line(world, qty_ordered=72)
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    decision.state = DECISION_CHALLENGED
    db.commit()

    result = SalesOrderService(db).update(
        core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None, "removal must raise a batch (AC-A1)"
    batch = db.get(PlanningChangeBatch, envelope["id"])
    assert batch.source_kind == PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "cancelled"
    assert row.project_line_id == str(mirror_line.id)
    assert row.from_json["qty"] == _q(72)
    assert row.to_json.get("qty") in (None, "0", _q(0)) or row.to_json.get("status") == "closed"

    assert (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == mirror_line.id).count()
        >= 1
    ), "removal must not touch the inquiry row it raised"

    db.expire_all()
    lines_by_id = {str(ln["id"]): ln for ln in result["lines"]}
    if str(core_line.id) in lines_by_id:
        assert lines_by_id[str(core_line.id)]["line_status"] == "cancelled"


# --------------------------------------------------------------------------- #
# AC-A1b: removing a line with an ACTIVE held decision is accepted
# --------------------------------------------------------------------------- #

def test_removing_a_line_with_a_held_decision_raises_cancelled(api):
    world, _project = api
    db = world.db
    core_so, core_line, _product, order, mirror_line = _adopted_line(world, qty_ordered=72)
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    result = SalesOrderService(db).update(
        core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None, "removal must raise a batch (AC-A1)"
    batch = db.get(PlanningChangeBatch, envelope["id"])
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "cancelled"
    assert row.project_line_id == str(mirror_line.id)
    assert row.from_json["qty"] == _q(72)
    assert row.to_json.get("qty") in (None, "0", _q(0)) or row.to_json.get("status") == "closed"


# --------------------------------------------------------------------------- #
# AC-A2a: adding a line to an order with held lines raises `added` in the batch
# --------------------------------------------------------------------------- #

def test_adding_a_line_to_an_order_with_held_lines_raises_added_in_the_same_batch(api):
    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, mirror_line)
    new_product = _product(db)

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": core_line.id, "sku": product.product_code, "qty_ordered": 80},
            {"sku": new_product.product_code, "qty_ordered": 10},
        ]),
        user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None
    batch = db.get(PlanningChangeBatch, envelope["id"])
    rows = _rows_for(db, batch.id)
    kinds = sorted(r.kind for r in rows)
    assert kinds == ["added", "qty_up"], kinds
    added_row = next(r for r in rows if r.kind == "added")
    assert added_row.to_json["qty"] == _q(10)
    assert added_row.item_code == new_product.product_code
    assert not (added_row.from_json or {}).get("qty")
    batch_ids = {r.batch_id for r in rows}
    assert batch_ids == {batch.id}


# --------------------------------------------------------------------------- #
# AC-A2b: adding a line to an UNDECIDED order raises nothing
# --------------------------------------------------------------------------- #

def test_adding_a_line_to_an_undecided_order_raises_nothing(api):
    world, project = api
    db = world.db
    core_so, core_line, product, _order, _mirror_line = _linked_line(
        world, project, qty_ordered=72,
    )
    new_product = _product(db)
    before_count = db.query(PlanningChangeBatch).count()

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": core_line.id, "sku": product.product_code, "qty_ordered": 72},
            {"sku": new_product.product_code, "qty_ordered": 10},
        ]),
        user_id=world.actor,
    )

    assert result["planning_change_batch"] is None
    assert db.query(PlanningChangeBatch).count() == before_count


# --------------------------------------------------------------------------- #
# AC-A3: changing a held line's product raises exactly one `product_changed` row
# --------------------------------------------------------------------------- #

def test_changing_a_held_lines_product_raises_exactly_one_product_changed_row(api):
    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, mirror_line)
    new_product = _product(db)

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": core_line.id, "sku": new_product.product_code, "qty_ordered": 72},
        ]),
        user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None, "a product swap must still raise a batch"
    batch = db.get(PlanningChangeBatch, envelope["id"])
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1, [r.kind for r in rows]
    row = rows[0]
    assert row.kind == "product_changed"
    assert row.from_json["item_code"] == product.product_code
    assert row.to_json["item_code"] == new_product.product_code
    assert row.item_code == new_product.product_code
    assert not any(r.kind == "cancelled" for r in rows)
    assert not any(r.kind == "added" for r in rows)


# --------------------------------------------------------------------------- #
# AC-A4: setting a held line's qty to 0 raises `cancelled`, never `qty_down`
# --------------------------------------------------------------------------- #

def test_setting_a_held_lines_qty_to_zero_raises_cancelled_not_qty_down(api):
    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    # `SalesOrderLineInput.qty_ordered` is `Field(..., gt=0)` today - a held line settling
    # to 0 is new vocabulary this slice must accept (rule 5, "qty-to-zero as cancelled"),
    # so this construction itself is expected to raise until the coder loosens it to
    # `ge=0`. That IS today's red, not a fixture bug.
    update = SalesOrderUpdate(lines=[
        {"id": core_line.id, "sku": product.product_code, "qty_ordered": 0},
    ])

    result = SalesOrderService(db).update(core_so.id, update, user_id=world.actor)

    envelope = result["planning_change_batch"]
    assert envelope is not None
    batch = db.get(PlanningChangeBatch, envelope["id"])
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "cancelled"
    assert row.from_json["qty"] == _q(72)
    assert row.to_json.get("qty") in (None, "0", _q(0)) or row.to_json.get("status") == "closed"


# --------------------------------------------------------------------------- #
# R-S5 (review round): qty-to-zero and removal both end with the SAME core-line
# shape - line_status CANCELLED - so a later reader has one thing to check, not two.
# --------------------------------------------------------------------------- #

def test_setting_a_held_lines_qty_to_zero_marks_the_line_cancelled(api):
    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    update = SalesOrderUpdate(lines=[
        {"id": core_line.id, "sku": product.product_code, "qty_ordered": 0},
    ])
    SalesOrderService(db).update(core_so.id, update, user_id=world.actor)

    db.expire_all()
    from app.services.document_ingest_service import CANCELLED

    reloaded = db.get(SalesOrderLine, core_line.id)
    assert reloaded.line_status == CANCELLED, reloaded.line_status


# --------------------------------------------------------------------------- #
# Schema contract: every PLANNING_CHANGE_KIND_* constant is in the wire Literal,
# and "closed" (the pre-rename row kind) is not.
# --------------------------------------------------------------------------- #

def test_every_planning_change_kind_constant_is_in_the_schema_literal_and_closed_is_not():
    import typing

    from app import models
    from app.schemas.planning_change import PlanningChangeKind

    kind_constants = {
        value for name, value in vars(models.planning_change).items()
        if name.startswith("PLANNING_CHANGE_KIND_") and isinstance(value, str)
    }
    assert kind_constants, "expected at least one PLANNING_CHANGE_KIND_* constant"
    literal_values = set(typing.get_args(PlanningChangeKind))
    assert kind_constants <= literal_values, (
        f"model kind constants {kind_constants - literal_values} are missing from "
        "PlanningChangeKind - a row with that kind will 500 on response validation"
    )
    assert "closed" not in literal_values, (
        "PLANNING_CHANGE_KIND_CLOSED is renamed to 'cancelled' "
        "(PLAN-scm-change-management-one-engine.md, Slice A) - 'closed' must not remain "
        "in the wire literal"
    )


# --------------------------------------------------------------------------- #
# R-B1 (review round): re-adding the same product after a cancellation is a
# NEW open line, never a write onto the cancelled row the SKU fallback would
# otherwise re-match.
# --------------------------------------------------------------------------- #

def test_re_adding_the_same_product_after_a_cancellation_creates_a_new_open_line(api):
    from app.services.document_ingest_service import CANCELLED

    world, _project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _adopted_line(world, qty_ordered=72)
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    SalesOrderService(db).update(core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor)
    db.expire_all()
    assert db.get(SalesOrderLine, core_line.id).line_status == CANCELLED

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{"sku": product.product_code, "qty_ordered": 30}]),
        user_id=world.actor,
    )

    lines_by_id = {str(ln["id"]): ln for ln in result["lines"]}
    assert str(core_line.id) in lines_by_id, "the cancelled line must survive, untouched"
    cancelled_line = lines_by_id[str(core_line.id)]
    assert cancelled_line["line_status"] == "cancelled"
    assert cancelled_line["qty_ordered"] == 72

    new_lines = [
        ln for ln in result["lines"]
        if str(ln["id"]) != str(core_line.id) and ln["sku"] == product.product_code
    ]
    assert len(new_lines) == 1, result["lines"]
    new_line = new_lines[0]
    assert new_line["line_status"] == "open"
    assert new_line["qty_ordered"] == 30

    envelope = result["planning_change_batch"]
    assert envelope is not None
    batch = db.get(PlanningChangeBatch, envelope["id"])
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1, [r.kind for r in rows]
    assert rows[0].kind == "added", rows[0].kind


# --------------------------------------------------------------------------- #
# R-B2 (review round): saving the identical payload a second time must not
# re-raise the cancellation - the line is already gone from the payload,
# already cancelled; nothing NEW changed.
# --------------------------------------------------------------------------- #

def test_saving_the_same_payload_again_does_not_re_raise_the_cancellation(api):
    world, _project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _adopted_line(world, qty_ordered=72)
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    SalesOrderService(db).update(core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor)
    SalesOrderService(db).update(core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor)

    batches = db.query(PlanningChangeBatch).all()
    assert len(batches) == 1, [b.id for b in batches]
    all_rows = [r for b in batches for r in _rows_for(db, b.id)]
    cancelled_rows = [r for r in all_rows if r.kind == "cancelled"]
    assert len(cancelled_rows) == 1, [r.kind for r in all_rows]


# --------------------------------------------------------------------------- #
# R-S2 (review round): a held line's removal is only ever bypassed by the
# SOLineAllocation Confirm itself writes - another project's AllocationClaim
# on the same mirror line still refuses the removal.
# --------------------------------------------------------------------------- #

def test_removing_a_held_line_with_an_allocation_claim_is_still_refused(api):
    world, project = api
    db = world.db
    core_so, core_line, _held_product, order, mirror_line = _adopted_line(world, qty_ordered=72)
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    claim_product = _product(db)
    claim = AllocationClaim(
        id=_uid(), from_project_id=project.id, to_project_id=project.id,
        so_line_id=mirror_line.id, product_id=claim_product.id, qty=Decimal("5"),
    )
    db.add(claim)
    db.commit()

    with pytest.raises(AppException) as exc:
        SalesOrderService(db).update(
            core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SO_LINE_LINKED_TO_PROJECT"


# --------------------------------------------------------------------------- #
# R-S3 (review round): the order header's own totals must not still count a
# cancelled line's quantity.
# --------------------------------------------------------------------------- #

def test_order_totals_exclude_a_cancelled_line(api):
    world, _project = api
    db = world.db
    core_so, core_line, _product, order, mirror_line = _adopted_line(world, qty_ordered=72)
    _freeze_with_a_full_buy(db, world, order, mirror_line)

    result = SalesOrderService(db).update(
        core_so.id, SalesOrderUpdate(lines=[]), user_id=world.actor,
    )

    assert result["total_qty"] == 0, result["total_qty"]
    assert result["open_line_count"] == 0, result["open_line_count"]


# --------------------------------------------------------------------------- #
# R-S4 (review round): a brand-new order can never be created with a
# zero-qty line - only an EDIT settling an existing held line reads 0 as
# "cancel it" (AC-A4).
# --------------------------------------------------------------------------- #

def test_create_rejects_a_zero_qty_line(api):
    from app.models.numbering import DocumentNumberingRule

    world, _project = api
    db = world.db
    customer = Customer(
        id=_uid(), customer_code=f"ZZT-{_uid()[:8]}", customer_name=f"{MARKER} co",
    )
    # `SalesOrderService.create` numbers via `NumberingService.get_next_number
    # ("sales_order", commit_rule=False)` with no `company_id` - the scratch schema has
    # no rule at all, so this seeds the cheapest one (unscoped) rather than depending on
    # a fixture this file does not otherwise need.
    numbering_rule = DocumentNumberingRule(
        id=_uid(), company_id=None, doc_type="sales_order", enabled=True,
        prefix_template="ZZT-{year}-", number_digits=4, next_value=1, start_value=1,
        reset_policy="none",
    )
    db.add_all([customer, numbering_rule])
    db.commit()
    product = _product(db)

    client, originals = _api_client(db, world.actor)
    try:
        response = client.post(
            "/api/v1/scm/sales-orders",
            json={
                "order_type": "SO",
                "customer_code": customer.customer_code,
                "lines": [{"sku": product.product_code, "qty_ordered": 0}],
            },
        )
    finally:
        _restore_api_client(originals)

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# R2-N1 (round 2): re-sending an already-zero line, unchanged, must not cancel
# it - `_upsert_lines`'s qty-to-zero cancel (R-S5) keys on the NEW value alone
# (`if float(ln.qty_ordered or 0) <= 0`), so an AutoCount-style line already at
# 0 (25,738 of them on the prod copy) gets cancelled the instant an unrelated
# line on the SAME order is edited in the same save. The fix is `old > 0 >=
# new` - a transition, not a bare value check.
# --------------------------------------------------------------------------- #

def test_re_sending_an_already_zero_line_does_not_cancel_it(api):
    world, _project = api
    db = world.db
    core_so, core_line_a, product_a, order, mirror_line_a = _adopted_line(
        world, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, mirror_line_a)

    product_b = _product(db)
    core_line_b = SalesOrderLine(
        id=_uid(), company_id=world.company_id, sales_order_id=core_so.id,
        product_id=product_b.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("0"), qty_delivered=Decimal("0"), line_status="open",
        source_system="autocount", line_total=Decimal("500.00"),
    )
    db.add(core_line_b)
    db.commit()

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": core_line_a.id, "sku": product_a.product_code, "qty_ordered": 80},
            {"id": core_line_b.id, "sku": product_b.product_code, "qty_ordered": 0},
        ]),
        user_id=world.actor,
    )

    lines_by_id = {str(ln["id"]): ln for ln in result["lines"]}
    assert lines_by_id[str(core_line_b.id)]["line_status"] == "open", (
        "an already-zero line resent unchanged must stay open, not be cancelled "
        "as a side effect of an unrelated line's edit"
    )
    assert result["total_amount"] is not None
    assert float(result["total_amount"]) == 500.0, (
        "B's own line_total must still count toward the order's total - it was never "
        "cancelled"
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None
    batch = db.get(PlanningChangeBatch, envelope["id"])
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1, [r.kind for r in rows]
    assert rows[0].kind == "qty_up", rows[0].kind
