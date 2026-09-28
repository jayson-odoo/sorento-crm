"""AC-IS070 - the #1355 migration, run over the blank schema rather than asserted
against a live database.

`create_all` builds today's models, which already carry the cursor table and the
partial unique index, so the fixture drops both first to rewind to the
pre-migration shape.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._pg_fixture import blank_session

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "ideation_status_events_s1.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("m_ideation_status_events_s1", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade"):
    """``upgrade()`` builds the index CONCURRENTLY in an autocommit block, which would
    commit this test's outer transaction; ``_upgrade(concurrently=False)`` is the same
    DDL inside it (aud_0001's test pattern)."""
    module = _load()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        if direction == "upgrade":
            module._upgrade(concurrently=False)
        else:
            module.downgrade()


@pytest.fixture
def db():
    with blank_session() as session:
        session.execute(text("DROP INDEX IF EXISTS uq_integration_log_ideation_status_event"))
        session.execute(text("DROP TABLE IF EXISTS ideation_status_event_cursors"))
        yield session


def _table_exists(db) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'ideation_status_event_cursors'"
            )
        ).scalar()
    )


def _index_exists(db) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() "
                "AND indexname = 'uq_integration_log_ideation_status_event'"
            )
        ).scalar()
    )


def _log(db, business_table: str, business_id: str):
    db.execute(
        text(
            "INSERT INTO integration_log (id, integration_channel, business_table, business_id, "
            "direction, endpoint, http_method, status, retry_count, max_retry_allowed) "
            "VALUES (:id, 'respond_io', :bt, :bid, 'outbound', 'x', 'POST', 'skipped', 0, 3)"
        ),
        {"id": str(uuid.uuid4()), "bt": business_table, "bid": business_id},
    )


def test_upgrade_creates_the_cursor_table_and_index(db):
    _run(db)

    assert _table_exists(db)
    assert _index_exists(db)
    db.execute(
        text(
            "INSERT INTO ideation_status_event_cursors (id, feed_base_url) "
            "VALUES (gen_random_uuid(), 'https://x')"
        )
    )
    assert (
        db.execute(
            text("SELECT after_seq FROM ideation_status_event_cursors WHERE feed_base_url = 'https://x'")
        ).scalar()
        == 0
    )


def test_index_is_partial_to_ideation_status_events(db):
    _run(db)
    other = str(uuid.uuid4())
    _log(db, "some_other_table", other)
    _log(db, "some_other_table", other)  # other tables may repeat a business_id

    eid = str(uuid.uuid4())
    _log(db, "ideation_status_events", eid)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _log(db, "ideation_status_events", eid)


def test_upgrade_is_rerunnable(db):
    _run(db)
    _run(db)
    assert _table_exists(db) and _index_exists(db)


def test_upgrade_is_the_concurrent_build():
    source = MIGRATION.read_text()
    assert "_upgrade(concurrently=True)" in source
    assert "autocommit_block()" in source


def test_downgrade_drops_both(db):
    _run(db)
    _run(db, "downgrade")
    assert not _table_exists(db)
    assert not _index_exists(db)
