"""A manual SO edit propagates exactly like a book upload (captain, 20 Aug 2026 follow-up
to `documentation/plans/scm/PLAN-so-book-diff-replanning.md`): a qty/date change made by
hand on the sales-order detail screen raises the SAME `planning_change_batch` reaction an
uploaded book raises for the identical change - `SalesOrderService._propagate_planning
_change`, mirroring `outstanding_import_service.apply()`'s own best-effort call to
`planning_change_service.build_batch`.

Helper functions below (`_uid`, `_sorento`, `_user`, `_product`, `_warehouse`, `_core_so`,
`_core_line`, `_project_so`, `_project_line`, the `api` fixture) are copied from
`tests/test_planning_changes.py` rather than imported - that file is owned by a concurrent
slice and is not touched here. Postgres only (`tests/_pg_fixture.py`), PRINCIPLES: never
sqlite, every FK seeded here, never a borrowed `LIMIT 1` row.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.planning_change import (
    PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import SO_STATUS_PUBLISHED, ProjectSalesOrder, ProjectSalesOrderLine
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.user import User
from app.schemas.scm_orders import SalesOrderUpdate
from app.services import project_seed_service
from app.services.scm.sales_order_service import SalesOrderService
from tests._pg_fixture import blank_session, pg_session, unique_code
from tests.scm.conftest import as_user, requires_pg, seed_user

MARKER = "zzt-soedit"


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


def _project_so(db, project, *, status=SO_STATUS_PUBLISHED, so_id=None,
                 autocount_doc_no=None) -> ProjectSalesOrder:
    order = ProjectSalesOrder(
        id=_uid(), company_id=project.company_id, project_id=project.id,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}", area_group="TOWER", status=status,
        so_id=so_id, autocount_doc_no=autocount_doc_no,
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
    """A project-linked world, mirroring `tests/test_planning_changes.py::api` - the
    `build_batch` machinery this propagation calls (`ProjectSupplyService.active_decision`,
    `frozen_lines_of`, hot-selling evidence) needs a real project + product + warehouse
    chain seeded, not a bare pair of rows.
    """
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
    """One project-linked core line, ready for a propagation-raising edit."""
    db = world.db
    product = _product(db)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, product, world.own_wh, qty_ordered=qty_ordered, required_date=required_date,
    )
    order = _project_so(db, project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    _project_line(db, order, line_no=1, product=product, core_line=core_line)
    db.commit()
    return core_so, core_line, product


def _row_for(db, batch_id: str) -> PlanningChangeRow:
    return db.query(PlanningChangeRow).filter(PlanningChangeRow.batch_id == batch_id).one()


def _api_client(db, user_id: str):
    """A TestClient wired onto `db` and an authenticated `user_id`, mirroring
    `tests/test_planning_changes.py::_client` - copied rather than imported (that file is
    owned by a concurrent slice, see the module docstring). Only used by the route-level
    regression test below; every other test in this file talks to the service directly."""
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


# --------------------------------------------------------------------------- #
# qty edit
# --------------------------------------------------------------------------- #

def test_qty_up_raises_a_batch_with_source_kind_manual_edit(api):
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(world, project, qty_ordered=72)

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 90,
        }]),
        user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None
    assert envelope["order_count"] == 1
    assert envelope["line_count"] == 1

    batch = db.get(PlanningChangeBatch, envelope["id"])
    assert batch is not None
    assert batch.source_kind == PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT
    row = _row_for(db, envelope["id"])
    assert row.kind == "qty_up"


def test_manual_edit_batch_is_listed_by_the_planning_changes_route(api):
    """Regression for the live 500 fixed 20 Aug 2026: `PlanningChangeSourceKind` on the
    schema was pinned to `'so_book_upload'` alone, so the first `so_manual_edit` batch
    failed response validation and `GET /planning-changes` 500'd (read by the caller as an
    empty list). Drive the real route, not just the service, so a future narrowing of the
    literal is caught the same way this one was missed - at the wire, not the model."""
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(world, project, qty_ordered=72)

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 90,
        }]),
        user_id=world.actor,
    )
    db.commit()
    envelope = result["planning_change_batch"]
    assert envelope is not None
    batch_id = envelope["id"]

    client, originals = _api_client(db, world.actor)
    try:
        response = client.get("/api/v1/project-sales/planning-changes")
    finally:
        _restore_api_client(originals)

    assert response.status_code == 200, response.text
    body = response.json()
    batches_by_id = {b["id"]: b for b in body["data"]}
    assert batch_id in batches_by_id
    assert batches_by_id[batch_id]["source"]["kind"] == PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT


def test_qty_down_raises_a_batch_kind_qty_down(api):
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(world, project, qty_ordered=72)

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 50,
        }]),
        user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None
    row = _row_for(db, envelope["id"])
    assert row.kind == "qty_down"
    assert row.applied_state == "pending"


# --------------------------------------------------------------------------- #
# date move
# --------------------------------------------------------------------------- #

def test_date_moved_later_raises_a_delayed_row(api):
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(
        world, project, qty_ordered=72, required_date=date(2026, 8, 20),
    )

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 72,
            "required_date": "2026-09-03",
        }]),
        user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None
    row = _row_for(db, envelope["id"])
    assert row.kind == "delayed"
    assert row.days_moved == 14


def test_date_moved_earlier_raises_an_advanced_row(api):
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(
        world, project, qty_ordered=72, required_date=date(2026, 8, 20),
    )

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 72,
            "required_date": "2026-08-01",
        }]),
        user_id=world.actor,
    )

    envelope = result["planning_change_batch"]
    assert envelope is not None
    row = _row_for(db, envelope["id"])
    assert row.kind == "advanced"


# --------------------------------------------------------------------------- #
# no material change / non-project edit -> no batch
# --------------------------------------------------------------------------- #

def test_no_material_change_raises_no_batch(api):
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(
        world, project, qty_ordered=72, required_date=date(2026, 8, 20),
    )
    before_count = db.query(PlanningChangeBatch).count()

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 72,
        }]),
        user_id=world.actor,
    )

    assert result["planning_change_batch"] is None
    assert db.query(PlanningChangeBatch).count() == before_count


def test_a_sub_epsilon_qty_wobble_raises_no_batch(api):
    """0.0001 rounding drift is noise, not an edit - the same `_QTY_EPSILON` the diff
    itself is built on (`outstanding_diff._QTY_EPSILON`)."""
    world, project = api
    db = world.db
    core_so, core_line, product = _linked_line(world, project, qty_ordered=72)

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 72.0001,
        }]),
        user_id=world.actor,
    )

    assert result["planning_change_batch"] is None


def test_non_project_so_edit_raises_no_batch_but_still_saves(api):
    world, _project = api
    db = world.db
    product = _product(db)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, product, world.own_wh, qty_ordered=72)
    db.commit()
    before_count = db.query(PlanningChangeBatch).count()

    result = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[{
            "id": core_line.id, "sku": product.product_code, "qty_ordered": 90,
        }]),
        user_id=world.actor,
    )

    assert result["planning_change_batch"] is None
    assert db.query(PlanningChangeBatch).count() == before_count
    assert result["lines"][0]["qty_ordered"] == 90
    db.expire_all()
    row = db.get(SalesOrderLine, core_line.id)
    assert float(row.qty_ordered) == 90


# --------------------------------------------------------------------------- #
# UoM select route
# --------------------------------------------------------------------------- #

def _code(stem: str) -> str:
    # `units_of_measure.uom_code` is `varchar(20)` on the live DB - narrower than the
    # model's declared `String(50)` (a pre-existing schema/model drift, not this slice's
    # to fix). Truncated so the test seeds cleanly either way.
    return f"ZZ-{stem}-{uuid.uuid4().hex[:6]}".upper()[:20]


@requires_pg
def test_uom_select_returns_only_active_uoms(scm_app):
    from fastapi.testclient import TestClient

    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, "purchasing")
    as_user(app, gcu, gcuak, uid)

    active = UnitOfMeasure(id=_uid(), uom_code=_code("EA"), uom_name="Each", is_active=True)
    inactive = UnitOfMeasure(
        id=_uid(), uom_code=_code("RETIRED"), uom_name="Retired unit", is_active=False,
    )
    db.add_all([active, inactive])
    db.flush()

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders/uoms")

    assert res.status_code == 200, res.text
    codes = {row["uom_code"] for row in res.json()}
    assert active.uom_code in codes
    assert inactive.uom_code not in codes


@requires_pg
def test_uom_select_denied_without_dashboard_view(scm_app):
    from fastapi.testclient import TestClient

    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, None)
    as_user(app, gcu, gcuak, uid)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders/uoms")

    assert res.status_code == 403


# --------------------------------------------------------------------------- #
# UoM write: explicit null still clears the override (existing behaviour kept)
# --------------------------------------------------------------------------- #

def test_explicit_null_uom_still_clears_the_override():
    with pg_session() as db:
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code(MARKER),
            category_name=f"{MARKER} cat",
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u",
        )
        db.add_all([cat, uom])
        db.flush()
        product = Product(
            id=str(uuid.uuid4()), product_code=unique_code("SKU"), product_name=f"{MARKER} p",
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
        )
        customer = Customer(id=str(uuid.uuid4()), customer_code=unique_code("C"),
                            customer_name=f"{MARKER} Acme")
        db.add_all([product, customer])
        db.flush()
        so = SalesOrder(id=str(uuid.uuid4()), so_number=unique_code(MARKER), status="open",
                        customer_id=customer.id)
        db.add(so)
        db.flush()
        line = SalesOrderLine(
            id=str(uuid.uuid4()), sales_order_id=so.id, product_id=product.id,
            qty_ordered=10, qty_delivered=0, line_status="open", uom="BOX",
        )
        db.add(line)
        db.flush()

        SalesOrderService(db).update(
            so.id,
            SalesOrderUpdate(lines=[{
                "id": line.id, "sku": product.product_code, "qty_ordered": 10, "uom": None,
            }]),
            user_id=None,
        )

        db.expire_all()
        row = db.get(SalesOrderLine, line.id)
        assert row.uom is None


# --------------------------------------------------------------------------- #
# PlanningChangeSourceKind literal must cover every model source constant - the exact
# defect fixed 20 Aug 2026 (see the route test above). The model's own docstring calls a
# new source "a new constant, not a migration"; this test makes the schema literal part
# of that contract, so adding a constant here without widening the Literal fails loud in
# CI instead of 500ing the listing route in production.
# --------------------------------------------------------------------------- #

def test_schema_source_kind_literal_covers_every_model_source_constant():
    import typing

    from app import models
    from app.schemas.planning_change import PlanningChangeSourceKind

    model_constants = {
        value for name, value in vars(models.planning_change).items()
        if name.startswith("PLANNING_CHANGE_SOURCE_") and isinstance(value, str)
    }
    assert model_constants, "expected at least one PLANNING_CHANGE_SOURCE_* constant"
    schema_literal_values = set(typing.get_args(PlanningChangeSourceKind))
    assert model_constants <= schema_literal_values, (
        f"model source constants {model_constants - schema_literal_values} are missing "
        "from PlanningChangeSourceKind - a batch with that source_kind will 500 on "
        "response validation the moment it is listed"
    )
