"""Migration 456 - ``dealer_kit.page.draft_doc`` (B1, captain ruling 2 Sep).

Driven through ``upgrade()``/``downgrade()`` against the real database inside a
rolled-back transaction, exactly as ``test_migration_454_tag_template_versions``
does and for the same reason: the shared dev database converges through
``Base.metadata.create_all`` rather than ``alembic upgrade``, so this DDL is
hand-applied there with ``alembic_version`` parked elsewhere - a replay has to
be a no-op or the next person to run ``alembic upgrade head`` gets a
duplicate-column error on a database that was already correct.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from tests._pg_fixture import pg_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "456_page_draft_doc.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_456", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _has_column(db) -> bool:
    return "draft_doc" in {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("page", schema="dealer_kit")
    }


@pytest.fixture
def db():
    with pg_session() as session:
        if _has_column(session):
            _run(session, "downgrade")
        yield session


def _make_page(db) -> str:
    page_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO dealer_kit.page (id, name, slug, kind, company_id)"
            " VALUES (:id, :name, :slug, 'tag_sheet',"
            " '00000000-0000-0000-0000-000000000001')"
        ),
        {"id": page_id, "name": unique_code("ZZT Page"), "slug": unique_code("zzt-page").lower()},
    )
    return page_id


def test_the_column_does_not_exist_before_upgrade(db):
    assert not _has_column(db)


def test_upgrade_adds_a_nullable_draft_doc(db):
    page_id = _make_page(db)

    _run(db)

    assert _has_column(db)
    # Existing pages get NULL, which is exactly "no work in progress" - no
    # backfill needed and no page suddenly reopening on an empty document.
    assert (
        db.execute(
            text("SELECT draft_doc FROM dealer_kit.page WHERE id = :id"), {"id": page_id}
        ).scalar()
        is None
    )


def test_the_column_holds_jsonb(db):
    page_id = _make_page(db)
    _run(db)

    db.execute(
        text(
            "UPDATE dealer_kit.page SET draft_doc = CAST(:doc AS jsonb) WHERE id = :id"
        ),
        {"doc": '{"kind": "tag_sheet", "sheets": []}', "id": page_id},
    )

    stored = db.execute(
        text("SELECT draft_doc FROM dealer_kit.page WHERE id = :id"), {"id": page_id}
    ).scalar()
    assert stored == {"kind": "tag_sheet", "sheets": []}


def test_running_upgrade_a_second_time_is_a_no_op(db):
    """The shared dev DB has this hand-applied with ``alembic_version`` parked
    on another revision (see the migration docstring)."""
    _run(db)

    _run(db)  # replay - must not raise a duplicate-column error

    assert _has_column(db)


def test_the_downgrade_removes_the_column(db):
    _run(db)

    _run(db, "downgrade")

    assert not _has_column(db)
