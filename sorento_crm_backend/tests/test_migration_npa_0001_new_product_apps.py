"""NEW-PRODUCT-APP migration: revision id fits alembic_version and alembic keeps one head.

The DDL itself is `IF NOT EXISTS` and was applied, downgraded and re-applied on a dev copy;
the schema the suite runs on is built from the models (bootstrap_env), which these tests
compare against the migration's own column list.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDED_BY_NPA_0002 = {
    "dimension", "material", "thickness", "packing", "lead_time", "feedback_by", "feedback_at",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "alembic" / "versions" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _load("npa_0001_new_product_apps")
    assert module.revision == "npa_0001_new_product_apps"
    assert len(module.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert "npa_0001_new_product_apps" in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_migration_creates_every_model_column():
    """bootstrap_env builds CI's schema from the models, so a column the model has and the
    migration lacks would pass CI and fail on the real database."""
    from app.models.new_product_application import NewProductApplication, NewProductApplicationLine

    source = (ROOT / "alembic" / "versions" / "npa_0001_new_product_apps.py").read_text()
    for model in (NewProductApplication, NewProductApplicationLine):
        for column in model.__table__.columns:
            if column.name in ADDED_BY_NPA_0002:
                continue  # v4 columns live in npa_0002_paper_layout (its own test checks them)
            assert f"            {column.name} " in source, (model.__tablename__, column.name)
