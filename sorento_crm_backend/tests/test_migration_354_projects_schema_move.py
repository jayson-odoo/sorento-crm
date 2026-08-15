"""Migration 354 has to be a no-op on a fresh database and do the work on an old one.

The projects module's 47 tables move from the default schema into `projects`, and the 34
that carried the `project_` prefix drop it on the way (ADR-0011). A database built by
`create_all` from the post-move models arrives with the tables already there and already
named; the shared development database arrives with all 47 sitting in `public` under their
old names. One revision serves both starting schemas, and every step is guarded on "the
source is there and the destination is not".

That guard is the whole revision, and it is the kind of thing never exercised until a
deploy: CI takes the no-op path, so a bug in the moving path ships, and a developer whose
database takes the moving path never sees the no-op path break. Both are run here.

The revision is imported and executed against a scratch schema pair rather than asserted
about the live database, per the pattern in CLAUDE.md and in
`test_migration_353_order_inquiry_rename.py`. Its `TARGET_SCHEMA` is rebound to the
fixture's scratch projects schema first: the module resolves its SOURCE schema from
`current_schema()` for the same reason, so neither end of the move can reach past the
scratch schemas into the real database and move production tables.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.database import Base
from app.models.base import set_company_scope
from app.models.project_so import OrderInquiry, ProjectSalesOrder
from app.models.projects import Project, ProjectLead
from tests._pg_fixture import blank_schema_engine, blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "354_projects_schema_move.py"
)


def _scratch_projects_schema() -> str:
    """The scratch stand-in for the real `projects` schema, from the fixture's own map."""
    options = blank_schema_engine().get_execution_options()
    return options["schema_translate_map"]["projects"]


def _scratch_default_schema() -> str:
    options = blank_schema_engine().get_execution_options()
    return options["schema_translate_map"][None]


@pytest.fixture
def db():
    """A scratch schema pair built by ``create_all``, so it carries the POST-move shape.

    Everything here is DDL, and Postgres runs DDL inside the transaction the fixture rolls
    back, so both scratch schemas are unchanged afterwards.
    """
    with blank_session() as session:
        yield session


def _module():
    spec = importlib.util.spec_from_file_location("m354", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Point the revision at the scratch projects schema. Without this the ALTERs would
    # name the REAL `projects` schema, and the test would move production tables.
    module.TARGET_SCHEMA = _scratch_projects_schema()
    return module


def _run(db, direction: str) -> None:
    module = _module()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, direction)()


def _schemas() -> list[str]:
    return [_scratch_default_schema(), _scratch_projects_schema()]


def _tables(db) -> set[str]:
    """Every module table, as `schema.table`, across BOTH scratch schemas.

    Filtering on `current_schema()` alone - which is what the 353 test does - would see an
    empty set after the move and pass regardless of what the revision did.
    """
    names = {old for old, _ in _module().TABLES} | {new for _, new in _module().TABLES}
    rows = db.execute(
        text(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname = ANY(:schemas) AND tablename = ANY(:names)"
        ),
        {"schemas": _schemas(), "names": sorted(names)},
    )
    return {f"{row[0]}.{row[1]}" for row in rows}


def _indexes(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT schemaname, indexname FROM pg_indexes WHERE schemaname = ANY(:schemas)"
        ),
        {"schemas": _schemas()},
    )
    return {f"{row[0]}.{row[1]}" for row in rows}


def _constraints(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT n.nspname, c.relname, con.conname FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ANY(:schemas)"
        ),
        {"schemas": _schemas()},
    )
    return {f"{row[0]}.{row[1]}.{row[2]}" for row in rows}


def _snapshot(db):
    return (_tables(db), _indexes(db), _constraints(db))


# --------------------------------------------------------------------------- #
# the mapping itself
# --------------------------------------------------------------------------- #

def test_the_mapping_covers_exactly_the_models_that_declare_the_projects_schema():
    """The revision's table list and the model files must agree, table for table.

    Two independent sources of the same fact, which is the point: a model moved into the
    schema without a line in the revision would never reach a migrated database, and a line
    in the revision with no model behind it would move a table nothing reads.
    """
    module = _module()
    from app import models  # noqa: F401  register every model

    declared = {
        table.name
        for table in Base.metadata.tables.values()
        if table.schema == "projects"
    }

    assert len(module.TABLES) == 47
    assert {new for _, new in module.TABLES} == declared
    assert len({old for old, _ in module.TABLES}) == 47


# --------------------------------------------------------------------------- #
# the fresh database - CI, and every new install
# --------------------------------------------------------------------------- #

def test_upgrade_changes_nothing_when_the_tables_are_already_in_the_projects_schema(db):
    """A schema built from the current models is already moved. 354 must not raise."""
    target = _scratch_projects_schema()
    before = _snapshot(db)

    assert {name for name in before[0] if name.startswith(f"{target}.")}, (
        "the scratch schema pair is not the post-move one"
    )

    _run(db, "upgrade")

    assert _snapshot(db) == before


def test_upgrade_is_repeatable(db):
    """Twice is the same as once. A guard that only holds on the first pass is not a guard."""
    _run(db, "upgrade")
    before = _snapshot(db)

    _run(db, "upgrade")

    assert _snapshot(db) == before


# --------------------------------------------------------------------------- #
# the database that predates the move - the shared development one
# --------------------------------------------------------------------------- #

def test_upgrade_moves_and_renames_when_the_tables_are_in_the_default_schema(db):
    """Build the pre-354 schema with the revision's own downgrade, then move it back."""
    module = _module()
    default = _scratch_default_schema()
    target = _scratch_projects_schema()
    expected = _snapshot(db)

    _run(db, "downgrade")

    after_down = _tables(db)
    assert after_down == {f"{default}.{old}" for old, _ in module.TABLES}, (
        "downgrade did not produce the pre-move schema"
    )
    assert not [name for name in after_down if name.startswith(f"{target}.")]

    _run(db, "upgrade")

    # Back to exactly what create_all builds. Indexes and constraints are asserted too:
    # they ride along with SET SCHEMA and are deliberately NOT renamed, so a stray
    # rename in either direction would show here.
    assert _snapshot(db) == expected


def test_index_names_keep_the_project_prefix_inside_the_projects_schema(db):
    """Deliberate, per ADR-0011: `projects.parties` carries `ix_project_parties_*`.

    Pinned rather than left implicit because it reads as drift to the next person to run
    autogenerate, and the cost of "tidying" it is 200-odd renames of live objects.
    """
    target = _scratch_projects_schema()

    assert f"{target}.ix_project_parties_name" in _indexes(db)
    assert f"{target}.uq_projects_company_developer_title" in _indexes(db)


def test_rows_travel_with_the_tables(db):
    """A move, not a re-create: the row in the old table is the row in the new one.

    `ALTER TABLE ... SET SCHEMA` is metadata-only, which is the whole argument for doing
    this on a database that already holds project rows. Asserted rather than assumed.
    """
    set_company_scope(db, frozenset({SORENTO}))
    default = _scratch_default_schema()
    target = _scratch_projects_schema()

    lead = ProjectLead(
        lead_code=unique_code("lead"),
        title="ZZT Schema Move Lead",
        normalised_title=unique_code("zzt schema move"),
    )
    db.add(lead)
    db.flush()
    project = Project(
        project_code=unique_code("proj"),
        title="ZZT Schema Move Tower",
        normalised_title=unique_code("zzt schema move tower"),
        lead_id=lead.id,
    )
    db.add(project)
    db.flush()
    sales_order = ProjectSalesOrder(
        project_id=project.id, provisional_ref=unique_code("SO")
    )
    db.add(sales_order)
    db.flush()
    inquiry = OrderInquiry(project_sales_order_id=sales_order.id)
    db.add(inquiry)
    db.flush()
    inquiry_id = str(inquiry.id)

    # Detach the identity map before the tables move out from under it.
    db.expunge_all()

    _run(db, "downgrade")
    assert (
        db.execute(
            text(
                f'SELECT count(*) FROM "{default}"."project_order_inquiries" WHERE id = :i'
            ),
            {"i": inquiry_id},
        ).scalar()
        == 1
    ), "the row did not travel with the table on the way down"

    _run(db, "upgrade")

    assert (
        db.execute(
            text(f'SELECT count(*) FROM "{target}"."order_inquiries" WHERE id = :i'),
            {"i": inquiry_id},
        ).scalar()
        == 1
    )
