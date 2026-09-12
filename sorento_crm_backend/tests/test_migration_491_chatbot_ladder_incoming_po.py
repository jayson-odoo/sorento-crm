"""Migration `491_chatbot_ladder_incoming_po` (D7, owner ruling 8 Sep 2026).

Appends `purchase_order` to the `incoming` origin of `system_settings.
chatbot_crossdomain_ladder` ONLY where the row still holds the exact 489 default; a
custom ladder is untouched. Loaded by file path (the `_run_migration` idiom).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "491_chatbot_ladder_incoming_po.py"
OLD = {"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}
NEW = {"inventory": ["incoming", "purchase_order"], "incoming": ["inventory", "purchase_order"]}
CUSTOM = {"inventory": ["incoming"]}


def _load_migration():
    assert MIGRATION.exists(), f"{MIGRATION} does not exist"
    spec = importlib.util.spec_from_file_location("m491_ladder", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_id_is_under_32_characters():
    module = _load_migration()
    assert len(module.revision) <= 32, (module.revision, len(module.revision))
    assert module.down_revision == "490_chatbot_parser_growth"


def _insert_settings(db, ladder: dict) -> str:
    """Through the model, so every NOT NULL column takes its own default; the ladder is
    the one value this test sets by hand."""
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), chatbot_crossdomain_ladder=ladder)
    db.add(row)
    db.flush()
    return str(row.id)


def _ladder(db, sid: str) -> dict:
    return db.execute(
        text("SELECT chatbot_crossdomain_ladder FROM system_settings WHERE id = :i"), {"i": sid}
    ).scalar()


def test_upgrade_moves_only_the_489_default_and_is_idempotent():
    module = _load_migration()
    with blank_session() as db:
        db.execute(text("DELETE FROM system_settings"))
        default_row = _insert_settings(db, OLD)
        custom_row = _insert_settings(db, CUSTOM)
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()
        assert _ladder(db, default_row) == NEW
        assert _ladder(db, custom_row) == CUSTOM
        with Operations.context(ctx):
            module.upgrade()  # a second run changes nothing
        assert _ladder(db, default_row) == NEW
        assert _ladder(db, custom_row) == CUSTOM
        with Operations.context(ctx):
            module.downgrade()
        assert _ladder(db, default_row) == OLD
        assert _ladder(db, custom_row) == CUSTOM


def test_the_column_server_default_moves_with_the_migration():
    module = _load_migration()
    with blank_session() as db:
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()
        default = db.execute(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'system_settings' AND column_name = 'chatbot_crossdomain_ladder' "
                "AND table_schema = current_schema()"
            )
        ).scalar()
        assert '"incoming": ["inventory", "purchase_order"]' in (default or ""), default
