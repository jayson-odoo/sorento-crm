"""S4 sample and customer-PO ROUTES (UAC Group F).

Route-level because the HTTP layer carries decisions of its own here: the superseded
refusal reaching the client as a 409 with a usable message, the auto-status-edge result
being reported on the create response rather than left for the client to guess, and the
mismatch flags surviving serialisation.
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

MARKER = "zzt-s4-route"
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


def _product(db, list_price: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
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


def _quoted_version(client, db, project_id: str, *, unit_price="900.00", quantity=10):
    """A quotation with one priced line, through the HTTP surface."""
    response = client.post(
        f"{BASE}/projects/{project_id}/quotations", json={"scope_label": "House Units"}
    )
    assert response.status_code == 201, response.text
    quotation = response.json()
    version_id = quotation["current_version_id"]
    product = _product(db, "1200.00")
    line = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={
            "product_id": product.id,
            "unit_price": unit_price,
            "quantity": str(quantity),
        },
    )
    assert line.status_code == 201, line.text
    return quotation, version_id, product


# ----------------------------------------------------------------------- samples


def test_a_sample_is_created_and_listed_with_a_readable_scope(api):
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)

    created = client.post(
        f"{BASE}/projects/{project.id}/samples",
        json={"quotation_version_id": version_id, "submitted_on": "2026-07-20"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["scope_label"] == "House Units"
    assert created.json()["version_no"] == 1
    assert created.json()["is_version_current"] is True

    listed = client.get(f"{BASE}/projects/{project.id}/samples")
    assert listed.status_code == 200
    assert listed.json()["pagination"]["total"] == 1


def test_a_sample_against_a_superseded_version_is_409_with_the_version_to_use(api):
    """AC-F2 through HTTP. The message has to be usable: "409" alone sends the user back
    to press the same button."""
    client, db, _company_id, _user_id, project = api
    quotation, version_id, _product = _quoted_version(client, db, project.id)
    revise = client.post(f"{BASE}/quotations/{quotation['id']}/revise")
    assert revise.status_code == 201, revise.text

    refused = client.post(
        f"{BASE}/projects/{project.id}/samples",
        json={"quotation_version_id": version_id},
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert "v2" in (body.get("detail") or body.get("message") or "")


def test_editing_a_sample_on_a_superseded_version_still_works(api):
    """The developer's feedback arrives after the revise, and it is the whole point."""
    client, db, _company_id, _user_id, project = api
    quotation, version_id, _product = _quoted_version(client, db, project.id)
    sample = client.post(
        f"{BASE}/projects/{project.id}/samples",
        json={"quotation_version_id": version_id},
    ).json()
    client.post(f"{BASE}/quotations/{quotation['id']}/revise")

    updated = client.put(
        f"{BASE}/samples/{sample['id']}",
        json={"developer_feedback": "Approved the matte finish"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["developer_feedback"] == "Approved the matte finish"
    assert updated.json()["is_version_current"] is False


def test_a_sample_is_hard_deleted(api):
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)
    sample = client.post(
        f"{BASE}/projects/{project.id}/samples",
        json={"quotation_version_id": version_id},
    ).json()

    assert client.delete(f"{BASE}/samples/{sample['id']}").status_code == 200
    assert client.get(f"{BASE}/projects/{project.id}/samples").json()["empty"] is True


# ---------------------------------------------------------------- purchase orders


def test_the_first_po_reports_that_it_moved_the_status(api):
    """AC-F10. The client should not have to re-read the project to find out."""
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)

    created = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-1",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
            "po_date": "2026-07-24",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status_moved_to_po_received"] is True

    detail = client.get(f"{BASE}/projects/{project.id}")
    assert detail.json()["status_label"] == "PO Received"


def test_a_second_po_does_not_claim_to_have_moved_the_status(api):
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)
    for number in ("PO-1", "PO-2"):
        created = client.post(
            f"{BASE}/projects/{project.id}/purchase-orders",
            json={
                "po_number": number,
                "po_source": "contractor_direct",
                "quotation_version_id": version_id,
            },
        )
        assert created.status_code == 201, created.text
    assert created.json()["status_moved_to_po_received"] is False


def test_a_duplicate_po_number_on_one_project_is_refused(api):
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)
    body = {
        "po_number": "PO-SAME",
        "po_source": "contractor_direct",
        "quotation_version_id": version_id,
    }
    assert client.post(f"{BASE}/projects/{project.id}/purchase-orders", json=body).status_code == 201
    again = client.post(f"{BASE}/projects/{project.id}/purchase-orders", json=body)
    assert again.status_code >= 400


def test_an_unknown_po_source_is_422(api):
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)

    response = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-BAD",
            "po_source": "walked_in",
            "quotation_version_id": version_id,
        },
    )
    assert response.status_code == 422, response.text


def test_a_mismatched_line_is_recorded_and_flagged_not_rejected(api):
    """AC-F9 through HTTP: 201 with the flag set, not a 4xx."""
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, product = _quoted_version(client, db, project.id, unit_price="900.00")
    po = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-3",
            "po_source": "trading_house",
            "quotation_version_id": version_id,
        },
    ).json()

    line = client.post(
        f"{BASE}/purchase-orders/{po['id']}/lines",
        json={"product_id": product.id, "unit_price": "820.00", "quantity": "10"},
    )
    assert line.status_code == 201, line.text
    assert line.json()["price_mismatch"] is True
    assert line.json()["quoted_unit_price"] == "900.00"

    listed = client.get(f"{BASE}/projects/{project.id}/purchase-orders").json()["data"]
    assert listed[0]["price_mismatch_count"] == 1


def test_the_po_list_carries_the_erosion_figure(api):
    """AC-F9a on the list, so management sees it without opening every PO."""
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, product = _quoted_version(
        client, db, project.id, unit_price="1000.00", quantity=10
    )
    po = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-4",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    ).json()
    client.post(
        f"{BASE}/purchase-orders/{po['id']}/lines",
        json={"product_id": product.id, "unit_price": "800.00", "quantity": "10"},
    )

    row = client.get(f"{BASE}/projects/{project.id}/purchase-orders").json()["data"][0]
    assert row["v1_total"] == "10000.00"
    assert row["drift_delta"] == "-2000.00"
    assert row["drift_percent"] == "-20.00"


def test_a_line_cannot_be_edited_through_another_pos_url(api):
    """Without the po_id in the filter, a line id from PO A would be editable through
    PO B's path, which the URL flatly claims is impossible."""
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, product = _quoted_version(client, db, project.id)
    first = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-5",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    ).json()
    second = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-6",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    ).json()
    line = client.post(
        f"{BASE}/purchase-orders/{first['id']}/lines",
        json={"product_id": product.id, "unit_price": "900.00", "quantity": "1"},
    ).json()

    response = client.put(
        f"{BASE}/purchase-orders/{second['id']}/lines/{line['id']}",
        json={"unit_price": "1.00"},
    )
    assert response.status_code == 404, response.text


def test_deleting_the_last_po_unblocks_nothing_but_leaves_the_status(api):
    """The funnel is not rewound: the project genuinely passed through PO Received, and
    quietly reversing it would hide the correction from the board."""
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)
    po = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-7",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    ).json()

    assert client.delete(f"{BASE}/purchase-orders/{po['id']}").status_code == 200
    detail = client.get(f"{BASE}/projects/{project.id}")
    assert detail.json()["status_label"] == "PO Received"


def test_a_project_with_a_po_cannot_be_deleted(api):
    """AC-G10, now that the table the guard looks for exists."""
    client, db, _company_id, _user_id, project = api
    _quotation, version_id, _product = _quoted_version(client, db, project.id)
    client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": "PO-8",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    )

    response = client.delete(f"{BASE}/projects/{project.id}")
    assert response.status_code == 409, response.text
