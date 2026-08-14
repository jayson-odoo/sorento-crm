"""Migration 353 has to be a no-op on a fresh database and do the work on an old one.

The two order-inquiry tables were created as `order_inquiries` / `order_inquiry_rows` by
revisions 319 and 322. Those revisions now emit the `project_` prefixed names directly, so a
database built from scratch arrives at 353 with the new names already in place and there is
nothing to rename. The shared development database, created before that edit, arrives with the
old ones. One revision therefore has to serve two different starting schemas, and every step in
it is guarded on "the old name is present and the new one is not".

That guard is the whole revision, and it is exactly the kind of thing that is never exercised
until a deploy: CI takes the no-op path, so a bug in the renaming path ships, and a developer
whose database takes the renaming path never sees the no-op path break. Both are run here.

The migration is imported and executed against a scratch schema rather than asserted about the
live database, per the pattern in CLAUDE.md. The live database is already past this revision,
so "the new table exists there" would be a statement about the environment, not about the code.
The old-name schema is built by running the revision's own `downgrade()`, which pins that half
of the file at the same time.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.project_so import OrderInquiry, ProjectSalesOrder
from app.models.projects import Project, ProjectLead
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "353_project_order_inquiry_rename.py"
)

NEW_TABLES = ("project_order_inquiries", "project_order_inquiry_rows")
OLD_TABLES = ("order_inquiries", "order_inquiry_rows")


@pytest.fixture
def db():
    """A scratch schema built by ``create_all``, so it carries the NEW names already.

    Everything here is DDL, and Postgres runs DDL inside the transaction the fixture rolls
    back, so the shared blank schema is unchanged afterwards.
    """
    with blank_session() as session:
        yield session


def _module():
    spec = importlib.util.spec_from_file_location("m353", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str) -> None:
    module = _module()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, direction)()


def _tables(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
            "AND (tablename LIKE 'order_inquir%' OR tablename LIKE 'project_order_inquir%')"
        )
    )
    return {row[0] for row in rows}


def _indexes(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
            "AND tablename = ANY(:names)"
        ),
        {"names": list(NEW_TABLES + OLD_TABLES)},
    )
    return {row[0] for row in rows}


def _constraints(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relname = ANY(:names)"
        ),
        {"names": list(NEW_TABLES + OLD_TABLES)},
    )
    return {row[0] for row in rows}


# --------------------------------------------------------------------------- #
# the fresh database - CI, and every new install
# --------------------------------------------------------------------------- #

def test_upgrade_changes_nothing_when_the_new_names_are_already_there(db):
    """A schema built from the current models arrives already renamed. 353 must not raise.

    The assertion is that NOTHING moved, not merely that the tables still exist: the guards
    cover indexes and constraints separately, and a missing guard on one of those would
    raise ``ALTER INDEX ... does not exist`` rather than quietly do the wrong thing.
    """
    before = (_tables(db), _indexes(db), _constraints(db))
    assert set(NEW_TABLES) <= before[0]
    assert not (set(OLD_TABLES) & before[0]), "the scratch schema is not the post-rename one"

    _run(db, "upgrade")

    assert (_tables(db), _indexes(db), _constraints(db)) == before


def test_upgrade_is_repeatable_on_the_new_names(db):
    """Twice is the same as once. A guard that only holds on the first pass is not a guard."""
    _run(db, "upgrade")
    before = (_tables(db), _indexes(db), _constraints(db))

    _run(db, "upgrade")

    assert (_tables(db), _indexes(db), _constraints(db)) == before


# --------------------------------------------------------------------------- #
# the database that predates the rename - the shared development one
# --------------------------------------------------------------------------- #

def test_upgrade_renames_when_the_old_names_are_present(db):
    """Build the pre-353 schema with the revision's own downgrade, then upgrade it back."""
    expected = (_tables(db), _indexes(db), _constraints(db))

    _run(db, "downgrade")

    old_names = _tables(db)
    assert set(OLD_TABLES) <= old_names, "downgrade did not produce the pre-rename schema"
    assert not (set(NEW_TABLES) & old_names)
    assert "order_inquiries_pkey" in _constraints(db)
    assert "ix_order_inquiries_order" in _indexes(db)

    _run(db, "upgrade")

    # Back to exactly the schema create_all builds: every table, index and constraint name
    # round-trips. Anything the revision renamed on the way down and forgot on the way up
    # would show here as a leftover `order_inquir%` name.
    assert (_tables(db), _indexes(db), _constraints(db)) == expected


def test_upgrade_carries_the_rows_across_the_rename(db):
    """A rename, not a re-create: the row that was in the old table is in the new one.

    This is the reason 353 exists at all. Re-creating the tables would have been shorter,
    and it would have silently emptied the order inquiries the shared development database
    was already holding.
    """
    set_company_scope(db, frozenset({SORENTO}))

    lead = ProjectLead(
        lead_code=unique_code("lead"),
        title="ZZT Rename Lead",
        normalised_title=unique_code("zzt rename"),
    )
    db.add(lead)
    db.flush()
    project = Project(
        project_code=unique_code("proj"),
        title="ZZT Rename Tower",
        normalised_title=unique_code("zzt rename tower"),
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
            text("SELECT count(*) FROM order_inquiries WHERE id = :i"), {"i": inquiry_id}
        ).scalar()
        == 1
    ), "the row did not travel with the table on the way down"

    _run(db, "upgrade")

    assert (
        db.execute(
            text("SELECT count(*) FROM project_order_inquiries WHERE id = :i"),
            {"i": inquiry_id},
        ).scalar()
        == 1
    )
