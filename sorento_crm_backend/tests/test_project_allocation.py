"""P9 allocation over HTTP: ranked sources, per-line confirmation, cross-project claims.

Route level because the rules that matter here are refusals, and a refusal is only real if
it reaches the client: confirming a source with more than the location holds, pulling
another project's stock without asking, refusing a claim without saying why. Every one of
those is enforced in the service and asserted through the API, not in the UI.

The load-bearing rule is AC-H4's last sentence, "nothing moves on silence". A claim sits in
``requested`` until the holding project's CS answers, and while it does the line must NOT
read as sourced: no stock location, and the pending allocation grants no hold that would
make a THIRD project's screen show the stock as spoken for.

Cleanup is by rollback and every assertion is scoped to rows the test created: the shared
local database is a copy of production.
"""
from __future__ import annotations

import uuid
from datetime import date
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


def test_candidates_rank_brw_first_and_name_the_holding_project(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, brw, 80)
    _stock(db, world.product, mwh, 200)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    # Seri Heights already holds the whole MWH pile.
    other_order, other_line = _sales_order(db, world.other_project, product=world.product, qty="200")
    db.commit()
    _act_as(client, world.farah)
    confirmed = client.put(
        f"{BASE}/sales-order-lines/{other_line.id}/allocation",
        json={"sources": [{"source_type": "own", "warehouse_id": mwh.id, "qty": "200"}]},
    )
    assert confirmed.status_code == 200, confirmed.text
    _act_as(client, world.eling)

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


# ------------------------------------------------------------------------- confirm


def test_confirming_a_source_stamps_it_and_becomes_the_stock_location(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 500)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    response = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "135"}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["state"] == "confirmed"
    assert body["stock_location"] == BRW_CODE
    assert body["allocated_qty"] == "135"
    source = body["sources"][0]
    assert source["source_type"] == "brw"
    assert source["confirmed"] is True
    assert source["confirmed_by_name"] == f"{MARKER} Eling"

    db.expire_all()
    assert db.get(ProjectSalesOrderLine, line.id).stock_location == BRW_CODE


def test_a_split_reads_as_both_locations(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, brw, 80)
    _stock(db, world.product, mwh, 100)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    response = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={
            "sources": [
                {"source_type": "brw", "warehouse_id": brw.id, "qty": "80"},
                {"source_type": "own", "warehouse_id": mwh.id, "qty": "55"},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "confirmed"
    assert body["stock_location"] == f"{BRW_CODE} + {mwh.warehouse_code}"


def test_confirming_more_than_the_location_holds_is_refused(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 20)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    response = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "135"}]},
    )
    assert response.status_code == 409, response.text
    assert "20" in response.json()["message"]


def test_confirming_more_than_the_line_needs_is_refused(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 500)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    response = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "200"}]},
    )
    assert response.status_code == 422, response.text


def test_ordering_is_a_source_and_carries_no_location(api):
    client, world = api
    db = world.db
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    body = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "order", "qty": "135"}]},
    ).json()

    assert body["state"] == "confirmed"
    assert body["stock_location"] is None
    assert body["sources"][0]["warehouse_code"] is None


def test_a_partial_decision_reads_as_partial(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 80)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    body = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "80"}]},
    ).json()
    assert body["state"] == "partial"
    assert body["outstanding_qty"] == "55"


def test_an_override_replaces_the_previous_decision(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, brw, 500)
    _stock(db, world.product, mwh, 500)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "135"}]},
    )
    body = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "own", "warehouse_id": mwh.id, "qty": "135"}]},
    ).json()

    assert len(body["sources"]) == 1
    assert body["stock_location"] == mwh.warehouse_code


def test_clearing_the_decision_unallocates_the_line(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 500)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "135"}]},
    )
    cleared = client.delete(f"{BASE}/sales-order-lines/{line.id}/allocation")
    assert cleared.status_code == 204, cleared.text

    db.expire_all()
    assert db.get(ProjectSalesOrderLine, line.id).stock_location is None
    body = client.get(f"{BASE}/sales-orders/{line.project_sales_order_id}/allocations").json()
    assert body["data"][0]["state"] == "unallocated"


def test_another_salespersons_line_cannot_be_sourced(api):
    client, world = api
    db = world.db
    brw = _warehouse(db, BRW_CODE)
    _stock(db, world.product, brw, 500)
    _order, line = _sales_order(db, world.other_project, product=world.product, qty="135")
    db.commit()

    response = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={"sources": [{"source_type": "brw", "warehouse_id": brw.id, "qty": "135"}]},
    )
    assert response.status_code == 403, response.text


# -------------------------------------------------------------------------- claims


def _held_pile(world, client):
    """Seri Heights holds 200 at MWH; Eling's line needs 135 of the same product."""
    db = world.db
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, mwh, 200)
    _other_order, other_line = _sales_order(
        db, world.other_project, product=world.product, qty="200"
    )
    db.commit()
    _act_as(client, world.farah)
    assert (
        client.put(
            f"{BASE}/sales-order-lines/{other_line.id}/allocation",
            json={"sources": [{"source_type": "own", "warehouse_id": mwh.id, "qty": "200"}]},
        ).status_code
        == 200
    )
    _act_as(client, world.eling)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()
    return mwh, line


def test_a_cross_project_pull_raises_a_claim_and_moves_nothing(api):
    client, world = api
    mwh, line = _held_pile(world, client)

    raised = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={
            "warehouse_id": mwh.id,
            "to_project_id": world.other_project.id,
            "qty": "135",
        },
    )
    assert raised.status_code == 201, raised.text
    claim = raised.json()
    assert claim["state"] == "requested"
    assert claim["to_project_code"] == world.other_project.project_code
    assert claim["to_project_cs_name"] == f"{MARKER} Farah"
    assert claim["qty"] == "135"

    # Nothing moves on silence: the line is not sourced while the claim is open.
    line_row = client.get(
        f"{BASE}/sales-orders/{line.project_sales_order_id}/allocations"
    ).json()["data"][0]
    assert line_row["state"] == "pending_claim"
    assert line_row["stock_location"] is None
    assert line_row["allocated_qty"] == "0"
    assert line_row["sources"][0]["confirmed"] is False
    assert line_row["sources"][0]["claim_state"] == "requested"

    world.db.expire_all()
    assert world.db.get(ProjectSalesOrderLine, line.id).stock_location is None


def test_a_pending_claim_grants_no_hold_to_a_third_project(api):
    """An unanswered request must not make the stock look spoken for by the asker."""
    from app.services.project_service import register_project

    client, world = api
    db = world.db
    mwh, line = _held_pile(world, client)
    client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    )

    joey = _user(db, f"{MARKER} Joey")
    third = register_project(
        db,
        company_id=world.company_id,
        actor_user_id=joey,
        developer_party_id=None,
        title=f"{MARKER} Third Avenue",
    )
    _third_order, third_line = _sales_order(db, third, product=world.product, qty="10")
    db.commit()

    _act_as(client, joey)
    candidates = client.get(
        f"{BASE}/sales-order-lines/{third_line.id}/allocation-candidates"
    ).json()
    held = [c for c in candidates["candidates"] if c["warehouse_code"] == mwh.warehouse_code][0]
    # Only Seri Heights' confirmed 200 is held. Tuju's unanswered 135 is not on top of it.
    assert held["held_for_other_projects"] == "200"
    assert held["held_for_this_project"] == "0"
    assert [h["project_code"] for h in held["holders"]] == [
        world.other_project.project_code
    ]


def test_confirming_a_held_source_without_an_accepted_claim_is_refused(api):
    client, world = api
    mwh, line = _held_pile(world, client)

    response = client.put(
        f"{BASE}/sales-order-lines/{line.id}/allocation",
        json={
            "sources": [
                {
                    "source_type": "other_project",
                    "warehouse_id": mwh.id,
                    "source_project_id": world.other_project.id,
                    "qty": "135",
                }
            ]
        },
    )
    assert response.status_code == 409, response.text
    assert "claim" in response.json()["message"].lower()


def test_accepting_a_claim_sources_the_line(api):
    client, world = api
    mwh, line = _held_pile(world, client)
    claim = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    ).json()

    _act_as(client, world.farah)
    accepted = client.post(f"{BASE}/allocation-claims/{claim['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "accepted"
    assert accepted.json()["decided_by_name"] == f"{MARKER} Farah"

    _act_as(client, world.eling)
    line_row = client.get(
        f"{BASE}/sales-orders/{line.project_sales_order_id}/allocations"
    ).json()["data"][0]
    assert line_row["state"] == "confirmed"
    assert line_row["stock_location"] == mwh.warehouse_code
    assert line_row["sources"][0]["confirmed"] is True


def test_only_the_holding_projects_cs_may_answer_a_claim(api):
    client, world = api
    mwh, line = _held_pile(world, client)
    claim = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    ).json()

    # Still Eling: the asker cannot answer her own request.
    response = client.post(f"{BASE}/allocation-claims/{claim['id']}/accept")
    assert response.status_code == 403, response.text


def test_a_refusal_needs_a_reason(api):
    client, world = api
    mwh, line = _held_pile(world, client)
    claim = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    ).json()

    _act_as(client, world.farah)
    blank = client.post(
        f"{BASE}/allocation-claims/{claim['id']}/refuse", json={"reason": "   "}
    )
    assert blank.status_code == 422, blank.text

    refused = client.post(
        f"{BASE}/allocation-claims/{claim['id']}/refuse",
        json={"reason": "Committed to our own July hand-over."},
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["state"] == "refused"
    assert refused.json()["reason"] == "Committed to our own July hand-over."

    _act_as(client, world.eling)
    line_row = client.get(
        f"{BASE}/sales-orders/{line.project_sales_order_id}/allocations"
    ).json()["data"][0]
    assert line_row["state"] == "refused"
    assert line_row["stock_location"] is None
    assert line_row["sources"][0]["claim_reason"] == "Committed to our own July hand-over."


def test_a_claim_is_answered_once(api):
    client, world = api
    mwh, line = _held_pile(world, client)
    claim = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    ).json()

    _act_as(client, world.farah)
    assert client.post(f"{BASE}/allocation-claims/{claim['id']}/accept").status_code == 200
    again = client.post(
        f"{BASE}/allocation-claims/{claim['id']}/refuse", json={"reason": "Changed my mind"}
    )
    assert again.status_code == 409, again.text


def test_more_cannot_be_claimed_than_the_other_project_holds(api):
    """Seri Heights holds 50 of the 200 at MWH, so 135 cannot be asked of them."""
    client, world = api
    db = world.db
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, mwh, 200)
    _other_order, other_line = _sales_order(
        db, world.other_project, product=world.product, qty="50"
    )
    db.commit()
    _act_as(client, world.farah)
    assert (
        client.put(
            f"{BASE}/sales-order-lines/{other_line.id}/allocation",
            json={"sources": [{"source_type": "own", "warehouse_id": mwh.id, "qty": "50"}]},
        ).status_code
        == 200
    )
    _act_as(client, world.eling)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    response = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    )
    assert response.status_code == 409, response.text
    assert "50" in response.json()["message"]


def test_more_cannot_be_claimed_than_the_line_needs(api):
    client, world = api
    mwh, line = _held_pile(world, client)

    response = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "500"},
    )
    assert response.status_code == 422, response.text


def test_a_project_cannot_claim_from_itself(api):
    client, world = api
    db = world.db
    mwh = _warehouse(db, f"ZZT-MWH-{_uid()[:4]}")
    _stock(db, world.product, mwh, 200)
    _order, line = _sales_order(db, world.project, product=world.product, qty="135")
    db.commit()

    response = client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.project.id, "qty": "135"},
    )
    assert response.status_code == 422, response.text


def test_the_worklist_shows_claims_awaiting_this_users_projects(api):
    client, world = api
    mwh, line = _held_pile(world, client)
    client.post(
        f"{BASE}/sales-order-lines/{line.id}/allocation-claims",
        json={"warehouse_id": mwh.id, "to_project_id": world.other_project.id, "qty": "135"},
    )

    # Eling raised it, so it is hers OUTGOING and nothing is waiting on her.
    mine = client.get(f"{BASE}/allocation-claims?direction=incoming").json()
    assert mine["data"] == []
    outgoing = client.get(f"{BASE}/allocation-claims?direction=outgoing").json()
    assert [row["from_project_code"] for row in outgoing["data"]] == [
        world.project.project_code
    ]

    _act_as(client, world.farah)
    waiting = client.get(f"{BASE}/allocation-claims?direction=incoming").json()
    assert waiting["pagination"]["total"] == 1
    row = waiting["data"][0]
    assert row["from_project_code"] == world.project.project_code
    assert row["product_code"] == world.product.product_code
    assert row["warehouse_code"] == mwh.warehouse_code
    assert row["state"] == "requested"


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
