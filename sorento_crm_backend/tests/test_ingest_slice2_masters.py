"""AutoCount ingest Slice 2 — sales_agents, payment_methods, tax_entities.

Flat masters, same contract as Slice 1: canonical validation, idempotent on
source_ref, created-vs-updated, adopt-by-business-code, dry-run-writes-nothing,
plus the ingest-safe annotation. Runs on blank_session (isolated scratch schema,
create_savepoint join) so the annotation service's real commit stays contained.
"""
import pytest
from sqlalchemy import text

from app.models.payment_method import PaymentMethod
from app.models.sales_agent import SalesAgent
from app.models.tax_entity import TaxEntity
from app.services.autocount_mirror_service import MirrorReadService
from app.services.master_ingest_service import IngestOutcome, MasterIngestService
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return MasterIngestService(db, integration_id=None)


class TestSalesAgentIngest:
    def _p(self, code="ZZT-AGENT", ref=None, **extra):
        return {"source_ref": ref or f"SA-{code}", "code": code, "description": code, **extra}

    def test_creates(self, db, svc):
        r = svc.ingest("sales_agents", [self._p()])
        assert r.records[0].outcome is IngestOutcome.CREATED
        row = db.query(SalesAgent).filter_by(sales_agent="ZZT-AGENT").one()
        assert row.is_active is True
        assert row.internal_note is None

    def test_idempotent(self, db, svc):
        svc.ingest("sales_agents", [self._p(ref="SA-1", description="A")])
        r = svc.ingest("sales_agents", [self._p(ref="SA-1", description="B")])
        assert r.records[0].outcome is IngestOutcome.UPDATED
        assert db.query(SalesAgent).count() == 1

    def test_unknown_field_rejected(self, svc):
        r = svc.ingest("sales_agents", [self._p(**{"SalesAgent": "leaked"})])
        assert r.records[0].outcome is IngestOutcome.FAILED

    def test_dry_run_writes_nothing(self, db, svc):
        r = svc.ingest("sales_agents", [self._p()], dry_run=True)
        assert r.records[0].outcome is IngestOutcome.CREATED
        assert db.query(SalesAgent).count() == 0


class TestPaymentMethodIngest:
    def _p(self, code="ZZT-CASH", ref=None, **extra):
        return {"source_ref": ref or f"PM-{code}", "code": code, "description": "Cash",
                "bank_account": "111", "journal_type": "CB", **extra}

    def test_creates_with_all_columns(self, db, svc):
        r = svc.ingest("payment_methods", [self._p()])
        assert r.records[0].outcome is IngestOutcome.CREATED
        row = db.query(PaymentMethod).filter_by(payment_method="ZZT-CASH").one()
        assert row.bank_account == "111"
        assert row.journal_type == "CB"

    def test_adopts_by_code(self, db, svc):
        db.execute(text(
            "INSERT INTO payment_methods (id, payment_method, is_active, follow_up) "
            "VALUES ('22222222-2222-2222-2222-222222222222', 'ZZT-CASH', true, false)"
        ))
        r = svc.ingest("payment_methods", [self._p()])
        assert r.records[0].outcome is IngestOutcome.UPDATED
        assert r.records[0].entity_id == "22222222-2222-2222-2222-222222222222"


class TestTaxEntityIngest:
    def _p(self, code="ZZT-TE-1", ref=None, **extra):
        return {"source_ref": ref or f"TE-{code}", "code": code, "name": "Acme Bhd",
                "tin": "C123", "tax_classification": 7, "msic_code": "01113",
                "country_code": "MYS", **extra}

    def test_creates_wide_row(self, db, svc):
        r = svc.ingest("tax_entities", [self._p()])
        assert r.records[0].outcome is IngestOutcome.CREATED
        row = db.query(TaxEntity).filter_by(tax_entity_id="ZZT-TE-1").one()
        assert row.name == "Acme Bhd"
        assert row.tax_classification == 7
        assert row.country_code == "MYS"

    def test_idempotent_on_surrogate(self, db, svc):
        svc.ingest("tax_entities", [self._p(ref="TE-1", name="Old")])
        svc.ingest("tax_entities", [self._p(ref="TE-1", name="New")])
        assert db.query(TaxEntity).filter_by(tax_entity_id="ZZT-TE-1").one().name == "New"
        assert db.query(TaxEntity).count() == 1


class TestAnnotationSurvivesResync:
    def test_note_and_flag_survive_resync(self, db, svc):
        svc.ingest("sales_agents", [{"source_ref": "SA-1", "code": "ZZT-A", "description": "x"}])
        row = db.query(SalesAgent).filter_by(sales_agent="ZZT-A").one()
        MirrorReadService(db).annotate(
            SalesAgent, row.id, resource="Sales Agent",
            internal_note="follow up", follow_up=True, set_note=True, set_follow_up=True,
        )
        svc.ingest("sales_agents", [{"source_ref": "SA-1", "code": "ZZT-A", "description": "y"}])
        db.refresh(row)
        assert row.description == "y"
        assert row.internal_note == "follow up"
        assert row.follow_up is True
