"""P9 allocation over HTTP, as Stage 1C leaves it: the READS.

Per-line confirmation is gone. `PLAN-scm-front-planning.md` 3.1 replaced it with one
atomic Project SO confirmation, so `PUT`/`DELETE .../allocation` and the claim
raise/accept/refuse routes no longer exist and the tests that pinned them went with the
behaviour, in the same commit (STAGE0 note section 5). What they proved is proved again
against the new contract in `tests/test_so_supply_confirmation.py`: the balance invariant,
the recheck, the refusals, and a cross-project Borrow written straight to `accepted` by
the confirming CS with no donor left to answer (AC-B10).

What survives is what Stage 1C still reads:

* the ranked candidates, which are the Borrow-candidate source the supply sheet offers;
* the allocation list for one order, which now shows the components of its active
  decision;
* the claims worklist, which is history plus the accepted claims confirmation writes.

Holds and claims are therefore SEEDED here rather than created through a write route, and
that is the honest shape now: the only writer is the atomic confirmation, and it has its
own tests.

Cleanup is by rollback and every assertion is scoped to rows the test created: the shared
local database is a copy of production.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import ProjectSalesOrder, ProjectSalesOrderLine
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-alloc"
BASE = "/api/v1/project-sales"
BRW_CODE = "BRW-BB"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
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
        product_name=f"{MARKER} Grating",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("392.85"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str, *, active: bool = True) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, location="ZZT", is_active=active
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, on_hand: int, reserved: int = 0) -> None:
    db.add(
        Stock(
            id=_uid(),
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity_on_hand=on_hand,
            quantity_reserved=reserved,
        )
    )
    db.flush()


def _sales_order(db, project, *, product: Product, qty: str = "135"):
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        provisional_ref=f"ZZT-SO-{_uid()[:8]}",
        area_group="TOWER",
        status="draft",
    )
    db.add(order)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_uid(),
        company_id=project.company_id,
        project_sales_order_id=order.id,
        line_no=1,
        product_id=product.id,
        description=f"{MARKER} floor grating",
        qty=Decimal(qty),
        uom="SET",
        unit_price=Decimal("392.85"),
        amount=Decimal(qty) * Decimal("392.85"),
        delivery_date=date(2026, 7, 1),
    )
    db.add(line)
    db.flush()
    return order, line


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
    # Deliberately WITHOUT the manage grant: ownership is what decides who may answer a
    # claim, and a blanket manager grant would hide that.
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.projects.view",
        "projects.projects.create",
        "projects.projects.edit",
    ]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


class _World:
    """The two projects, their CS, the product and the locations, in one handle."""

    def __init__(self, db, company_id, eling, farah, project, other_project, product):
        self.db = db
        self.company_id = company_id
        self.eling = eling
        self.farah = farah
        self.project = project
        self.other_project = other_project
        self.product = product


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        eling = _user(db, f"{MARKER} Eling")
        farah = _user(db, f"{MARKER} Farah")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=eling,
            developer_party_id=None,
            title=f"{MARKER} Tuju Residences",
        )
        other_project = register_project(
            db,
            company_id=company_id,
            actor_user_id=farah,
            developer_party_id=None,
            title=f"{MARKER} Seri Heights",
        )
        product = _product(db)
        db.commit()
        client, originals = _client(db, eling)
        world = _World(db, company_id, eling, farah, project, other_project, product)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, world
        finally:
            _restore(originals)


def _act_as(client, user_id: str) -> None:
    """Swap the current principal without rebuilding the app overrides."""
    from app.database import get_db  # noqa: F401  (kept for symmetry with _client)
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)


# --------------------------------------------------------------------- candidates


def _hold(db, line, warehouse, qty: str, *, actor: str) -> None:
    """A confirmed component on somebody's line: what makes a pile "held".

    Written directly because the only writer is now the atomic confirmation
    (`project_supply_service`), and dragging a whole Project SO confirmation into a
    candidate-ranking test would test the wrong thing.
    """
    from app.models.project_so import SOLineAllocation

    db.add(
        SOLineAllocation(
            id=_uid(),
            company_id=line.company_id,
            so_line_id=line.id,
            source_type="own",
            warehouse_id=warehouse.id,
            qty=Decimal(qty),
            confirmed_by=actor,
            confirmed_at=datetime.utcnow(),
        )
    )
    db.flush()


def test_candidates_rank_brw_first_and_name_the_holding_project(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, brw, 80)
    _stock(db, world.product, mwh, 200)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")

    # Seri Heights already holds the whole MWH pile.
    _other_order, other_line = _sales_order(
        db, world.other_project, product=world.product, qty="200"
    )
    _hold(db, other_line, mwh, "200", actor=world.farah)
    db.commit()

    response = client.get(f"{BASE}/sales-order-lines/{line.id}/allocation-candidates")
    assert response.status_code == 200, response.text
    body = response.json()

    assert [c["source_type"] for c in body["candidates"]] == ["brw", "other_project", "order"]
    brw_candidate = body["candidates"][0]
    assert brw_candidate["warehouse_code"] == BRW_CODE
    assert brw_candidate["on_hand"] == "80"
    assert brw_candidate["available"] == "80"

    held = body["candidates"][1]
    assert held["held_for_other_projects"] == "200"
    assert held["available"] == "0"
    assert held["requires_claim"] is True
    assert held["holders"][0]["project_code"] == world.other_project.project_code
    assert held["holders"][0]["cs_name"] == f"{MARKER} Farah"

    assert body["covered"] is False
    assert body["shortfall"] == "55"
    assert body["plan"] == [{"warehouse_id": brw.id, "warehouse_code": BRW_CODE, "qty": "80"}]


def test_inactive_locations_are_not_offered(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    dead = _warehouse(db, f"ZZT-DFCT-{_uid()[:4]}", active=False)
    _stock(db, world.product, brw, 10)
    _stock(db, world.product, dead, 9999)
    _order, line = _sales_order(db, world.project, product=world.product, qty="10")
    db.commit()

    body = client.get(f"{BASE}/sales-order-lines/{line.id}/allocation-candidates").json()
    assert [c["warehouse_code"] for c in body["candidates"]] == [BRW_CODE, None]


# ----------------------------------------------------------------- the write routes


def test_the_per_line_allocation_write_routes_are_gone(api):
    """Stage 1C: there is no per-line confirmation and no durable partial state (AC-C01).

    Asserted rather than assumed, because a route that quietly stayed mounted would let a
    caller write a component outside the atomic transaction - which is exactly the
    double-promise the whole contract is built to prevent.
    """
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 500)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    confirm = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "135"}]},
    )
    assert confirm.status_code in (404, 405), confirm.text
    assert client.delete(
        f"{BASE}/sales-order-lines/{line.id}/allocation"
    ).status_code in (404, 405)
    assert client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": brw.id, "to_project_id": world.other_project.id, "qty": "1"},
    ).status_code in (404, 405)


# ------------------------------------------------------------------- the worklists


def test_the_worklist_shows_claims_by_direction(api):
    """The claims list stays as the audit read (AC-B10: they are written accepted now)."""
    from app.models.project_so import CLAIM_ACCEPTED, AllocationClaim

    client, world = api
    db = world.db
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, mwh, 200)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.add(
        AllocationClaim(
            id=_uid(),
            company_id=world.project.company_id,
            from_project_id=world.project.id,
            to_project_id=world.other_project.id,
            so_line_id=line.id,
            product_id=world.product.id,
            warehouse_id=mwh.id,
            qty=Decimal("135"),
            state=CLAIM_ACCEPTED,
            reason="Seri Heights has surplus this month.",
            requested_by=world.eling,
            decided_by=world.eling,
            decided_at=datetime.utcnow(),
        )
    )
    db.commit()

    incoming = client.get(f"{BASE}/allocation-claims?direction=incoming").json()
    assert incoming["data"] == [], "nothing waits on the borrowing project"

    outgoing = client.get(f"{BASE}/allocation-claims?direction=outgoing").json()
    assert [row["from_project_code"] for row in outgoing["data"]] == [
        world.project.project_code
    ]
    row = outgoing["data"][0]
    assert row["state"] == CLAIM_ACCEPTED
    assert row["product_code"] == world.product.product_code
    assert row["warehouse_code"] == mwh.warehouse_code
    assert row["decided_by_name"] == f"{MARKER} Eling"
    assert row["can_answer"] is False, "a claim is not answered any more; it is confirmed"


def test_the_order_allocation_list_covers_every_line(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 500)
    order, line = _sales_order(db, world.project, product=world.product, qty="135")
    second = ProjectSalesOrderLine(
        id=_uid(),
        company_id=world.project.company_id,
        project_sales_order_id=order.id,
        line_no=2,
        product_id=world.product.id,
        description=f"{MARKER} companion",
        qty=Decimal("135"),
        uom="SET",
        unit_price=Decimal("0"),
        amount=Decimal("0"),
    )
    db.add(second)
    db.commit()

    body = client.get(f"{BASE}/sales-orders/{order.id}/allocations").json()
    assert body["pagination"]["total"] == 2
    assert [row["line_no"] for row in body["data"]] == [1, 2]
    assert {row["state"] for row in body["data"]} == {"unallocated"}
    assert body["data"][0]["product_code"] == world.product.product_code
