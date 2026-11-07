"""NPA-FROM-SI migration (npasi_0001_lineage): id fits alembic_version, one head, additive and
idempotent, the DDL matches the models, and running it twice on a migrated database is a no-op."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
NAME = "npasi_0001_lineage"


def _load():
    path = ROOT / "alembic" / "versions" / f"{NAME}.py"
    spec = importlib.util.spec_from_file_location(NAME, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _load()
    assert module.revision == NAME and len(module.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert NAME in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_the_ddl_is_additive_and_idempotent():
    module = _load()
    for statement in module.UPGRADE:
        upper = " ".join(statement.split()).upper()
        assert "IF NOT EXISTS" in upper, statement
        assert upper.startswith(
            ("ALTER TABLE", "CREATE TABLE IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS", "DO $$ BEGIN IF NOT EXISTS")
        ), statement
        if upper.startswith("ALTER TABLE"):
            assert "ADD COLUMN IF NOT EXISTS" in upper, statement
        assert not any(word in upper for word in ("DROP ", "RENAME ", "ALTER COLUMN"))


def test_the_models_carry_what_the_ddl_adds():
    from app.models.new_product_application import NewProductApplication, NewProductApplicationSource
    from app.models.procurement import StockInquiry

    si = {c.name for c in StockInquiry.__table__.columns}
    assert {"npa_requested", "npa_requested_by", "npa_requested_at"} <= si
    npa = {c.name for c in NewProductApplication.__table__.columns}
    assert {
        "new_product_id", "new_code_closed_reason", "new_code_by", "new_code_at", "new_code_text", "cost_price"
    } <= npa
    source = (ROOT / "alembic" / "versions" / f"{NAME}.py").read_text()
    for needle in ("new_code_text VARCHAR(100)", "cost_price NUMERIC(12, 2)", "ck_new_product_applications_cost"):
        assert needle in source, needle
    src = {c.name for c in NewProductApplicationSource.__table__.columns}
    assert src == {"id", "application_id", "product_id", "position"}


def test_running_the_upgrade_again_is_a_no_op():
    from app.database import engine

    module = _load()
    with engine.begin() as conn:
        for statement in module.UPGRADE:
            conn.execute(sa.text(statement))
