"""NEW-PRODUCT-APP v4 migration (npa_0002_paper_layout): id fits alembic_version, one head,
every column the models gained is in the DDL, and the DDL is idempotent."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "npa_0002_paper_layout"
NEW_COLUMNS = {
    "new_product_application_lines": ["dimension", "material", "thickness", "packing"],
    "new_product_applications": ["lead_time", "feedback_by", "feedback_at"],
}


def _path(name: str) -> Path:
    return ROOT / "alembic" / "versions" / f"{name}.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _path(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_chains_onto_npa_0001_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _load(NAME)
    assert module.revision == NAME
    assert len(module.revision) <= 32
    assert module.down_revision == "npa_0001_new_product_apps"
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert NAME in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_every_new_column_is_in_the_ddl_and_the_ddl_is_idempotent():
    source = _path(NAME).read_text()
    for table, columns in NEW_COLUMNS.items():
        assert table in source, table
        for column in columns:
            assert re.search(rf"\b{column}\b", source), column
    assert "IF NOT EXISTS" in source.upper()
    assert "ADD COLUMN IF NOT EXISTS" in source.upper()


def test_feedback_by_references_users_set_null_like_decided_by():
    source = _path(NAME).read_text()
    assert re.search(r"feedback_by[^\n,]*VARCHAR\(100\)", source, re.I)
    assert "users" in source
    assert "SET NULL" in source.upper()


def test_the_models_carry_the_new_columns():
    from app.models.new_product_application import NewProductApplication, NewProductApplicationLine

    for model, table in ((NewProductApplicationLine, "new_product_application_lines"),
                         (NewProductApplication, "new_product_applications")):
        names = {c.name for c in model.__table__.columns}
        assert set(NEW_COLUMNS[table]) <= names, (table, set(NEW_COLUMNS[table]) - names)


def test_migration_covers_every_model_column_that_npa_0001_does_not():
    from app.models.new_product_application import NewProductApplication, NewProductApplicationLine

    first = (ROOT / "alembic" / "versions" / "npa_0001_new_product_apps.py").read_text()
    second = _path(NAME).read_text()
    for model in (NewProductApplication, NewProductApplicationLine):
        for column in model.__table__.columns:
            in_first = f"            {column.name} " in first
            assert in_first or re.search(rf"\b{column.name}\b", second), (model.__tablename__, column.name)
