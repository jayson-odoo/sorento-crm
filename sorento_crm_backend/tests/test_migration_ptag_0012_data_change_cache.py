"""Migration ptag_0012 - the list's stored product-data-change cache (AC-D1).

PLAN-price-tag-currency-token-extract-prompt.md section D: computing the diff
per list row would add up to 50 x 60 ms to every page load, so the count is
cached on the request and refreshed only for rows a cheap query says were
touched. This migration is the cache columns.

Written test-FIRST (PRINCIPLES.md Phase 2): the migration file does not exist
yet, so importing it below fails at collection with a `FileNotFoundError` -
the same single-file RED `test_migration_ptag_0011_line_promotion.py` and
`test_migration_ptag_0009_combos_tags.py` both start from.

Unlike ptag_0011's own test, `blank_session()`'s `create_all` here still
builds the PRE-migration model (the coder's D slice has not landed), so no
"rewind" step is needed - the scratch schema already looks like production
looked before this revision.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "ptag_0012_data_change_cache.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("ptag0012", MIGRATION)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(MIGRATION)
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
    return module


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _contact(db) -> str:
    contact_id = _uid()
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, :n)"),
        {"i": contact_id, "p": f"+60{uuid.uuid4().hex[:9]}", "n": unique_code("contact")},
    )
    db.flush()
    return contact_id


def _request(db) -> str:
    request_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_requests (id, company_id, contact_id, doc_number, status) "
            "VALUES (:i, :co, :ct, :d, 'designing')"
        ),
        {"i": request_id, "co": SORENTO, "ct": _contact(db), "d": unique_code("PT12")[:40]},
    )
    db.flush()
    return request_id


# --------------------------------------------------------------------------- AC-D1


def test_upgrade_adds_the_two_columns_with_the_right_defaults(db):
    request_id = _request(db)

    _run_upgrade(db)

    columns = {
        column["name"]: column
        for column in inspect(db.get_bind()).get_columns("price_tag_requests")
    }
    assert "data_changed_tag_count" in columns
    assert "data_checked_at" in columns
    assert columns["data_changed_tag_count"]["nullable"] is False
    assert columns["data_checked_at"]["nullable"] is True

    row = db.execute(
        text(
            "SELECT data_changed_tag_count, data_checked_at FROM price_tag_requests "
            "WHERE id = :i"
        ),
        {"i": request_id},
    ).one()
    assert row.data_changed_tag_count == 0
    assert row.data_checked_at is None


def test_single_alembic_head_still_holds_after_this_revision(db):
    """ptag_0012 must chain onto ptag_0011, never branch it (LESSONS-LEARNT:
    a dual head fails CI's `check-migration-heads` gate)."""
    module = _load_migration()
    assert module.down_revision == "ptag_0011_line_promo"
    assert len(module.revision) <= 32


def test_downgrade_drops_the_two_columns(db):
    _request(db)
    _run_upgrade(db)

    _run_downgrade(db)

    columns = {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_requests")
    }
    assert "data_changed_tag_count" not in columns
    assert "data_checked_at" not in columns
