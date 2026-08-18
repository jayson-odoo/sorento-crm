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


def test_table_created_with_expected_columns(db):
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
