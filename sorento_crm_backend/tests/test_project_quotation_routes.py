"""S3 quotation ROUTES (UAC Group E).

Route-level because the wiring is its own seam -- S2c proved that with a serializer
keyword mismatch that every service test passed. The cases here are the ones where the
HTTP layer carries a decision of its own: the frozen-version refusal reaching the client
as a 422, alert counts appearing on the list, and the config surface being reachable at
all (a shadowed /config/series would 404 while looking like empty data).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-quote-route"
BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add(row)
    db.flush()
    return row.id


def _category(db, name: str, parent_id=None) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
        parent_category_id=parent_id,
    )
    db.add(row)
    db.flush()
    return row


def _product(db, category_id: str, uom_id: str, list_price: str) -> Product:
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Basin",
        description="Wall-hung basin",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
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

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    # See tests/test_project_lead_routes.py: the router-level resolver would otherwise
    # re-stamp the scope from a request that carries no active company.
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.projects.view",
        "projects.projects.create",
        "projects.projects.edit",
        "projects.projects.delete",
        "projects.projects.manage",
        "projects.types.view",
        "projects.types.edit",
    ]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Ali")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=user_id,
            developer_party_id=None,
            title=f"{MARKER} Tower",
        )
        db.commit()
        client, originals = _client(db, user_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, user_id, project
        finally:
            _restore(originals)


def _quotation(client, project_id: str, **body) -> dict:
    payload = {"scope_label": "House Units", **body}
    response = client.post(f"{BASE}/projects/{project_id}/quotations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_creating_a_quotation_returns_it_with_version_one_already_open(api):
    client, _db, _company_id, _user_id, project = api

    quotation = _quotation(client, project.id)

    assert quotation["current_version_no"] == 1
    assert quotation["version_count"] == 1
    assert quotation["outcome"] == "open"
    assert quotation["line_count"] == 0


def test_lines_are_added_to_a_version_and_roll_up_into_the_list(api):
    client, db, company_id, _user_id, project = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    created = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={
            "product_id": product.id,
            "unit_price": "900.00",
            "quantity": "10",
            "unit_type": "house_unit",
        },
    )
    assert created.status_code == 201, created.text
    line = created.json()
    assert line["line_total"] == "9000.00"
    # Snapshotted, so the response can print a quotation without joining the catalogue.
    assert line["product_code"] == product.product_code
    assert line["list_price"] == "1000.00"

    listed = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"]
    assert listed[0]["line_count"] == 1
    assert listed[0]["current_total"] == "9000.00"


def test_editing_a_line_saves_in_place_without_creating_a_version(api):
    client, db, company_id, _user_id, project = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    line = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": "900.00", "quantity": "10"},
    ).json()

    updated = client.put(
        f"{BASE}/quotation-versions/{version_id}/lines/{line['id']}",
        json={"unit_price": "880.00"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["line_total"] == "8800.00"

    versions = client.get(f"{BASE}/quotations/{quotation['id']}/versions").json()["data"]
    assert [v["version_no"] for v in versions] == [1]


def test_revise_freezes_the_old_version_and_the_client_can_see_which_is_current(api):
    client, db, company_id, _user_id, project = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    quotation = _quotation(client, project.id)
    first_version = quotation["current_version_id"]
    client.post(
        f"{BASE}/quotation-versions/{first_version}/lines",
        json={"product_id": product.id, "unit_price": "900.00", "quantity": "10"},
    )

    revised = client.post(f"{BASE}/quotations/{quotation['id']}/revise")
    assert revised.status_code == 201, revised.text
    assert revised.json()["version_no"] == 2
    assert revised.json()["is_current"] is True

    versions = client.get(f"{BASE}/quotations/{quotation['id']}/versions").json()["data"]
    assert [(v["version_no"], v["is_current"]) for v in versions] == [(2, True), (1, False)]
    assert versions[1]["frozen_at"] is not None

    # Lines carried across, so a revision starts from the last one rather than blank.
    carried = client.get(
        f"{BASE}/quotation-versions/{revised.json()['id']}/lines"
    ).json()["data"]
    assert len(carried) == 1


def test_editing_a_frozen_version_is_refused_with_a_422_the_user_can_act_on(api):
    client, db, company_id, _user_id, project = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    quotation = _quotation(client, project.id)
    frozen_version = quotation["current_version_id"]
    line = client.post(
        f"{BASE}/quotation-versions/{frozen_version}/lines",
        json={"product_id": product.id, "unit_price": "900.00", "quantity": "1"},
    ).json()
    client.post(f"{BASE}/quotations/{quotation['id']}/revise")

    refused = client.put(
        f"{BASE}/quotation-versions/{frozen_version}/lines/{line['id']}",
        json={"unit_price": "800.00"},
    )
    assert refused.status_code == 422, refused.text
    assert "superseded" in refused.json()["message"]

    deleting = client.delete(
        f"{BASE}/quotation-versions/{frozen_version}/lines/{line['id']}"
    )
    assert deleting.status_code == 422


def test_the_alert_counts_reach_the_client_from_the_current_version_only(api):
    client, db, company_id, _user_id, project = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    floor = client.post(
        f"{BASE}/config/price-floors",
        json={"mode": "percent", "value": "90", "category_id": category.id},
    )
    assert floor.status_code == 201, floor.text
    db.commit()

    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    breaching = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": "800.00", "quantity": "1"},
    ).json()
    assert breaching["is_below_floor"] is True
    assert breaching["floor_value_applied"] == "900.00"
    assert breaching["floor_level_applied"] == "category"

    listed = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"]
    assert listed[0]["below_floor_count"] == 1

    # Revise, then fix the price. The old breach is history and must not keep counting.
    revised = client.post(f"{BASE}/quotations/{quotation['id']}/revise").json()
    carried = client.get(
        f"{BASE}/quotation-versions/{revised['id']}/lines"
    ).json()["data"][0]
    client.put(
        f"{BASE}/quotation-versions/{revised['id']}/lines/{carried['id']}",
        json={"unit_price": "950.00"},
    )

    listed = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"]
    assert listed[0]["below_floor_count"] == 0


def test_an_off_catalog_line_needs_a_description_and_is_flagged_non_standard(api):
    client, _db, _company_id, _user_id, project = api

    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    refused = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"unit_price": "4000.00", "quantity": "1"},
    )
    assert refused.status_code == 422, refused.text

    created = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={
            "description_snapshot": "Bespoke stone counter",
            "unit_price": "4000.00",
            "quantity": "1",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_non_standard"] is True


def test_marking_a_quotation_lost_requires_a_configured_reason(api):
    client, _db, _company_id, _user_id, project = api

    reasons = client.get(f"{BASE}/config/loss-reasons")
    assert reasons.status_code == 200, reasons.text
    assert "price" in {row["value"] for row in reasons.json()}

    quotation = _quotation(client, project.id)

    refused = client.post(
        f"{BASE}/quotations/{quotation['id']}/outcome",
        json={"outcome": "lost", "loss_reason": "they hated us"},
    )
    assert refused.status_code == 422, refused.text

    accepted = client.post(
        f"{BASE}/quotations/{quotation['id']}/outcome",
        json={"outcome": "lost", "loss_reason": "price"},
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["outcome"] == "lost"
    assert body["loss_reason_label"] == "Price"


def test_winning_one_scope_makes_the_project_won_without_moving_its_status(api):
    """AC-E10 + AC-E10a through HTTP."""
    client, db, _company_id, _user_id, project = api
    status_before = project.status_id

    house = _quotation(client, project.id)
    common = _quotation(client, project.id, scope_label="Common Area")

    client.post(
        f"{BASE}/quotations/{common['id']}/outcome",
        json={"outcome": "lost", "loss_reason": "price"},
    )
    detail = client.get(f"{BASE}/projects/{project.id}").json()
    assert detail["outcome"] == "open"

    client.post(f"{BASE}/quotations/{house['id']}/outcome", json={"outcome": "won"})
    detail = client.get(f"{BASE}/projects/{project.id}").json()
    assert detail["outcome"] == "won"
    assert detail["status_id"] == status_before


def test_the_series_config_surface_is_reachable_and_reports_its_coverage(api):
    client, db, _company_id, _user_id, _project = api
    top = _category(db, "Sanitary Ware")
    _category(db, "Basins", parent_id=top.id)
    db.commit()

    created = client.post(
        f"{BASE}/config/series",
        json={"name": f"{MARKER} Premium", "category_ids": [top.id]},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["category_ids"] == [top.id]
    # Nominated one, covers two: the parent plus its descendant (AC-E5).
    assert body["covered_category_count"] == 2

    listed = client.get(f"{BASE}/config/series").json()["data"]
    assert [row["id"] for row in listed] == [body["id"]]


def test_a_series_in_use_cannot_be_deleted(api):
    client, db, _company_id, _user_id, project = api
    category = _category(db, "Basins")
    db.commit()

    series = client.post(
        f"{BASE}/config/series",
        json={"name": f"{MARKER} In Use", "category_ids": [category.id]},
    ).json()
    _quotation(client, project.id, series_id=series["id"])

    refused = client.delete(f"{BASE}/config/series/{series['id']}")
    assert refused.status_code == 409, refused.text


def test_the_floor_config_surface_upserts_per_level_rather_than_stacking(api):
    client, db, _company_id, _user_id, _project = api
    category = _category(db, "Basins")
    db.commit()

    first = client.post(
        f"{BASE}/config/price-floors",
        json={"mode": "percent", "value": "80", "category_id": category.id},
    ).json()
    second = client.post(
        f"{BASE}/config/price-floors",
        json={"mode": "percent", "value": "85", "category_id": category.id},
    ).json()

    assert first["id"] == second["id"]
    assert second["value"] == "85.00"
    assert second["level"] == "category"

    listed = client.get(f"{BASE}/config/price-floors").json()["data"]
    assert len([row for row in listed if row["category_id"] == category.id]) == 1

    refused = client.post(
        f"{BASE}/config/price-floors", json={"mode": "percent", "value": "950"}
    )
    assert refused.status_code == 422, refused.text
