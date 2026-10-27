"""RESUBMITTED-STATUS migration: revision id fits, one alembic head, and the widened NPA CHECK
matches the model (CI builds its schema from the models, so a drift would pass CI and fail on
the real database)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "resub_0001_resubmitted_status"


def _load():
    spec = importlib.util.spec_from_file_location(NAME, ROOT / "alembic" / "versions" / f"{NAME}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _load()
    assert module.revision == NAME
    assert len(module.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert NAME in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_npa_check_matches_the_model():
    from app.models.new_product_application import STATUSES

    module = _load()
    migrated = {s.strip().strip("'") for s in module._NPA_STATUSES_NEW.split(",")}
    assert migrated == set(STATUSES)
    assert "resubmitted" in migrated
