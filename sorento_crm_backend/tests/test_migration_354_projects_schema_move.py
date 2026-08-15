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

    In the default schema only the PRE-move names count. Seven of the post-move bare names
    (`brands`, `purchase_orders`, `sales_orders` and friends) are also CORE tables sitting
    right there, and counting those would make the assertion drift with core rather than
    with this revision. The pre-move names carry the `project_` prefix precisely so they
    cannot be confused, and the 13 that never carried it collide with nothing.
    """
    projects_schema = _scratch_projects_schema()
    old_names = sorted(old for old, _ in _module().TABLES)
    rows = db.execute(
        text(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname = :projects "
            "   OR (schemaname = :default AND tablename = ANY(:old_names))"
        ),
        {
            "projects": projects_schema,
            "default": _scratch_default_schema(),
            "old_names": old_names,
        },
    )
    return {f"{row[0]}.{row[1]}" for row in rows}


def _scope_params() -> dict:
    return {
        "projects": _scratch_projects_schema(),
        "default": _scratch_default_schema(),
        "old_names": sorted(old for old, _ in _module().TABLES),
    }


#: Same scoping as ``_tables``: module tables only, never the core table that happens to
#: share a bare name. Including core's `brands_pkey` here would make the round-trip
#: expectation below rewrite a core index name.
_MODULE_TABLE_SCOPE = (
    "(n.nspname = :projects OR (n.nspname = :default AND c.relname = ANY(:old_names)))"
)


def _indexes(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT n.nspname, ic.relname FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE {_MODULE_TABLE_SCOPE}"
        ),
        _scope_params(),
    )
    return {f"{row[0]}.{row[1]}" for row in rows}


def _constraints(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT n.nspname, c.relname, con.conname FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE {_MODULE_TABLE_SCOPE}"
        ),
        _scope_params(),
    )
    return {f"{row[0]}.{row[1]}.{row[2]}" for row in rows}


def _snapshot(db):
    return (_tables(db), _indexes(db), _constraints(db))


def _with_derived_names_restored(names: set[str]) -> set[str]:
    """Apply the down-direction rule to a set of qualified constraint / index names.

    A name Postgres DERIVED from the post-move table name (`brands_pkey`) becomes the name
    it would have derived from the pre-move one (`project_brands_pkey`). ``downgrade()``
    does this because index names are unique per schema and `brands_pkey` is already taken
    in the default schema by CORE `brands`; ``upgrade()`` deliberately does not undo it,
    since renaming 200-odd live objects would be risk spent on cosmetics (ADR-0011).

    So a create_all schema that has been round-tripped down and back carries the prefixed
    names - which is exactly what a database migrated by this revision has always carried.
    """
    mapping = {new: old for old, new in _module().TABLES if old != new}
    out = set()
    for qualified in names:
        head, _, name = qualified.rpartition(".")
        for new, old in mapping.items():
            if name.startswith(f"{new}_"):
                name = f"{old}{name[len(new):]}"
                break
        out.add(f"{head}.{name}")
    return out


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

    tables, indexes, constraints = _snapshot(db)
    # Every table is back where create_all put it, under the name create_all gave it.
    assert tables == expected[0]
    # Indexes and constraints are asserted too, because they ride along with SET SCHEMA
    # and a stray rename in either direction would show here. The one expected change is
    # the derived-name restoration the downgrade had to perform and the upgrade
    # deliberately does not undo.
    assert indexes == _with_derived_names_restored(expected[1])
    assert constraints == _with_derived_names_restored(expected[2])


def test_downgrade_moves_a_colliding_table_back_beside_its_core_namesake(db):
    """`projects.brands` has to land next to CORE `brands` without either losing its key.

    Index names are unique per SCHEMA. A schema built by create_all calls the module key
    `brands_pkey`, and CORE `brands` already owns that name in the default schema, so a
    plain SET SCHEMA is refused outright - which is what this revision did before the
    downgrade learned to restore derived names. Five of the seven colliding tables hit it.
    """
    default = _scratch_default_schema()

    _run(db, "downgrade")

    names = {name.rpartition(".")[2] for name in _indexes(db)}
    assert "project_brands_pkey" in names, "the module key did not come back prefixed"
    assert f"{default}.project_brands" in _tables(db)

    # Core's own key is untouched and still where it was.
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = :s AND c.relname = 'brands_pkey'"
            ),
            {"s": default},
        ).scalar()
        == 1
    )


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
