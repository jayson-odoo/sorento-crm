"""What a plan row's product LOOKS like (AC-7).

> "as IT I do not know what a product looks like" (captain, 2026-08-15)

Written BEFORE the implementation.

The photo is not a new asset: it is the one already chosen in Dealer Kit -> Brochure
images (`product_attachments.is_primary`), read through the same viewer-gated reader the
catalogue uses. So what is pinned here is the CONTRACT, not the picture: one call for the
whole run keyed by product id, a product with no permitted image ABSENT from the map
rather than mapped to null (the popover has a designed empty state and a blank url would
render a broken image), the same permission as every sibling reorder-run endpoint, and a
run belonging to another company reading as 404 rather than leaking its product list.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTPIMG"


class _SigningBackend:
    """A signer that works whatever this machine has installed.

    `resolve_signed_url` signs STRICTLY here (a photo that cannot be signed is an absent
    image), and the real CloudFront/R2 keys are not on a test box. Without the stub these
    tests would pass or fail on local configuration instead of on the contract.
    """

    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://cdn.test.invalid/{key}?Signature=stub"


@pytest.fixture(autouse=True)
def _signing_works(monkeypatch):
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _SigningBackend())


def _u() -> str:
    return str(uuid.uuid4())


def _product(db, company_id):
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    code = unique_code(MARKER)
    cat = ProductCategory(id=_u(), category_code=code, category_name=f"{MARKER} cat {code}")
    uom = UnitOfMeasure(id=_u(), uom_code=code[:20], uom_name=f"{MARKER} uom {code}")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(),
        product_code=code,
        product_name=f"{MARKER} product {code}",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
        company_id=company_id,
    )
    db.add(product)
    db.flush()
    return product


def _primary_photo(db, product, company_id, *, mime="image/jpeg", thumb=None):
    """The Brochure-images choice, as the picker writes it: an image attachment linked
    to the product with `is_primary` set."""
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment
    from tests._pg_fixture import unique_code

    name = unique_code("zztpimg")
    attachment = Attachment(
        id=_u(),
        original_filename=f"{name}.jpg",
        stored_filename=f"{name}.jpg",
        file_path=f"products/{name}.jpg",
        thumbnail_path=thumb,
        mime_type=mime,
        storage_provider="s3",
        company_id=company_id,
        is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    db.add(
        ProductAttachment(
            id=_u(),
            product_id=product.id,
            attachment_id=attachment.id,
            is_primary=True,
            sort_order=0,
            access_levels=["dealer", "end_user"],
            company_id=company_id,
        )
    )
    db.flush()
    return attachment


def _run_with(db, company_id, products):
    run_id = _u()
    db.execute(
        text(
            "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
            "VALUES (:id, 'completed', false, :co, now())"
        ),
        {"id": run_id, "co": company_id},
    )
    for product in products:
        db.execute(
            text(
                "INSERT INTO scm.reorder_recommendation "
                "(id, run_id, product_id, rec_type, rounded_qty, status, company_id) "
                "VALUES (:id, :r, :p, 'buy', 10, 'proposed', :co)"
            ),
            {"id": _u(), "r": run_id, "p": product.id, "co": company_id},
        )
    db.flush()
    return run_id


def test_the_run_serves_the_primary_photo_of_each_product_it_planned(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _primary_photo(db, product, company_id)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    images = r.json()["images"]
    assert str(product.id) in images
    assert images[str(product.id)].startswith("https://cdn.test.invalid/")


def test_the_thumbnail_is_preferred_over_the_full_size_photo(scm_app):
    """A plan of four thousand rows must not pull full-resolution photographs; the reader
    already prefers the thumbnail, and this endpoint must not undo that."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _primary_photo(db, product, company_id, thumb="products/thumbs/zzt-thumb.jpg")
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert "thumb" in r.json()["images"][str(product.id)]


def test_a_product_with_no_photo_is_absent_rather_than_null(scm_app):
    """Absent, not `null`: the popover renders "No primary photo yet" for a missing key,
    and a null url would reach the browser as a broken image instead."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    with_photo = _product(db, company_id)
    without = _product(db, company_id)
    _primary_photo(db, with_photo, company_id)
    run_id = _run_with(db, company_id, [with_photo, without])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    images = r.json()["images"]
    assert str(with_photo.id) in images
    assert str(without.id) not in images


def test_a_spec_sheet_linked_to_the_product_is_not_its_photo(scm_app):
    """`product_attachments` links whatever is attached to a product, PDFs included. A
    spec sheet rendered as the product photo is worse than no photo."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _primary_photo(db, product, company_id, mime="application/pdf")
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert str(product.id) not in r.json()["images"]


def test_a_run_with_no_recommendations_answers_an_empty_map(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    run_id = _run_with(db, company_id, [])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert r.json() == {"images": {}}


def test_a_user_without_the_dashboard_permission_is_denied(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _primary_photo(db, product, company_id)
    run_id = _run_with(db, company_id, [product])

    nobody = seed_user(db, None)
    for dep in (gcu, gcuk):
        app.dependency_overrides[dep] = lambda: {"id": nobody, "email": "x@y", "roles": []}

    with TestClient(app) as c:
        denied = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert denied.status_code == 403


def test_an_unknown_run_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{_u()}/product-images")

    assert r.status_code == 404


def test_a_run_from_another_company_is_a_404_not_a_leak(scm_app):
    """`assert_run_visible` is the gate every sibling endpoint relies on: another
    company's run must read as not found, never served with its product list."""
    from app.models.base import set_company_scope
    from app.models.company import Company

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    set_company_scope(db, None)
    other = Company(id=_u(), code=f"{MARKER}-OTH"[:20], name=f"{MARKER} other company")
    db.add(other)
    db.flush()
    product = _product(db, other.id)
    _primary_photo(db, product, other.id)
    run_id = _run_with(db, other.id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 404
