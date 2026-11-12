"""NEW-PRODUCT-APP migration: revision id fits alembic_version and alembic keeps one head.

The DDL itself is `IF NOT EXISTS` and was applied, downgraded and re-applied on a dev copy;
the schema the suite runs on is built from the models (bootstrap_env), which these tests
compare against the migration's own column list.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDED_BY_NPA_0002 = {
    "dimension", "material", "thickness", "packing", "lead_time", "feedback_by", "feedback_at",
}

# NPA-FROM-SI (#2233, migration npasi_0001_lineage) added the purchasing new-code columns to the
# header table. Read from that migration's own DDL, table-qualified, so a column is only excused
# here when the later migration really adds it to new_product_applications.
# NPA-FORM-SLA (#2261, migration npasla_0002_npa_revision_no) added revision_no to the header
# table the same way.
LATER_MIGRATIONS = ("npasi_0001_lineage", "npasla_0002_npa_revision_no")


def _added_by_later_migrations(table: str) -> set[str]:
    added: set[str] = set()
    for name in LATER_MIGRATIONS:
        source = (ROOT / "alembic" / "versions" / f"{name}.py").read_text()
        added |= set(re.findall(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS (\w+) ", source))
    return added


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
        later = _added_by_later_migrations(model.__tablename__)
        for column in model.__table__.columns:
            if column.name in ADDED_BY_NPA_0002:
                continue  # v4 columns live in npa_0002_paper_layout (its own test checks them)
            if column.name in later:
                continue  # added by a later migration (LATER_MIGRATIONS), found in its DDL
            assert f"            {column.name} " in source, (model.__tablename__, column.name)
