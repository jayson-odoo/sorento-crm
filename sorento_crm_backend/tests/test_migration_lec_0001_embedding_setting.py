"""AC-LEC-2: migration lec_0001_embedding_setting, run for real on a blank Postgres schema.

The blank schema comes from the models, so the four columns may already exist; the tests
downgrade first where they need the pre-migration shape. Everything rolls back.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import TEST_PREFIX, blank_session

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "lec_0001_embedding_setting.py"
COLS = ("embedding_provider", "embedding_model", "embedding_records_search_model", "embedding_backfill_rpm")


def _module():
    assert MIGRATION.exists(), f"missing {MIGRATION.name}"
    spec = importlib.util.spec_from_file_location("_lec_0001_test", MIGRATION)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(db, fn):
    m = _module()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(m, fn)()


def _cols(db):
    rows = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'system_settings'"
        )
    ).all()
    return {r[0] for r in rows}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _row_without_columns(db):
    """A settings row and the pre-migration shape (columns dropped through the migration's own downgrade)."""
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} LEC"))
    db.flush()
    _run(db, "downgrade")
    assert not set(COLS) & _cols(db)


def _label(db, provider, model):
    vid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO ai_prompt_versions (id, name, version, type, template, variables) "
            "VALUES (:i, 'chatbot_lookup_embedder', 1, 'text', 'x', '[]'::jsonb)"
        ),
        {"i": vid},
    )
    db.execute(
        text(
            "INSERT INTO ai_prompt_labels (id, name, label, version_id, provider, model) "
            "VALUES (:i, 'chatbot_lookup_embedder', 'production', :v, :p, :m)"
        ),
        {"i": str(uuid.uuid4()), "v": vid, "p": provider, "m": model},
    )


def _values(db):
    return db.execute(
        text(
            "SELECT embedding_provider, embedding_model, embedding_records_search_model, embedding_backfill_rpm "
            "FROM system_settings"
        )
    ).one()


def test_ac_lec_2_revision_id_fits_and_chains():
    m = _module()
    assert m.revision == "lec_0001_embedding_setting" and len(m.revision) <= 32
    assert m.down_revision


def test_ac_lec_2_upgrade_copies_production_label(db):
    _row_without_columns(db)
    _label(db, "gemini", "gemini-embedding-001")
    _run(db, "upgrade")
    assert set(COLS) <= _cols(db)
    assert tuple(_values(db)) == ("gemini", "gemini-embedding-001", "text-embedding-3-small", 20)


def test_ac_lec_2_without_label_provider_and_model_stay_null(db):
    _row_without_columns(db)
    _run(db, "upgrade")
    provider, model, search, _rpm = _values(db)
    assert provider is None and model is None
    assert search == "text-embedding-3-small"


def test_ac_lec_2_upgrade_twice_is_safe_and_keeps_edits(db):
    _row_without_columns(db)
    _label(db, "gemini", "gemini-embedding-001")
    _run(db, "upgrade")
    db.execute(text("UPDATE system_settings SET embedding_provider = 'openai', embedding_model = 'text-embedding-3-large'"))
    _run(db, "upgrade")
    assert tuple(_values(db))[:3] == ("openai", "text-embedding-3-large", "text-embedding-3-small")


def test_ac_lec_2_downgrade_drops_the_four_columns(db):
    _run(db, "upgrade")
    assert set(COLS) <= _cols(db)
    _run(db, "downgrade")
    assert not set(COLS) & _cols(db)
