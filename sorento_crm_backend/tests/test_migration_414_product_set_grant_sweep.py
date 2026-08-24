"""The product-set grant sweep - `PRINCIPLES.md` DoD gate 3.

The migration's `upgrade()` is imported and run inside a rolled-back transaction against
a blank schema, so what is under test is the CODE rather than whatever the local database
happens to hold. CI's database is empty, so every role and every grant here is seeded by
the test with a `zzt_` marker and nothing is read off an existing row.

The assertion that matters is the one that names a NON-admin role. `admin` and
`superadmin` reach these screens whether or not the grant exists, because
`UserPermissionService.check_user_has_permission` short-circuits on those two slugs - so
a test that only proved an admin could see product sets would have stayed green through
the entire outage this migration closes.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

# Loaded by PATH, not by dotted name: `alembic/versions` has no `__init__.py`, so it is
# not an importable package, and the revision id starts with a digit besides.
_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "414_product_set_grant_sweep.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_414", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PRODUCT_SLUGS = (
    "master_data.products.view",
    "master_data.products.add",
    "master_data.products.edit",
    "master_data.products.delete",
)
_SET_SLUGS = (
    "master_data.product_sets.view",
    "master_data.product_sets.add",
    "master_data.product_sets.edit",
    "master_data.product_sets.delete",
)


def _permission(db, slug: str) -> str:
    from app.models.user import UserPermission

    row = db.query(UserPermission).filter_by(slug=slug).first()
    if row is None:
        row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(row)
        db.flush()
    return row.id


def _role(db, slug: str) -> str:
    from app.models.user import UserRole

    row = UserRole(
        id=str(uuid.uuid4()),
        slug=slug,
        name=slug,
        description="",
        is_protected=False,
        is_default=False,
    )
    db.add(row)
    db.flush()
    return row.id


def _grant(db, role_id: str, slug: str) -> None:
    from app.models.user import UserRolePermission

    db.add(
        UserRolePermission(
            id=str(uuid.uuid4()), role_id=role_id, permission_id=_permission(db, slug)
        )
    )
    db.flush()


def _slugs_for(db, role_id: str) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT p.slug
            FROM user_role_permissions rp
            JOIN user_permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = :role
            """
        ),
        {"role": role_id},
    ).all()
    return {row[0] for row in rows}


def _run(db, direction: str = "upgrade") -> None:
    """Run the migration body against this session's connection.

    `op.get_bind()` needs a MigrationContext, so one is built over the test's own
    connection - everything it writes is inside the transaction blank_session rolls back.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


@pytest.fixture
def db():
    with blank_session() as s:
        for slug in (*_PRODUCT_SLUGS, *_SET_SLUGS):
            _permission(s, slug)
        yield s


def test_a_non_admin_role_gains_every_product_set_permission(db):
    """The DoD item itself: a provisioned, non-admin role holds all four afterwards.

    `zzt_director` stands in for `director`, which holds all four `products.*` grants on
    the live copy. Without this sweep it held none of the four set grants, and the whole
    screen 403'd for everyone who is not an admin.
    """
    role = _role(db, "zzt_director")
    for slug in _PRODUCT_SLUGS:
        _grant(db, role, slug)

    _run(db)

    assert set(_SET_SLUGS) <= _slugs_for(db, role)


def test_each_grant_follows_its_own_source_slug(db):
    """A warehouse executive may READ products, so it may READ sets and no more."""
    role = _role(db, "zzt_warehouse_executive")
    _grant(db, role, "master_data.products.view")

    _run(db)

    slugs = _slugs_for(db, role)
    assert "master_data.product_sets.view" in slugs
    assert slugs & {
        "master_data.product_sets.add",
        "master_data.product_sets.edit",
        "master_data.product_sets.delete",
    } == set()


def test_integration_roles_are_included(db):
    """Deliberately unlike migration 361, which excluded them.

    n8n already holds `products.add`/`.edit`/`.delete`; a set is a grouping of rows it may
    already write, and the external link and promotion paths resolve set codes on its
    behalf. Nothing is inverted by letting it through, and excluding it would silently
    break the flyer-code path this feature exists for.
    """
    role = _role(db, "integration_n8n")
    for slug in _PRODUCT_SLUGS:
        _grant(db, role, slug)

    _run(db)

    assert set(_SET_SLUGS) <= _slugs_for(db, role)


def test_a_role_holding_no_product_permission_gains_nothing(db):
    role = _role(db, "zzt_outsider")

    _run(db)

    assert _slugs_for(db, role) == set()


def test_a_database_with_no_roles_at_all_is_a_no_op(db):
    """CI's database has no seed data. The sweep must be silent there, not red."""
    db.execute(text("DELETE FROM user_role_permissions"))
    db.execute(text("DELETE FROM user_roles"))

    _run(db)

    assert db.execute(text("SELECT count(*) FROM user_role_permissions")).scalar() == 0


def test_the_permission_rows_are_created_when_absent(db):
    """A fresh deploy runs migrations BEFORE the app's registry sync.

    The sync only ever inserts permission rows, never grants, so if the four set rows are
    missing when this runs the sweep would find no target and the feature would ship
    ungranted forever.
    """
    db.execute(
        text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"),
        {"slugs": list(_SET_SLUGS)},
    )
    role = _role(db, "zzt_fresh_deploy")
    _grant(db, role, "master_data.products.view")

    _run(db)

    assert "master_data.product_sets.view" in _slugs_for(db, role)
    name = db.execute(
        text("SELECT name FROM user_permissions WHERE slug = :slug"),
        {"slug": "master_data.product_sets.view"},
    ).scalar()
    # Matches `_crud("master_data", "product_sets", "Product Sets")` so the row the
    # migration writes cannot drift from the row the registry sync would have written.
    assert name == "View Product Sets"


def test_running_it_twice_changes_nothing(db):
    role = _role(db, "zzt_idempotent")
    _grant(db, role, "master_data.products.view")

    _run(db)
    first = _slugs_for(db, role)
    _run(db)

    assert _slugs_for(db, role) == first
    # And not as duplicate rows under one slug, which the set above would hide.
    count = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :role"),
        {"role": role},
    ).scalar()
    assert count == len(first)


def test_downgrade_takes_the_grants_back_and_leaves_the_permissions(db):
    role = _role(db, "zzt_reversible")
    for slug in _PRODUCT_SLUGS:
        _grant(db, role, slug)
    _run(db)

    _run(db, "downgrade")

    assert _slugs_for(db, role) & set(_SET_SLUGS) == set()
    # The rows predate this migration; removing them would delete what it never made.
    remaining = db.execute(
        text("SELECT count(*) FROM user_permissions WHERE slug = ANY(:slugs)"),
        {"slugs": list(_SET_SLUGS)},
    ).scalar()
    assert remaining == len(_SET_SLUGS)


def test_downgrade_leaves_a_hand_made_grant_alone(db):
    """It removes exactly what it added, not everything that looks like it.

    A role granted `product_sets.view` by hand, with no `products.view` behind it, was
    never written by this migration and must survive its reversal.
    """
    role = _role(db, "zzt_hand_granted")
    _grant(db, role, "master_data.product_sets.view")

    _run(db)
    _run(db, "downgrade")

    assert "master_data.product_sets.view" in _slugs_for(db, role)
