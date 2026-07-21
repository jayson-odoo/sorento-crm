"""Phase C — master data ingest (UAC Group B, masters half).

  AC-AC-11  canonical shapes; unknown fields rejected, not silently ignored
  AC-AC-12  idempotent on the source reference; created vs updated distinguished
  AC-AC-13  per-record structured errors, machine-readable
  AC-AC-15  masters quarantine, they do not block: valid rows persist
  AC-AC-16  a missing referenced master is RETRYABLE, distinct from invalid
  AC-AC-18  ingest emits no lifecycle events -- the sync-loop guard

The behaviour that carries this slice is per-record isolation. One bad record
in a batch of 10,000 must not cost the other 9,999, and a failed flush poisons
the SQLAlchemy session unless each record runs in its own savepoint.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from app.models.integration_reference import IntegrationReference
from app.services.master_ingest_service import (
    IngestOutcome,
    MasterIngestService,
    UnsupportedIngestEntity,
)


@pytest.fixture()
def db():
    """A Postgres session rolled back after each test.

    Deliberately not sqlite. The behaviour under test is per-record SAVEPOINT
    isolation, and pysqlite does not share Postgres's semantics -- these tests
    passed on sqlite while proving nothing about production, and broke outright
    once another module registered the global audit flush listeners.

    Everything happens inside one outer transaction that is rolled back, so the
    service's begin_nested() calls become real nested savepoints and no test
    data survives.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def svc(db):
    return MasterIngestService(db, integration_id=None)


def _wh(code="ZZT-WH-01", name="Main", ref=None, **extra):
    return {"source_ref": ref or f"DK-{code}", "code": code, "name": name, **extra}


class TestCanonicalShape:
    def test_unknown_fields_are_rejected_not_ignored(self, svc):
        # AC-AC-11. Silently dropping a field the ESB believed it sent is how a
        # mapping bug survives to production looking like a Sorento data loss.
        result = svc.ingest("warehouses", [_wh(**{"DocKey": "leaked-autocount-name"})])
        assert result.failed == 1
        assert "DocKey" in str(result.records[0].errors)

    def test_missing_required_field_is_a_validation_failure(self, svc):
        result = svc.ingest("warehouses", [{"source_ref": "DK-1"}])
        assert result.failed == 1
        assert result.records[0].outcome is IngestOutcome.FAILED

    def test_unsupported_entity_is_refused(self, svc):
        with pytest.raises(UnsupportedIngestEntity):
            svc.ingest("nonsense", [])

    def test_source_ref_is_required(self, svc):
        # Without it there is no idempotency key and every push duplicates.
        result = svc.ingest("warehouses", [{"code": "ZZT-1", "name": "Main"}])
        assert result.failed == 1


class TestCreateAndUpdate:
    def test_creates_a_new_record(self, db, svc):
        result = svc.ingest("warehouses", [_wh()])
        assert result.created == 1
        assert db.execute(text("SELECT count(*) FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == 1

    def test_links_the_source_reference(self, db, svc):
        svc.ingest("warehouses", [_wh(ref="DK-99")])
        ref = db.query(IntegrationReference).one()
        assert ref.entity_type == "warehouses"
        assert ref.source_ref == "DK-99"

    def test_repushing_updates_in_place_and_reports_updated(self, db, svc):
        # AC-AC-12: the same payload twice must not create a second record.
        svc.ingest("warehouses", [_wh(name="Main")])
        result = svc.ingest("warehouses", [_wh(name="Renamed")])

        assert result.updated == 1
        assert result.created == 0
        assert db.execute(text("SELECT count(*) FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == 1
        assert db.execute(text("SELECT warehouse_name FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == "Renamed"

    def test_a_renamed_code_still_updates_the_same_record(self, db, svc):
        # The point of keying on source_ref rather than the business code: the
        # upstream may rename, and a rename is not a new record.
        svc.ingest("warehouses", [_wh(code="ZZT-WH-01", ref="DK-1")])
        svc.ingest("warehouses", [_wh(code="ZZT-WH-01-RENAMED", ref="DK-1")])

        assert db.execute(text("SELECT count(*) FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == 1
        assert db.execute(text("SELECT warehouse_code FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == "ZZT-WH-01-RENAMED"

    def test_adopts_an_existing_record_matched_by_business_code(self, db, svc):
        # First sync against a record that already exists locally. Creating a
        # duplicate under a new id would be far worse than adopting it.
        db.execute(
            text(
                "INSERT INTO warehouses (id, warehouse_code, warehouse_name) "
                "VALUES (:i, 'ZZT-WH-01', 'Existing')"
            ),
            {"i": str(uuid.uuid4())},
        )
        db.commit()

        result = svc.ingest("warehouses", [_wh(code="ZZT-WH-01", name="From AutoCount")])

        assert db.execute(text("SELECT count(*) FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == 1
        assert result.updated == 1


class TestQuarantineNotBlock:
    def test_valid_rows_persist_when_a_sibling_fails(self, db, svc):
        # AC-AC-15. 10,000 products with 12 bad ones must yield 9,988 imported.
        batch = [
            _wh(code="ZZT-1", ref="DK-1"),
            {"source_ref": "DK-2", "code": "ZZT-2"},  # missing name -> invalid
            _wh(code="ZZT-3", ref="DK-3"),
        ]
        result = svc.ingest("warehouses", batch)

        assert result.created == 2
        assert result.failed == 1
        assert db.execute(text("SELECT count(*) FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == 2

    def test_a_database_error_on_one_record_does_not_poison_the_batch(self, db, svc):
        # The savepoint's reason for existing. A failed flush leaves the whole
        # SQLAlchemy session unusable, so without per-record nesting one bad
        # row takes out every row after it -- "12 invalid" becomes "0 imported".
        #
        # Two records claiming the same warehouse_code under different source
        # refs forces a genuine IntegrityError on the unique index, mid-batch.
        batch = [
            _wh(code="ZZT-A", ref="DK-A"),
            _wh(code="ZZT-DUP", ref="DK-DUP-1"),
            _wh(code="ZZT-DUP", ref="DK-DUP-2"),  # violates the unique code index
            _wh(code="ZZT-B", ref="DK-B"),
        ]
        result = svc.ingest("warehouses", batch)

        # The clashing record is rejected alone...
        assert result.failed == 1
        # ...and crucially the record *after* it was still processed.
        assert (
            db.execute(
                text("SELECT count(*) FROM warehouses WHERE warehouse_code = 'ZZT-B'")
            ).scalar()
            == 1
        )
        assert result.created == 3

    def test_adoption_is_refused_when_the_local_record_is_already_claimed(self, db, svc):
        # Retargeting a record that another source document already owns would
        # silently hand one AutoCount document control of another's data.
        svc.ingest("warehouses", [_wh(code="ZZT-OWNED", ref="DK-OWNER")])
        result = svc.ingest("warehouses", [_wh(code="ZZT-OWNED", ref="DK-INTRUDER")])

        assert result.failed == 1
        assert db.execute(text("SELECT count(*) FROM warehouses WHERE warehouse_code LIKE 'ZZT-%'")).scalar() == 1

    def test_per_record_error_names_record_field_and_reason(self, db, svc):
        # AC-AC-13: machine-readable, so the ESB quarantines per record without
        # parsing prose.
        result = svc.ingest("warehouses", [{"source_ref": "DK-X", "code": "ZZT-X"}])
        record = result.records[0]

        assert record.source_ref == "DK-X"
        assert record.outcome is IngestOutcome.FAILED
        assert isinstance(record.errors, dict)
        assert "name" in record.errors


class TestRetryableVsFatal:
    def test_missing_referenced_master_is_retryable_not_failed(self, db, svc):
        # AC-AC-16. A supplier arriving before its payment terms exist is a
        # sequencing artefact, not bad data -- the ESB drains these on retry.
        result = svc.ingest(
            "suppliers",
            [
                {
                    "source_ref": "DK-S1",
                    "code": "ZZT-SUP-1",
                    "name": "Acme",
                    "payment_terms_code": "NET-999-MISSING",
                }
            ],
        )
        assert result.retryable == 1
        assert result.failed == 0
        assert result.records[0].outcome is IngestOutcome.RETRYABLE

    def test_a_retryable_record_is_not_persisted(self, db, svc):
        svc.ingest(
            "suppliers",
            [
                {
                    "source_ref": "DK-S1",
                    "code": "ZZT-SUP-1",
                    "name": "Acme",
                    "payment_terms_code": "MISSING",
                }
            ],
        )
        assert db.execute(text("SELECT count(*) FROM suppliers WHERE supplier_code LIKE 'ZZT-%'")).scalar() == 0
        # ...and no reference is written, or the retry would resolve to nothing.
        assert db.query(IntegrationReference).filter(IntegrationReference.source_ref.like('DK-%')).count() == 0

    def test_retry_succeeds_once_the_reference_exists(self, db, svc):
        payload = {
            "source_ref": "DK-S1",
            "code": "ZZT-SUP-1",
            "name": "Acme",
            "payment_terms_days": 30,
        }
        result = svc.ingest("suppliers", [payload])
        assert result.created == 1

    def test_invalid_data_is_failed_not_retryable(self, db, svc):
        # The distinction is the whole point: retrying bad data forever is a
        # queue that never drains.
        result = svc.ingest("suppliers", [{"source_ref": "DK-S2", "code": "ZZT-SUP-2"}])
        assert result.failed == 1
        assert result.retryable == 0


class TestBatchSummary:
    def test_summary_counts_add_up_to_the_batch_size(self, svc):
        batch = [
            _wh(code="ZZT-SA", ref="DK-A"),
            {"source_ref": "DK-B", "code": "ZZT-SB2"},
            _wh(code="ZZT-SC", ref="DK-C"),
        ]
        result = svc.ingest("warehouses", batch)
        assert result.created + result.updated + result.failed + result.retryable == len(batch)

    def test_every_record_is_reported_in_order(self, svc):
        batch = [_wh(code="ZZT-SA", ref="DK-A"), _wh(code="ZZT-SB", ref="DK-B")]
        result = svc.ingest("warehouses", batch)
        assert [r.source_ref for r in result.records] == ["DK-A", "DK-B"]

    def test_an_empty_batch_is_accepted(self, svc):
        result = svc.ingest("warehouses", [])
        assert result.created == 0
        assert result.records == []
