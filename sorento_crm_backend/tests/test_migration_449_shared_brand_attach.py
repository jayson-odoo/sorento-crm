"""AC-H7 - migration 449, run directly rather than asserted against the live DB.

`documentation/plans/multi-company/shared-brand-attachments-acceptance-criteria.md`
AC-H7: id <= 32 chars, `down_revision` is the main head at branch time, one
head after upgrade, downgrade restores NOT NULL on
`attachment_directories.company_id` (after stamping NULL rows with the
incumbent company), drops `is_shared`, restores the old (non-coalesced)
certificate identity index.

A fourth piece landed with the S4 slice (certificate follow, R5): migration 312
already gave `certificates.company_id` NOT NULL, which the ORM-level
`nullable=True` never surfaced against `blank_session`'s `create_all` schema
(hence `upgrade()`'s DROP NOT NULL on it being exercised here, same as the
`attachment_directories` piece). Downgrade restores that NOT NULL too (after
stamping any NULL rows to Sorento, same pattern), which makes the "two NULL
rows collide" scenario for the OLD plain index genuinely unreachable post-
downgrade: a NULL company_id is rejected before the index is ever consulted.
That is a STRONGER guarantee than what the old index alone gave, so the test
below asserts the NOT NULL rejection rather than the old duplicate-NULL
behaviour it can no longer produce.

`tests/test_alembic_revision_ids.py` already asserts id-length and
single-head GRAPH-WIDE; this file is the one that actually EXECUTES 449's
`upgrade()`/`downgrade()` on a scratch schema, the way
`tests/test_migration_320_company_routing.py` does for its migration -
running the function is what proves the guard logic (stamp-before-NOT-NULL,
idempotent re-run) actually behaves, not just that the id is well-formed.

The scratch schema `blank_session` builds already matches the CURRENT models
(nullable `company_id`, `is_shared` present) since it comes from
`Base.metadata.create_all`, not from replaying migrations - so `upgrade()` is
exercised as a re-run (idempotent) here, and `downgrade()` is exercised as the
thing that actually changes the schema shape, which is where AC-H7's real
content lives.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"
REVISION_ID = "449_shared_brand_attach"
MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / f"{REVISION_ID}.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m449", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()
    return module


def _run_downgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.downgrade()


def _script_directory() -> ScriptDirectory:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(cfg)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _current_schema(db) -> str:
    return db.execute(text("SELECT current_schema()")).scalar()


# --------------------------------------------------------------------------- #
# Identity: id length, down_revision, single head
# --------------------------------------------------------------------------- #


def test_revision_id_fits_the_32_char_column():
    assert len(REVISION_ID) <= 32, REVISION_ID


def test_down_revision_is_the_main_head_at_branch_time():
    module = _load_migration()
    assert module.down_revision == "448_merge_s6b_ptag"


def test_449_is_the_single_head_of_the_whole_graph():
    heads = _script_directory().get_heads()
    assert heads == [REVISION_ID], (
        f"449 must be the ONLY head after upgrade; found {heads}"
    )


# --------------------------------------------------------------------------- #
# upgrade() - idempotent re-run (the shared dev DB gets this applied by hand,
# same lesson as migration 320's own `test_migration_is_rerunnable`)
# --------------------------------------------------------------------------- #


def test_upgrade_is_rerunnable(db):
    _run_upgrade(db)
    _run_upgrade(db)

    schema = _current_schema(db)
    cols = db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'attachment_types' AND column_name = 'is_shared' "
            "AND table_schema = :s"
        ),
        {"s": schema},
    ).scalar()
    assert cols == 1

    idx = db.execute(
        text(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = :s "
            "AND indexname = 'uq_certificates_company_scheme_number'"
        ),
        {"s": schema},
    ).scalar()
    assert idx == 1


def test_upgraded_index_rejects_a_second_shared_certificate_of_the_same_identity(db):
    _run_upgrade(db)

    scheme = f"ZZT-SCHEME-{uuid.uuid4().hex[:6]}"
    number = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
            "VALUES (:i, :s, :n, NULL)"
        ),
        {"i": str(uuid.uuid4()), "s": scheme, "n": number},
    )

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
                "VALUES (:i, :s, :n, NULL)"
            ),
            {"i": str(uuid.uuid4()), "s": scheme, "n": number},
        )
    db.rollback()


# --------------------------------------------------------------------------- #
# downgrade() - stamps NULL folders BEFORE restoring NOT NULL, drops
# is_shared, restores the old (NULL-distinct) certificate index
# --------------------------------------------------------------------------- #


def test_downgrade_stamps_null_folders_with_sorento_before_restoring_not_null(db):
    _run_upgrade(db)

    folder_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO attachment_directories (id, name, company_id, is_deleted) "
            "VALUES (:i, :n, NULL, false)"
        ),
        {"i": folder_id, "n": "ZZT Shared Folder"},
    )
    db.commit()

    _run_downgrade(db)

    stamped = db.execute(
        text("SELECT company_id FROM attachment_directories WHERE id = :i"), {"i": folder_id}
    ).scalar()
    assert str(stamped) == SORENTO, (
        "a NULL folder must be stamped to the incumbent company BEFORE the "
        "NOT NULL constraint comes back, or the ALTER itself would fail"
    )

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO attachment_directories (id, name, company_id, is_deleted) "
                "VALUES (:i, 'ZZT Should Fail', NULL, false)"
            ),
            {"i": str(uuid.uuid4())},
        )
    db.rollback()


def test_downgrade_drops_is_shared_column(db):
    _run_upgrade(db)
    _run_downgrade(db)

    schema = _current_schema(db)
    cols = db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'attachment_types' AND column_name = 'is_shared' "
            "AND table_schema = :s"
        ),
        {"s": schema},
    ).scalar()
    assert cols == 0


def test_downgrade_stamps_null_certificates_with_sorento_before_restoring_not_null(db):
    _run_upgrade(db)
    scheme = f"ZZT-SCHEME-{uuid.uuid4().hex[:6]}"
    number = f"ZZT-{uuid.uuid4().hex[:8]}"
    cert_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
            "VALUES (:i, :s, :n, NULL)"
        ),
        {"i": cert_id, "s": scheme, "n": number},
    )
    db.commit()

    _run_downgrade(db)

    stamped = db.execute(
        text("SELECT company_id FROM certificates WHERE id = :i"), {"i": cert_id}
    ).scalar()
    assert str(stamped) == SORENTO, (
        "a shared certificate must be stamped to the incumbent company BEFORE "
        "the NOT NULL constraint comes back, or the ALTER itself would fail"
    )

    # A NULL certificate is now rejected by the restored NOT NULL BEFORE the
    # old (non-coalesced) index is ever consulted - a certificate cannot be
    # shared at all post-downgrade, which is the stronger, correct guarantee.
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
                "VALUES (:i, :s, :n, NULL)"
            ),
            {"i": str(uuid.uuid4()), "s": scheme, "n": number},
        )
    db.rollback()


def test_downgrade_restores_the_old_index_allowing_two_distinct_company_duplicates(db):
    """The OLD plain (non-coalesced) index only ever distinguished on the real
    `company_id` value - it never had to reason about NULL at all before this
    slice. Post-downgrade, two SORENTO-company rows with the same identity
    still collide (this was always true); this is the index-shape assertion
    the retired NULL-duplicate test conflated with the (now separately
    enforced) NOT NULL question above."""
    _run_upgrade(db)
    _run_downgrade(db)

    scheme = f"ZZT-SCHEME-{uuid.uuid4().hex[:6]}"
    number = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
            "VALUES (:i, :s, :n, :c)"
        ),
        {"i": str(uuid.uuid4()), "s": scheme, "n": number, "c": SORENTO},
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
                "VALUES (:i, :s, :n, :c)"
            ),
            {"i": str(uuid.uuid4()), "s": scheme, "n": number, "c": SORENTO},
        )
    db.rollback()


def test_downgrade_drops_the_coalesced_index_before_stamping_so_a_real_collision_surfaces_at_index_create(db):
    """Reviewer fix round (S8): dropping the coalesced index BEFORE the
    stamp-to-Sorento UPDATE means that UPDATE can never fail on a still-live
    unique index. Seed a Sorento-owned certificate AND a SHARED certificate
    with the SAME identity - legal today (NULL and Sorento coalesce to
    different keys) - and prove the eventual duplicate surfaces at the LAST
    step (the plain index's CREATE), not mid-UPDATE."""
    _run_upgrade(db)
    scheme = f"ZZT-SCHEME-{uuid.uuid4().hex[:6]}"
    number = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
            "VALUES (:i, :s, :n, :c)"
        ),
        {"i": str(uuid.uuid4()), "s": scheme, "n": number, "c": SORENTO},
    )
    db.execute(
        text(
            "INSERT INTO certificates (id, scheme, certificate_number, company_id) "
            "VALUES (:i, :s, :n, NULL)"
        ),
        {"i": str(uuid.uuid4()), "s": scheme, "n": number},
    )
    db.commit()

    # The stamp-to-Sorento UPDATE inside downgrade() must not be what raises -
    # the coalesced index is already gone by then, so it always succeeds; the
    # genuine duplicate this creates only fails the LATER plain-index CREATE.
    with pytest.raises(IntegrityError):
        _run_downgrade(db)
    db.rollback()


# --------------------------------------------------------------------------- #
# Round trip (AC-H7 / S9): nullability toggles correctly both directions
# --------------------------------------------------------------------------- #


def _certificates_company_id_nullable(db) -> str:
    schema = _current_schema(db)
    return db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'certificates' AND column_name = 'company_id' "
            "AND table_schema = :s"
        ),
        {"s": schema},
    ).scalar()


def test_upgrade_downgrade_upgrade_round_trip_toggles_certificates_company_id_nullability(db):
    _run_upgrade(db)
    assert _certificates_company_id_nullable(db) == "YES"

    _run_downgrade(db)
    assert _certificates_company_id_nullable(db) == "NO"

    _run_upgrade(db)
    assert _certificates_company_id_nullable(db) == "YES"
