"""AutoCount ingest Slice 7 — request-for-quotation document (header + RQDTL).

New parent+lines supplier RFQ mirror: idempotent by DocKey; rq_number =
AC-{DocKey}; supplier resolved best-effort (nullable FK); a line whose product
has not synced makes the WHOLE RFQ retryable; lines replaced wholesale;
annotation survives re-sync.

blank_session (isolated scratch schema, create_savepoint join).
"""
import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.procurement import Supplier
from app.models.request_quotation import RequestQuotation, RequestQuotationLine
from app.models.integration_reference import IntegrationReference
from app.services.request_quotation_ingest_service import RequestQuotationIngestService
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return RequestQuotationIngestService(db, integration_id=None)


@pytest.fixture()
def seeded(db):
    cat = ProductCategory(category_code="ZZT-C", category_name="C")
    uom = UnitOfMeasure(uom_code="ZZT-U", uom_name="U")
    db.add_all([cat, uom])
    db.flush()
    p = Product(product_code="ZZT-ITEM", product_name="ZZT Item",
                category_id=cat.id, base_uom_id=uom.id, list_price=0)
    sup = Supplier(supplier_code="ZZT-SUP", supplier_name="ZZT Supplier")
    db.add_all([p, sup])
    db.flush()
    return {"product": p, "supplier": sup}


def _line(product="ZZT-ITEM", qty="7", **extra):
    return {"product_code": product, "uom": "PCS", "location": "HQ", "qty": qty,
            "unit_price": "9.00", "sub_total": "63.00", **extra}


def _rq(dockey="RK1", creditor="ZZT-SUP", **extra):
    return {"source_ref": dockey, "source_doc_no": f"RQ-{dockey}",
            "creditor_code": creditor, "creditor_name": "ZZT Supplier",
            "doc_date": "2026/07/26", "purchase_agent": "PA1",
            "lines": [_line()], **extra}


class TestCreate:
    def test_creates_rfq_with_lines(self, db, svc, seeded):
        res = svc.ingest([_rq()])
        assert res.created == 1
        rq = db.query(RequestQuotation).one()
        assert rq.rq_number == "AC-RK1"
        assert rq.supplier_id == seeded["supplier"].id  # best-effort resolved
        assert rq.purchase_agent == "PA1"
        lines = db.query(RequestQuotationLine).filter_by(request_quotation_id=rq.id).all()
        assert len(lines) == 1
        assert lines[0].product_id == seeded["product"].id
        assert str(lines[0].qty) == "7.0000"

    def test_links_integration_reference(self, db, svc, seeded):
        svc.ingest([_rq()])
        rq = db.query(RequestQuotation).one()
        ref = db.query(IntegrationReference).filter_by(
            entity_type="request_quotations", source_ref="RK1"
        ).one()
        assert ref.entity_id == rq.id

    def test_supplier_unresolved_is_ok(self, db, svc, seeded):
        res = svc.ingest([_rq(creditor="NOPE")])
        assert res.created == 1
        rq = db.query(RequestQuotation).one()
        assert rq.supplier_id is None
        assert rq.creditor_code == "NOPE"

    def test_source_and_supplier_code_via_serializer(self, db, svc, seeded):
        from app.schemas.autocount_mirror import RequestQuotationResponse
        svc.ingest([_rq()])
        rq = db.query(RequestQuotation).one()
        r = RequestQuotationResponse.model_validate(rq)
        assert r.source == "autocount"
        assert r.supplier_code == "ZZT-SUP"
        assert r.lines[0].product_code == "ZZT-ITEM"


class TestIdempotency:
    def test_reingest_updates_in_place(self, db, svc, seeded):
        svc.ingest([_rq()])
        first = db.query(RequestQuotation).one().id
        res = svc.ingest([_rq(purchase_agent="PA2")])
        assert res.updated == 1
        assert db.query(RequestQuotation).count() == 1
        rq = db.query(RequestQuotation).one()
        assert rq.id == first
        assert rq.purchase_agent == "PA2"

    def test_reingest_replaces_lines_wholesale(self, db, svc, seeded):
        svc.ingest([_rq()])
        svc.ingest([_rq(lines=[_line(), _line(qty="1")])])
        rq = db.query(RequestQuotation).one()
        assert db.query(RequestQuotationLine).filter_by(request_quotation_id=rq.id).count() == 2


class TestRetryable:
    def test_missing_product_makes_whole_rfq_retryable(self, db, svc, seeded):
        res = svc.ingest([_rq(lines=[_line(product="PHANTOM")])])
        assert res.retryable == 1
        assert res.created == 0
        assert db.query(RequestQuotation).count() == 0


class TestDryRun:
    def test_dry_run_writes_nothing(self, db, svc, seeded):
        res = svc.ingest([_rq()], dry_run=True)
        assert res.created == 1
        assert db.query(RequestQuotation).count() == 0


class TestAnnotation:
    def test_note_survives_resync(self, db, svc, seeded):
        from app.services.autocount_mirror_service import MirrorReadService
        svc.ingest([_rq()])
        rq = db.query(RequestQuotation).one()
        MirrorReadService(db).annotate(
            RequestQuotation, rq.id, resource="Request Quotation",
            internal_note="chase supplier", follow_up=True,
            set_note=True, set_follow_up=True,
        )
        svc.ingest([_rq(purchase_agent="changed")])
        rq2 = db.query(RequestQuotation).filter_by(id=rq.id).one()
        assert rq2.internal_note == "chase supplier"
        assert rq2.follow_up is True
        assert rq2.purchase_agent == "changed"
