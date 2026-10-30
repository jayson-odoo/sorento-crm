"""QUOTE-NO-FREE-TEXT: a quotation line saves only with a catalogue product or a product set.

UAC: documentation/plans/project-sales/quote-no-free-text-acceptance-criteria.md (AC-1 .. AC-7).
A line with neither is refused with 422 `quotation_line_product_required` on every write path,
whatever its description says, and nothing is written.

AC-7 (an out-of-series product line is still stored is_non_standard) is already pinned by
test_project_quotations.py::test_a_product_outside_the_nominated_series_raises_the_non_standard_alert
and test_project_series_product_routes.py (non_standard vs standard line, ~:564), so it is not
duplicated here.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.product_set import ProductSet, ProductSetMember
from app.models.projects import (
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)

from .test_project_quotation_document_routes import (  # noqa: F401  (fixture import)
    BASE,
    MARKER,
    _category,
    _product,
    _uom,
    api,
)

CODE = "quotation_line_product_required"


def _seed_product(db, price: str = "300.00"):
    product = _product(db, _category(db, "Basins").id, _uom(db), price)
    db.commit()
    return product


def _seed_set(db, company_id: str, product):
    row = ProductSet(
        id=str(uuid.uuid4()),
        company_id=company_id,
        set_code=f"ZZTQN{uuid.uuid4().hex[:8].upper()}",
        name=f"{MARKER} set",
        is_active=True,
    )
    db.add(row)
    db.flush()
    db.add(
        ProductSetMember(
            id=str(uuid.uuid4()),
            product_set_id=row.id,
            product_id=product.id,
            quantity=Decimal("1"),
            contributes_to_price=True,
            sort_order=0,
        )
    )
    db.commit()
    return row


def _scope_version(client, project_id: str) -> str:
    response = client.post(
        f"{BASE}/projects/{project_id}/quotations",
        json={"scope_label": f"{MARKER} House Units"},
    )
    assert response.status_code == 201, response.text
    return response.json()["current_version_id"]


def _lines(client, version_id: str) -> list:
    response = client.get(f"{BASE}/quotation-versions/{version_id}/lines")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _bulk(client, version_id: str, lines: list):
    return client.put(f"{BASE}/quotation-versions/{version_id}/lines", json={"lines": lines})


def _free_text(description: str = "Bespoke stone counter", **extra) -> dict:
    return {"description_snapshot": description, "unit_price": "10.00", "quantity": "1", **extra}


def _refused(response) -> None:
    assert response.status_code == 422, response.text
    assert response.json().get("code") == CODE, response.text


def _docs(db, project_id: str):
    db.expire_all()
    return (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.project_id == project_id)
        .all()
    )


def _scope_count(db, project_id: str) -> int:
    db.expire_all()
    return db.query(ProjectQuotation).filter(ProjectQuotation.project_id == project_id).count()


def _stored_rows(db, version_id: str):
    db.expire_all()
    return (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id == version_id)
        .order_by(ProjectQuotationLine.sort_order)
        .all()
    )


# ------------------------------------------------------------------ AC-1


def test_ac1_adding_a_line_with_a_description_but_no_product_or_set_is_refused(api):
    client, db, _company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    product = _seed_product(db)
    ok = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": "300.00", "quantity": "1"},
    )
    assert ok.status_code == 201, ok.text
    before = _lines(client, version_id)

    _refused(
        client.post(f"{BASE}/quotation-versions/{version_id}/lines", json=_free_text())
    )
    assert _lines(client, version_id) == before


# ------------------------------------------------------------------ AC-2


def test_ac2_clearing_the_product_of_a_catalogue_line_is_refused_and_keeps_the_line(api):
    client, db, _company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    product = _seed_product(db)
    created = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": "300.00", "quantity": "1"},
    )
    assert created.status_code == 201, created.text
    line_id = created.json()["id"]

    _refused(
        client.put(
            f"{BASE}/quotation-versions/{version_id}/lines/{line_id}",
            json={"product_id": None},
        )
    )
    stored = _lines(client, version_id)
    assert [row["id"] for row in stored] == [line_id]
    assert stored[0]["product_id"] == product.id
    assert stored[0]["description"] == created.json()["description"]
    assert stored[0]["description"]


# ------------------------------------------------------------------ AC-3


def test_ac3_a_bulk_save_with_one_product_less_line_is_refused_and_changes_nothing(api):
    client, db, _company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    product = _seed_product(db)
    seeded = _bulk(
        client,
        version_id,
        [
            {"product_id": product.id, "unit_price": "100.00", "quantity": "1"},
            {"product_id": product.id, "unit_price": "200.00", "quantity": "2"},
        ],
    )
    assert seeded.status_code == 200, seeded.text
    before = _lines(client, version_id)
    assert len(before) == 2
    total_before = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"][0][
        "current_total"
    ]

    _refused(
        _bulk(
            client,
            version_id,
            [
                {"id": before[0]["id"], "unit_price": "999.00"},
                {"id": before[1]["id"]},
                _free_text(),
            ],
        )
    )
    assert _lines(client, version_id) == before
    assert (
        client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"][0]["current_total"]
        == total_before
    )


# ------------------------------------------------------------------ AC-4


def test_ac4_the_new_quotation_form_with_a_product_less_line_is_refused_and_leaves_nothing(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    docs_before = len(_docs(db, project.id))
    scopes_before = _scope_count(db, project.id)

    response = client.post(
        f"{BASE}/projects/{project.id}/quotation-documents",
        json={
            "scopes": [
                {
                    "scope_label": f"{MARKER} Townhouse",
                    "lines": [
                        {"product_id": product.id, "unit_price": "250.00", "quantity": "1"},
                    ],
                },
                {"scope_label": f"{MARKER} Guard House", "lines": [_free_text()]},
            ]
        },
    )
    _refused(response)
    assert len(_docs(db, project.id)) == docs_before
    assert _scope_count(db, project.id) == scopes_before
    assert (
        db.query(ProjectQuotationVersion)
        .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationVersion.quotation_id)
        .filter(ProjectQuotation.project_id == project.id)
        .count()
        == 0
    )


# ------------------------------------------------------------------ AC-5


def test_ac5_the_edit_form_with_a_product_less_line_is_refused_and_keeps_the_stored_lines(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    created = client.post(
        f"{BASE}/projects/{project.id}/quotation-documents",
        json={
            "scopes": [
                {
                    "scope_label": f"{MARKER} Townhouse",
                    "lines": [
                        {"product_id": product.id, "unit_price": "250.00", "quantity": "4"},
                    ],
                }
            ]
        },
    )
    assert created.status_code == 201, created.text
    document = created.json()
    scope_id = document["scopes"][0]["id"]
    version_id = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"][0][
        "current_version_id"
    ]
    before = [(row.id, row.product_id, row.description_snapshot) for row in _stored_rows(db, version_id)]
    assert len(before) == 1

    response = client.patch(
        f"{BASE}/projects/{project.id}/quotation-documents/{document['id']}",
        json={
            "scopes": [
                {
                    "id": scope_id,
                    "lines": [
                        {"id": before[0][0], "product_id": product.id},
                        _free_text(),
                    ],
                }
            ]
        },
    )
    _refused(response)
    after = [(row.id, row.product_id, row.description_snapshot) for row in _stored_rows(db, version_id)]
    assert after == before


# ------------------------------------------------------------------ AC-6 (regression, green today)


def test_ac6_a_product_line_a_set_line_and_an_edited_description_all_still_save(api):
    client, db, company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    product = _seed_product(db)
    product_set = _seed_set(db, company_id, _seed_product(db, "50.00"))

    added = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": "300.00", "quantity": "1"},
    )
    assert added.status_code == 201, added.text

    edited = client.put(
        f"{BASE}/quotation-versions/{version_id}/lines/{added.json()['id']}",
        json={"description_snapshot": f"{MARKER} reworded for the customer"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["product_id"] == product.id
    assert edited.json()["description"] == f"{MARKER} reworded for the customer"

    set_line = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_set_id": product_set.id, "unit_price": "80.00", "quantity": "1"},
    )
    assert set_line.status_code == 201, set_line.text

    bulk = _bulk(
        client,
        version_id,
        [
            {"id": added.json()["id"]},
            {"id": set_line.json()["id"]},
            {"product_id": product.id, "unit_price": "10.00", "quantity": "2"},
        ],
    )
    assert bulk.status_code == 200, bulk.text
    assert len(bulk.json()["data"]) == 3

    form = client.post(
        f"{BASE}/projects/{project.id}/quotation-documents",
        json={
            "scopes": [
                {
                    "scope_label": f"{MARKER} Form scope",
                    "lines": [
                        {"product_id": product.id, "unit_price": "250.00", "quantity": "1"},
                        {"product_set_id": product_set.id, "unit_price": "80.00", "quantity": "1"},
                    ],
                }
            ]
        },
    )
    assert form.status_code == 201, form.text


# ------------------------------------------------------------------ AC-16 (review round 1)


def _foreign_product(db, template) -> str:
    """A product owned by ANOTHER company, by raw SQL so the scope layer cannot stamp it ours."""
    import uuid as _uuid

    from sqlalchemy import text

    other = str(_uuid.uuid4())
    db.execute(
        text("INSERT INTO companies (id, code, name, is_active) VALUES (:id, :code, :name, true)"),
        {"id": other, "code": f"ZZT{_uuid.uuid4().hex}", "name": f"{MARKER} Mocha"},
    )
    product_id = str(_uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO products (id, company_id, product_code, product_name, category_id, "
            "base_uom_id, list_price, is_active, is_discontinued) "
            "VALUES (:id, :company, :code, :name, :cat, :uom, 10.00, true, false)"
        ),
        {
            "id": product_id,
            "company": other,
            "code": f"ZZTF-{product_id[:8]}",
            "name": f"{MARKER} their product",
            "cat": template.category_id,
            "uom": template.base_uom_id,
        },
    )
    db.commit()
    return product_id


def _not_found(response) -> None:
    assert response.status_code == 404, response.text
    body = response.json()
    assert body.get("code") == "product_not_found", response.text
    assert "That product was not found." in response.text


def test_ac16_a_product_id_that_does_not_exist_is_a_404_and_writes_nothing(api):
    import uuid as _uuid

    client, db, _company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    before = _lines(client, version_id)

    _not_found(
        client.post(
            f"{BASE}/quotation-versions/{version_id}/lines",
            json={"product_id": str(_uuid.uuid4()), "unit_price": "10.00", "quantity": "1"},
        )
    )
    assert _lines(client, version_id) == before


def test_ac16_another_companys_product_is_a_404_and_writes_nothing(api):
    client, db, _company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    foreign = _foreign_product(db, _seed_product(db))
    before = _lines(client, version_id)

    _not_found(
        client.post(
            f"{BASE}/quotation-versions/{version_id}/lines",
            json={"product_id": foreign, "unit_price": "10.00", "quantity": "1"},
        )
    )
    assert _lines(client, version_id) == before


def test_ac16_the_bulk_save_and_the_form_refuse_an_unknown_product_too(api):
    import uuid as _uuid

    client, db, _company_id, _user_id, project, _party = api
    version_id = _scope_version(client, project.id)
    product = _seed_product(db)
    assert _bulk(
        client, version_id, [{"product_id": product.id, "unit_price": "5.00", "quantity": "1"}]
    ).status_code == 200
    before = _lines(client, version_id)
    ghost = {"product_id": str(_uuid.uuid4()), "unit_price": "10.00", "quantity": "1"}

    _not_found(_bulk(client, version_id, [{"id": before[0]["id"]}, ghost]))
    assert _lines(client, version_id) == before

    docs_before = len(_docs(db, project.id))
    _not_found(
        client.post(
            f"{BASE}/projects/{project.id}/quotation-documents",
            json={"scopes": [{"scope_label": f"{MARKER} Ghost", "lines": [ghost]}]},
        )
    )
    assert len(_docs(db, project.id)) == docs_before
