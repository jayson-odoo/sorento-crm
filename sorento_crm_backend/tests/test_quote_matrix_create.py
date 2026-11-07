"""PS-QUOTE-MATRIX: a scope's column headers travel with the quotation FORM's save.

The owner's rule (28 Oct): create, edit and view are one form. A scope added on the form has no
version until Save, so its columns cannot go through ``PUT /quotation-versions/{id}/columns``;
they ride in the same payload as its lines, and the server applies them first, in the same
transaction, so each line's ``quantity`` is derived from its cells. Postgres only, through the
form-save suite's fixture.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.projects import ProjectQuotationDocument, ProjectQuotationVersion

from .test_project_quotation_document_routes import (  # noqa: F401  (fixture import)
    MARKER,
    api,
)
from .test_quotation_form_save import _create, _lines_of_scope, _patch, _seed_product

COLUMNS = [
    {
        "key": "ta",
        "label": "Type A",
        "cols": [{"key": "ta-kit", "label": "Kitchen"}, {"key": "ta-bal", "label": "Balcony"}],
    },
    {"key": "tank", "label": "Break tank", "cols": []},
]


def _version_of(db, scope_id: str) -> ProjectQuotationVersion:
    return (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == scope_id)
        .order_by(ProjectQuotationVersion.version_no.desc())
        .first()
    )


def _grid_scope(product, label: str = "Unit") -> dict:
    return {
        "scope_label": f"{MARKER} {label}",
        "matrix_columns": COLUMNS,
        "lines": [
            {
                "product_id": product.id,
                "unit_price": "45.00",
                # Ignored on a grid scope: quantity is the sum of the cells.
                "quantity": "1",
                "qty_cells": {"ta-kit": "120", "ta-bal": "3.5", "tank": "2"},
            },
            {"product_id": product.id, "unit_price": "10.00", "qty_cells": {}},
        ],
    }


def test_create_stores_a_new_scopes_columns_and_cells_and_derives_quantity(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)

    response = _create(client, project.id, {"scopes": [_grid_scope(product)]})
    assert response.status_code == 201, response.text
    scope_id = response.json()["scopes"][0]["id"]

    db.expire_all()
    assert _version_of(db, scope_id).matrix_columns == COLUMNS
    first, second = _lines_of_scope(db, scope_id)
    assert first.qty_cells == {"ta-kit": "120.00", "ta-bal": "3.50", "tank": "2.00"}
    assert Decimal(first.quantity) == Decimal("125.50")
    assert Decimal(first.line_total) == Decimal("5647.50")
    assert not second.qty_cells
    assert Decimal(second.quantity) == Decimal("0")
    assert Decimal(str(response.json()["scopes"][0]["scope_total"])) == Decimal("5647.50")


def test_a_cell_under_an_unknown_column_refuses_the_whole_create(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    scope = _grid_scope(product)
    scope["lines"][0]["qty_cells"] = {"nope": "1"}

    response = _create(client, project.id, {"scopes": [scope]})
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_cells_invalid", response.text
    db.expire_all()
    assert (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.project_id == project.id)
        .count()
        == 0
    )


def test_invalid_columns_refuse_the_whole_create(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    scope = _grid_scope(product)
    scope["matrix_columns"] = [{"key": "x", "label": " ", "cols": []}]

    response = _create(client, project.id, {"scopes": [scope]})
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_columns_invalid", response.text


def test_a_scope_added_on_edit_carries_its_columns_too(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    created = _create(client, project.id, {"scopes": [{"scope_label": f"{MARKER} Plain"}]})
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    response = _patch(client, project.id, document_id, {"scopes": [_grid_scope(product, "Added")]})
    assert response.status_code == 200, response.text
    added = next(s for s in response.json()["scopes"] if s["scope_label"].endswith("Added"))
    db.expire_all()
    assert _version_of(db, added["id"]).matrix_columns == COLUMNS
    assert Decimal(_lines_of_scope(db, added["id"])[0].quantity) == Decimal("125.50")


def test_columns_on_a_saved_scope_in_the_form_are_refused(api):
    """A saved scope's columns change through PUT .../columns (it moves quantities); the form
    payload is not a second way in."""
    client, db, _company_id, _user_id, project, _party = api
    created = _create(client, project.id, {"scopes": [{"scope_label": f"{MARKER} Plain"}]})
    document_id = created.json()["id"]
    scope_id = created.json()["scopes"][0]["id"]

    response = _patch(
        client,
        project.id,
        document_id,
        {"scopes": [{"id": scope_id, "matrix_columns": COLUMNS}]},
    )
    assert response.status_code == 422, response.text
    db.expire_all()
    assert not _version_of(db, scope_id).matrix_columns
