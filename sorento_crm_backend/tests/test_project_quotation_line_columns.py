"""S3: the columns the printed quotation actually carries, on the wire.

The document slice could store `is_rate_only` and could exclude it from every total, but the
LINE schema did not accept it, so the only way to create such a line was to reach past the API
into the service. The route tests said so explicitly rather than pretending otherwise. This file
closes that gap: every printed column is now writable through the endpoint a person uses.

The assertion that earns its keep is the arithmetic one. A rate-only line keeps a unit rate and a
`line_total`, because the customer is being shown a rate - it simply must not be added up. On the
real Cabana Elmina quotation five such alternates would have added RM 235,075 nobody quoted, so
the test states the total both ways round: what it must be, and what it must NOT be.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import Project, ProjectQuotationLine, ProjectQuotationVersion
from app.models.user import User
from app.services import project_quotation_document_service as qdocs
from app.services import project_quotation_service as quotes
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-qline"

# Off the real workbook: 1,046 water closets at RM 250, and the alternate at RM 180 that prints
# as a rate and counts for nothing.
PRICED_QTY = Decimal("1046")
PRICED_RATE = Decimal("250")
ALTERNATE_RATE = Decimal("180")
PRICED_TOTAL = Decimal("261500.00")
WRONG_TOTAL_IF_SUMMED = Decimal("449780.00")


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, code: str) -> Product:
    category = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} Sanitary",
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("300.00"),
    )
    db.add(product)
    db.flush()
    return product


def _project(db, company_id: str, owner: str) -> Project:
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"ZZT-{_uid()[:8]}",
        title=f"{MARKER} Cabana Elmina",
        normalised_title=f"{MARKER} cabana elmina",
        owner_user_id=owner,
    )
    db.add(project)
    db.flush()
    return project


def _scope(db, company_id: str, owner: str):
    project = _project(db, company_id, owner)
    document = qdocs.create_document(db, project=project, actor_user_id=owner)
    scope = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} Apartment units", actor_user_id=owner
    )
    return project, document, scope


def test_every_column_the_printed_quotation_carries_is_writable_through_the_service():
    """These are not decoration: without them a salesperson types the quotation twice.

    The A / B / C letter groups a water closet with its angle valve and its hose, which is one
    item to the customer's QS. The band is the customer's own bill-of-quantities heading. Both
    are free text on purpose, because the next customer numbers their BQ differently.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Baser")
        _project_row, _document, scope = _scope(db, company_id, owner)
        product = _product(db, f"{MARKER}-CWC604-RL")

        line = quotes.upsert_line(
            db,
            version=quotes.current_version(db, scope.id),
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": str(PRICED_RATE),
                "quantity": str(PRICED_QTY),
                "item_label": "A",
                "brand_snapshot": "CABANA",
                "technical_spec": "Washdown, S-trap 100mm",
                "complete_set": "With soft close seat",
                "band_label": "BILL NO 3 PAGE 15/4",
            },
        )
        db.flush()

        stored = (
            db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == line.id).one()
        )
        assert stored.item_label == "A"
        assert stored.brand_snapshot == "CABANA"
        assert stored.technical_spec == "Washdown, S-trap 100mm"
        assert stored.complete_set == "With soft close seat"
        assert stored.band_label == "BILL NO 3 PAGE 15/4"
        assert stored.is_rate_only is False


def test_a_rate_only_line_prints_its_rate_and_is_left_out_of_every_total():
    """The single most expensive mistake this model can make.

    A rate-only line keeps its rate and its line_total, because the customer is being shown a
    price. Adding it up would overstate the quotation, and on the sample that error is over
    RM 188,000 from ONE line. The stored version total, the scope total and the document total
    all have to agree about it, which is why all three are asserted here rather than one.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Baser")
        _project_row, document, scope = _scope(db, company_id, owner)
        priced_product = _product(db, f"{MARKER}-CWC604-RL")
        alternate_product = _product(db, f"{MARKER}-CWC605-RL")
        version = quotes.current_version(db, scope.id)

        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "product_id": priced_product.id,
                "unit_price": str(PRICED_RATE),
                "quantity": str(PRICED_QTY),
            },
        )
        alternate = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "product_id": alternate_product.id,
                "unit_price": str(ALTERNATE_RATE),
                "quantity": str(PRICED_QTY),
                "is_rate_only": True,
            },
        )
        db.flush()

        # The rate is still recorded. It PRINTS; it does not count.
        assert alternate.is_rate_only is True
        assert Decimal(alternate.unit_price) == ALTERNATE_RATE
        assert Decimal(alternate.line_total) > 0

        refreshed = (
            db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id == version.id)
            .one()
        )
        assert Decimal(refreshed.total_amount) == PRICED_TOTAL
        assert Decimal(refreshed.total_amount) != WRONG_TOTAL_IF_SUMMED
        assert qdocs.scope_total(db, scope) == PRICED_TOTAL
        assert qdocs.document_total(db, document) == PRICED_TOTAL


def test_clearing_rate_only_puts_the_money_back_into_the_total():
    """Marking a line is reversible, and the totals have to follow it in both directions.

    An alternate the customer accepts becomes a priced line, and if the stored total only ever
    moved one way the quotation would understate itself for good, which is the harder error to
    notice.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Baser")
        _project_row, _document, scope = _scope(db, company_id, owner)
        product = _product(db, f"{MARKER}-CWC605-RL")
        version = quotes.current_version(db, scope.id)

        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": str(ALTERNATE_RATE),
                "quantity": str(PRICED_QTY),
                "is_rate_only": True,
            },
        )
        db.flush()
        assert qdocs.scope_total(db, scope) == Decimal("0.00")

        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            line=line,
            payload={"is_rate_only": False},
        )
        db.flush()

        expected = (PRICED_QTY * ALTERNATE_RATE).quantize(Decimal("0.01"))
        assert qdocs.scope_total(db, scope) == expected
        refreshed = (
            db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id == version.id)
            .one()
        )
        assert Decimal(refreshed.total_amount) == expected


def test_the_line_response_names_the_printed_columns_the_screen_reads():
    """The screen cannot render a column the serializer does not send.

    Pinned because the request and the response deliberately DISAGREE on one name: the body takes
    `brand_snapshot` (it is a snapshot of the catalogue at quote time) while the response calls it
    `brand` (it is just the brand to a reader). That asymmetry is easy to 'tidy' into a bug.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Baser")
        _project_row, _document, scope = _scope(db, company_id, owner)
        product = _product(db, f"{MARKER}-CWC604-RL")

        quotes.upsert_line(
            db,
            version=quotes.current_version(db, scope.id),
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": str(PRICED_RATE),
                "quantity": str(PRICED_QTY),
                "item_label": "A",
                "brand_snapshot": "CABANA",
                "band_label": "BILL NO 3 PAGE 15/4",
                "is_rate_only": True,
            },
        )
        db.flush()

        rows = quotes.serialize_lines(db, quotes.list_lines(db, quotes.current_version(db, scope.id).id))
        assert len(rows) == 1
        row = rows[0]
        assert row["item_label"] == "A"
        assert row["brand"] == "CABANA"
        assert row["band_label"] == "BILL NO 3 PAGE 15/4"
        assert row["is_rate_only"] is True
