"""Migration 375 tested by running it, not by asserting on the live database.

The local database is a copy of production and is already past this lineage, so
"does the table exist" there proves nothing. This builds the schema on a scratch
schema (tests/_pg_fixture.blank_session), seeds users the way production has them
BEFORE the migration, runs the raw-SQL ``upgrade()`` against it and asserts the
backfill (AC-2): one (NULL, NULL) row per user with either discontinued toggle on,
none for a user with both off, and re-running it is a no-op (no duplicate row, no
error from the guard's own NOT EXISTS check).

Same shape as tests/test_migration_371_brand_routing.py: ``MigrationContext`` +
``Operations.context`` so ``op.execute`` runs against the test's own connection.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.user import User, UserStatus
from tests._pg_fixture import blank_session, unique_code

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "375_user_discontinued_scopes.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m375", MIGRATION)
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


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _user(db, *, email_pref=False, wa_pref=False) -> str:
    u = User(
        id=unique_code("user"),
        email=f"{unique_code('u')}@zzt.test",
        name="ZZT User",
        status=UserStatus.ACTIVE.value,
        notify_email_on_product_discontinued=email_pref,
        notify_whatsapp_on_product_discontinued=wa_pref,
    )
    db.add(u)
    db.flush()
    return str(u.id)


def _scope_rows(db, user_id: str) -> list[tuple]:
    rows = db.execute(
        text(
            "SELECT company_id, brand_id FROM user_product_discontinued_scopes "
            "WHERE user_id = :u"
        ),
        {"u": user_id},
    ).all()
    return [(r[0], r[1]) for r in rows]


def _drop_table(db):
    """Let the migration's own DDL be what builds the table.

    ``blank_session`` runs ``Base.metadata.create_all``, which already created
    ``user_product_discontinued_scopes`` from the model - so the migration's
    ``CREATE TABLE IF NOT EXISTS`` is a no-op and an assertion afterwards is
    describing the MODEL, not the migration. Dropping it first is the difference
    between testing the DDL and testing SQLAlchemy.
    """
    db.execute(text("DROP TABLE IF EXISTS user_product_discontinued_scopes CASCADE"))
    db.flush()


def test_table_created_with_expected_columns(db):
    _drop_table(db)

    _run_upgrade(db)

    columns = {
        r[0]: r[2]
        for r in db.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'user_product_discontinued_scopes'"
            )
        )
    }
    assert set(columns) == {"id", "user_id", "company_id", "brand_id", "created_at"}
    assert columns["user_id"] == "NO"
    assert columns["company_id"] == "YES"
    assert columns["brand_id"] == "YES"


def test_table_created_with_cascading_foreign_keys(db):
    """AC-11: a deleted user, company or brand takes its scope rows with it."""
    _drop_table(db)

    _run_upgrade(db)

    fks = {
        r[0]: r[1]
        for r in db.execute(
            text(
                "SELECT ref.relname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con "
                "JOIN pg_class cl ON cl.oid = con.conrelid "
                "JOIN pg_namespace ns ON ns.oid = cl.relnamespace "
                "JOIN pg_class ref ON ref.oid = con.confrelid "
                "WHERE con.contype = 'f' "
                "AND ns.nspname = current_schema() "
                "AND cl.relname = 'user_product_discontinued_scopes'"
            )
        )
    }
    assert set(fks) == {"users", "companies", "brands"}
    assert "(user_id)" in fks["users"]
    assert "(company_id)" in fks["companies"]
    assert "(brand_id)" in fks["brands"]
    for definition in fks.values():
        assert "ON DELETE CASCADE" in definition


def test_table_created_with_the_four_expected_indexes(db):
    """Three lookup indexes plus the coalesce unique index that is what actually
    stops a duplicate (company, brand) pair - a plain unique index would not,
    because NULL is never equal to NULL in Postgres."""
    _drop_table(db)

    _run_upgrade(db)

    indexes = {
        r[0]: r[1]
        for r in db.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = 'user_product_discontinued_scopes'"
            )
        )
    }
    for name in (
        "ix_user_product_discontinued_scopes_user_id",
        "ix_user_product_discontinued_scopes_company_id",
        "ix_user_product_discontinued_scopes_brand_id",
        "uq_user_product_discontinued_scopes",
    ):
        assert name in indexes, sorted(indexes)

    unique_def = indexes["uq_user_product_discontinued_scopes"]
    assert "CREATE UNIQUE INDEX" in unique_def
    assert "COALESCE" in unique_def.upper()
    assert "user_id" in unique_def


def test_the_unique_index_rejects_a_duplicate_all_all_row(db):
    """The index is only worth having if it bites, so make it bite."""
    _drop_table(db)
    _run_upgrade(db)
    uid = _user(db, email_pref=False)
    db.flush()

    db.execute(
        text(
            "INSERT INTO user_product_discontinued_scopes (id, user_id, company_id, brand_id) "
            "VALUES (:i, :u, NULL, NULL)"
        ),
        {"i": str(uuid.uuid4()), "u": uid},
    )
    db.flush()

    from sqlalchemy.exc import IntegrityError

    # Inside a savepoint so the aborted statement does not poison the session the
    # fixture still has to tear down.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO user_product_discontinued_scopes "
                    "(id, user_id, company_id, brand_id) VALUES (:i, :u, NULL, NULL)"
                ),
                {"i": str(uuid.uuid4()), "u": uid},
            )


def test_a_partial_prior_run_is_completed_not_doubled(db):
    """A user who already has the all/all row (e.g. from a partial prior run of
    this same migration) keeps exactly one - the NOT EXISTS guard, proven by
    inserting the row by hand before the migration's own INSERT runs."""
    _run_upgrade(db)  # creates the table
    uid = _user(db, email_pref=True)
    db.flush()
    db.execute(
        text(
            "INSERT INTO user_product_discontinued_scopes (id, user_id, company_id, brand_id) "
            "VALUES (:i, :u, NULL, NULL)"
        ),
        {"i": str(uuid.uuid4()), "u": uid},
    )
    db.flush()

    _run_upgrade(db)  # re-run: CREATE TABLE IF NOT EXISTS + guarded INSERT

    assert _scope_rows(db, uid) == [(None, None)]


def test_ac2_backfill_gives_exactly_one_all_all_row_per_toggled_on_user(db):
    email_only = _user(db, email_pref=True)
    wa_only = _user(db, email_pref=False, wa_pref=True)
    both = _user(db, email_pref=True, wa_pref=True)
    neither = _user(db, email_pref=False, wa_pref=False)
    db.flush()

    _run_upgrade(db)

    assert _scope_rows(db, email_only) == [(None, None)]
    assert _scope_rows(db, wa_only) == [(None, None)]
    assert _scope_rows(db, both) == [(None, None)]
    assert _scope_rows(db, neither) == []


def test_ac2_rerunning_the_backfill_is_idempotent(db):
    uid = _user(db, email_pref=True)
    db.flush()

    _run_upgrade(db)
    first = _scope_rows(db, uid)

    _run_upgrade(db)  # CREATE TABLE IF NOT EXISTS + NOT EXISTS-guarded insert
    second = _scope_rows(db, uid)

    assert first == [(None, None)]
    assert second == [(None, None)]


def test_ac2_trashed_users_are_backfilled_too(db):
    """Toggle state is what the row preserves; the fan-out filters trashed users
    on its own read, not the backfill."""
    uid = _user(db, email_pref=True)
    db.execute(text("UPDATE users SET is_trashed = true WHERE id = :u"), {"u": uid})
    db.flush()

    _run_upgrade(db)

    assert _scope_rows(db, uid) == [(None, None)]


def test_revision_id_fits_alembic_version_num(db):
    module = _load_migration()
    assert len(module.revision) <= 32


def test_downgrade_drops_the_table(db):
    _run_upgrade(db)
    _run_downgrade(db)

    assert db.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'user_product_discontinued_scopes'"
        )
    ).scalar() == 0
