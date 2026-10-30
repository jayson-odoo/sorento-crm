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
