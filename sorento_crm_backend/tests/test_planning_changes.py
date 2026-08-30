"""SO-book diff replanning (`documentation/plans/scm/PLAN-so-book-diff-replanning.md`).

AC-R12 pins one test per row of section 0's rule table against `suggest()` (pure). The rest
exercise `build_batch` / `apply` against a real Postgres chain (`_pg_fixture.blank_session`,
PRINCIPLES: never sqlite, every FK seeded here) and the four HTTP routes.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    SO_STATUS_PUBLISHED,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User
from app.services import planning_change_service, project_seed_service
from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    DATE_MOVED,
    QTY_CHANGED,
    Change,
    Diff,
    Line,
)

from ._pg_fixture import blank_session

MARKER = "zzt-planchg"
BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
REQUIRED_DATE = date(2027, 3, 1)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, *, discontinued: bool = False) -> Product:
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
        is_discontinued=discontinued,
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str, *, segment=None, pool_warehouse_id=None) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, location="ZZT",
        is_active=True, segment=segment, pool_warehouse_id=pool_warehouse_id,
        fulfilment_planning=True,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, on_hand, reserved=0) -> Stock:
    row = Stock(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=on_hand, quantity_reserved=reserved,
    )
    db.add(row)
    db.flush()
    return row


def _core_so(db, company_id: str):
    from app.models.order import SalesOrder

    so = SalesOrder(
        id=_uid(), company_id=company_id, so_number=f"ZZT-CORE-{_uid()[:8]}",
        status="open", demand_class="project",
    )
    db.add(so)
    db.flush()
    return so


def _core_line(db, so, product: Product, warehouse: Warehouse, *, qty_ordered,
                qty_delivered="0", required_date=REQUIRED_DATE):
    from app.models.order import SalesOrderLine

    line = SalesOrderLine(
        id=_uid(), company_id=so.company_id, sales_order_id=so.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(qty_ordered),
        qty_delivered=Decimal(qty_delivered), required_date=required_date,
        line_status="open",
    )
    db.add(line)
    db.flush()
    return line


def _project_so(db, project, *, status=SO_STATUS_PUBLISHED, so_id=None,
                 autocount_doc_no=None):
    order = ProjectSalesOrder(
        id=_uid(), company_id=project.company_id, project_id=project.id,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}", area_group="TOWER", status=status,
        so_id=so_id, autocount_doc_no=autocount_doc_no,
    )
    db.add(order)
    db.flush()
    return order


def _project_line(db, order, *, line_no, product: Product, core_line):
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
        core_sales_order_line_id=core_line.id if core_line else None, line_no=line_no,
        product_id=product.id, description=f"{MARKER} line {line_no}",
        qty=core_line.qty_ordered if core_line else Decimal("0"), uom="SET",
        unit_price=Decimal("120.00"), amount=Decimal("0"),
        delivery_date=core_line.required_date if core_line else REQUIRED_DATE,
    )
    db.add(line)
    db.flush()
    return line


def _classification(db, product: Product, warehouse: Warehouse, *,
                     abc_class_retail=None, abc_class_project=None):
    from app.models.scm import ItemClassification

    row = ItemClassification(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        abc_class_retail=abc_class_retail, abc_class_project=abc_class_project,
    )
    db.add(row)
    db.flush()
    return row


def _client(db, user_id: str):
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
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [VIEW]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


class _World:
    def __init__(self, db, company_id, actor, project, product, own_wh, pool_wh):
        self.db = db
        self.company_id = company_id
        self.actor = actor
        self.project = project
        self.product = product
        self.own_wh = own_wh
        self.pool_wh = pool_wh


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = _user(db, f"{MARKER} Aina")
        project = register_project(
            db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
            title=f"{MARKER} Tuju Residences",
        )
        product = _product(db)
        own_wh = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}", segment="project")
        pool_wh = _warehouse(db, f"ZZT-BRW-{_uid()[:4]}", segment="dealer")
        own_wh.pool_warehouse_id = pool_wh.id
        db.flush()
        db.commit()
        client, originals = _client(db, actor)
        world = _World(db, company_id, actor, project, product, own_wh, pool_wh)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, world
        finally:
            _restore(originals)


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


def _place_row_on_a_real_po(db, world, row: OrderInquiryRow, *, qty_ordered):
    """Places `row` through the REAL section-G path (`ProjectOrderInquiryService.place_on_po`)
  - never by hand-setting `row.state`. The 20 Aug regression only reproduces through this
    path: every earlier green test that hand-set `INQUIRY_ACTIONED` never exercised the state
    the live "Place on PO" workflow actually writes (`INQUIRY_PLACED`), which is why 145 live
    placed rows sat invisible to this netting for as long as they did. Returns `(po, po_line)`."""
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal(str(qty_ordered)), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()
    ProjectOrderInquiryService(db).place_on_po(row.id, po_line.id, actor_user_id=world.actor)
    db.commit()
    return po, po_line


# ============================================================================
# AC-R12: one test per row of the section-0 rule table, against `suggest()` (pure).
# ============================================================================


def _facts(*, dealer=False, dealer_where=None, project_hot=False, discontinued=False,
           days_moved=0, within_window=True, window_days=60, buy_actioned=False,
           po_number=None):
    return {
        "dealer_hot_selling": {"value": dealer, "where": dealer_where or []},
        "project_hot_selling": {"value": project_hot, "where": []},
        "discontinued": discontinued,
        "days_moved": days_moved,
        "within_reserve_window": {
            "value": within_window, "window_days": window_days,
            "new_date": "2026-09-01", "window_end": "2026-10-01",
        },
        "buy_actioned": {"value": buy_actioned, "po_number": po_number},
    }


def _held(*, reserve=None, buy_qty="0"):
    return {
        "reserve": reserve or [], "borrow": [], "buy_qty": buy_qty,
        "timely_spo_qty": "0", "revision_no": 1,
    }


def test_rule_1_delay_within_window_not_hot_keeps():
    verb, why = planning_change_service.suggest(
        "delayed",
        _held(reserve=[{"location": "BRW-BB", "qty": "66"}]),
        _facts(days_moved=14, within_window=True),
    )
    assert verb == "keep"
    assert "window" in why


def test_rule_2_delay_beyond_window_not_hot_not_discontinued_releases():
    verb, why = planning_change_service.suggest(
        "delayed",
        _held(reserve=[{"location": "MWH-IB", "qty": "40"}]),
        _facts(days_moved=197, within_window=False),
    )
    assert verb == "release"
    assert "beyond" in why


def test_rule_3_delay_dealer_hot_selling_releases_whatever_the_delay():
    verb, why = planning_change_service.suggest(
        "delayed",
        _held(reserve=[{"location": "BRW", "qty": "30"}]),
        _facts(days_moved=21, within_window=True, dealer=True, dealer_where=["BRW", "BRW-IB"]),
    )
    assert verb == "release"
    assert "Dealer hot-selling" in why


def test_rule_4_delay_discontinued_keeps_whatever_the_delay():
    verb, why = planning_change_service.suggest(
        "delayed",
        _held(reserve=[{"location": "MWH-IB", "qty": "18"}]),
        _facts(days_moved=259, within_window=False, discontinued=True),
    )
    assert verb == "keep"
    assert "Discontinued" in why


def test_rule_5_delay_holds_only_buy_not_actioned_keeps():
    verb, why = planning_change_service.suggest(
        "delayed", _held(reserve=[], buy_qty="25"),
        _facts(days_moved=19, buy_actioned=False),
    )
    assert verb == "keep"
    assert "has not actioned" in why


def test_rule_6_delay_buy_already_actioned_keeps_and_notes_po():
    verb, why = planning_change_service.suggest(
        "delayed", _held(reserve=[], buy_qty="18"),
        _facts(days_moved=21, buy_actioned=True, po_number="PO2026-0412"),
    )
    assert verb == "keep"
    assert "PO2026-0412" in why


def test_rule_7_advance_always_replans():
    verb, why = planning_change_service.suggest(
        "advanced", _held(reserve=[{"location": "BRW-BB", "qty": "20"}], buy_qty="40"),
        _facts(days_moved=-14),
    )
    assert verb == "replan"
    assert "Advanced" in why


def test_rule_8_qty_up_replans_the_delta():
    verb, why = planning_change_service.suggest(
        "qty_up", _held(reserve=[{"location": "BRW-BB", "qty": "72"}]), _facts(),
    )
    assert verb == "replan"


def test_rule_9_qty_down_reduces():
    verb, why = planning_change_service.suggest(
        "qty_down", _held(reserve=[{"location": "BRW-BB", "qty": "50"}], buy_qty="16"),
        _facts(),
    )
    assert verb == "reduce"


def test_rule_10_closed_retires():
    verb, why = planning_change_service.suggest(
        "closed", _held(reserve=[{"location": "MWH-IB", "qty": "4"}], buy_qty="8"), _facts(),
    )
    assert verb == "retire"


def test_rule_11_new_line_on_planned_order_replans_not_decided():
    verb, why = planning_change_service.suggest("added", None, _facts())
    assert verb == "replan"
    assert "New line" in why


def test_ac_r03_no_decision_always_replans_whatever_the_kind():
    verb, why = planning_change_service.suggest("delayed", None, _facts(days_moved=90))
    assert verb == "replan"
    verb2, _ = planning_change_service.suggest("closed", None, _facts())
    assert verb2 == "replan"


# ============================================================================
# build_batch
# ============================================================================


def _diff_change(kind, core_line, *, doc_number, item_code, location, old_date, new_date,
                  old_qty, new_qty):
    before = Line(doc_number=doc_number, item_code=item_code, location=location,
                  qty=float(old_qty), required_date=old_date, row_ref=str(core_line.id))
    after = None
    if kind != CLOSED:
        after = Line(doc_number=doc_number, item_code=item_code, location=location,
                     qty=float(new_qty), required_date=new_date, row_ref="1")
    return Change(kind, doc_number, item_code, location, before=before, after=after)


def test_build_batch_covers_only_planned_lines_and_is_none_when_nothing_planned_changed(api):
    _client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    planned_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                               required_date=date(2026, 8, 20))
    unplanned_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                                 required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    _project_line(db, order, line_no=1, product=world.product, core_line=planned_line)
    db.commit()

    changed = _diff_change(
        DATE_MOVED, planned_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="72", new_qty="72",
    )
    unplanned_changed = _diff_change(
        DATE_MOVED, unplanned_line, doc_number=core_so.so_number, item_code="ZZT-ITEM-2",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="10", new_qty="10",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed, unplanned_changed])
    applied_line_ids = {id(changed): str(planned_line.id), id(unplanned_changed): str(unplanned_line.id)}
    order_ids = {core_so.so_number: str(core_so.id)}

    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids=applied_line_ids, order_ids=order_ids,
        actor=world.actor, import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    assert batch.order_count == 1
    assert batch.line_count == 1  # the unplanned line is not in the batch

    only_unplanned_diff = Diff(scope_documents=(core_so.so_number,), changes=[unplanned_changed])
    no_batch = planning_change_service.build_batch(
        db, only_unplanned_diff, applied_line_ids=applied_line_ids, order_ids=order_ids,
        actor=world.actor, import_job_id=None, file_name="test.xlsx",
    )
    assert no_batch is None


def test_build_batch_skips_a_date_move_anchored_on_a_null_date(api):
    """PLAN section 10 / the 19 Aug 2026 incident: a date change with no FROM or no TO
    builds no reaction - a first-time date, or one an unreadable cell wiped, is not a
    delay or an advance."""
    _client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    null_from = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=None,
        new_date=date(2026, 9, 3), old_qty="72", new_qty="72",
    )
    no_batch = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[null_from]),
        applied_line_ids={id(null_from): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    assert no_batch is None

    null_to = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=None, old_qty="72", new_qty="72",
    )
    no_batch_2 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[null_to]),
        applied_line_ids={id(null_to): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    assert no_batch_2 is None

    # A real move alongside a null-anchored one still builds a batch, with only the real
    # move as a row - the null-anchored one is silently dropped, not merely unclassified.
    real_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                            required_date=date(2026, 8, 20))
    _project_line(db, order, line_no=2, product=world.product, core_line=real_line)
    db.commit()
    real_move = _diff_change(
        DATE_MOVED, real_line, doc_number=core_so.so_number, item_code="ZZT-ITEM-2",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="10", new_qty="10",
    )
    batch = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[null_from, real_move]),
        applied_line_ids={id(null_from): str(core_line.id), id(real_move): str(real_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    assert batch.line_count == 1


def test_build_batch_row_shape_has_facts_and_why_and_ac_r03_no_decision(api):
    _client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="72", new_qty="72",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch is not None

    out = planning_change_service.get_batch(db, str(batch.id))
    assert out["source"]["file_name"] == "book.xlsx"
    assert len(out["orders"]) == 1
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "delayed"
    assert row["held"] is None
    assert row["decision"] is None  # AC-R03: no decision, no acceptance offered
    assert row["suggested"] == "replan"
    assert row["facts"]["days_moved"] == 14


# ============================================================================
# apply()
# ============================================================================


def _confirm(client, order_id, payload):
    response = client.post(f"{BASE}/sales-orders/{order_id}/confirm", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_apply_release_returns_the_whole_line_to_the_board_with_no_buy_and_no_oi_change(api):
    """AC-R06 as corrected 19 Aug 2026 (PLAN section 6): release excludes the whole line
    from the new revision - the hold is gone, the line is undecided, nothing is bought for
    it, and no Order Inquiry row is touched (release is not a purchase)."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="40", new_qty="40",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch is not None
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["suggested"] == "release"
    assert row["why"].endswith("- back on the board.")

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == []
    assert result["applied_orders"] == [core_so.so_number]

    from app.models.project_so import SOSupplyDecision

    # The hold is gone: this was the order's only covered line, so it has NO active
    # decision left at all - undecided, back on the board, not a revision that still
    # carries an empty reserve.
    active = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one_or_none()
    )
    assert active is None

    # No Buy was raised for the released quantity - a release is not a purchase.
    order_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id)
        .all()
    )
    assert order_rows == []

    from app.models.planning_change import PlanningChangeRow as PlanningChangeRowModel

    row_model = db.query(PlanningChangeRowModel).filter(
        PlanningChangeRowModel.id == row["id"]
    ).one()
    assert row_model.applied_state == "applied"
    assert row_model.result_json["back_on_board"] is True
    assert row_model.result_json["released"]["qty"] == "40"
    assert row_model.result_json["released"]["location"] == world.pool_wh.warehouse_code


def test_apply_release_gives_up_a_reserved_lines_whole_claim_and_asks_purchasing_for_nothing(api):
    """Captain, 19 August 2026 (correcting the first cut of AC-R08): a release gives up
    the project's claim ENTIRELY - the reserve goes back to the pool and a RELEASE change
    row makes that visible in the worklist the way a DELAY row does.

    The line is wholly reserved (AC-L5: a line is met entirely from stock or entirely
    bought), which is also the only shape a release can now find a reserve on."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=150)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="150",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "150"}]),
    ]})

    # A reserved line asks purchasing for nothing, so it raises no ORDER row at all.
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .count()
        == 0
    )

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="150", new_qty="150",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["suggested"] == "release"
    assert row["why"].endswith("- back on the board.")

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == []

    from app.models.planning_change import PlanningChangeBatch as PlanningChangeBatchModel

    batch_model = db.query(PlanningChangeBatchModel).filter(
        PlanningChangeBatchModel.id == batch.id
    ).one()
    # A reserved line held no purchase, so releasing it asks purchasing for nothing at all
    # - the stock simply frees. Under AC-L5 a line can no longer hold both a reserve and a
    # Buy, so the "move the Buy to the pool" half of a release only ever applies to
    # revisions frozen before that rule.
    assert batch_model.result_json["inquiry_rows_changed"] == []
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id)
        .count()
        == 0
    )

    # And the claim is gone: the new revision does not cover the line, so it is back on the
    # board and its 150 are free at the pool again.
    from app.models.project_so import SOSupplyDecision
    from app.services.project_supply_service import ProjectSupplyService

    active = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .first()
    )
    snapshots = active.line_snapshots if active else []
    assert [snap for snap in snapshots if snap["line_id"] == str(line.id)] == []
    assert ProjectSupplyService(db).free_stock_by_location([world.product.id])[
        (world.product.id, world.pool_wh.id)
    ] == Decimal("150")


def test_apply_qty_down_reduces_the_row_in_place_and_writes_no_cancel_balance(api):
    """AC-P3-8 (26 August 2026), replacing the CANCEL_BALANCE this test used to pin.

    The drop is not a second instruction: the row purchasing already holds is REDUCED, and
    its own note carries what it was. An exception row beside it said the same thing twice,
    on a screen whose whole rule is one row per sales-order line."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="66",
                            required_date=date(2027, 1, 15))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        # Wholly bought (AC-L5), so the 16-unit reduction has only the Buy to come off.
        _line_payload(line.id, buy_qty="66", buy_reason="Nothing free elsewhere."),
    ]})

    core_line.qty_ordered = Decimal("50")
    db.flush()
    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2027, 1, 15),
        new_date=date(2027, 1, 15), old_qty="66", new_qty="50",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "qty_down"
    assert row["suggested"] == "reduce"

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == []

    from app.models.project_so import SOSupplyDecision

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    snapshot = decision.line_snapshots[0]
    buy = [c for c in snapshot["components"] if c["kind"] == "buy"]
    # 16 dropped off the Buy, for the whole 16-unit reduction; the line is still wholly
    # bought, now for 50.
    assert [c["qty"] for c in buy] == ["50"]

    cancel_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == "CANCEL_BALANCE")
        .all()
    )
    assert cancel_rows == [], "the row absorbed the drop; nothing is raised beside it"

    db.expire_all()
    live = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id,
                OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    assert len(live) == 1, "one order inquiry row per sales-order line, always"
    assert live[0].qty == Decimal("50")
    assert "66" in (live[0].note or ""), "and it says what it was"


def test_apply_closed_retires_open_row_and_notes_actioned_row(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12",
                            required_date=date(2027, 1, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        # Wholly bought (AC-L5).
        _line_payload(line.id, buy_qty="12", buy_reason="Timely stock short."),
    ]})

    # The Buy above already raised a row against this order's OWN inquiry
    # (`refresh_for_decision`, inside `confirm()`); action it here as purchasing would,
    # rather than creating a second inquiry (the `amendment_id IS NULL` singleton would
    # refuse it).
    actioned_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    actioned_row.state = INQUIRY_ACTIONED
    actioned_row.spo_ref = "PO2026-0398"
    db.commit()

    changed = _diff_change(
        CLOSED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2027, 1, 20), new_date=None,
        old_qty="12", new_qty="0",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "closed"
    assert row["suggested"] == "retire"

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == []

    db.refresh(actioned_row)
    assert actioned_row.state == INQUIRY_ACTIONED  # kept, never retired
    assert "closed" in (actioned_row.note or "").lower()


def test_apply_per_order_failure_does_not_block_the_other_order(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)

    core_so_a = _core_so(db, world.company_id)
    core_line_a = _core_line(db, core_so_a, world.product, world.own_wh, qty_ordered="40",
                              required_date=date(2026, 8, 25))
    order_a = _project_so(db, world.project, so_id=core_so_a.id,
                           autocount_doc_no=core_so_a.so_number)
    line_a = _project_line(db, order_a, line_no=1, product=world.product, core_line=core_line_a)

    core_so_b = _core_so(db, world.company_id)
    core_line_b = _core_line(db, core_so_b, world.product, world.own_wh, qty_ordered="30",
                              required_date=date(2026, 8, 25))
    order_b = _project_so(db, world.project, so_id=core_so_b.id,
                           autocount_doc_no=core_so_b.so_number)
    line_b = _project_line(db, order_b, line_no=1, product=world.product, core_line=core_line_b)
    db.commit()

    _confirm(client, order_a.id, {"lines": [
        _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})
    _confirm(client, order_b.id, {"lines": [
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "30"}]),
    ]})

    changed_a = _diff_change(
        DATE_MOVED, core_line_a, doc_number=core_so_a.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="40", new_qty="40",
    )
    changed_b = _diff_change(
        DATE_MOVED, core_line_b, doc_number=core_so_b.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="30", new_qty="30",
    )
    diff = Diff(scope_documents=(core_so_a.so_number, core_so_b.so_number),
                changes=[changed_a, changed_b])
    batch = planning_change_service.build_batch(
        db, diff,
        applied_line_ids={id(changed_a): str(core_line_a.id), id(changed_b): str(core_line_b.id)},
        order_ids={core_so_a.so_number: str(core_so_a.id), core_so_b.so_number: str(core_so_b.id)},
        actor=world.actor, import_job_id=None, file_name="book.xlsx",
    )
    db.commit()

    # Order B is re-planned on the board BETWEEN batch build and Apply - a real revision
    # bump so `apply()`'s own drift path (the same `confirm()` re-validation every other
    # apply goes through) refuses it honestly, without hand-rolling a failure.
    _confirm(client, order_b.id, {"lines": [
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "30"}],
                      amend_reason="Re-planned on the board."),
    ]})

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert core_so_a.so_number in result["applied_orders"]
    failed_numbers = {f["so_number"] for f in result["failed_orders"]}
    # Order A applies; order B's row was superseded, so it applies nothing and is excluded
    # rather than named a failure (AC-R11: superseded, not failed).
    assert core_so_b.so_number not in failed_numbers or core_so_b.so_number in result["applied_orders"]


def test_apply_twice_is_a_noop(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="40", new_qty="40",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()

    first = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert first["already_applied"] is False

    second = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert second["already_applied"] is True
    assert second["applied_orders"] == first["applied_orders"]


def test_set_row_decision_refuses_accept_on_a_superseded_row(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="40", new_qty="40",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()

    # The board re-plans it before anybody reviews the batch.
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}],
                      amend_reason="Re-planned on the board."),
    ]})

    out = planning_change_service.get_batch(db, str(batch.id))
    row_id = out["orders"][0]["rows"][0]["id"]
    assert out["orders"][0]["rows"][0]["applied_state"] == "superseded"

    with pytest.raises(Exception) as excinfo:
        planning_change_service.set_row_decision(db, str(batch.id), row_id, "accept")
    assert getattr(excinfo.value, "status_code", None) == 409


def test_apply_stamps_applied_at_only_when_something_actually_applied(api):
    """PLAN section 10, defect B: a batch every one of whose orders fails must stay
    pending - not `applied_at` stamped with nothing written, which locked the row
    decisions AND a retry both behind the "already applied" gate."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})

    # A 14-day move, within the reserve window: `suggest()` returns "keep", not
    # "replan"/"release" - those two skip `confirm()` entirely via
    # `supersede_for_material_change`, which does not gate on order status, so the
    # failure below needs a row that actually reaches `confirm()`.
    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 9, 8), old_qty="40", new_qty="40",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row_id = out["orders"][0]["rows"][0]["id"]
    assert out["orders"][0]["rows"][0]["suggested"] == "keep"
    planning_change_service.set_row_decision(db, str(batch.id), row_id, "accept")

    # A guaranteed, fix-independent failure: the order is no longer confirmable.
    order.status = "draft"
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["applied_orders"] == []
    assert len(result["failed_orders"]) == 1
    assert result["already_applied"] is False

    from app.models.planning_change import PlanningChangeBatch as PlanningChangeBatchModel

    stored = db.query(PlanningChangeBatchModel).filter(
        PlanningChangeBatchModel.id == batch.id
    ).one()
    assert stored.applied_at is None  # left pending, not falsely marked done

    # Re-apply is not blocked by an "already applied" no-op, and the row decision is
    # still editable - the two consequences PLAN section 10 named.
    again = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert again["already_applied"] is False

    updated = planning_change_service.set_row_decision(db, str(batch.id), row_id, "keep")
    assert updated["decision"] == "keep"


# ============================================================================
# Routes
# ============================================================================


def test_routes_list_get_put_and_apply_happy_path(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "72"}]),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="72", new_qty="72",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()

    listing = client.get(f"{BASE}/planning-changes")
    assert listing.status_code == 200, listing.text
    assert any(b["id"] == str(batch.id) for b in listing.json()["data"])

    detail = client.get(f"{BASE}/planning-changes/{batch.id}")
    assert detail.status_code == 200, detail.text
    row = detail.json()["orders"][0]["rows"][0]
    assert row["suggested"] == "keep"  # 14 days, within the reserve window
    row_id = row["id"]
    put = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row_id}", json={"decision": "keep"},
    )
    assert put.status_code == 200, put.text
    assert put.json()["decision"] == "keep"

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["already_applied"] is False


def test_routes_denied_without_the_view_permission(api):
    client, world = api
    from app.services.user_service import UserPermissionService

    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: False
    try:
        response = client.get(f"{BASE}/planning-changes")
        assert response.status_code == 403
    finally:
        UserPermissionService.check_user_has_permission = original


def test_apply_and_put_are_denied_for_a_view_only_principal(api):
    """PUT and Apply take `projects.projects.edit` - the same dependency the board's own
    `confirm` route uses - not the read-only `projects.projects.view` GETs sit on."""
    client, world = api
    db = world.db
    from app.services.user_service import UserPermissionService

    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="72", new_qty="72",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    row_id = planning_change_service.get_batch(db, str(batch.id))["orders"][0]["rows"][0]["id"]

    original = UserPermissionService.check_user_has_permission
    # A view-only principal: holds VIEW, but not EDIT.
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug == VIEW
    try:
        listing = client.get(f"{BASE}/planning-changes")
        assert listing.status_code == 200

        put = client.put(
            f"{BASE}/planning-changes/{batch.id}/rows/{row_id}", json={"decision": "keep"},
        )
        assert put.status_code == 403

        apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
        assert apply_response.status_code == 403
    finally:
        UserPermissionService.check_user_has_permission = original


def test_route_put_rejects_an_unknown_decision_with_422(api):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 9, 3), old_qty="72", new_qty="72",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    row_id = planning_change_service.get_batch(db, str(batch.id))["orders"][0]["rows"][0]["id"]

    response = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row_id}", json={"decision": "yolo"},
    )
    assert response.status_code == 422


# ============================================================================
# `confirm` / `amend` (captain, 19 August 2026: "clicking accept here has no effect" on a
# replan row - `accept` recorded a decision Apply never executed for it).
# ============================================================================


def test_composition_from_proposal_reads_the_boards_own_sources():
    proposal = {
        "project_line_id": "line-1",
        "qty": "50",
        "qty_outstanding": "50",
        "qty_proposed_incoming": "0",
        "qty_proposed_reserve": "20",
        "qty_proposed_buy": "30",
        "sources": [
            {"kind": "reserve", "qty": "20", "warehouse_id": "wh-own", "location": "OWN"},
            {"kind": "buy", "qty": "30"},
        ],
    }
    composed = planning_change_service.composition_from_proposal(proposal)
    assert composed["project_line_id"] == "line-1"
    assert composed["reserve"] == [{"warehouse_id": "wh-own", "qty": "20"}]
    assert composed["borrow"] == []
    assert composed["buy_qty"] == "30"
    assert composed["timely_spo_qty"] == "0"


def test_composition_from_proposal_derives_buy_when_the_server_states_no_figure():
    proposal = {
        "project_line_id": "line-2",
        "qty": "10",
        "sources": [],
    }
    composed = planning_change_service.composition_from_proposal(proposal)
    assert composed["buy_qty"] == "10"
    assert composed["reserve"] == []


def test_composition_from_proposal_warns_when_sources_disagree_with_the_aggregate(caplog):
    """Fix 2, the cheap guard: if a future producer bug lets `sources` drift from the
    aggregate `qty_proposed_reserve` (the original defect on SO397450 - the aggregate
    read 0 while `sources` still named a 432 pool draw), the mismatch is LOGGED rather
    than passing in silence. The aggregate still wins - `composition_from_proposal` has
    always trusted it over `sources` - but a warning now names the row."""
    proposal = {
        "project_line_id": "line-9",
        "key": "SO-1|1|ITEM|w1",
        "qty": "50",
        "qty_outstanding": "50",
        "qty_proposed_incoming": "0",
        "qty_proposed_reserve": "0",
        "qty_proposed_buy": "50",
        "sources": [
            {"kind": "reserve", "qty": "40", "warehouse_id": "wh-brw", "location": "BRW"},
        ],
    }
    with caplog.at_level(logging.WARNING, logger="app.services.planning_change_service"):
        composed = planning_change_service.composition_from_proposal(proposal)
    assert composed["reserve"] == []  # the aggregate (0) is still authoritative
    assert composed["buy_qty"] == "50"
    assert any(
        "disagrees with the proposed reserve" in record.message and "SO-1|1|ITEM|w1" in record.message
        for record in caplog.records
    )


def test_composition_from_proposal_no_warning_when_sources_agree_with_the_aggregate(caplog):
    proposal = {
        "project_line_id": "line-9",
        "key": "SO-1|1|ITEM|w1",
        "qty": "40",
        "qty_outstanding": "40",
        "qty_proposed_incoming": "0",
        "qty_proposed_reserve": "40",
        "qty_proposed_buy": "0",
        "sources": [
            {"kind": "reserve", "qty": "40", "warehouse_id": "wh-brw", "location": "BRW"},
        ],
    }
    with caplog.at_level(logging.WARNING, logger="app.services.planning_change_service"):
        planning_change_service.composition_from_proposal(proposal)
    assert not any("disagrees with the proposed reserve" in r.message for r in caplog.records)


# ============================================================================
# `_apply_placed_offset` (pure): the captain's 21 Aug ruling on SO397450 / SRT382-6-DIY.
# ============================================================================


def test_apply_placed_offset_full_redirect_when_the_pool_alone_covers_it():
    """Pool has plenty (`qty_proposed_reserve` 20 >= placed 12): the WHOLE placed
    quantity redirects and nothing is relabelled - `sources`/`trail` are untouched, which
    is what keeps them agreeing with the aggregate (Fix 1's own guarantee)."""
    proposal = {
        "qty_proposed_reserve": "20",
        "qty_proposed_incoming": "0",
        "qty_proposed_buy": "0",
        "sources": [{"kind": "reserve", "qty": "20", "location": "BRW"}],
        "trail": [
            {"step": 2, "kind": "pool", "location": "BRW", "taken": "20",
             "remaining_after": "0", "outcome": "took"},
        ],
    }
    out = planning_change_service._apply_placed_offset(proposal, Decimal("12"), "PO-1")
    assert out["qty_proposed_reserve"] == "20"
    assert out["qty_proposed_buy"] == "0"
    assert out["placed_redirect_qty"] == "12"
    assert out["sources"] == proposal["sources"]
    assert out["trail"][0].get("note") is None  # nothing relabelled, nothing to narrate


def test_apply_placed_offset_relabels_the_water_before_it_redirects_the_pool():
    """LADDER V5, second pass (27 August 2026): a placed PO is expected supply, and so is
    the water question 1 draws off the group's net. Two promises of one delivery, so the
    PO relabels the WATER first and only what is left of it reaches the pool redirect.

    9 on the water and 5 in the pool against 12 placed: the whole 9 becomes Buy, and 3 of
    the placed quantity redirects to replenish the pool. Under the old order the redirect
    ate 5 of the 12 first and left 2 of the water standing beside a PO that had already
    bought it."""
    proposal = {
        "qty_proposed_reserve": "5",
        "qty_proposed_incoming": "9",
        "qty_proposed_buy": "0",
        "sources": [
            {"kind": "reserve", "qty": "5", "location": "BRW"},
            {"kind": "timely_spo", "qty": "9", "location": "OWN", "spo_number": "SPO-1"},
        ],
        "trail": [
            {"step": 2, "kind": "incoming", "location": "OWN", "taken": "9",
             "remaining_after": "0", "outcome": "took"},
            {"step": 3, "kind": "pool", "location": "BRW", "taken": "5",
             "remaining_after": "0", "outcome": "took"},
        ],
    }
    out = planning_change_service._apply_placed_offset(proposal, Decimal("12"), "PO-2")
    assert out["qty_proposed_reserve"] == "5"  # untouched - the pool take always stands
    assert out["qty_proposed_incoming"] == "0"  # the whole 9 was already bought
    assert out["qty_proposed_buy"] == "9"
    assert out["placed_redirect_qty"] == "3"  # 12 - 9, and 3 <= the pool's 5

    assert not [s for s in out["sources"] if s["kind"] == "timely_spo"]
    reserve_source = next(s for s in out["sources"] if s["kind"] == "reserve")
    assert reserve_source["qty"] == "5"  # untouched

    incoming_step = next(s for s in out["trail"] if s["kind"] == "incoming")
    assert "9 already placed on PO-2, kept as the buy" in incoming_step["note"]
    pool_step = next(s for s in out["trail"] if s["kind"] == "pool")
    assert pool_step.get("note") is None  # the redirect-eligible rung is never narrated here


def test_apply_placed_offset_narrates_a_v5_trail_whose_water_came_to_a_sibling():
    """A ladder v5 trail has no `incoming` step - question 1 draws the water, under the key
    `own` - and question 1's step names the LINE's own location while the water may be
    coming to a sibling. Matching the code exactly then found nothing, so the step went on
    claiming 9 the aggregate had just moved onto Buy, which is the exact defect
    `_annotate_trail_for_offset` was written to stop.
    """
    proposal = {
        "qty_proposed_reserve": "5",
        "qty_proposed_incoming": "9",
        "qty_proposed_buy": "0",
        "sources": [
            {"kind": "reserve", "qty": "5", "location": "BRW"},
            {"kind": "timely_spo", "qty": "9", "location": "MWH-SMC"},
        ],
        "trail": [
            {"step": 1, "kind": "own", "location": "BRW-SMC", "taken": "9",
             "remaining_after": "5", "outcome": "took"},
            {"step": 2, "kind": "pool", "location": "BRW", "taken": "5",
             "remaining_after": "0", "outcome": "took"},
        ],
    }
    out = planning_change_service._apply_placed_offset(proposal, Decimal("12"), "PO-4")

    assert out["qty_proposed_incoming"] == "0"
    assert out["qty_proposed_buy"] == "9"
    assert out["placed_redirect_qty"] == "3"
    own_step = next(s for s in out["trail"] if s["kind"] == "own")
    assert "9 already placed on PO-4, kept as the buy" in (own_step["note"] or "")
    pool_step = next(s for s in out["trail"] if s["kind"] == "pool")
    assert pool_step.get("note") is None


def test_apply_placed_offset_redirects_the_whole_placed_qty_when_there_is_no_water():
    """The other side of the same order: nothing on the water, so nothing is relabelled and
    the pool redirect gets the whole placed quantity - exactly the captain's 21 Aug ruling,
    unchanged. What moved is only WHICH of the two goes first when both are on the table."""
    proposal = {
        "qty_proposed_reserve": "5",
        "qty_proposed_incoming": "0",
        "qty_proposed_buy": "7",
        "sources": [{"kind": "reserve", "qty": "5", "location": "BRW"}],
        "trail": [
            {"step": 2, "kind": "pool", "location": "BRW", "taken": "5",
             "remaining_after": "7", "outcome": "took"},
        ],
    }
    out = planning_change_service._apply_placed_offset(proposal, Decimal("12"), "PO-3")
    assert out["qty_proposed_reserve"] == "5"
    assert out["qty_proposed_incoming"] == "0"
    assert out["qty_proposed_buy"] == "7"
    assert out["placed_redirect_qty"] == "5"


def test_apply_placed_offset_is_a_noop_with_nothing_placed():
    proposal = {"qty_proposed_reserve": "10", "sources": ["sentinel"], "trail": ["sentinel"]}
    out = planning_change_service._apply_placed_offset(proposal, Decimal("0"))
    assert out is proposal


def _no_decision_replan_row(client, world, *, qty="72", days_moved=14):
    """A changed planned line with NO active decision (AC-R03): always `replan`, with a
    real board `proposal` behind it (no stock seeded, so the board proposes the whole
    quantity as Buy) - the common case the captain's fix targets."""
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty,
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 20),
        new_date=date(2026, 8, 20) + timedelta(days=days_moved), old_qty=qty, new_qty=qty,
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["suggested"] == "replan"
    assert row["decision"] is None  # the fix: no longer defaults to a no-op `accept`
    assert row["proposal"] is not None
    return batch, order, line, row


def test_route_put_confirm_composes_from_the_proposal_and_apply_writes_it(api):
    client, world = api
    batch, order, line, row = _no_decision_replan_row(client, world)

    put = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row['id']}", json={"decision": "confirm"},
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["decision"] == "confirm"
    assert body["composition"]["buy_qty"] == "72"  # no stock seeded - the whole line is Buy
    assert body["composition"]["project_line_id"] == line.id

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text
    result = apply_response.json()
    assert result["applied_orders"] == [order.autocount_doc_no]

    from app.models.project_so import SOSupplyDecision

    decision = (
        world.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    snapshot = decision.line_snapshots[0]
    buy = [c for c in snapshot["components"] if c["kind"] == "buy"]
    assert buy and Decimal(buy[0]["qty"]) == Decimal("72")

    batch_out = planning_change_service.get_batch(world.db, str(batch.id))
    assert batch_out["result"]["lines_confirmed"] == 1


def test_route_put_amend_requires_a_composition_with_422(api):
    client, world = api
    batch, _order, _line, row = _no_decision_replan_row(client, world)

    response = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row['id']}", json={"decision": "amend"},
    )
    assert response.status_code == 422


def test_route_put_amend_rejects_a_composition_that_does_not_balance_with_422(api):
    client, world = api
    batch, _order, line, row = _no_decision_replan_row(client, world)

    response = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row['id']}",
        json={
            "decision": "amend",
            "composition": _line_payload(line.id, buy_qty="10"),  # line is open for 72
        },
    )
    assert response.status_code == 422


def test_route_put_amend_stores_the_planners_own_composition_and_apply_writes_it(api):
    client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=100)
    batch, order, line, row = _no_decision_replan_row(client, world)

    response = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row['id']}",
        json={
            "decision": "amend",
            # Wholly from stock (AC-L5): the planner takes the whole line from the pool
            # rather than the Buy the proposal offered.
            "composition": _line_payload(
                line.id,
                reserve=[{"warehouse_id": world.pool_wh.id, "qty": "72"}],
                amend_reason="The pool has stock the proposal did not use.",
            ),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["composition"]["reserve"] == [
        {"warehouse_id": world.pool_wh.id, "qty": "72"}
    ]

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text

    from app.models.project_so import SOSupplyDecision

    decision = (
        world.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    snapshot = decision.line_snapshots[0]
    reserve = [c for c in snapshot["components"] if c["kind"] == "reserve"]
    assert reserve and Decimal(reserve[0]["qty"]) == Decimal("72")


# ============================================================================
# (d) PLAN-so-book-diff-replanning.md section 10, defect A, through the real caller.
# ============================================================================


def test_apply_carries_a_kept_lines_own_reserve_past_a_rival_that_moved_in(api):
    """Live reproduction, 19 August 2026: a covered line whose reserve is a Reserve at the
    shared pool moves 90 days out (beyond the window), so the system suggests Release; the
    planner overrides it with "Keep as is" instead. A second, unrelated covered line on the
    same order is accepted normally. Between the batch being built and Apply, something
    else claims the pool dry - exactly what this order's own un-netted hold would show as
    free once the kept line is named again. Apply must still write one new revision: the
    kept line's Reserve carries unchanged, and the accepted line applies alongside it."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=10)
    core_so = _core_so(db, world.company_id)
    core_line_kept = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                                 required_date=date(2026, 8, 25))
    core_line_accepted = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5",
                                     required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line_kept = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_kept)
    line_accepted = _project_line(db, order, line_no=2, product=world.product,
                                   core_line=core_line_accepted)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line_kept.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]),
        _line_payload(line_accepted.id, buy_qty="5", buy_reason="Nothing free elsewhere."),
    ]})

    # A rival claims the pool dry - everything this order's own un-netted Reserve would
    # otherwise show as free once the kept line names it again.
    pool_stock = (
        db.query(Stock)
        .filter(Stock.product_id == world.product.id, Stock.warehouse_id == world.pool_wh.id)
        .one()
    )
    pool_stock.quantity_reserved = 10
    db.commit()

    changed_kept = _diff_change(
        DATE_MOVED, core_line_kept, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 8, 25) + timedelta(days=90), old_qty="10", new_qty="10",
    )
    changed_accepted = _diff_change(
        DATE_MOVED, core_line_accepted, doc_number=core_so.so_number, item_code="ZZT-ITEM-2",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 8, 25) + timedelta(days=14), old_qty="5", new_qty="5",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed_kept, changed_accepted])
    batch = planning_change_service.build_batch(
        db, diff,
        applied_line_ids={
            id(changed_kept): str(core_line_kept.id),
            id(changed_accepted): str(core_line_accepted.id),
        },
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    rows = {row["line_no"]: row for row in out["orders"][0]["rows"]}
    assert rows[1]["suggested"] == "release"  # 90 days out, beyond the reserve window
    assert rows[2]["suggested"] == "keep"  # 14 days, within window, Buy only

    # The planner overrides the system's Release suggestion and keeps line 1 as is; line
    # 2 is left on its default "accept" decision.
    planning_change_service.set_row_decision(db, str(batch.id), rows[1]["id"], "keep")
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    assert result["applied_orders"] == [core_so.so_number]

    from app.models.project_so import SOLineAllocation, SOSupplyDecision

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id, SOSupplyDecision.state == "active")
        .one()
    )
    assert decision.revision_no == 2  # a new revision was actually written, not skipped
    allocations = {
        a.so_line_id: a
        for a in db.query(SOLineAllocation).filter(SOLineAllocation.decision_id == decision.id).all()
    }
    assert allocations[line_kept.id].qty == Decimal("10")
    assert str(allocations[line_kept.id].warehouse_id) == world.pool_wh.id


def test_apply_uncovers_a_replan_line_instead_of_letting_confirm_carry_it_forward(api):
    """Live reproduction, 19 August 2026: `_apply_one_order` deliberately leaves a
    `replan`/`release`/`retire` row OUT of the body it posts to `ProjectSupplyService
    .confirm()` so the line returns to the board undecided - but `confirm()`'s own "union
    is the server's" rule (PLAN 13.4) carries any covered line the body does not name
    forward VERBATIM, so the instant another line on the SAME order IS named, the excluded
    one rode along uninvited with its stale composition (seen live: SO403765 rev 5 kept
    line 12's old Buy and old date after an ADVANCE had been raised for it). The un-decide
    seam (`confirm(..., uncover_line_ids=...)`) is what `_apply_one_order` now uses to name
    it instead of merely omitting it."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                              required_date=date(2026, 8, 25))
    core_line_b = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="21",
                              required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line_a = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_a)
    line_b = _project_line(db, order, line_no=2, product=world.product, core_line=core_line_b)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
        _line_payload(line_b.id, buy_qty="21", buy_reason="Nothing free elsewhere."),
    ]})
    buy_row_b = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_b.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    changed_a = _diff_change(
        DATE_MOVED, core_line_a, doc_number=core_so.so_number, item_code="ZZT-ITEM-A",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 8, 25) + timedelta(days=14), old_qty="40", new_qty="40",
    )
    changed_b = _diff_change(
        DATE_MOVED, core_line_b, doc_number=core_so.so_number, item_code="ZZT-ITEM-B",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 8, 25) - timedelta(days=14), old_qty="21", new_qty="21",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed_a, changed_b])
    batch = planning_change_service.build_batch(
        db, diff,
        applied_line_ids={
            id(changed_a): str(core_line_a.id), id(changed_b): str(core_line_b.id),
        },
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    rows = {row["line_no"]: row for row in out["orders"][0]["rows"]}
    assert rows[1]["suggested"] == "keep"  # 14 days, within window, reserve held
    assert rows[2]["suggested"] == "replan"  # advanced - rule 7, unconditional

    # Line 2's row is explicitly accepted (a planner - or a batch built before the default
    # changed to `null` for a `replan` row - can still do this; `held` is not `None`, so
    # the write is legal). This is the exact shape that carried the line forward: NAMED as
    # accepted, but excluded from the confirm body because its suggestion is `replan`.
    planning_change_service.set_row_decision(db, str(batch.id), rows[2]["id"], "accept")
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    assert result["applied_orders"] == [core_so.so_number]

    from app.models.project_so import SOSupplyDecision

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    snapshot_line_ids = {s.get("project_line_id") for s in decision.line_snapshots}
    assert str(line_a.id) in snapshot_line_ids  # accepted normally: revised, still covered
    assert str(line_b.id) not in snapshot_line_ids  # replan: dropped, not carried forward

    from app.services.project_supply_service import ProjectSupplyService

    supply = ProjectSupplyService(db)
    frozen = supply.frozen_lines_of(supply.active_decision(str(order.id)))
    assert str(line_b.id) not in frozen

    # `refresh_for_decision` treats a line absent from `buy_lines` as dropped and cancels
    # what it had raised - the same behaviour a genuinely-undecided line already gets.
    db.refresh(buy_row_b)
    assert buy_row_b.state == INQUIRY_CANCELLED


def test_build_batch_proposal_for_a_covered_replan_row_is_the_boards_full_contribution(api):
    """Captain, 19 August 2026: the trail popover on an `advanced` row showed nothing - the
    row's `proposal_json` had one source and `trail: []`. Root cause: the ACTIVE decision
    still covers the line when `build_batch` builds its proposal (Apply is what excludes it,
    and Apply has not run yet), so a plain board build found it `covered` and handed back the
    FROZEN composition (`_apply_frozen`: one source, no trail, no `rank_factors`) instead of
    running the ladder fresh. `_proposal_for` now previews this one line as uncovered
    (`FulfilmentBoardService.build(..., exclude_covered_line_ids=[project_line_id])`), so the
    proposal is the board's own full `BoardContribution` - sources, a 7-rung trail,
    `rank_factors`, and `item_flags` - the same shape `BoardTrailPopover` / `BoardAmendDialog`
    already render off the live board."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="432",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    # Covered today by a plain Buy - the "Buy 432" the captain read with nothing under it.
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="432", buy_reason="Nothing free elsewhere."),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ADV",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 8, 25) - timedelta(days=14), old_qty="432", new_qty="432",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff,
        applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["suggested"] == "replan"  # advanced - rule 7, unconditional

    proposal = row["proposal"]
    assert proposal is not None
    # LADDER V5 (section 1e): the four questions plus Buy. The read-only own-location
    # strip is folded into question 1 - it existed to name the queue, which is one of that
    # question's facts - and incoming is not a question at all, because an SPO is inside
    # the ownership group's own net.
    assert [step["step"] for step in proposal["trail"]] == [1, 2, 3, 4, 5]
    assert [step["kind"] for step in proposal["trail"]] == [
        "own", "pool", "cross_group_borrow", "group_borrow", "buy",
    ]
    assert proposal["rank_factors"]
    assert proposal["sources"]
    assert proposal["item_flags"] is not None
    # Now free at its own location, so the fresh ladder proposes a Reserve rather than
    # repeating the stale frozen Buy - the tell that the ladder was actually walked.
    assert Decimal(proposal["qty_proposed_reserve"]) == Decimal("432")


def test_apply_confirms_only_the_batchs_own_line_leaving_an_unconfirmable_sibling_carried(api):
    """Live reproduction, SO391698 rev 2, 20 August 2026: a batch with ONE row (line 39, a
    `qty_up` 12 -> 14) failed Apply with "9 lines cannot be confirmed. Nothing was written."
  - `_apply_one_order` renamed EVERY line the active revision covered from its frozen
    snapshot (`_confirm_payload`) into the confirm body, even the 39 this batch never
    touched, so the whole order was re-validated against live facts on an apply that decided
    one line. `confirm()` already carries an UNNAMED covered line forward verbatim (PLAN
    13.4, "the union is the server's") - the fix is to stop naming a bystander line at all
    and let that carry-forward do its job, so a sibling that would refuse if re-validated is
    never asked.

    This test reproduces the same `_apply_one_order` code path with an `advanced` row rather
    than `qty_up` - `challenge_if_drifted` (PLAN 5.3, unrelated to this bug) always
    supersedes the WHOLE order's active decision the moment a covered line's own live open
    quantity has already moved off what was frozen, which a `qty_up` row's own composition
    needs live to total correctly; that would drop every OTHER line to undecided AFTER this
    fix, confounding the assertion below (a challenged revision carries nothing, module
    docstring). It does NOT drop them regardless of this fix: pre-fix, `_apply_one_order`
    renamed every covered line explicitly from its own frozen snapshot, so a clean sibling
    was preserved in the new revision whatever the target line's own drift did - the carry-
    forward path that a challenge starves was never in use. An `advanced` row exercises the
    identical bystander-renaming bug (any `suggested='replan'` + `decision='confirm'` row
    takes the same branch in `_apply_one_order`) without that unrelated confound, since
    neither its own nor the sibling's frozen facts move in the DB. See
    `test_apply_returns_a_dropped_bystander_in_returned_to_review` below for the drifted
    case this one deliberately avoids."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=8)
    core_so = _core_so(db, world.company_id)
    core_line_target = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12",
                                   required_date=date(2026, 9, 4))
    core_line_sibling = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="8",
                                    required_date=date(2026, 9, 4))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line_target = _project_line(db, order, line_no=1, product=world.product,
                                 core_line=core_line_target)
    line_sibling = _project_line(db, order, line_no=2, product=world.product,
                                  core_line=core_line_sibling)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line_target.id, buy_qty="12", buy_reason="Nothing free elsewhere."),
        _line_payload(line_sibling.id,
                      reserve=[{"warehouse_id": world.pool_wh.id, "qty": "8"}]),
    ]})

    # Between this confirm and the planning-change batch, the sibling's pool is retired -
    # if it were re-named and re-validated, `_check_line` would refuse it (the location is
    # no longer in `_reserve_ladder_locations`). It is never touched by this batch, so it
    # must never be asked.
    world.pool_wh.is_active = False
    db.commit()

    changed_target = _diff_change(
        DATE_MOVED, core_line_target, doc_number=core_so.so_number, item_code="ZZT-TARGET",
        location=world.own_wh.warehouse_code, old_date=date(2026, 9, 4),
        new_date=date(2026, 9, 4) - timedelta(days=14), old_qty="12", new_qty="12",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed_target])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed_target): str(core_line_target.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    assert len(out["orders"][0]["rows"]) == 1  # the sibling never appears in this batch
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "advanced"
    assert row["suggested"] == "replan"

    planning_change_service.set_row_decision(db, str(batch.id), row["id"], "confirm")
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    assert result["applied_orders"] == [core_so.so_number]

    from app.models.planning_change import PlanningChangeRow as PlanningChangeRowModel
    from app.models.project_so import SOSupplyDecision

    row_model = db.query(PlanningChangeRowModel).filter(
        PlanningChangeRowModel.id == row["id"]
    ).one()
    assert row_model.applied_state == "applied"

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    assert decision.revision_no == 2  # a new revision was written
    snapshots = {s["project_line_id"]: s for s in decision.line_snapshots}
    assert str(line_target.id) in snapshots
    assert str(line_sibling.id) in snapshots  # carried forward, not dropped

    # The sibling's hold is untouched: same warehouse, same qty, even though that
    # warehouse is no longer a valid Reserve source - proof it was carried, not re-posed.
    sibling_components = snapshots[str(line_sibling.id)]["components"]
    sibling_reserve = [c for c in sibling_components if c["kind"] == "reserve"]
    assert len(sibling_reserve) == 1
    assert sibling_reserve[0]["source_warehouse_id"] == str(world.pool_wh.id)
    assert sibling_reserve[0]["qty"] == "8"

    # The target line's own composition was actually re-decided (its pool is retired too,
    # so the fresh ladder still lands on Buy 12) and its OI row reflects that decision.
    target_components = snapshots[str(line_target.id)]["components"]
    target_buy = sum(Decimal(c["qty"]) for c in target_components if c["kind"] == "buy")
    assert target_buy == Decimal("12")

    order_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_target.id, OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.state != INQUIRY_CANCELLED)
        .one()
    )
    assert order_row.qty == Decimal("12")


def test_apply_returns_a_dropped_bystander_in_returned_to_review(api):
    """B1 (code review, 20 Aug 2026): the case the test above deliberately dodges. A real
    `qty_up` diff (12 -> 14) on the batch's own line moves that line's OWN live open
    quantity off what rev 1 froze, so `challenge_if_drifted` supersedes the whole order's
    active decision the moment Apply calls `confirm()` - "nothing is carried from a
    challenged revision; the lines it covered are undecided again" (module docstring).
    That is documented doctrine, not a bug: an unrelated sibling line the batch never named
    falls back to undecided too, and its raised Buy row is retired exactly like any other
    line dropped from the revision. The defect this pins is SILENCE - the apply result must
    say so, not just report `applied_orders`."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line_target = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12",
                                   required_date=date(2026, 9, 4))
    core_line_sibling = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="8",
                                    required_date=date(2026, 9, 4))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line_target = _project_line(db, order, line_no=1, product=world.product,
                                 core_line=core_line_target)
    line_sibling = _project_line(db, order, line_no=2, product=world.product,
                                  core_line=core_line_sibling)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line_target.id, buy_qty="12", buy_reason="Nothing free elsewhere."),
        _line_payload(line_sibling.id, buy_qty="8", buy_reason="Nothing free elsewhere."),
    ]})
    buy_row_sibling = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_sibling.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    # The book upload that produced this diff already wrote the new quantity to the core
    # line (the real `outstanding_import_service.apply()` order of operations) - the batch
    # is built AFTER that write, so its own proposal already walks the ladder for 14.
    core_line_target.qty_ordered = Decimal("14")
    db.flush()
    changed_target = _diff_change(
        QTY_CHANGED, core_line_target, doc_number=core_so.so_number, item_code="ZZT-TARGET",
        location=world.own_wh.warehouse_code, old_date=date(2026, 9, 4),
        new_date=date(2026, 9, 4), old_qty="12", new_qty="14",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed_target])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed_target): str(core_line_target.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    assert len(out["orders"][0]["rows"]) == 1  # the sibling never appears in this batch
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "qty_up"
    assert row["suggested"] == "replan"

    planning_change_service.set_row_decision(db, str(batch.id), row["id"], "confirm")
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    assert result["applied_orders"] == [core_so.so_number]

    # The silence this finding fixes: apply's own result names the bystander it dropped.
    assert len(result["returned_to_review"]) == 1
    returned = result["returned_to_review"][0]
    assert returned["so_number"] == core_so.so_number
    assert returned["line_count"] == 1
    assert returned["line_nos"] == [2]
    assert returned["reason"]  # a real reason derived off the decision, not a guess

    from app.models.project_so import SOSupplyDecision

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    assert decision.revision_no == 2  # a new revision was written
    snapshots = {s["project_line_id"]: s for s in decision.line_snapshots}
    # The batch's own line is confirmed at the NEW quantity...
    assert str(line_target.id) in snapshots
    target_components = snapshots[str(line_target.id)]["components"]
    target_buy = sum(Decimal(c["qty"]) for c in target_components if c["kind"] == "buy")
    assert target_buy == Decimal("14")
    # ...the untouched sibling is undecided again - dropped, not carried, exactly as an
    # unrelated `replan`/`release`/`retire` row would be.
    assert str(line_sibling.id) not in snapshots

    from app.services.project_supply_service import ProjectSupplyService

    supply = ProjectSupplyService(db)
    frozen = supply.frozen_lines_of(supply.active_decision(str(order.id)))
    assert str(line_sibling.id) not in frozen

    # Its raised Buy row is retired, same as any other line the revision no longer covers.
    db.refresh(buy_row_sibling)
    assert buy_row_sibling.state == INQUIRY_CANCELLED


def test_apply_of_an_already_challenged_revision_still_reports_its_bystanders(api):
    """S4 (fix-cluster, 20 Aug 2026): the headline case the report was built for, and the one
    the first version of the fix could not actually reach. `_apply_one_order` used to read the
    ORDER's `active_decision` as "the previous revision" - but a revision a drift challenge
    already flipped to CHALLENGED (the state a GET on the supply page, or an earlier apply,
    leaves behind) is not `active_decision` any more, so `previous_decision` read None and the
    whole report short-circuited to []. This is the same drift as the test above, except the
    challenge has ALREADY happened by the time Apply runs - `active_decision` is None from the
    first line of `_apply_one_order`, not merely mutated mid-flight."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line_target = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12",
                                   required_date=date(2026, 9, 4))
    core_line_sibling = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="8",
                                    required_date=date(2026, 9, 4))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line_target = _project_line(db, order, line_no=1, product=world.product,
                                 core_line=core_line_target)
    line_sibling = _project_line(db, order, line_no=2, product=world.product,
                                  core_line=core_line_sibling)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line_target.id, buy_qty="12", buy_reason="Nothing free elsewhere."),
        _line_payload(line_sibling.id, buy_qty="8", buy_reason="Nothing free elsewhere."),
    ]})

    core_line_target.qty_ordered = Decimal("14")
    db.flush()

    # The drift challenge runs BEFORE the batch exists at all - exactly what a CS user
    # opening the supply page would trigger, days before a book upload is even imported.
    from app.services.project_supply_service import ProjectSupplyService

    supply = ProjectSupplyService(db)
    expected_reason = supply.challenge_if_drifted(order)
    assert expected_reason, "the qty drift on the target line must be caught"
    db.commit()

    from app.models.project_so import SOSupplyDecision

    challenged = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    assert challenged.state == "challenged"  # confirmed: apply enters with NO active decision

    changed_target = _diff_change(
        QTY_CHANGED, core_line_target, doc_number=core_so.so_number, item_code="ZZT-TARGET",
        location=world.own_wh.warehouse_code, old_date=date(2026, 9, 4),
        new_date=date(2026, 9, 4), old_qty="12", new_qty="14",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed_target])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed_target): str(core_line_target.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    planning_change_service.set_row_decision(db, str(batch.id), row["id"], "confirm")
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    assert result["applied_orders"] == [core_so.so_number]

    # The fix: the report fires even though the order entered Apply with no ACTIVE decision
    # at all, only a CHALLENGED one.
    assert len(result["returned_to_review"]) == 1
    returned = result["returned_to_review"][0]
    assert returned["so_number"] == core_so.so_number
    assert returned["line_nos"] == [2]
    assert returned["line_count"] == len(returned["line_nos"])
    # The genuine drift reason travels through, not the generic "Reconfirmed by CS." caption
    # `_write_decision` stamps on an ACTIVE row it supersedes (this row was never ACTIVE
    # again once challenged, so that caption is never written here at all).
    assert returned["reason"] == expected_reason
    assert returned["reason"] != "Reconfirmed by CS."


def test_apply_of_a_genuinely_unconfirmable_target_line_still_fails_with_its_reason(api):
    """The fix above stops a BYSTANDER line from being re-validated - it must not also stop
    the line the batch actually decided from being checked. A target line whose own
    composition no longer clears live facts (its Reserve pool was claimed by a rival between
    the decision and Apply) still refuses, and nothing is written for that order."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=5)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                            required_date=date(2026, 9, 4))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="10", buy_reason="Nothing free elsewhere."),
    ]})

    core_line.qty_ordered = Decimal("15")
    db.flush()
    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number, item_code="ZZT-TARGET",
        location=world.own_wh.warehouse_code, old_date=date(2026, 9, 4),
        new_date=date(2026, 9, 4), old_qty="10", new_qty="15",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["suggested"] == "replan"

    # A hand-amended composition: the extra 5 comes off the pool, 10 stays Buy - legal
    # shape at PUT time (totals to the 15 the line is open for).
    planning_change_service.set_row_decision(
        db, str(batch.id), row["id"], "amend",
        composition={
            "project_line_id": str(line.id),
            "timely_spo_qty": "0",
            "reserve": [{"warehouse_id": world.pool_wh.id, "qty": "5"}],
            "borrow": [],
            "buy_qty": "10",
            "buy_reason": "Nothing free elsewhere.",
            "amend_reason": "The extra 5 comes off the pool.",
        },
    )
    db.commit()

    # A rival claims the pool dry before Apply runs.
    pool_stock = (
        db.query(Stock)
        .filter(Stock.product_id == world.product.id, Stock.warehouse_id == world.pool_wh.id)
        .one()
    )
    pool_stock.quantity_reserved = pool_stock.quantity_on_hand
    db.commit()

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["applied_orders"] == []
    assert len(result["failed_orders"]) == 1
    assert result["failed_orders"][0]["so_number"] == core_so.so_number
    assert "cannot be confirmed" in result["failed_orders"][0]["reason"]

    from app.models.planning_change import PlanningChangeRow as PlanningChangeRowModel
    from app.models.project_so import SOSupplyDecision

    row_model = db.query(PlanningChangeRowModel).filter(
        PlanningChangeRowModel.id == row["id"]
    ).one()
    assert row_model.applied_state == "failed"
    assert "cannot be confirmed" in row_model.applied_reason

    # Nothing was written: the order's active decision is still the original revision.
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    assert decision.revision_no == 1


# ============================================================================
# The 20 Aug placed/actioned state-vocabulary regression (the captain, live-testing
# section G). Every fixture below places its row through the REAL section-G path
# (`_place_row_on_a_real_po`), never by hand-setting `INQUIRY_ACTIONED` - that hand-set
# shortcut is exactly what let this regression through the existing suite for a day.
# ============================================================================


def test_apply_qty_up_after_a_real_place_on_po_updates_the_one_row_and_keeps_its_link(api):
    """Case A (the captain, 20 Aug): SO349754 WESERP10B - a line already covered by an
    active decision, placed 5 on a real PO, then the book raised the qty to 10. Before the
    fix, the netting predicate only recognised `INQUIRY_ACTIONED` (0 rows company-wide;
    "Place on PO" writes `INQUIRY_PLACED`), so a reconfirm re-raised the FULL new need on
    top of the untouched placed row - 15 against a 10 line.

    Since AC-P3-5 the answer is ONE row, not two: the line's own row is updated in place
    to the 10 the book says, its 5 stays on the purchase order it was placed on, and the
    row reads partly linked. The name used to promise a freshly-raised delta row, which is
    the shape this test now exists to say does NOT happen."""
    client, world = api
    db = world.db
    # No pool stock: the board proposes the whole line as Buy, isolating this case from
    # the Reserve-relabelling fix (Case B, covered separately below).
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5",
                            required_date=date(2027, 2, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="5", buy_reason="Nothing free elsewhere."),
    ]})
    placed_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    po, _po_line = _place_row_on_a_real_po(db, world, placed_row, qty_ordered="5")
    db.expire_all()
    placed_row = db.get(OrderInquiryRow, placed_row.id)
    assert placed_row.state == INQUIRY_PLACED
    assert placed_row.po_ref == po.po_number

    core_line.qty_ordered = Decimal("10")
    db.commit()
    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2027, 2, 1),
        new_date=date(2027, 2, 1), old_qty="5", new_qty="10",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "qty_up"
    assert row["suggested"] == "replan"
    assert row["proposal"]["qty_proposed_buy"] == "10"  # no stock - the whole new qty
    # No pool source at all (`qty_proposed_reserve` is "0"), so there is nothing for the
    # placed 5 to redirect against - the boundary the captain's 21 Aug ruling names, and
    # the old relabel-onto-Buy path (netted below by `refresh_for_decision`, not by a
    # trim here, because there is nothing on Reserve/incoming to trim) still applies.
    assert row["proposal"]["placed_redirect_qty"] == "0"

    put = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row['id']}", json={"decision": "confirm"},
    )
    assert put.status_code == 200, put.text
    assert Decimal(put.json()["composition"]["buy_qty"]) == Decimal("10")

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["applied_orders"] == [order.autocount_doc_no]

    db.expire_all()
    live_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    # AC-P3-5 (26 August 2026): ONE row, updated. The 5 already on the purchase order
    # stays on it - the link is untouched - and the row now asks for the 10 the book says,
    # of which 5 is covered. It used to be two rows, the placed 5 and a fresh 5, which is
    # the same line reading as two instructions on purchasing's list.
    assert len(live_rows) == 1, "one order inquiry row per sales-order line, always"
    survivor = live_rows[0]
    assert survivor.id == placed_row.id
    assert survivor.qty == Decimal("10")
    assert survivor.state == INQUIRY_PARTLY_LINKED
    assert survivor.po_ref == po.po_number  # the placement is intact
    links = ProjectOrderInquiryService(db)._links_of(survivor.id)
    assert [str(link.qty) for link in links] == ["5.0000"]


def test_apply_qty_up_with_no_decision_and_a_real_placed_row_redirects_it_to_the_pool(api):
    """Case B (the captain, 20 Aug, REVERSED by the captain's 21 Aug ruling on SO397450 /
    SRT382-6-DIY): SO349754 SRTWC287A-RL - a real placed 5 and NO active decision at all,
    the pool holding plenty of stock. The board proposes Reserve for the WHOLE new
    quantity (10, all from the pool) - this used to be trimmed to 5 and relabelled onto
    Buy so the placed 5 was not double-counted; the ruling reverses that: the pool take
    STANDS (Reserve 10 in full), and the already-placed 5 is instead REDIRECTED to
    replenish the pool it now draws down, never relabelled and never cancelled."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    # Inside the lead-time reserve window, and relative so it stays there: ladder v3 buys a
    # line beyond `today + lead time + 14` whole and consults no pool at all (AC-L1).
    needed = date.today() + timedelta(days=30)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5",
                            required_date=needed)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    from app.models.project_so import INQUIRY_RAISED, OrderInquiry

    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state=INQUIRY_RAISED, raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("5"), verb=IV_ORDER, state=INQUIRY_RAISED,
        supply_decision_id=None, stock_location=world.own_wh.warehouse_code,
    )
    db.add(row)
    db.commit()
    po, _po_line = _place_row_on_a_real_po(db, world, row, qty_ordered="5")

    core_line.qty_ordered = Decimal("10")
    db.commit()
    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=needed,
        new_date=needed, old_qty="5", new_qty="10",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row_out = out["orders"][0]["rows"][0]
    assert row_out["kind"] == "qty_up"
    assert row_out["suggested"] == "replan"
    assert row_out["held"] is None  # no active decision at all (AC-R03)
    assert row_out["facts"]["buy_actioned"]["value"] is True
    assert Decimal(row_out["facts"]["buy_actioned"]["qty"]) == Decimal("5")
    assert row_out["facts"]["buy_actioned"]["po_number"] == po.po_number

    proposal = row_out["proposal"]
    assert Decimal(proposal["qty_proposed_reserve"]) == Decimal("10"), (
        "the pool take stands in full - it is no longer trimmed by the placed 5"
    )
    assert Decimal(proposal["qty_proposed_buy"]) == Decimal("0")
    assert Decimal(proposal["placed_redirect_qty"]) == Decimal("5"), (
        "the overlap the pool covers, read back at Apply to redirect the placed PO"
    )
    # sources/trail agree with the untouched aggregate - nothing was trimmed.
    reserve_sources_total = sum(
        (Decimal(s["qty"]) for s in proposal["sources"] if s["kind"] == "reserve"),
        Decimal("0"),
    )
    assert reserve_sources_total == Decimal("10")

    put = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row_out['id']}", json={"decision": "confirm"},
    )
    assert put.status_code == 200, put.text
    composition = put.json()["composition"]
    assert Decimal(composition["buy_qty"]) == Decimal("0")
    reserve_total = sum((Decimal(c["qty"]) for c in composition["reserve"]), Decimal("0"))
    assert reserve_total == Decimal("10")

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["applied_orders"] == [order.autocount_doc_no]

    db.expire_all()
    live_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    assert len(live_rows) == 1, (
        "the placed row is redirected, not cancelled and not duplicated - no CANCEL_BALANCE, "
        "no fresh ORDER row"
    )
    assert live_rows[0].id == row.id
    assert live_rows[0].state == INQUIRY_PLACED  # untouched state; still a real placed PO
    assert live_rows[0].qty == Decimal("5")  # untouched quantity
    assert live_rows[0].po_ref == po.po_number  # untouched PO link
    assert live_rows[0].redirected_to_pool is True
    assert live_rows[0].stock_location == world.pool_wh.warehouse_code
    assert "Redirected" in (live_rows[0].note or "")
    assert world.own_wh.warehouse_code in (live_rows[0].note or "")  # names where it WAS


def test_apply_advance_with_pool_available_redirects_both_placed_rows_to_the_pool(api):
    """The SO397450 / SRT382-6-DIY shape, end-to-end, under the captain's 21 Aug ruling:
    an ADVANCE whose fresh proposal draws 432 from the pool at BRW while the line already
    has 432 on TWO real purchase orders (300 + 132). Confirming as proposed keeps the
    pool's Reserve 432 whole - no relabel onto Buy - and Apply redirects the placed row to
    replenish the pool: it is not cancelled, not duplicated, and no CANCEL_BALANCE is
    raised for the placed 432 the fresh Buy no longer needs.

    Since section 3.I the two purchase orders are two LINKS on ONE row rather than two
    split rows (AC-I6), so the redirect marks one row and the documents are read off its
    links. The arithmetic is unchanged: 432 placed, 432 redirected, nothing re-raised."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="432",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    # Covered today by a plain Buy - the same starting shape the trail-popover test above
    # uses, plus the real placed PO the live row also carried.
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="432", buy_reason="Nothing free elsewhere."),
    ]})
    placed_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po_a = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    po_b = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po_a, po_b])
    db.flush()
    po_line_a = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po_a.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("300"), qty_received=Decimal("0"), line_status="open",
    )
    po_line_b = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po_b.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("132"), qty_received=Decimal("0"), line_status="open",
    )
    db.add_all([po_line_a, po_line_b])
    db.commit()

    # The G2 cascade split - the real path two placed rows come from, never hand-set.
    ProjectOrderInquiryService(db).place_on_po_allocations(
        placed_row.id,
        [
            {"po_line_id": po_line_a.id, "qty": "300"},
            {"po_line_id": po_line_b.id, "qty": "132"},
        ],
        actor_user_id=world.actor,
    )
    db.commit()

    placed_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state == INQUIRY_PLACED)
        .all()
    )
    assert len(placed_rows) == 1, "one instruction per sales-order line (AC-I6)"
    assert placed_rows[0].qty == Decimal("432")
    assert len(ProjectOrderInquiryService(db)._links_of(placed_rows[0].id)) == 2

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ADV",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2026, 8, 25) - timedelta(days=14), old_qty="432", new_qty="432",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row_out = out["orders"][0]["rows"][0]
    assert row_out["suggested"] == "replan"  # advance, rule 7, unconditional

    proposal = row_out["proposal"]
    assert Decimal(proposal["qty_proposed_reserve"]) == Decimal("432")
    assert Decimal(proposal["qty_proposed_buy"]) == Decimal("0")
    assert Decimal(proposal["placed_redirect_qty"]) == Decimal("432")
    # The trail still reads "the pool took 432 at BRW", unedited - the pool take stands,
    # so there is nothing to relabel and nothing to narrate.
    pool_step = next(step for step in proposal["trail"] if step["kind"] == "pool")
    assert Decimal(pool_step["took"]) == Decimal("432")
    # Its note says which pools were opened (ladder v5's own hint) and nothing about a
    # placed quantity, because there was nothing to relabel.
    assert "already placed" not in (pool_step.get("note") or "")
    # sources agree with the aggregate - Fix 2's guard has nothing to warn about here.
    reserve_sources_total = sum(
        (Decimal(s["qty"]) for s in proposal["sources"] if s["kind"] == "reserve"),
        Decimal("0"),
    )
    assert reserve_sources_total == Decimal("432")

    put = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row_out['id']}", json={"decision": "confirm"},
    )
    assert put.status_code == 200, put.text
    composition = put.json()["composition"]
    assert Decimal(composition["buy_qty"]) == Decimal("0")
    reserve_total = sum((Decimal(c["qty"]) for c in composition["reserve"]), Decimal("0"))
    assert reserve_total == Decimal("432")

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["applied_orders"] == [order.autocount_doc_no]

    db.expire_all()
    live_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    # Two live rows: the redirected placed ORDER row carrying both links, plus the
    # informational ADVANCE row every advance/delay always raises (`_oi_demand_rows`) - a
    # date-change instruction, never a purchase (Fix 3's own subject). No CANCEL_BALANCE,
    # and no fresh ORDER row: `refresh_for_decision` sees a composed need of 0 and a
    # placed total of 0 (redirected), so it raises nothing further.
    assert len(live_rows) == 2
    assert [r for r in live_rows if r.verb == "CANCEL_BALANCE"] == []
    assert [r for r in live_rows if r.verb == IV_ORDER and r.state == INQUIRY_RAISED] == []

    order_rows = [r for r in live_rows if r.verb == IV_ORDER]
    assert len(order_rows) == 1
    redirected = order_rows[0]
    assert redirected.state == INQUIRY_PLACED
    assert redirected.redirected_to_pool is True
    assert redirected.stock_location == world.pool_wh.warehouse_code
    assert "Redirected" in (redirected.note or "")
    assert redirected.qty == Decimal("432")
    # BOTH purchase orders are still named, off the links rather than off a scalar that
    # could only ever hold one of them.
    links = ProjectOrderInquiryService(db)._links_of(redirected.id)
    assert {link.qty for link in links} == {Decimal("300.0000"), Decimal("132.0000")}
    assert {link.document for link in links} == {po_a.po_number, po_b.po_number}

    advance_row = next(r for r in live_rows if r.verb == "ADVANCE")
    assert advance_row.state == INQUIRY_RAISED
    assert advance_row.qty == Decimal("432")
    # Fix 3's own subject: the worklist's "Taken from PO"/"Remaining" for THIS row are
    # scoped to ORDER-verb siblings only, both now 0 (both redirected) - a figure that
    # would read as "fully handled" next to an unactioned date change; the frontend mutes
    # it with an honest per-verb label instead (`flowExclusionLabel`).
    flow = OrderInquiryWorklistService(db)._quantity_flow_by_so_line([advance_row])
    line_flow = flow.get(str(line.id), {})
    assert line_flow.get("taken", Decimal("0")) == Decimal("0")
    assert line_flow.get("remaining", Decimal("0")) == Decimal("0")


def test_build_batch_facts_read_buy_actioned_true_for_a_really_placed_row(api):
    """`_inquiry_rows_and_buy_actioned` must read `INQUIRY_PLACED` as actioned, not only
    `INQUIRY_ACTIONED` - proven through a row placed on a real PO, not a hand-set state."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20",
                            required_date=date(2027, 2, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="20", buy_reason="Nothing free elsewhere."),
    ]})
    placed_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    po, _po_line = _place_row_on_a_real_po(db, world, placed_row, qty_ordered="20")

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2027, 2, 1),
        new_date=date(2027, 2, 11), old_qty="20", new_qty="20",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["kind"] == "delayed"
    assert row["facts"]["buy_actioned"]["value"] is True
    assert row["facts"]["buy_actioned"]["po_number"] == po.po_number
    assert Decimal(row["facts"]["buy_actioned"]["qty"]) == Decimal("20")
    assert row["suggested"] == "keep"
    assert "already a placed purchase order" in row["why"]
    assert po.po_number in row["why"]


def test_a_wholly_bought_line_delayed_beyond_the_window_buys_for_the_pool(api):
    """The captain's ruling of 26 August 2026 (AC-P3-10), reviving the dead release path.

    `release` used to be gated on the held composition carrying a RESERVE, and the whole-
    line rule (AC-L5) had already made a reserve-and-Buy mix impossible - so a wholly
    bought line delayed most of a year suggested `keep` and purchasing was told nothing
    worth acting on. It releases now: the purchase is for the POOL, so the row moves
    there, and because nobody has put it on a document yet purchasing also gets a DELAY
    carrying the date it moved from.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=150)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="150",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="150", buy_reason="Nothing free elsewhere."),
    ]})

    order_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    assert order_row.stock_location == world.own_wh.warehouse_code

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=date(2027, 3, 10), old_qty="150", new_qty="150",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row = out["orders"][0]["rows"][0]
    assert row["held"]["reserve"] == [], "wholly bought, so there is no reserve to release"
    assert row["suggested"] == "release"
    assert "beyond the 60-day reserve window" in row["why"]

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == []

    from app.models.planning_change import PlanningChangeBatch as PlanningChangeBatchModel

    batch_model = db.query(PlanningChangeBatchModel).filter(
        PlanningChangeBatchModel.id == batch.id
    ).one()
    assert {"verb": "DELAY", "count": 1} in batch_model.result_json["inquiry_rows_changed"]
    assert not any(
        entry["verb"] == "RELEASE"
        for entry in batch_model.result_json["inquiry_rows_changed"]
    )

    db.expire_all()
    live = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    # The purchase is not lost: an ORDER row for the whole 150, now for the POOL rather
    # than for a line that has moved most of a year out, with a DELAY row beside it
    # naming the date it moved from.
    orders = [r for r in live if r.verb == IV_ORDER]
    assert [str(r.qty) for r in orders] == ["150.0000"]
    assert orders[0].stock_location == world.pool_wh.warehouse_code
    delays = [r for r in live if r.verb == "DELAY"]
    assert len(delays) == 1
    assert "2026-08-25" in (delays[0].note or "")
