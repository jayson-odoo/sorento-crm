"""AutoCount ingest Slice 1 — credit_terms + tax_codes masters + annotation.

Mirrors the master-ingest contract already proven for warehouses/suppliers
(test_master_ingest.py): canonical validation, idempotent-on-source_ref,
created-vs-updated, adopt-by-business-code, dry-run-writes-nothing. Adds the two
Slice-1 specifics:

  * credit_terms unblocks supplier/customer payment_terms_code resolution --
    previously any code was reported RETRYABLE forever;
  * the annotation columns (internal_note/follow_up) are Sorento-only and must
    survive a re-sync, since ingest never writes them.

Runs on blank_session (isolated scratch schema, create_savepoint join mode) so
the annotation service's real db.commit() cannot touch the prod-copy dev DB.
"""
import pytest
from sqlalchemy import text

from app.models.credit_term import CreditTerm
from app.models.tax_code import TaxCode
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


def _ct(code="30 DAYS", ref=None, **extra):
    return {"source_ref": ref or f"CT-{code}", "code": code, "terms": "Net 30", "term_days": 30, **extra}


def _tx(code="SR", ref=None, **extra):
    return {"source_ref": ref or f"TX-{code}", "code": code, "supply_purchase": "S", "tax_rate": "6.0", **extra}


class TestCreditTermIngest:
    def test_creates_a_new_credit_term(self, db, svc):
        result = svc.ingest("credit_terms", [_ct()])
        assert result.records[0].outcome is IngestOutcome.CREATED
        row = db.query(CreditTerm).filter_by(display_term="30 DAYS").one()
        assert row.term_days == 30
        assert row.is_active is True
        # Ingest never sets annotations.
        assert row.internal_note is None
        assert row.follow_up is False

    def test_idempotent_on_source_ref(self, db, svc):
        svc.ingest("credit_terms", [_ct(term_days=30, ref="CT-1")])
        result = svc.ingest("credit_terms", [_ct(term_days=45, ref="CT-1")])
        assert result.records[0].outcome is IngestOutcome.UPDATED
        assert db.query(CreditTerm).filter_by(display_term="30 DAYS").one().term_days == 45
        assert db.query(CreditTerm).count() == 1

    def test_adopts_an_existing_row_by_display_term(self, db, svc):
        db.execute(text(
            "INSERT INTO credit_terms (id, display_term, is_active, follow_up) "
            "VALUES ('11111111-1111-1111-1111-111111111111', '30 DAYS', true, false)"
        ))
        result = svc.ingest("credit_terms", [_ct()])
        assert result.records[0].outcome is IngestOutcome.UPDATED
        assert result.records[0].entity_id == "11111111-1111-1111-1111-111111111111"

    def test_unknown_fields_are_rejected(self, svc):
        result = svc.ingest("credit_terms", [_ct(**{"DisplayTerm": "leaked"})])
        assert result.records[0].outcome is IngestOutcome.FAILED

    def test_dry_run_writes_nothing(self, db, svc):
        result = svc.ingest("credit_terms", [_ct()], dry_run=True)
        assert result.dry_run is True
        assert result.records[0].outcome is IngestOutcome.CREATED
        assert db.query(CreditTerm).count() == 0


class TestTaxCodeIngest:
    def test_creates_a_new_tax_code(self, db, svc):
        result = svc.ingest("tax_codes", [_tx()])
        assert result.records[0].outcome is IngestOutcome.CREATED
        row = db.query(TaxCode).filter_by(tax_code="SR").one()
        assert str(row.tax_rate) == "6.0000"
        assert row.supply_purchase == "S"

    def test_idempotent_and_updates_rate(self, db, svc):
        svc.ingest("tax_codes", [_tx(ref="TX-1")])
        svc.ingest("tax_codes", [dict(_tx(ref="TX-1"), tax_rate="8.0")])
        assert str(db.query(TaxCode).filter_by(tax_code="SR").one().tax_rate) == "8.0000"
        assert db.query(TaxCode).count() == 1

    def test_missing_required_code_fails(self, svc):
        result = svc.ingest("tax_codes", [{"source_ref": "TX-9"}])
        assert result.records[0].outcome is IngestOutcome.FAILED


class TestSupplierCreditTermResolution:
    """credit_terms landing is what unblocks supplier/customer ingest."""

    def _supplier(self, **extra):
        return {"source_ref": "SUP-1", "code": "ZZT-SUP", "name": "Acme", **extra}

    def test_unresolvable_code_is_retryable(self, db, svc):
        result = svc.ingest("suppliers", [self._supplier(payment_terms_code="NOPE")])
        assert result.records[0].outcome is IngestOutcome.RETRYABLE

    def test_resolvable_code_sets_days_and_creates(self, db, svc):
        svc.ingest("credit_terms", [_ct(code="30 DAYS", term_days=30, ref="CT-1")])
        result = svc.ingest("suppliers", [self._supplier(payment_terms_code="30 DAYS")])
        assert result.records[0].outcome is IngestOutcome.CREATED
        row = db.execute(
            text("SELECT payment_terms_days FROM suppliers WHERE supplier_code = 'ZZT-SUP'")
        ).first()
        assert row[0] == 30

    def test_explicit_days_wins_over_code_lookup(self, db, svc):
        # ESB already knew the number; no credit_term needed.
        result = svc.ingest("suppliers", [self._supplier(payment_terms_days=14)])
        assert result.records[0].outcome is IngestOutcome.CREATED
        row = db.execute(
            text("SELECT payment_terms_days FROM suppliers WHERE supplier_code = 'ZZT-SUP'")
        ).first()
        assert row[0] == 14


class TestAnnotationSurvivesResync:
    def test_annotation_touches_only_two_columns_and_survives_resync(self, db, svc):
        svc.ingest("credit_terms", [_ct(term_days=30, ref="CT-1")])
        row = db.query(CreditTerm).filter_by(display_term="30 DAYS").one()

        MirrorReadService(db).annotate(
            CreditTerm, row.id, resource="Credit Term",
            internal_note="chase finance", follow_up=True,
            set_note=True, set_follow_up=True,
        )
        db.refresh(row)
        assert row.internal_note == "chase finance"
        assert row.follow_up is True

        # Re-sync with a changed business field must NOT clobber the annotation.
        svc.ingest("credit_terms", [_ct(term_days=45, ref="CT-1")])
        db.refresh(row)
        assert row.term_days == 45
        assert row.internal_note == "chase finance"
        assert row.follow_up is True

    def test_partial_patch_only_touches_supplied_field(self, db, svc):
        svc.ingest("tax_codes", [_tx(ref="TX-1")])
        row = db.query(TaxCode).filter_by(tax_code="SR").one()
        rs = MirrorReadService(db)
        rs.annotate(TaxCode, row.id, resource="Tax Code", internal_note="note A",
                    follow_up=None, set_note=True, set_follow_up=False)
        # Only follow_up in the second patch: note must remain.
        rs.annotate(TaxCode, row.id, resource="Tax Code", internal_note=None,
                    follow_up=True, set_note=False, set_follow_up=True)
        db.refresh(row)
        assert row.internal_note == "note A"
        assert row.follow_up is True
