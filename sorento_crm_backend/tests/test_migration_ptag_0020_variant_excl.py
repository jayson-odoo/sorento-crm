"""PRICETAG-UPGRADE-VARIANTS BE test 9: migration `ptag_0020_variant_excl`.

Written test-FIRST: the revision file does not exist yet. Additive:
`price_tag_request_lines.excluded_variant_ids JSONB NOT NULL DEFAULT '[]'`.
"""
from __future__ import annotations

import ast
from pathlib import Path

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session

BACKEND = Path(__file__).resolve().parent.parent
REVISION_FILE = BACKEND / "alembic" / "versions" / "ptag_0020_variant_excl.py"


def test_revision_is_additive_and_chains_onto_one_head():
    tree = ast.parse(REVISION_FILE.read_text())
    assigns = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
    }
    assert assigns["revision"] == "ptag_0020_variant_excl"
    assert len(assigns["revision"]) <= 32

    source = REVISION_FILE.read_text()
    upgrade = source.split("def downgrade", 1)[0]
    for word in ("drop_table", "drop_column", "DROP TABLE", "DROP COLUMN", "DELETE FROM"):
        assert word not in upgrade, f"upgrade is additive only: found {word}"
    for needle in ("price_tag_request_lines", "excluded_variant_ids", "JSONB", "'[]'"):
        assert needle in source, f"the migration never mentions {needle}"

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    known = {rev.revision for rev in script.walk_revisions()}
    assert assigns["down_revision"] in known and assigns["down_revision"] != assigns["revision"]
    ancestry = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert "ptag_0020_variant_excl" in ancestry


def test_the_column_exists_with_an_empty_list_default():
    from sqlalchemy import text

    with blank_session() as db:
        column = db.execute(
            text(
                "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = 'price_tag_request_lines' AND column_name = 'excluded_variant_ids' "
                "AND table_schema = current_schema()"
            )
        ).first()
        assert column is not None, "price_tag_request_lines.excluded_variant_ids is missing"
        assert column.data_type == "jsonb"
        assert column.is_nullable == "NO"
        assert "[]" in column.column_default


def test_a_line_inserted_without_the_field_reads_an_empty_list(monkeypatch):
    r9.block_respond(monkeypatch)
    with blank_session() as db:
        host = seed.product(db, "ZZMIG")
        request = seed.submit_one(db, host)
        db.flush()
        db.expire_all()
        assert request.lines[0].excluded_variant_ids == []
