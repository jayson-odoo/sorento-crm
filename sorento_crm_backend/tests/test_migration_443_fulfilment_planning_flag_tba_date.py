"""Migration 443 round trip - `PRINCIPLES.md` DoD gate 3.

`upgrade()` and `downgrade()` are imported and run inside a rolled-back transaction against
the REAL shared database via `pg_session`, never `blank_session`'s schema-translated
scratch copy - the same reasoning `test_migration_396_oi_single_location.py` records: this
migration's DDL is schema-QUALIFIED (`op.add_column(..., schema="scm")`,
`sa.inspect(bind).get_columns(table, schema="scm")`) and its permission sweep is RAW SQL
(`sa.text("INSERT INTO user_permissions ...")`). Neither resolves through a
`schema_translate_map` - a raw `scm.priority_policy` reference and an inspector call given
`schema="scm"` both name the literal schema, so run against a translated scratch copy they
would silently read/write nothing (the 396 lesson) or, worse for `ALTER TABLE`, the wrong
database's real table. `pg_session` is the real database inside one outer transaction that
is rolled back at teardown - Postgres DDL is fully transactional, so a genuine
`ADD COLUMN` / `DROP COLUMN` here is exactly as reversible as any other write.

Migration 443 is already hand-applied on the shared dev database (its own docstring: the
`alembic_version` there points at another lane's head, so it is applied by hand and has to
be idempotent when re-run) - so the round trip below starts at `downgrade()`, which finds
the new columns present and the caps absent and genuinely drops/adds them, then
`upgrade()` genuinely adds/drops them back, then `downgrade()` again - asserting the full
state at every step rather than only the seed function in isolation.

The non-admin-role assertion is the one that matters for the permission sweep (AC-S1-1's
sibling rule, AC-S2-8's own migration): `admin`/`superadmin` reach every screen regardless
of a grant (`UserPermissionService.check_user_has_permission` short-circuits on those two
slugs), so a test that only proved an admin could see Stock Debt would stay green through
the exact outage this sweep exists to prevent.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from tests._pg_fixture import pg_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "443_fulfilment_planning_flag_tba_date.py"
)

_SOURCE_SLUG = "projects.projects.view"
_TARGET_SLUG = "projects.stock_debt.view"
MARKER = "ZZTMIG443"


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_443", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        id=str(uuid.uuid4()), slug=f"{MARKER}-{slug}-{uuid.uuid4().hex[:6]}",
        name=f"{MARKER} {slug} {uuid.uuid4().hex[:6]}", description="",
        is_protected=False, is_default=False,
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
    connection - everything it writes is inside the transaction `pg_session` rolls back.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _warehouse_columns(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'warehouses' AND table_schema = 'public'"
        )
    ).all()
    return {row[0] for row in rows}


def _policy_columns(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'priority_policy' AND table_schema = 'scm'"
        )
    ).all()
    return {row[0] for row in rows}


@pytest.fixture
def db():
    with pg_session() as s:
        set_company_scope(s, None)
        yield s


# --------------------------------------------------------------------------- AC-S1-1 / S1-2


def test_downgrade_then_upgrade_then_downgrade_round_trips_every_column(db):
    """AC-S1-1 / AC-S1-2. The shared dev database already carries the post-443 shape (hand
    applied), so the meaningful exercise is reverting it for real and bringing it back for
    real, inside a transaction that never commits."""
    assert "fulfilment_planning" in _warehouse_columns(db)
    assert "tba_date_from" in _policy_columns(db)
    assert {"cross_group_borrow_max_qty", "cross_group_borrow_max_pct"} & _policy_columns(db) == set()

    _run(db, "downgrade")
    assert "fulfilment_planning" not in _warehouse_columns(db)
    assert "tba_date_from" not in _policy_columns(db)
    assert {"cross_group_borrow_max_qty", "cross_group_borrow_max_pct"} <= _policy_columns(db)

    _run(db, "upgrade")
    assert "fulfilment_planning" in _warehouse_columns(db)
    assert "tba_date_from" in _policy_columns(db)
    assert {"cross_group_borrow_max_qty", "cross_group_borrow_max_pct"} & _policy_columns(db) == set()

    _run(db, "downgrade")
    assert "fulfilment_planning" not in _warehouse_columns(db)
    assert "tba_date_from" not in _policy_columns(db)
    assert {"cross_group_borrow_max_qty", "cross_group_borrow_max_pct"} <= _policy_columns(db)


def test_upgrade_seeds_the_default_tba_date_and_the_flagged_bins(db):
    """The seed rule (AC-S1-1) and the TBA default (AC-S1-2), from the migration's own
    upgrade path rather than by calling `seed_fulfilment_planning_flags` directly - the
    add_column path is exercised for real because `downgrade` ran first.

    Rows are inserted with raw SQL, not the ORM: `Warehouse`'s mapped columns still include
    `fulfilment_planning` regardless of what the live table holds at this instant (the ORM
    metadata is the CURRENT model, not a reflection), so an ORM insert right after
    `downgrade` drops the column would itself fail with UndefinedColumn - the column
    genuinely does not exist on the table at that point in the transaction.
    """
    _run(db, "downgrade")  # pre-443 shape, so the add_column path below is real

    stem = uuid.uuid4().hex[:6].upper()
    company = "00000000-0000-0000-0000-000000000001"
    codes = {
        "on": f"{MARKER}-{stem}-BB",
        "off_group": f"{MARKER}-{stem}-HP",
        "inactive": f"{MARKER}-{stem}R-BB",
    }
    for key, code in codes.items():
        db.execute(
            text(
                "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
                "is_active) VALUES (:id, :company, :code, :code, :active)"
            ),
            {
                "id": str(uuid.uuid4()), "company": company, "code": code,
                "active": key != "inactive",
            },
        )

    _run(db, "upgrade")

    flags = dict(
        db.execute(
            text(
                "SELECT warehouse_code, fulfilment_planning FROM warehouses "
                "WHERE warehouse_code = ANY(:codes)"
            ),
            {"codes": list(codes.values())},
        ).all()
    )

    assert flags[codes["on"]] is True
    assert flags[codes["off_group"]] is False
    assert flags[codes["inactive"]] is False

    default = db.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'priority_policy' AND table_schema = 'scm' "
            "AND column_name = 'tba_date_from'"
        )
    ).scalar()
    assert default is not None and "2029-01-01" in default


def test_a_bin_turned_off_by_hand_stays_off_when_upgrade_runs_again(db):
    """The seed is a one-off STARTING POSITION, not a rule (the migration's own docstring).

    443 is applied by hand on the shared dev copy and has to be re-runnable, and a deploy
    can replay `upgrade()` - so the second pass must find the column present and leave every
    flag exactly as an admin left it. Seeding outside the `add_column` branch turned every
    bin somebody had switched off back on, which is a silent configuration rollback wearing
    the clothes of an idempotent migration.
    """
    _run(db, "downgrade")  # pre-443 shape, so the seed below is the real add_column path

    code = f"{MARKER}-{uuid.uuid4().hex[:6].upper()}-BB"
    db.execute(
        text(
            "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
            "is_active) VALUES (:id, :company, :code, :code, true)"
        ),
        {
            "id": str(uuid.uuid4()),
            "company": "00000000-0000-0000-0000-000000000001",
            "code": code,
        },
    )

    def _flag() -> bool:
        return db.execute(
            text(
                "SELECT fulfilment_planning FROM warehouses WHERE warehouse_code = :code"
            ),
            {"code": code},
        ).scalar()

    _run(db, "upgrade")
    assert _flag() is True, "the first pass seeds the planned bin"

    db.execute(
        text(
            "UPDATE warehouses SET fulfilment_planning = false WHERE warehouse_code = :code"
        ),
        {"code": code},
    )
    _run(db, "upgrade")

    assert _flag() is False, "a second upgrade() leaves an admin's decision alone"


# --------------------------------------------------------------------------- AC-S2-8


def test_a_non_admin_role_holding_projects_view_gains_stock_debt_view(db):
    role = _role(db, "purchasing")
    _grant(db, role, _SOURCE_SLUG)

    _run(db)

    assert _TARGET_SLUG in _slugs_for(db, role)


def test_a_role_without_projects_view_gains_nothing(db):
    role = _role(db, "outsider")

    _run(db)

    assert _slugs_for(db, role) == set()


def test_the_permission_row_is_recreated_when_absent(db):
    """A fresh deploy runs migrations BEFORE the app's registry sync (same lesson as 414).
    Deletes and restores the real row inside the rolled-back transaction only."""
    existing_id, existing_name, existing_descr = db.execute(
        text("SELECT id, name, description FROM user_permissions WHERE slug = :s"),
        {"s": _TARGET_SLUG},
    ).one()
    db.execute(text("DELETE FROM user_permissions WHERE slug = :s"), {"s": _TARGET_SLUG})
    role = _role(db, "fresh_deploy")
    _grant(db, role, _SOURCE_SLUG)

    _run(db)

    assert _TARGET_SLUG in _slugs_for(db, role)
    name = db.execute(
        text("SELECT name FROM user_permissions WHERE slug = :s"), {"s": _TARGET_SLUG}
    ).scalar()
    assert name == "View Stock Debt"


def test_running_it_twice_changes_nothing(db):
    role = _role(db, "idempotent")
    _grant(db, role, _SOURCE_SLUG)

    _run(db)
    first = _slugs_for(db, role)
    _run(db)

    assert _slugs_for(db, role) == first
    count = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :role"),
        {"role": role},
    ).scalar()
    assert count == len(first)


def test_downgrade_takes_the_grant_back_and_leaves_the_permission_row(db):
    role = _role(db, "reversible")
    _grant(db, role, _SOURCE_SLUG)
    _run(db)

    _run(db, "downgrade")

    assert _TARGET_SLUG not in _slugs_for(db, role)
    remaining = db.execute(
        text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": _TARGET_SLUG}
    ).scalar()
    assert remaining == 1


def test_downgrade_leaves_a_hand_made_grant_alone(db):
    role = _role(db, "hand_granted")
    _grant(db, role, _TARGET_SLUG)  # granted directly, no projects.projects.view behind it

    _run(db)
    _run(db, "downgrade")

    assert _TARGET_SLUG in _slugs_for(db, role)
