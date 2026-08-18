"""Saving a whole customer PO in one request: the header and its full line set.

The PO detail screen is an edit VIEW now, the way the quotation document already is: nothing
is written while somebody types, and one Save covers the header and every line. That needs one
atomic write, so ``PUT /purchase-orders/{po_id}`` accepts an optional ``lines`` array holding
the FULL desired set.

Route-level, because the decisions worth pinning are at the HTTP boundary: the whole-set
semantics (a stored line whose id is absent is deleted), the refusals a client must be able to
show a person, and the fact that a header-only save still leaves the lines alone -- the modal
that records a PO sends exactly that shape and must keep working.
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

MARKER = "zzt-po-doc"
BASE = "/api/v1/project-sales"
EDIT = "projects.projects.edit"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, code_hint: str, list_price: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{code_hint}-{_uid()[:6]}",
        product_name=f"{MARKER} {code_hint}",
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


def _quoted_version(client, db, project_id: str, *, unit_price="900.00"):
    """A quotation with one priced line, so the PO has something to be checked against."""
    response = client.post(
        f"{BASE}/projects/{project_id}/quotations", json={"scope_label": "House Units"}
    )
    assert response.status_code == 201, response.text
    version_id = response.json()["current_version_id"]
    product = _product(db, "WC", "1200.00")
    line = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": unit_price, "quantity": "10"},
    )
    assert line.status_code == 201, line.text
    return version_id, product


def _po(client, project_id: str, version_id: str | None, number: str) -> dict:
    created = client.post(
        f"{BASE}/projects/{project_id}/purchase-orders",
        json={
            "po_number": number,
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
            "po_date": "2026-07-24",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _line(client, po_id: str, **body) -> dict:
    created = client.post(f"{BASE}/purchase-orders/{po_id}/lines", json=body)
    assert created.status_code == 201, created.text
    return created.json()


def _lines(client, po_id: str) -> list[dict]:
    listed = client.get(f"{BASE}/purchase-orders/{po_id}/lines")
    assert listed.status_code == 200, listed.text
    return listed.json()["data"]


# --------------------------------------------------------------------- happy path


def test_one_save_writes_the_header_and_the_whole_line_set(api):
    """The edit view's Save: a header field, an edited line, an added line and a removal,
    in ONE request. What comes back is the arrangement the user made, in their order."""
    client, db, _company_id, _user_id, project = api
    version_id, product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-1")
    kept = _line(
        client,
        po["id"],
        product_id=product.id,
        unit_price="900.00",
        quantity="10",
        uom="PCS",
    )
    dropped = _line(client, po["id"], product_code="THEIRS-OLD", unit_price="10.00")

    saved = client.put(
        f"{BASE}/purchase-orders/{po['id']}",
        json={
            "po_number": "PO-DOC-1A",
            "notes": "Staged ordering, phase 1 only",
            "lines": [
                # Same line, re-priced. Its id is what keeps it the same row.
                {
                    "id": kept["id"],
                    "product_id": product.id,
                    "unit_price": "820.00",
                    "quantity": "12",
                    "uom": "PCS",
                },
                # New, and off-catalog: the contractor's own code is all we have.
                {"product_code": "THEIRS-NEW", "description": "Their basin", "unit_price": "300.00"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["po_number"] == "PO-DOC-1A"
    assert body["notes"] == "Staged ordering, phase 1 only"
    assert body["line_count"] == 2

    rows = _lines(client, po["id"])
    assert [row["id"] for row in rows][0] == kept["id"]
    assert [row["sort_order"] for row in rows] == [0, 1]
    assert rows[0]["unit_price"] == "820.00"
    assert rows[0]["quantity"] == "12.00"
    assert rows[0]["line_total"] == "9840.00"
    # Re-checked against the bound version on the way in, not left as it was.
    assert rows[0]["price_mismatch"] is True
    assert rows[0]["quoted_unit_price"] == "900.00"
    assert rows[1]["product_code"] == "THEIRS-NEW"
    assert rows[1]["model_mismatch"] is True
    # A stored line whose id never reached the request is gone.
    assert dropped["id"] not in [row["id"] for row in rows]


def test_a_header_only_save_leaves_the_lines_alone(api):
    """The record-a-PO modal sends no `lines` at all. Reading that as "an empty set" would
    wipe every line on the PO the first time somebody corrected its date."""
    client, db, _company_id, _user_id, project = api
    version_id, product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-2")
    _line(client, po["id"], product_id=product.id, unit_price="900.00", quantity="10")

    saved = client.put(
        f"{BASE}/purchase-orders/{po['id']}", json={"po_date": "2026-08-01"}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["po_date"] == "2026-08-01"
    assert len(_lines(client, po["id"])) == 1


def test_an_empty_line_array_clears_the_po(api):
    """Explicitly sending nothing is a real intent - the user removed every line - and it
    is how it differs from omitting the key."""
    client, db, _company_id, _user_id, project = api
    version_id, product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-3")
    _line(client, po["id"], product_id=product.id, unit_price="900.00", quantity="10")

    saved = client.put(f"{BASE}/purchase-orders/{po['id']}", json={"lines": []})
    assert saved.status_code == 200, saved.text
    assert saved.json()["line_count"] == 0
    assert _lines(client, po["id"]) == []


def test_rebinding_the_version_in_the_same_save_rechecks_the_lines_against_it(api):
    """The binding decides what every line is compared to, so it has to be applied BEFORE
    the lines are written or the flags would answer for the version that was there before."""
    client, db, _company_id, _user_id, project = api
    first_version, product = _quoted_version(client, db, project.id, unit_price="900.00")
    po = _po(client, project.id, None, "PO-DOC-4")
    kept = _line(
        client, po["id"], product_id=product.id, unit_price="900.00", quantity="10"
    )
    # Unbound, so nothing was checked.
    assert _lines(client, po["id"])[0]["model_mismatch"] is True

    saved = client.put(
        f"{BASE}/purchase-orders/{po['id']}",
        json={
            "quotation_version_id": first_version,
            "lines": [
                {
                    "id": kept["id"],
                    "product_id": product.id,
                    "unit_price": "900.00",
                    "quantity": "10",
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    row = _lines(client, po["id"])[0]
    assert row["model_mismatch"] is False
    assert row["price_mismatch"] is False
    assert row["quoted_unit_price"] == "900.00"


def test_the_list_says_how_many_sales_orders_were_already_published(api):
    """A PO whose orders are out is still editable - corrections happen - but the screen has
    to be able to say so before somebody saves over it."""
    from app.models.project_so import SO_STATUS_PUBLISHED, ProjectSalesOrder

    client, db, company_id, _user_id, project = api
    version_id, _product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-5")

    db.add(
        ProjectSalesOrder(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            purchase_order_id=po["id"],
            provisional_ref=f"{MARKER}-{_uid()[:8]}",
            status=SO_STATUS_PUBLISHED,
        )
    )
    db.flush()

    row = [
        item
        for item in client.get(f"{BASE}/projects/{project.id}/purchase-orders").json()["data"]
        if item["id"] == po["id"]
    ][0]
    assert row["published_sales_order_count"] == 1


# ---------------------------------------------------------------------- refusals


def test_a_line_with_neither_a_product_nor_a_code_is_422(api):
    client, db, _company_id, _user_id, project = api
    version_id, _product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-6")

    refused = client.put(
        f"{BASE}/purchase-orders/{po['id']}",
        json={"lines": [{"description": "Something they wrote", "unit_price": "10.00"}]},
    )
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert "product" in (body.get("detail") or body.get("message") or "").lower()


def test_the_same_line_twice_in_one_save_is_422(api):
    """Treating it as two rows would silently duplicate the line the client meant to move."""
    client, db, _company_id, _user_id, project = api
    version_id, product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-7")
    line = _line(client, po["id"], product_id=product.id, unit_price="900.00")

    refused = client.put(
        f"{BASE}/purchase-orders/{po['id']}",
        json={
            "lines": [
                {"id": line["id"], "product_id": product.id, "unit_price": "900.00"},
                {"id": line["id"], "product_id": product.id, "unit_price": "800.00"},
            ]
        },
    )
    assert refused.status_code == 422, refused.text


def test_a_line_from_another_po_is_404_and_nothing_is_written(api):
    """The whole save is refused before anything moves: a half-applied Save is the state
    nobody typed."""
    client, db, _company_id, _user_id, project = api
    version_id, product = _quoted_version(client, db, project.id)
    first = _po(client, project.id, version_id, "PO-DOC-8")
    second = _po(client, project.id, version_id, "PO-DOC-9")
    foreign = _line(client, first["id"], product_id=product.id, unit_price="900.00")
    mine = _line(client, second["id"], product_code="MINE", unit_price="5.00")

    refused = client.put(
        f"{BASE}/purchase-orders/{second['id']}",
        json={
            "po_number": "PO-DOC-9-RENAMED",
            "lines": [
                {"id": foreign["id"], "product_id": product.id, "unit_price": "900.00"}
            ],
        },
    )
    assert refused.status_code == 404, refused.text

    # Neither the header nor the lines moved.
    rows = _lines(client, second["id"])
    assert [row["id"] for row in rows] == [mine["id"]]
    listed = [
        item
        for item in client.get(f"{BASE}/projects/{project.id}/purchase-orders").json()["data"]
        if item["id"] == second["id"]
    ][0]
    assert listed["po_number"] == "PO-DOC-9"


def test_a_reader_cannot_save_a_po(api):
    """Auth denial at the route, before any of the whole-set logic runs."""
    from app.services.user_service import UserPermissionService

    client, db, _company_id, _user_id, project = api
    version_id, _product = _quoted_version(client, db, project.id)
    po = _po(client, project.id, version_id, "PO-DOC-10")

    granted = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug != EDIT
    )
    try:
        refused = client.put(
            f"{BASE}/purchase-orders/{po['id']}",
            json={"po_number": "PO-DOC-10-HACKED", "lines": []},
        )
    finally:
        UserPermissionService.check_user_has_permission = granted

    assert refused.status_code == 403, refused.text
    listed = [
        item
        for item in client.get(f"{BASE}/projects/{project.id}/purchase-orders").json()["data"]
        if item["id"] == po["id"]
    ][0]
    assert listed["po_number"] == "PO-DOC-10"
