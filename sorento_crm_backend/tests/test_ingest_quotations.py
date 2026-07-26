"""AutoCount ingest Slice 6 — quotation document (header + QTDTL) mirror.

New parent+lines document: idempotent by DocKey via integration_references;
quote_number = AC-{DocKey}; a line whose product has not synced makes the WHOLE
quotation retryable (never half-written); lines replaced wholesale on re-push;
annotation columns on the header survive re-sync.

blank_session (isolated scratch schema, create_savepoint join) so raw-SQL inserts
+ the service commits stay contained.
"""
import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.quotation import Quotation, QuotationLine
from app.models.integration_reference import IntegrationReference
from app.services.quotation_ingest_service import QuotationIngestService
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return QuotationIngestService(db, integration_id=None)


@pytest.fixture()
def seeded(db):
    cat = ProductCategory(category_code="ZZT-C", category_name="C")
    uom = UnitOfMeasure(uom_code="ZZT-U", uom_name="U")
    db.add_all([cat, uom])
    db.flush()
    p = Product(product_code="ZZT-ITEM", product_name="ZZT Item",
                category_id=cat.id, base_uom_id=uom.id, list_price=0)
    db.add(p)
    db.flush()
    return {"product": p}


def _line(product="ZZT-ITEM", qty="5", **extra):
    return {"product_code": product, "uom": "PCS", "location": "HQ", "qty": qty,
            "unit_price": "12.50", "sub_total": "62.50", "tax_code": "SR",
            "tax_rate": "6", "tax": "3.75", "description": "line desc", **extra}


def _quote(dockey="QK1", **extra):
    return {"source_ref": dockey, "source_doc_no": f"QT-{dockey}",
            "debtor_code": "D001", "debtor_name": "Debtor One",
            "doc_date": "2026/07/26", "attention": "Mr X", "terms": "30 days",
            "sales_agent": "AG1", "lines": [_line()], **extra}


class TestCreate:
    def test_creates_quotation_with_lines(self, db, svc, seeded):
        res = svc.ingest([_quote()])
        assert res.created == 1
        q = db.query(Quotation).one()
        assert q.quote_number == "AC-QK1"
        assert q.source_doc_no == "QT-QK1"
        assert q.debtor_name == "Debtor One"
        assert q.is_cancelled is False
        lines = db.query(QuotationLine).filter_by(quotation_id=q.id).all()
        assert len(lines) == 1
        assert lines[0].product_id == seeded["product"].id
        assert lines[0].tax_code == "SR"
        assert str(lines[0].qty) == "5.0000"

    def test_links_integration_reference(self, db, svc, seeded):
        svc.ingest([_quote()])
        q = db.query(Quotation).one()
        ref = db.query(IntegrationReference).filter_by(
            entity_type="quotations", source_ref="QK1"
        ).one()
        assert ref.entity_id == q.id
        assert ref.source_doc_no == "QT-QK1"

    def test_source_defaults_autocount_via_serializer(self, db, svc, seeded):
        from app.schemas.autocount_mirror import QuotationResponse
        svc.ingest([_quote()])
        q = db.query(Quotation).one()
        r = QuotationResponse.model_validate(q)
        assert r.source == "autocount"
        assert r.lines[0].product_code == "ZZT-ITEM"


class TestIdempotency:
    def test_reingest_updates_in_place(self, db, svc, seeded):
        svc.ingest([_quote()])
        first = db.query(Quotation).one().id
        res = svc.ingest([_quote(attention="Ms Y")])
        assert res.updated == 1
        assert db.query(Quotation).count() == 1
        q = db.query(Quotation).one()
        assert q.id == first
        assert q.attention == "Ms Y"

    def test_reingest_replaces_lines_wholesale(self, db, svc, seeded):
        svc.ingest([_quote()])
        svc.ingest([_quote(lines=[_line(), _line(qty="9")])])
        q = db.query(Quotation).one()
        assert db.query(QuotationLine).filter_by(quotation_id=q.id).count() == 2


class TestRetryable:
    def test_missing_product_makes_whole_quotation_retryable(self, db, svc, seeded):
        res = svc.ingest([_quote(lines=[_line(product="PHANTOM")])])
        assert res.retryable == 1
        assert res.created == 0
        assert db.query(Quotation).count() == 0  # never half-written


class TestDryRun:
    def test_dry_run_writes_nothing(self, db, svc, seeded):
        res = svc.ingest([_quote()], dry_run=True)
        assert res.created == 1  # verdict says it WOULD create
        assert db.query(Quotation).count() == 0


class TestAnnotation:
    def test_note_survives_resync(self, db, svc, seeded):
        from app.services.autocount_mirror_service import MirrorReadService
        svc.ingest([_quote()])
        q = db.query(Quotation).one()
        MirrorReadService(db).annotate(
            Quotation, q.id, resource="Quotation",
            internal_note="follow up with debtor", follow_up=True,
            set_note=True, set_follow_up=True,
        )
        # Re-push must NOT clobber the annotation (ingest never writes those cols).
        svc.ingest([_quote(attention="changed")])
        q2 = db.query(Quotation).filter_by(id=q.id).one()
        assert q2.internal_note == "follow up with debtor"
        assert q2.follow_up is True
        assert q2.attention == "changed"
