"""SO-book diff replanning (`documentation/plans/scm/PLAN-so-book-diff-replanning.md`).

AC-R12 pins one test per row of section 0's rule table against `suggest()` (pure). The rest
exercise `build_batch` / `apply` against a real Postgres chain (`_pg_fixture.blank_session`,
PRINCIPLES: never sqlite, every FK seeded here) and the four HTTP routes.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_ACTIONED,
    IV_ORDER,
    SO_STATUS_PUBLISHED,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User
from app.services import planning_change_service, project_seed_service
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
    _stock(db, world.product, world.own_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, status=SO_STATUS_PUBLISHED,
                         autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}]),
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
    assert row_model.result_json["released"]["location"] == world.own_wh.warehouse_code


def test_apply_release_moves_the_lines_order_row_to_the_pool_and_raises_a_release_row(api):
    """Captain, 19 August 2026 (correcting the first cut of AC-R08): a release gives up
    the project's claim ENTIRELY, not just the reserve - the Buy this line held is no
    longer a purchase for this line, so its existing (non-actioned) OI row moves to the
    line's pool location with a note, and a RELEASE change row makes that visible in the
    worklist the way a DELAY row does."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="150",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "2"}],
                      buy_qty="148", buy_reason="Nothing free elsewhere."),
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
    assert row["suggested"] == "release"
    assert row["why"].endswith("- back on the board.")

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == []

    from app.models.planning_change import PlanningChangeBatch as PlanningChangeBatchModel

    batch_model = db.query(PlanningChangeBatchModel).filter(
        PlanningChangeBatchModel.id == batch.id
    ).one()
    assert {"verb": "RELEASE", "count": 1} in batch_model.result_json["inquiry_rows_changed"]

    db.refresh(order_row)
    assert order_row.stock_location == world.pool_wh.warehouse_code
    assert order_row.verb == IV_ORDER  # the purchase itself is untouched, only its location
    assert "Released from" in (order_row.note or "")
    assert f"buy for {world.pool_wh.warehouse_code}" in (order_row.note or "")

    release_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == "RELEASE")
        .one()
    )
    assert release_row.qty == Decimal("148")
    assert release_row.stock_location == world.pool_wh.warehouse_code
    assert "Released from" in (release_row.note or "")


def test_apply_qty_down_reduces_buy_and_raises_cancel_balance(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="66",
                            required_date=date(2027, 1, 15))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "50"}],
                      buy_qty="16", buy_reason="Nothing free elsewhere."),
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
    assert buy == []  # 16 dropped off the Buy first, for the whole 16-unit reduction

    cancel_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == "CANCEL_BALANCE")
        .all()
    )
    assert len(cancel_rows) == 1
    assert cancel_rows[0].qty == Decimal("16")


def test_apply_closed_retires_open_row_and_notes_actioned_row(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12",
                            required_date=date(2027, 1, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "4"}],
                      buy_qty="8", buy_reason="Timely stock short."),
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
    _stock(db, world.product, world.own_wh, on_hand=200)

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
        _line_payload(line_a.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}]),
    ]})
    _confirm(client, order_b.id, {"lines": [
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "30"}]),
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
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "30"}],
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
    _stock(db, world.product, world.own_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}]),
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
    _stock(db, world.product, world.own_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}]),
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
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}],
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
    _stock(db, world.product, world.own_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2026, 8, 25))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}]),
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
    _stock(db, world.product, world.own_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 8, 20))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "72"}]),
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
    _stock(world.db, world.product, world.own_wh, on_hand=100)
    batch, order, line, row = _no_decision_replan_row(client, world)

    response = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row['id']}",
        json={
            "decision": "amend",
            "composition": _line_payload(
                line.id,
                reserve=[{"warehouse_id": world.own_wh.id, "qty": "50"}],
                buy_qty="22",
                amend_reason="Own location has stock the proposal did not use.",
            ),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["composition"]["reserve"] == [
        {"warehouse_id": world.own_wh.id, "qty": "50"}
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
    assert reserve and Decimal(reserve[0]["qty"]) == Decimal("50")


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
