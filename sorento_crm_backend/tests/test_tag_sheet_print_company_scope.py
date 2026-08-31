"""The tag sheet render payload answers for ONE company.

``/api/v1/public/print/tag-sheet/{download_id}`` is unauthenticated by
necessity - headless Chromium has no CRM session - so the session it runs on
sits at the fail-closed UNSET scope and the route has to widen it by hand to
find the page at all. It widened it to ALL companies and then resolved the
whole payload there: every product, every price, every asset and every font
another company owns was in reach of a token issued for this one.

The sibling catalogue route on the same module already does the right thing:
read the page across companies to learn WHICH company, then pin the scope to
that company for everything after. This proves the tag sheet route does too.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.company import Company
from app.models.dealer_kit import ExportRequest, Page, PageVersion
from app.models.download import DownloadStatus, UserDownload
from app.models.access import RespondContact
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.dealer_kit import render_token
from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db: Session):
    from app.database import get_db as _database_get_db
    from app.dependencies import get_db as _dependencies_get_db

    def _override_get_db():
        yield db

    app.dependency_overrides[_database_get_db] = _override_get_db
    app.dependency_overrides[_dependencies_get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _other_company(db: Session) -> str:
    company_id = str(uuid.uuid4())
    db.execute(
        Company.__table__.insert().values(
            id=company_id, name="ZZT Other Co", code=unique_code("OC")[:20], is_active=True,
        )
    )
    db.flush()
    return company_id


def _product(db: Session, company_id: str) -> Product:
    """A product with its FK chain, stamped for a NAMED company."""
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("cat"),
        category_name=unique_code("Category"),
        company_id=company_id,
    )
    brand = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code("br"),
        brand_name=unique_code("Brand"),
        company_id=company_id,
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_code=unique_code("uom"), uom_name="Each",
    )
    db.add_all([category, brand, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("prod"),
        product_name=unique_code("Product"),
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=100.00,
        company_id=company_id,
    )
    db.add(product)
    db.flush()
    return product


def _tag_sheet_download(db: Session, request, page_company_id: str) -> str:
    """A queued tag sheet export for ``request``, and the download id to fetch it."""
    page = Page(
        id=str(uuid.uuid4()),
        name=f"Tags - {request.doc_number}",
        slug=f"tag-sheet-{request.doc_number.lower()}",
        kind="tag_sheet",
        request_id=request.id,
        company_id=page_company_id,
    )
    db.add(page)
    db.flush()
    request.page_id = page.id

    version = PageVersion(
        id=str(uuid.uuid4()), page_id=page.id, version=1, doc={"sheets": []},
    )
    db.add(version)
    db.flush()

    download = UserDownload(
        id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        kind="dealer_kit_tag_sheet_pdf",
        source_entity_type="price_tag_request",
        source_entity_id=request.id,
        status=DownloadStatus.PENDING.value,
        filename="zzt-tags.pdf",
    )
    db.add(download)
    db.flush()
    db.add(
        ExportRequest(
            id=str(uuid.uuid4()),
            download_id=download.id,
            page_id=page.id,
            page_version_id=version.id,
            audience="staff",
            show_invoice_price=False,
        )
    )
    db.flush()
    return download.id


def test_the_payload_carries_this_company_and_no_other(db: Session, client: TestClient):
    """A line pointing at ANOTHER company's product resolves to nothing.

    The request, the page and one of its two products belong to Sorento; the
    second product belongs to a different company. Rendered at scope None, the
    foreign product came back with its code, its name and its price and would
    have been printed on Sorento's tags.
    """
    other_company_id = _other_company(db)
    mine = _product(db, _SORENTO)
    theirs = _product(db, other_company_id)

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=_SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {"line_type": "product", "product_id": mine.id},
                {"line_type": "product", "product_id": theirs.id},
            ],
        },
    )
    db.flush()
    line_ids = {line.product_id: line.id for line in request.lines}

    download_id = _tag_sheet_download(db, request, _SORENTO)
    db.flush()

    response = client.get(
        f"/api/v1/public/print/tag-sheet/{download_id}",
        params={"token": render_token.issue(download_id)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    resolved = payload["resolvedData"]

    # This company's line is there...
    assert line_ids[mine.id] in resolved
    assert resolved[line_ids[mine.id]]["code"] == mine.product_code
    # ...and the other company's is not, by id or by code.
    assert line_ids[theirs.id] not in resolved
    assert theirs.product_code not in response.text
