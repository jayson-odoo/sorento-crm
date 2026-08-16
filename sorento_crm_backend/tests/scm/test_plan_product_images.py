"""What a plan row's product LOOKS like (AC-7).

> "as IT I do not know what a product looks like" (captain, 2026-08-15)

Written BEFORE the implementation.

The photo is not a new asset: it is the one already chosen in Dealer Kit -> Brochure
images, read through the same viewer-gated reader the catalogue uses. So what is pinned
here is the CONTRACT, not the picture, and the contract is split in two on purpose:

- the run-wide call answers only WHETHER each product has a photo, in one SQL and with no
  signing, because the icon is on every row of a plan that can run to thousands of them;
- the per-product call signs exactly one URL, on the open of one popover.

`is_primary` says whether anyone ever made a deliberate choice in Brochure images. The
reader falls back to the first catalogue image when nobody did (744 of the 762 imaged
products on the live run), which is the right picture to show and still worth telling the
buyer about, so the popover can offer the loop back to the picker.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

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


def _photo(
    db,
    product,
    company_id,
    *,
    primary=True,
    mime="image/jpeg",
    thumb=None,
    deleted=False,
    sort_order=0,
):
    """A catalogue image linked to the product, as the Brochure-images picker writes it.

    `primary=False` is the ordinary live row: an image attached to the product that nobody
    ever nominated.
    """
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
        is_deleted=deleted,
    )
    db.add(attachment)
    db.flush()
    db.add(
        ProductAttachment(
            id=_u(),
            product_id=product.id,
            attachment_id=attachment.id,
            is_primary=primary,
            sort_order=sort_order,
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


@contextmanager
def _statements_touching(db, *tables):
    """Every SQL statement the request issued that names one of ``tables``.

    Counting SQL is the only way to state "this is one query" as a fact rather than as a
    reading of the code. The listener sits on the fixture's own connection, which is the
    one the route's session runs on, so the app's startup chatter on other connections
    cannot inflate the count.
    """
    seen: list[str] = []
    bind = db.get_bind()

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if any(t in statement for t in tables):
            seen.append(statement)

    event.listen(bind, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(bind, "before_cursor_execute", _record)


def _deny(app, db, gcu, gcuk):
    nobody = seed_user(db, None)
    for dep in (gcu, gcuk):
        app.dependency_overrides[dep] = lambda: {"id": nobody, "email": "x@y", "roles": []}


def _other_company(db):
    from app.models.base import set_company_scope
    from app.models.company import Company

    set_company_scope(db, None)
    other = Company(id=_u(), code=f"{MARKER}-OTH"[:20], name=f"{MARKER} other company")
    db.add(other)
    db.flush()
    return other


# ---------------------------------------------------------------------------
# the run-wide map: which rows get a lit icon
# ---------------------------------------------------------------------------

def test_the_run_says_which_of_its_products_have_a_photo(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    imaged = _product(db, company_id)
    bare = _product(db, company_id)
    _photo(db, imaged, company_id)
    run_id = _run_with(db, company_id, [imaged, bare])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    has_image = r.json()["has_image"]
    assert has_image[str(imaged.id)] is True
    # Absent, not `false`: the map is what the icon reads, and a product with nothing to
    # show simply is not in it.
    assert str(bare.id) not in has_image


def test_the_map_costs_no_signatures(scm_app, monkeypatch):
    """The icon is on EVERY row. A plan of four thousand lines must not sign four thousand
    URLs to decide which icons are lit - the signature is bought on the popover open."""
    from app.services.dealer_kit import product_images

    def _explode(*args, **kwargs):
        raise AssertionError("the run-wide map must not sign anything")

    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id)
    run_id = _run_with(db, company_id, [product])
    # The reader binds `resolve_signed_url` by name at import, so the module under test is
    # where the trap has to go.
    monkeypatch.setattr(product_images, "resolve_signed_url", _explode)

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert r.json()["has_image"][str(product.id)] is True


def test_the_map_is_one_query_not_a_fetch_then_a_big_in_list(scm_app):
    """The run's product ids are a JOIN, not something Python carries between two queries.

    Reading every distinct product id of the run into a list and then asking a second
    question with `IN (<thousands of ids>)` costs a round trip and a statement whose
    parameter list grows with the plan. The database can answer both halves at once.
    """
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    imaged = _product(db, company_id)
    bare = _product(db, company_id)
    _photo(db, imaged, company_id)
    run_id = _run_with(db, company_id, [imaged, bare])

    with _statements_touching(db, "reorder_recommendation", "product_attachments") as seen:
        with TestClient(app) as c:
            r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert r.json()["has_image"] == {str(imaged.id): True}
    assert len(seen) == 1, "the map must be ONE statement:\n" + "\n\n".join(seen)
    # And it must be the join, not one of the two halves on its own.
    assert "reorder_recommendation" in seen[0] and "product_attachments" in seen[0]


def test_a_product_nobody_nominated_still_counts_as_having_a_photo(scm_app):
    """744 of the 762 imaged products on the live run have no `is_primary` row. Dimming
    their icons would say "no photo" about a product we can show a photo of."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id, primary=False)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert r.json()["has_image"][str(product.id)] is True


def test_a_spec_sheet_linked_to_the_product_is_not_its_photo(scm_app):
    """`product_attachments` links whatever is attached to a product, PDFs included. A
    spec sheet rendered as the product photo is worse than no photo."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id, mime="application/pdf")
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert str(product.id) not in r.json()["has_image"]


def test_an_image_deleted_in_resource_management_does_not_light_the_icon(scm_app):
    """The reader skips soft-deleted attachments, so a lit icon that opens onto the empty
    state would be the map disagreeing with the popover about the same product."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id, deleted=True)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert str(product.id) not in r.json()["has_image"]


def test_a_run_with_no_recommendations_answers_an_empty_map(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    run_id = _run_with(db, company_id, [])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 200, r.text
    assert r.json() == {"has_image": {}}


def test_the_map_is_denied_without_the_dashboard_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id)
    run_id = _run_with(db, company_id, [product])
    _deny(app, db, gcu, gcuk)

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
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    other = _other_company(db)
    product = _product(db, other.id)
    _photo(db, product, other.id)
    run_id = _run_with(db, other.id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# the per-product photo: one signature, on the open of one popover
# ---------------------------------------------------------------------------

def test_the_chosen_photo_is_served_and_reported_as_chosen(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://cdn.test.invalid/")
    assert body["is_primary"] is True


def test_a_product_nobody_nominated_still_gets_a_photo_marked_as_a_fallback(scm_app):
    """The picture is the right one to show; `is_primary: false` is what lets the popover
    offer the way back to Brochure images so the buyer can nominate a better one."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id, primary=False)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://cdn.test.invalid/")
    assert body["is_primary"] is False


def test_the_nominated_photo_wins_over_the_other_catalogue_images(scm_app):
    """Someone deliberately picked one. Ordering must not quietly override that."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id, primary=False, sort_order=0)
    chosen = _photo(db, product, company_id, primary=True, sort_order=9)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert r.status_code == 200, r.text
    assert chosen.file_path in r.json()["url"]


def test_the_thumbnail_is_preferred_over_the_full_size_photo(scm_app):
    """A popover panel is 336px wide. Sending the full-resolution photograph is megabytes
    over a showroom's wifi for a picture rendered at a third of its size."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id, thumb="products/thumbs/zzt-thumb.jpg")
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert r.status_code == 200, r.text
    assert "thumb" in r.json()["url"]


def test_a_product_with_no_photo_answers_a_null_url_not_a_404(scm_app):
    """A 404 would read as "that product is not on this plan". It is: it simply has no
    picture, which is the popover's designed empty state."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    run_id = _run_with(db, company_id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert r.status_code == 200, r.text
    assert r.json() == {"url": None, "is_primary": False}


def test_a_product_that_is_not_on_the_run_is_a_404(scm_app):
    """The run id is the gate. Reading any product's imagery through it would make this a
    general product-photo endpoint that skipped the catalogue's own permissions."""
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    planned = _product(db, company_id)
    elsewhere = _product(db, company_id)
    _photo(db, elsewhere, company_id)
    run_id = _run_with(db, company_id, [planned])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{elsewhere.id}")

    assert r.status_code == 404


def test_the_photo_is_denied_without_the_dashboard_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    company_id = next(iter(as_company_user(app, db, gcu, gcuk)))
    product = _product(db, company_id)
    _photo(db, product, company_id)
    run_id = _run_with(db, company_id, [product])
    _deny(app, db, gcu, gcuk)

    with TestClient(app) as c:
        denied = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert denied.status_code == 403


def test_a_photo_on_another_company_s_run_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    other = _other_company(db)
    product = _product(db, other.id)
    _photo(db, product, other.id)
    run_id = _run_with(db, other.id, [product])

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{run_id}/product-images/{product.id}")

    assert r.status_code == 404
