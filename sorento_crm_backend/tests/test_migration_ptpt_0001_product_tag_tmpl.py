"""Migration ptpt_0001_product_tag_tmpl (PRICETAG-TEMPLATE-PER-PRODUCT, AC-18).

Additive and idempotent: a create_all database already holds both pieces, so
upgrade must be a no-op there; downgrade drops both. Run on the blank scratch
schema inside a rolled-back transaction (Postgres DDL is transactional).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session

_MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "ptpt_0001_product_tag_templates.py"
)


def _run(db, fn: str) -> None:
    spec = importlib.util.spec_from_file_location("migration_ptpt_0001", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(db.connection())):
        getattr(module, fn)()


def _state(db) -> tuple[bool, bool, bool]:
    # Unqualified: the scratch schema's dealer_kit sibling is on search_path.
    table = db.execute(text("SELECT to_regclass('product_tag_template') IS NOT NULL")).scalar()
    column = db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = 'price_tag_request_lines' AND column_name = 'tag_template_id'"
        )
    ).scalar()
    fk = db.execute(
        text(
            "SELECT count(*) FROM pg_constraint WHERE conname = "
            "'price_tag_request_lines_tag_template_id_fkey' "
            "AND conrelid = 'price_tag_request_lines'::regclass"
        )
    ).scalar()
    return bool(table), bool(column), bool(fk)


def test_upgrade_is_a_noop_on_create_all_and_downgrade_round_trips():
    with blank_session() as db:
        assert _state(db) == (True, True, True)  # create_all already has both
        _run(db, "upgrade")  # no-op, no error
        assert _state(db) == (True, True, True)
        _run(db, "downgrade")
        assert _state(db) == (False, False, False)
        _run(db, "upgrade")
        assert _state(db) == (True, True, True)
        _run(db, "upgrade")  # idempotent
        assert _state(db) == (True, True, True)
