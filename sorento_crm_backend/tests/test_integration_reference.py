"""Phase B — the integration reference table (UAC Group D).

Replaces the plan's per-table `source_system`/`source_ref` columns with a single
polymorphic mapping table: nine business tables stay untouched, and adding a
tenth entity type needs no DDL.

  AC-AC-21  consumed entities carry a source system and reference
  AC-AC-22  source_ref holds AutoCount's stable DocKey, never the mutable DocNo
  AC-AC-23  no row is left in a state that breaks a later sync

Two properties carry the design, because a polymorphic table has no foreign
keys to lean on:

  * **entity_type is an allowlist.** It reaches a table name, and it arrives
    from an ingest payload. An unchecked value is an injection surface.
  * **A reference whose target has been deleted must not resolve.** Nothing
    cascades, so a stale row would otherwise make ingest 'update' a record that
    no longer exists.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.integration_reference import IntegrationReference
from app.services.integration_reference_service import (
    SUPPORTED_ENTITY_TYPES,
    IntegrationReferenceService,
    UnsupportedEntityType,
)
from tests._sqlite_compat import create_all_sqlite_safe


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    create_all_sqlite_safe(Base.metadata, engine, tables=[IntegrationReference.__table__])
    session = sessionmaker(bind=engine)()
    # Minimal stand-in for the business table the service checks existence against.
    session.execute(text("CREATE TABLE products (id VARCHAR PRIMARY KEY)"))
    session.execute(text("CREATE TABLE orders (id VARCHAR PRIMARY KEY)"))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def svc(db):
    return IntegrationReferenceService(db)


def _product(db, pid=None):
    pid = pid or str(uuid.uuid4())
    db.execute(text("INSERT INTO products (id) VALUES (:i)"), {"i": pid})
    db.commit()
    return pid


class TestEntityTypeAllowlist:
    def test_the_nine_consumed_entities_are_supported(self):
        assert SUPPORTED_ENTITY_TYPES == {
            "products",
            "stock",
            "warehouses",
            "suppliers",
            "customers",
            "picking_headers",
            "picking_lines",
            "orders",
            "order_lines",
        }

    def test_unknown_entity_type_is_rejected_on_link(self, svc):
        with pytest.raises(UnsupportedEntityType):
            svc.link(entity_type="nonsense", entity_id="x", source_ref="DK-1")

    def test_unknown_entity_type_is_rejected_on_lookup(self, svc):
        with pytest.raises(UnsupportedEntityType):
            svc.resolve(entity_type="nonsense", source_ref="DK-1")

    def test_a_sql_injection_attempt_is_rejected_not_executed(self, svc):
        # entity_type reaches a table name and arrives from an ingest payload.
        with pytest.raises(UnsupportedEntityType):
            svc.resolve(entity_type="products; DROP TABLE products; --", source_ref="DK-1")


class TestLinking:
    def test_link_records_the_mapping(self, db, svc):
        pid = _product(db)
        ref = svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")

        assert ref.entity_type == "products"
        assert ref.entity_id == pid
        assert ref.source_ref == "DK-100"
        assert ref.source_system == "autocount"

    def test_relinking_the_same_source_ref_updates_in_place(self, db, svc):
        # AC-AC-12 idempotency rests on this: a re-push must not duplicate.
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")

        assert db.query(IntegrationReference).count() == 1

    def test_doc_no_is_stored_for_display_but_is_not_the_key(self, db, svc):
        # AC-AC-22: DocNo is mutable (AutoCount exposes NewDocNo), so a rename
        # must still resolve to the same local row.
        pid = _product(db)
        svc.link(
            entity_type="products", entity_id=pid, source_ref="DK-100", source_doc_no="PO-0001"
        )
        svc.link(
            entity_type="products", entity_id=pid, source_ref="DK-100", source_doc_no="PO-9999"
        )

        assert svc.resolve(entity_type="products", source_ref="DK-100") == pid
        assert db.query(IntegrationReference).one().source_doc_no == "PO-9999"

    def test_records_which_integration_wrote_it(self, db, svc):
        pid = _product(db)
        ref = svc.link(
            entity_type="products", entity_id=pid, source_ref="DK-1", integration_id="int-9"
        )
        assert ref.integration_id == "int-9"

    def test_same_source_ref_may_exist_for_different_entity_types(self, db, svc):
        # DocKey is only unique within an AutoCount entity, so a product and an
        # order can legitimately share the value.
        pid = _product(db)
        oid = str(uuid.uuid4())
        db.execute(text("INSERT INTO orders (id) VALUES (:i)"), {"i": oid})
        db.commit()

        svc.link(entity_type="products", entity_id=pid, source_ref="1")
        svc.link(entity_type="orders", entity_id=oid, source_ref="1")

        assert db.query(IntegrationReference).count() == 2


class TestUniqueness:
    def test_two_local_rows_cannot_claim_the_same_source_ref(self, db, svc):
        # Otherwise one AutoCount document maps to two Sorento records and the
        # next sync silently updates whichever it finds first.
        a, b = _product(db), _product(db)
        svc.link(entity_type="products", entity_id=a, source_ref="DK-1")
        with pytest.raises(Exception):
            svc.link(entity_type="products", entity_id=b, source_ref="DK-1")
            db.commit()

    def test_one_local_row_cannot_have_two_source_refs(self, db, svc):
        # A record has one origin. Two would make "where did this come from?"
        # unanswerable and ownership rules ambiguous.
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-1")
        with pytest.raises(Exception):
            svc.link(entity_type="products", entity_id=pid, source_ref="DK-2")
            db.commit()


class TestResolution:
    def test_resolves_a_source_ref_to_its_local_id(self, db, svc):
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        assert svc.resolve(entity_type="products", source_ref="DK-100") == pid

    def test_unknown_source_ref_resolves_to_none(self, svc):
        assert svc.resolve(entity_type="products", source_ref="never-seen") is None

    def test_origin_of_a_linked_record_is_reported(self, db, svc):
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        origin = svc.origin_of(entity_type="products", entity_id=pid)
        assert origin is not None
        assert origin.source_system == "autocount"

    def test_absence_of_a_reference_means_locally_created(self, db, svc):
        # The design decision that removes the backfill: no row == manual.
        # ~110k existing records would otherwise need a reference saying nothing.
        pid = _product(db)
        assert svc.origin_of(entity_type="products", entity_id=pid) is None
        assert svc.is_externally_sourced(entity_type="products", entity_id=pid) is False


class TestIdentifierTyping:
    """Most consumed tables key on Postgres ``uuid``, but entity_id is varchar
    because it addresses nine tables with differing key types."""

    def test_a_uuid_input_round_trips_as_its_string_form(self, db, svc):
        pid = uuid.uuid4()
        db.execute(text("INSERT INTO products (id) VALUES (:i)"), {"i": str(pid)})
        db.commit()
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-UUID")

        resolved = svc.resolve(entity_type="products", source_ref="DK-UUID")
        assert resolved == str(pid)
        # The trap this pins: a caller holding the UUID object must compare as
        # strings. Believing these differ would make ingest treat an existing
        # record as new and create the duplicate the table exists to prevent.
        assert resolved != pid
        assert str(resolved) == str(pid)

    def test_origin_lookup_accepts_either_form(self, db, svc):
        pid = uuid.uuid4()
        db.execute(text("INSERT INTO products (id) VALUES (:i)"), {"i": str(pid)})
        db.commit()
        svc.link(entity_type="products", entity_id=str(pid), source_ref="DK-UUID2")

        assert svc.origin_of(entity_type="products", entity_id=pid) is not None
        assert svc.origin_of(entity_type="products", entity_id=str(pid)) is not None


class TestOrphanHandling:
    def test_a_reference_to_a_deleted_record_does_not_resolve(self, db, svc):
        # Nothing cascades in a polymorphic table, so this is the guard that
        # stops ingest 'updating' a row that no longer exists.
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        db.execute(text("DELETE FROM products WHERE id = :i"), {"i": pid})
        db.commit()

        assert svc.resolve(entity_type="products", source_ref="DK-100") is None

    def test_the_orphaned_reference_is_cleaned_up_on_discovery(self, db, svc):
        # Lazily, on the path that notices -- not via a scheduled sweep, since
        # the scheduler is opt-in and defaults off in this codebase.
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        db.execute(text("DELETE FROM products WHERE id = :i"), {"i": pid})
        db.commit()

        svc.resolve(entity_type="products", source_ref="DK-100")
        assert db.query(IntegrationReference).count() == 0

    def test_cleanup_frees_the_source_ref_for_relinking(self, db, svc):
        # Re-importing a deleted document must succeed rather than tripping the
        # unique index on a reference nobody can reach.
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        db.execute(text("DELETE FROM products WHERE id = :i"), {"i": pid})
        db.commit()
        svc.resolve(entity_type="products", source_ref="DK-100")

        replacement = _product(db)
        svc.link(entity_type="products", entity_id=replacement, source_ref="DK-100")
        assert svc.resolve(entity_type="products", source_ref="DK-100") == replacement

    def test_unlink_removes_the_mapping(self, db, svc):
        pid = _product(db)
        svc.link(entity_type="products", entity_id=pid, source_ref="DK-100")
        svc.unlink(entity_type="products", entity_id=pid)
        assert db.query(IntegrationReference).count() == 0
