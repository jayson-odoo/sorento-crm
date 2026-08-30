"""AC-A2-7 - migration 445 sweeps three `.delete` slugs onto their `.edit` holders.

The gap it closes is not theoretical. `master_data.sales_agents.delete`,
`scm.sales_orders.delete` and `scm.purchase_orders.delete` are held by `admin`
and nobody else, while the matching `.edit` is held by `admin` plus
`integration_foundryx_esb` and `integration_n8n` - so the deletion endpoint
group A4 adds would 403 for exactly the principal it is built for, and read as
"the ESB cannot delete" rather than as a missing grant.

The eight `scm.sales_orders.*` / `scm.purchase_orders.*` rows are the migration's
own as well: they exist on the dev copy of production because a since-retired
migration put them there, so a database built any other way has neither the
target NOR the source of the sweep, and the sweep alone would be a no-op.

Driven through `apply()` / `revert()` rather than `alembic upgrade`: the local
database is shared across worktrees and its `alembic_version` is stamped for a
different branch, so stepping it here would move a version other checkouts are
running against. The functions are what `upgrade()`/`downgrade()` call, so this
tests the migration's own statements, not a copy of them.

Everything runs inside one transaction that is rolled back, and the seeded role
carries a `ZZTGRANT` marker so no assertion depends on a production row.
"""
from __future__ import annotations

import importlib.util
import os
import uuid

import pytest
from sqlalchemy import text

from app.database import engine

_MIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic",
    "versions",
    "445_autocount_grant_sweep.py",
)
_spec = importlib.util.spec_from_file_location("mig_445", _MIG_PATH)
mig445 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig445)

MARKER = "ZZTGRANT"
SOURCE = "scm.sales_orders.edit"
TARGET = "scm.sales_orders.delete"


@pytest.fixture()
def bind():
    """A connection whose every write is discarded.

    The sweep is a SELECT-driven INSERT over the live grant table, so it touches
    real roles as well as the seeded one. Rolled back rather than scoped: the
    statement under test is exactly the one production will run, and narrowing it
    for the test would stop testing it.
    """
    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _permission_id(bind, slug: str) -> str | None:
    return bind.execute(
        text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
    ).scalar()


def _ensure_permission(bind, slug: str) -> str:
    """The slug's id, created if this database has never seen it.

    CI's database carries no seed data at all, so the source slug may genuinely
    not be there; the migration itself creates targets the same way.
    """
    existing = _permission_id(bind, slug)
    if existing is not None:
        return existing
    new_id = str(uuid.uuid4())
    bind.execute(
        text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "VALUES (:i, :s, :n, :d, now())"
        ),
        {"i": new_id, "s": slug, "n": slug, "d": f"{MARKER} seeded"},
    )
    return new_id


def _seed_role_holding(bind, source_slug: str) -> str:
    """A scratch role holding one `.edit` slug and nothing else.

    `user_roles.name` is unique as well as `slug`, so both carry the suffix; a
    fixed name collided the moment a second role was seeded in one test.
    """
    role_id = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:8]
    bind.execute(
        text(
            # is_trashed carries only a Python-side default on the model, so a raw INSERT
            # must state it: CI's migration-built schema makes it NOT NULL with no
            # server default (the shared dev copy forgives the omission).
            "INSERT INTO user_roles (id, slug, name, description, is_protected, is_default, is_trashed) "
            "VALUES (:i, :s, :n, :d, false, false, false)"
        ),
        {
            "i": role_id,
            "s": f"{MARKER.lower()}_{suffix}",
            "n": f"{MARKER} role {suffix}",
            "d": f"{MARKER} scratch role",
        },
    )
    bind.execute(
        text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "VALUES (:i, :r, :p, now())"
        ),
        {
            "i": str(uuid.uuid4()),
            "r": role_id,
            "p": _ensure_permission(bind, source_slug),
        },
    )
    return role_id


@pytest.fixture()
def role_holding_edit(bind) -> str:
    return _seed_role_holding(bind, SOURCE)


def _grant_count(bind, role_id: str, slug: str) -> int:
    return bind.execute(
        text(
            "SELECT count(*) FROM user_role_permissions rp "
            "JOIN user_permissions p ON p.id = rp.permission_id "
            "WHERE rp.role_id = :r AND p.slug = :s"
        ),
        {"r": role_id, "s": slug},
    ).scalar()


def test_the_sweep_grants_delete_to_an_edit_holder(bind, role_holding_edit):
    assert _grant_count(bind, role_holding_edit, TARGET) == 0

    mig445.apply(bind)

    assert _grant_count(bind, role_holding_edit, TARGET) == 1


def test_the_sweep_is_idempotent(bind, role_holding_edit):
    """Run twice. A migration that duplicates its own grant on a re-run cannot be
    re-applied after a partial deploy, which is the situation it is most likely
    to meet."""
    mig445.apply(bind)
    mig445.apply(bind)

    assert _grant_count(bind, role_holding_edit, TARGET) == 1


def test_the_downgrade_takes_back_the_grant_and_leaves_the_permission(
    bind, role_holding_edit
):
    """Mirrored, not blanket. The grant goes; the permission row stays, because
    it was measured present before the migration ran and deleting it would
    remove something this migration did not create."""
    mig445.apply(bind)
    assert _grant_count(bind, role_holding_edit, TARGET) == 1

    mig445.revert(bind)

    assert _grant_count(bind, role_holding_edit, TARGET) == 0
    assert _permission_id(bind, TARGET) is not None


def test_the_scm_document_slugs_are_created_where_the_database_has_none(bind):
    """The eight `scm.*` rows are the migration's own, not something it assumes.

    They exist on the dev copy of production because a since-retired migration put
    them there, and they are declared nowhere else - so a database built any other
    way (CI, `scripts/bootstrap_env`, a fresh deploy) has none of them, the sweep's
    SELECT finds no source grant to copy, and the ESB is refused for ever. Deleted
    first inside the rolled-back transaction so this asserts the create, not the
    incumbent rows.
    """
    slugs = [slug for slug, _name, _descr in mig445._SCM_PERMISSIONS]
    assert len(slugs) == 8
    bind.execute(
        text("DELETE FROM user_role_permissions WHERE permission_id IN "
             "(SELECT id FROM user_permissions WHERE slug = ANY(:s))"),
        {"s": slugs},
    )
    bind.execute(text("DELETE FROM user_permissions WHERE slug = ANY(:s)"), {"s": slugs})
    assert all(_permission_id(bind, slug) is None for slug in slugs)

    mig445.apply(bind)

    for slug, name, description in mig445._SCM_PERMISSIONS:
        row = bind.execute(
            text("SELECT name, description FROM user_permissions WHERE slug = :s"),
            {"s": slug},
        ).first()
        assert row is not None, slug
        # The names `_crud(...)` would have written, so the two paths that can
        # create these rows cannot hand the screen two different labels.
        assert (row[0], row[1]) == (name, description), slug


def test_the_sweep_still_grants_delete_where_the_scm_slugs_were_absent(bind):
    """The create and the sweep in one run, on a database that had neither.

    A role holding `scm.sales_orders.edit` and nothing else still comes out of
    `apply()` holding `.delete` - which is the whole point of the migration, and
    the case CI and every fresh deploy actually run.
    """
    slugs = [slug for slug, _name, _descr in mig445._SCM_PERMISSIONS]
    bind.execute(
        text("DELETE FROM user_role_permissions WHERE permission_id IN "
             "(SELECT id FROM user_permissions WHERE slug = ANY(:s))"),
        {"s": slugs},
    )
    bind.execute(text("DELETE FROM user_permissions WHERE slug = ANY(:s)"), {"s": slugs})
    role_id = _seed_role_holding(bind, SOURCE)

    mig445.apply(bind)

    assert _grant_count(bind, role_id, TARGET) == 1


def test_every_swept_target_reaches_a_holder_of_its_source(bind):
    """All three pairs, not just the one the fixture seeds.

    A sweep that silently dropped a pair would still pass the tests above, and
    the symptom would be a 403 in group A4 on one entity out of three.
    """
    role_ids = {
        target: _seed_role_holding(bind, source)
        for target, source, _name, _descr in mig445._SWEEP
    }

    mig445.apply(bind)

    for target, role_id in role_ids.items():
        assert _grant_count(bind, role_id, target) == 1, target
