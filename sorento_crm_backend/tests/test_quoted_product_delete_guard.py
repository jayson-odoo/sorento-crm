"""QUOTE-NO-FREE-TEXT Q2 (UAC AC-13 .. AC-15): a product or set that sits on a quotation line
cannot be deleted. 409 naming the quotation; the product/set and the line are unchanged. The
guard lives in the service delete methods, so the direct route and the deferred record action
share it; each is asserted here."""
from __future__ import annotations

import pytest

from app.models.product import Product
from app.models.product_set import ProductSet
from app.models.projects import ProjectQuotationLine
from app.services.error_handler import AppException

from .test_quotation_line_product_required import (  # noqa: F401  (fixture import)
    BASE,
    MARKER,
    _seed_product,
    _seed_set,
    api,
)

PRODUCT_MESSAGE = "This product is on quotation {no}, so it cannot be deleted."
SET_MESSAGE = "This product set is on quotation {no}, so it cannot be deleted."


def _quoted(client, db, project_id: str, **line_target) -> dict:
    """A draft quotation document with one line naming the given product or set."""
    response = client.post(
        f"{BASE}/projects/{project_id}/quotation-documents",
        json={
            "scopes": [
                {
                    "scope_label": f"{MARKER} Townhouse",
                    "lines": [{"unit_price": "250.00", "quantity": "1", **line_target}],
                }
            ]
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_no"]
    return body


def _line_count(db, **where) -> int:
    db.expire_all()
    return db.query(ProjectQuotationLine).filter_by(**where).count()


# ------------------------------------------------------------------ AC-13 product


def test_ac13_deleting_a_quoted_product_through_the_route_is_refused_409(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _quoted(client, db, project.id, product_id=product.id)

    response = client.delete(f"/api/v1/master-data/products/{product.id}")

    assert response.status_code == 409, response.text
    assert PRODUCT_MESSAGE.format(no=document["document_no"]) in response.text
    db.expire_all()
    assert db.get(Product, product.id) is not None
    assert _line_count(db, product_id=product.id) == 1


def test_ac13_the_service_refuses_a_quoted_product_and_changes_nothing(api):
    from app.services.product_service import ProductService

    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _quoted(client, db, project.id, product_id=product.id)

    with pytest.raises(AppException) as refused:
        ProductService(db).delete_product(product.id)

    assert refused.value.status_code == 409
    assert refused.value.detail["message"] == PRODUCT_MESSAGE.format(no=document["document_no"])
    db.rollback()
    assert db.get(Product, product.id) is not None
    assert _line_count(db, product_id=product.id) == 1


def test_ac13_the_deferred_product_delete_handler_fails_with_the_same_text(api):
    """`product.delete` runs `record_actions._delete_product`; its failure is what the page toasts."""
    from app.services import record_actions

    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _quoted(client, db, project.id, product_id=product.id)

    with pytest.raises(AppException) as refused:
        record_actions._delete_product(db, {"entity_id": product.id})

    assert refused.value.status_code == 409
    assert refused.value.detail["message"] == PRODUCT_MESSAGE.format(no=document["document_no"])


# ------------------------------------------------------------------ AC-14 set


def test_ac14_deleting_a_quoted_set_through_the_route_is_refused_409(api):
    client, db, company_id, _user_id, project, _party = api
    product_set = _seed_set(db, company_id, _seed_product(db, "50.00"))
    document = _quoted(client, db, project.id, product_set_id=product_set.id)

    response = client.delete(f"/api/v1/master-data/product-sets/{product_set.id}")

    assert response.status_code == 409, response.text
    assert SET_MESSAGE.format(no=document["document_no"]) in response.text
    db.expire_all()
    assert db.get(ProductSet, product_set.id) is not None
    assert _line_count(db, product_set_id=product_set.id) == 1


def test_ac14_the_service_refuses_a_quoted_set_and_changes_nothing(api):
    from app.services.product_set_service import ProductSetService

    client, db, company_id, _user_id, project, _party = api
    product_set = _seed_set(db, company_id, _seed_product(db, "50.00"))
    document = _quoted(client, db, project.id, product_set_id=product_set.id)

    with pytest.raises(AppException) as refused:
        ProductSetService(db).delete(product_set.id)

    assert refused.value.status_code == 409
    assert refused.value.detail["message"] == SET_MESSAGE.format(no=document["document_no"])
    db.rollback()
    assert db.get(ProductSet, product_set.id) is not None
    assert _line_count(db, product_set_id=product_set.id) == 1


def test_ac14_the_deferred_set_delete_handler_fails_with_the_same_text(api):
    from app.services import record_actions

    client, db, company_id, _user_id, project, _party = api
    product_set = _seed_set(db, company_id, _seed_product(db, "50.00"))
    document = _quoted(client, db, project.id, product_set_id=product_set.id)

    with pytest.raises(AppException) as refused:
        record_actions._delete_product_set(db, {"entity_id": product_set.id})

    assert refused.value.status_code == 409
    assert refused.value.detail["message"] == SET_MESSAGE.format(no=document["document_no"])


# ------------------------------------------------------------------ AC-15 regression


def test_ac15_a_product_and_a_set_on_no_quotation_still_delete(api):
    client, db, company_id, _user_id, _project, _party = api
    product = _seed_product(db)
    product_set = _seed_set(db, company_id, _seed_product(db, "50.00"))

    deleted_product = client.delete(f"/api/v1/master-data/products/{product.id}")
    assert deleted_product.status_code == 200, deleted_product.text
    deleted_set = client.delete(f"/api/v1/master-data/product-sets/{product_set.id}")
    assert deleted_set.status_code == 204, deleted_set.text

    db.expire_all()
    assert db.get(Product, product.id) is None
    assert db.get(ProductSet, product_set.id) is None


# ------------------------------------------------------------------ AC-17 bulk delete


def test_ac17_a_bulk_delete_with_one_quoted_product_is_refused_and_deletes_nothing(api):
    client, db, _company_id, _user_id, project, _party = api
    quoted = _seed_product(db)
    free = _seed_product(db)
    document = _quoted(client, db, project.id, product_id=quoted.id)

    response = client.request(
        "DELETE",
        "/api/v1/master-data/products/bulk",
        json={"ids": [quoted.id, free.id]},
    )

    assert response.status_code == 409, response.text
    assert PRODUCT_MESSAGE.format(no=document["document_no"]) in response.text
    db.expire_all()
    assert db.get(Product, quoted.id) is not None
    assert db.get(Product, free.id) is not None
    assert _line_count(db, product_id=quoted.id) == 1


# ------------------------------------------------------------------ AC-18 ordering + issued


def test_ac18_the_409_names_the_lowest_document_no_not_the_first_created(api):
    from .test_project_quotation_document_routes import _current_version_id

    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    # Lowest number, created FIRST but given its product line LAST.
    low = client.post(
        f"{BASE}/projects/{project.id}/quotation-documents",
        json={"scopes": [{"scope_label": f"{MARKER} Low"}]},
    )
    assert low.status_code == 201, low.text
    high = _quoted(client, db, project.id, product_id=product.id)
    low_body = low.json()
    assert low_body["document_no"] < high["document_no"]
    version_id = _current_version_id(db, low_body["scopes"][0]["id"])
    added = client.post(
        f"{BASE}/quotation-versions/{version_id}/lines",
        json={"product_id": product.id, "unit_price": "10.00", "quantity": "1"},
    )
    assert added.status_code == 201, added.text
    # Make insertion order differ from number order: the product's FIRST line row belongs to
    # the higher-numbered document, so an unsorted query names the wrong quotation.
    response = client.delete(f"/api/v1/master-data/products/{product.id}")

    assert response.status_code == 409, response.text
    assert PRODUCT_MESSAGE.format(no=low_body["document_no"]) in response.text
    assert high["document_no"] not in response.text


def test_ac18_a_product_used_only_on_an_issued_version_is_still_refused(api):
    from .test_project_quotation_document_routes import _sign

    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _quoted(client, db, project.id, product_id=product.id)
    root = f"{BASE}/projects/{project.id}/quotation-documents"
    _sign(client, root, document["id"])
    issued = client.post(f"{root}/{document['id']}/issue")
    assert issued.status_code == 201, issued.text

    response = client.delete(f"/api/v1/master-data/products/{product.id}")

    assert response.status_code == 409, response.text
    assert PRODUCT_MESSAGE.format(no=document["document_no"]) in response.text
    db.expire_all()
    assert db.get(Product, product.id) is not None
