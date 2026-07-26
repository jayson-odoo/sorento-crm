"""The PDF worker, end to end, against a real browser and the running stack.

This is the test the slice exists for. Everything else proves the pieces; this
proves that a request actually becomes a file, and - the part that matters -
that a staff export and a consumer export of the SAME page produce DIFFERENT
documents.

Skipped unless the frontend is reachable, because it drives headless Chromium
at a real print page. Run with the stack up:

    DEALER_KIT_PRINT_BASE_URL=http://localhost:3020 pytest tests/test_dealer_kit_pdf_render.py
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.services.dealer_kit import collection_service, export_service, page_service
from app.tasks import dealer_kit_export_tasks as task
from tests._pg_fixture import unique_code

PRINT_BASE = os.environ.get("DEALER_KIT_PRINT_BASE_URL", "http://localhost:3020")
_USER = "00000000-0000-4000-8000-00000000e001"


@pytest.fixture()
def committed_db():
    """A session whose writes are REALLY committed, then cleaned up by marker.

    The usual rolled-back fixture cannot work here: a browser and the API read
    through their own connections, and uncommitted rows are invisible to them.
    So this commits for real - and because the local database is a copy of
    production, teardown deletes ONLY the ids this test created, never by
    pattern and never globally.
    """
    from app.database import SessionLocal
    from app.models.base import set_company_scope

    session = SessionLocal()
    set_company_scope(session, frozenset({"00000000-0000-0000-0000-000000000001"}))
    created: dict[str, list] = {"pages": [], "products": [], "categories": [], "uoms": [], "designs": []}
    try:
        yield session, created
    finally:
        try:
            from app.models.dealer_kit import Page, TileTemplate
            from app.models.product import Product, ProductCategory, UnitOfMeasure
            from app.models.download import UserDownload

            # Pages cascade to versions, labels, collections and export
            # requests; downloads cascade to their export request.
            for page_id in created["pages"]:
                session.query(UserDownload).filter(
                    UserDownload.source_entity_id == page_id
                ).delete(synchronize_session=False)
                session.query(Page).filter(Page.id == page_id).delete(
                    synchronize_session=False
                )
            for model, key in (
                (TileTemplate, "designs"),
                (Product, "products"),
                (ProductCategory, "categories"),
                (UnitOfMeasure, "uoms"),
            ):
                for row_id in created[key]:
                    session.query(model).filter(model.id == row_id).delete(
                        synchronize_session=False
                    )
            session.commit()
        finally:
            session.close()


def _frontend_up() -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(PRINT_BASE, timeout=3) as response:
            return response.status < 500
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
    ),
    pytest.mark.skipif(
        not _frontend_up(), reason=f"frontend not reachable at {PRINT_BASE}"
    ),
]


def _product(db, created):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTPDF")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=code,
        product_name=f"ZZT PDF product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("1290.00"),
        invoice_price=Decimal("777.77"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    created["categories"].append(category.id)
    created["uoms"].append(uom.id)
    created["products"].append(product.id)
    return product


def _page_with_products(db, created):
    """A published page carrying one collection block bound to one product."""
    from app.services.dealer_kit import tile_template_service

    product = _product(db, created)
    page = page_service.create_page(
        db,
        name=f"ZZT PDF {unique_code('page')}",
        slug=unique_code("zzt-pdf").lower(),
        user_id=None,
    )
    collection = collection_service.create_collection(
        db, scope="page", page_id=page.id, pinned_product_ids=[product.id]
    )
    design = tile_template_service.create_template(
        db, name=f"ZZT design {unique_code('d')}", fields=["name", "code", "price"]
    )
    created["pages"].append(page.id)
    created["designs"].append(design.id)

    doc = {
        "sections": [
            {
                "id": "s1",
                "name": "Products",
                "style": {"paddingY": "md"},
                "printMode": "include",
                "blocks": [
                    {
                        "id": "b1",
                        "type": "collection",
                        "props": {
                            "kind": "collection",
                            "collectionId": collection.id,
                            "tileTemplateId": design.id,
                            "columns": {"desktop": 3, "tablet": 2, "mobile": 1},
                        },
                    }
                ],
                "layouts": {
                    breakpoint: {
                        "blocks": {"b1": {"colStart": 1, "colSpan": 12, "rowStart": 1, "rowSpan": 6}},
                        "isDerived": breakpoint != "desktop",
                    }
                    for breakpoint in ("desktop", "tablet", "mobile")
                },
            }
        ],
        "printProfile": page_service.DEFAULT_PRINT_PROFILE,
    }

    version = page_service.save_version(
        db, page.id, doc=doc, commit_message="pdf test", user_id=None
    )
    page_service.move_label(db, page.id, "published", version_id=version.id, user_id=None)
    return page, product


def _render(db, page_id, audience, show_invoice_price):
    download = export_service.request_export(
        db,
        page_id=page_id,
        audience=audience,
        show_invoice_price=show_invoice_price,
        user_id=_USER,
    )
    db.commit()  # the browser and the API read through their OWN connections

    url = task._print_url(download.id)
    return task._render_pdf(url, landscape=False, paper="A4"), download


def _pdf_text(pdf_bytes: bytes) -> str:
    """Crude but sufficient: pull readable strings out of the PDF stream."""
    from pypdf import PdfReader
    from io import BytesIO

    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def test_a_request_becomes_a_real_pdf_containing_the_products(committed_db):
    db, created = committed_db
    page, product = _page_with_products(db, created)
    pdf_bytes, _download = _render(db, page.id, "staff", False)

    assert pdf_bytes.startswith(b"%PDF"), "not a PDF"
    assert len(pdf_bytes) > 1000

    text = _pdf_text(pdf_bytes)
    assert product.product_code in text
    # List price is public, so it renders for every audience.
    assert "1,290.00" in text


def test_a_staff_export_and_a_consumer_export_of_one_page_differ(committed_db):
    """The gate item: the audience recorded at enqueue changes the FILE."""
    db, created = committed_db
    page, _product = _page_with_products(db, created)

    staff_pdf, _ = _render(db, page.id, "staff", True)
    consumer_pdf, _ = _render(db, page.id, "consumer", True)

    staff_text = _pdf_text(staff_pdf)
    consumer_text = _pdf_text(consumer_pdf)

    # Same document, same toggle - only the audience differs.
    assert "777.77" in staff_text, "staff copy should carry the invoice price"
    assert "777.77" not in consumer_text, "consumer copy must NOT carry it"
