"""RESUBMITTED-STATUS migration: revision id fits, one alembic head, and the widened NPA CHECK
matches the model (CI builds its schema from the models, so a drift would pass CI and fail on
the real database)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "resub_0001_resubmitted_status"
# NPA-FORM-SLA (#2261, migration npasla_0003_npa_responded) widened the same NPA CHECK again, adding
# 'responded'. The database ends on that migration's CHECK, so the chain must hold: it starts from
# exactly this migration's set and its widened set is the model's.
LATER_NPA_CHECK = "npasla_0003_npa_responded"


def _load(name: str = NAME):
    spec = importlib.util.spec_from_file_location(name, ROOT / "alembic" / "versions" / f"{name}.py")
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

    def values(csv: str) -> set[str]:
        return {s.strip().strip("'") for s in csv.split(",")}

    module = _load()
    later = _load(LATER_NPA_CHECK)
    later_source = (ROOT / "alembic" / "versions" / f"{LATER_NPA_CHECK}.py").read_text()
    migrated = values(module._NPA_STATUSES_NEW)
    assert "resubmitted" in migrated
    assert "ck_new_product_applications_status" in later_source
    assert values(later._WITHOUT) == migrated
    assert values(later._WITH) == set(STATUSES)


def test_edition_open_keys_match_the_model_index_and_the_service():
    from app.models.dealer_kit import Edition
    from app.services.dealer_kit.edition_service import OPEN_STATUS_KEYS

    module = _load()
    migrated = {k.strip().strip("'") for k in module._EDITION_OPEN_NEW.split(",")}
    assert migrated == set(OPEN_STATUS_KEYS)
    index = next(i for i in Edition.__table__.indexes if i.name == module._EDITION_INDEX)
    where = str(index.dialect_options["postgresql"]["where"])
    assert all(f"'{key}'" in where for key in OPEN_STATUS_KEYS)


def test_seeding_the_rungs_is_idempotent_and_skips_a_graph_that_does_not_exist():
    from sqlalchemy import text

    from tests._pg_fixture import blank_session

    module = _load()
    with blank_session() as db:
        conn = db.connection()
        module.seed_resubmitted_rungs(conn)  # no graphs at all: nothing to do
        assert conn.execute(text("select count(*) from statuses where key = 'resubmitted'")).scalar() == 0

        spec = importlib.util.spec_from_file_location(
            "mig318_for_resub", ROOT / "alembic" / "versions" / "318_dealer_kit_edition.py"
        )
        mig318 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig318)
        mig318._seed_graph(conn)
        module.seed_resubmitted_rungs(conn)
        module.seed_resubmitted_rungs(conn)
        assert conn.execute(text("select count(*) from statuses where key = 'resubmitted'")).scalar() == 1
        edges = conn.execute(
            text(
                "select count(*) from status_transitions t join statuses s "
                "on s.id in (t.from_status_id, t.to_status_id) where s.key = 'resubmitted'"
            )
        ).scalar()
        assert edges == 3
