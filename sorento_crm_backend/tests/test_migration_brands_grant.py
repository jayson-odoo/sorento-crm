"""AC-10 - the migration that grants `master_data.brands.{view,edit,delete}`
to `integration_foundryx_esb`.

PLAN: documentation/plans/autocount/PLAN-autocount-brands-ingest.md D6.
UAC:  documentation/plans/autocount/autocount-brands-ingest-acceptance-criteria.md AC-10.

Driven through `apply()` / `revert()`, the `tests/test_migration_445_grant_
sweep.py` convention - not `alembic upgrade`, since the local database's
`alembic_version` stamp does not track this worktree's branch.

The module name is a GUESS the tester makes on the coder's behalf, named
explicitly here and in the tester's report: `alembic/versions/511_brands_esb_
grant.py`, with module-level `apply(conn)` / `revert(conn)`. If the coder picks
a different revision id, only the `_MIG_PATH` constant below needs to change.

Substrate: a REAL connection (`app.database.engine`), one outer transaction
rolled back at teardown - the same `bind` fixture `test_migration_445_grant_
sweep.py` uses, and for the same reason: the migration's own statements are
plain, unqualified SQL against `user_permissions` / `user_roles` / `user_role_
permissions`, resolved through the connection's ordinary `search_path`. A
`pg_empty_schema` scratch schema would NOT catch that SQL - its
`schema_translate_map` only rewrites compiled ORM/Core constructs, never a raw
`text()` string - so the migration's writes would land in the REAL tables
while a scratch-schema fixture's own seed rows sat somewhere else entirely,
proving nothing. Seeded rows carry a `ZZTBRDGRANT` marker; this database has no
`integration_foundryx_esb` role today (checked by hand), so the "role absent"
branch below needs no scratch name to prove itself.
"""
from __future__ import annotations

import importlib.util
import os
import uuid

import pytest
from sqlalchemy import text

from app.database import engine

MARKER = "ZZTBRDGRANT"

_MIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic",
    "versions",
    "511_brands_esb_grant.py",
)

_TARGET_SLUGS = (
    "master_data.brands.view",
    "master_data.brands.edit",
    "master_data.brands.delete",
)

_ESB_ROLE_SLUG = "integration_foundryx_esb"


def _load_migration():
    if not os.path.exists(_MIG_PATH):
        pytest.fail(
            f"expected migration module at {_MIG_PATH} (tester's assumed "
            "revision id - update _MIG_PATH here if the coder named it "
            "differently) with module-level apply(conn)/revert(conn)"
        )
    spec = importlib.util.spec_from_file_location("mig_511_brands_grant", _MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bind():
    """A connection whose every write is discarded - mirrors
    `test_migration_445_grant_sweep.py::bind` exactly, and for the same
    reason: the statement under test is exactly the one production will run,
    against the real tables, so narrowing it to a scratch schema would stop
    testing it."""
    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _esb_role(bind) -> str:
    """A role holding the real `integration_foundryx_esb` slug.

    This database carries no such role today, so one is seeded here - inside
    the transaction this fixture rolls back, so nothing survives the test.
    `user_roles.slug` and `.name` are both unique, so a fresh suffix on each
    keeps two tests in the same run from colliding with each other's
    still-uncommitted (but same-process-visible) rows.
    """
    role_id = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:8]
    bind.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, description, is_protected, "
            "is_default, is_trashed) VALUES (:i, :s, :n, :d, false, false, false)"
        ),
        {
            "i": role_id,
            "s": f"{_ESB_ROLE_SLUG}_{suffix}" if _role_slug_taken(bind) else _ESB_ROLE_SLUG,
            "n": f"{MARKER} ESB role {suffix}",
            "d": f"{MARKER} scratch",
        },
    )
    return role_id


def _role_slug_taken(bind) -> bool:
    return (
        bind.execute(
            text("SELECT 1 FROM user_roles WHERE slug = :s"), {"s": _ESB_ROLE_SLUG}
        ).first()
        is not None
    )


def _grant_count(bind, role_id: str, slug: str) -> int:
    return bind.execute(
        text(
            "SELECT count(*) FROM user_role_permissions rp "
            "JOIN user_permissions p ON p.id = rp.permission_id "
            "WHERE rp.role_id = :r AND p.slug = :s"
        ),
        {"r": role_id, "s": slug},
    ).scalar()


class TestGrantsTheEsbRole:
    def test_apply_grants_view_edit_delete_to_the_esb_role(self, bind):
        role_id = _esb_role(bind)
        mig = _load_migration()

        for slug in _TARGET_SLUGS:
            assert _grant_count(bind, role_id, slug) == 0

        mig.apply(bind)

        for slug in _TARGET_SLUGS:
            assert _grant_count(bind, role_id, slug) == 1, slug

    def test_apply_is_idempotent(self, bind):
        role_id = _esb_role(bind)
        mig = _load_migration()

        mig.apply(bind)
        mig.apply(bind)

        for slug in _TARGET_SLUGS:
            assert _grant_count(bind, role_id, slug) == 1, slug

    def test_downgrade_is_a_no_op(self, bind):
        role_id = _esb_role(bind)
        mig = _load_migration()

        mig.apply(bind)
        mig.revert(bind)

        for slug in _TARGET_SLUGS:
            assert _grant_count(bind, role_id, slug) == 1, (
                f"{slug} must survive the downgrade (D6: downgrade is a no-op, "
                "the grant may pre-date this migration)"
            )


class TestNoRoleIsANoOp:
    def test_apply_on_a_database_without_the_esb_role_does_not_error(self, bind):
        assert not _role_slug_taken(bind), (
            "this database already has an integration_foundryx_esb role - "
            "this test needs one that genuinely does not exist"
        )
        mig = _load_migration()

        before = bind.execute(
            text("SELECT count(*) FROM user_role_permissions")
        ).scalar()

        mig.apply(bind)  # must not raise

        after = bind.execute(
            text("SELECT count(*) FROM user_role_permissions")
        ).scalar()
        assert after == before, "nothing to grant to, so nothing new was granted"


class TestPermissionRowsCreatedIfAbsent:
    def test_apply_creates_the_permission_rows_when_the_database_has_none(self, bind):
        _esb_role(bind)
        mig = _load_migration()

        # This database's `master_data.brands.*` rows (seeded by the registry
        # sync on a normal boot) are removed for THIS test only, inside the
        # transaction the `bind` fixture rolls back at teardown - reproducing
        # the "database built by alembic alone, never booted" case D6 names,
        # without needing a second substrate to get a genuinely bare table.
        bind.execute(
            text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"),
            {"slugs": list(_TARGET_SLUGS)},
        )
        for slug in _TARGET_SLUGS:
            existing = bind.execute(
                text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": slug}
            ).first()
            assert existing is None, f"{slug} unexpectedly pre-exists on this database"

        mig.apply(bind)

        for slug in _TARGET_SLUGS:
            assert (
                bind.execute(
                    text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": slug}
                ).first()
                is not None
            ), slug
