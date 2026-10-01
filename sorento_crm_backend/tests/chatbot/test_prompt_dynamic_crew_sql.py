"""The crew-migration SQL for PROMPT-DYNAMIC (crew copy, 1 Oct 2026).

The crew copy's dev DB is migrated by plain SQL, not alembic, so `pdyn_0003_prod_identical`
needs a SQL twin. These tests hold it to the migration's own contract: run on the same
tables, it inserts ONE unlabelled version whose render equals the owner's file byte for
byte, swaps a list only where the tables reproduce it, is idempotent, and is generated
(never hand-edited) from the file and the code.
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry, chatbot_prompt_vars as pv
from tests._pg_fixture import pg_session
from tests.chatbot.test_prompt_dynamic_prod_snapshot import _seed_registries_to_the_file

KEY = "chatbot_semantic_parser"
BACKEND = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = BACKEND / "alembic" / "data" / "chatbot_semantic_parser.prod-20261001.txt"
SQL_FILE = BACKEND.parent / "documentation" / "plans" / "chatbot" / "crew-migration-prompt-dynamic.sql"
SHA = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()


def _gen():
    path = BACKEND / "scripts" / "prompt_dynamic_crew_sql.py"
    spec = importlib.util.spec_from_file_location("_t_crew_sql", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_cache():
    pv.clear_cache()
    ai_prompt_registry.bust_cache()
    yield
    pv.clear_cache()
    ai_prompt_registry.bust_cache()


def _exec(db, sql: str) -> None:
    """Through the raw driver cursor with no parameters, the way psql sends a file: the
    owner's text carries `%` and `:word` that a bound-parameter path would rewrite."""
    with db.connection().connection.cursor() as cur:
        cur.execute(sql)


def _run_sql(db, sql: str | None = None) -> None:
    db.execute(
        text("DELETE FROM ai_prompt_versions WHERE name = :n AND config_json->>'prod_snapshot_sha256' = :s"),
        {"n": KEY, "s": SHA},
    )
    _exec(db, sql if sql is not None else SQL_FILE.read_text(encoding="utf-8"))
    db.expire_all()
    pv.clear_cache()


def _row(db) -> AIPromptVersion:
    return (
        db.query(AIPromptVersion)
        .filter(AIPromptVersion.name == KEY, AIPromptVersion.config_json["prod_snapshot_sha256"].astext == SHA)
        .one()
    )


def _render(db, row) -> str:
    out, _ = ai_prompt_registry.render(db, KEY, current_date="TODAY", override_version_id=row.id)
    return out


def _expected() -> str:
    return SNAPSHOT.read_text(encoding="utf-8").replace("{{current_date}}", "TODAY")


def _sql_actions(row) -> list[tuple[str, str]]:
    return [(r["variable"], r["action"]) for r in row.config_json["identical_report"]]


def test_the_committed_sql_is_generated_from_the_file_and_the_code():
    assert SQL_FILE.read_text(encoding="utf-8") == _gen().build_sql()


def test_the_sql_carries_no_dash_characters():
    raw = SQL_FILE.read_text(encoding="utf-8")
    assert "—" not in raw and "–" not in raw


def test_on_tables_shaped_like_the_file_the_sql_swaps_and_renders_the_file():
    """The pdyn_0003 section alone: the full file re-seeds the 8 status rows first
    (pdyn_0001), which is exactly why `status_values` stays literal on the crew copy."""
    with pg_session() as db:
        _seed_registries_to_the_file(db)
        top = db.execute(
            text("SELECT max(version) FROM ai_prompt_versions WHERE name = :n AND config_json->>'prod_snapshot_sha256' IS DISTINCT FROM :s"),
            {"n": KEY, "s": SHA},
        ).scalar()
        _run_sql(db, _gen().pdyn_0003_sql())
        row = _row(db)
        assert row.version == int(top) + 1
        replaced = {v for v, a in _sql_actions(row) if a == "replaced"}
        assert {"teams", "status_values", "agents", "access_levels", "entity_kinds_detail"} <= replaced
        for name in replaced:
            assert "{{" + name + "}}" in row.template
        assert _render(db, row) == _expected()


def test_the_sql_agrees_with_the_python_migration_wherever_it_decides():
    """Every list the SQL swaps, the Python transform swaps on the same tables; every list
    the SQL keeps, it keeps for a reason the report names (no SQL renderer, or a differing
    registry)."""
    with pg_session() as db:
        _seed_registries_to_the_file(db)
        _run_sql(db, _gen().pdyn_0003_sql())
        sql_report = _row(db).config_json["identical_report"]
        _template, py_report = pv.identical_wording_layer(SNAPSHOT.read_text(encoding="utf-8"), db)
        py = [(r["variable"], r["action"]) for r in py_report]
        for variable, action in [(r["variable"], r["action"]) for r in sql_report]:
            if action == "replaced":
                assert (variable, "replaced") in py, variable


def test_on_tables_that_differ_the_sql_keeps_the_list_and_still_renders_the_file():
    with pg_session() as db:
        _run_sql(db)
        row = _row(db)
        assert ("domains", "kept literal") in _sql_actions(row)
        assert "{{domains}}" not in row.template
        assert _render(db, row) == _expected()


def test_the_sql_is_idempotent_unlabelled_and_leaves_other_versions_alone():
    with pg_session() as db:
        db.execute(
            text("DELETE FROM ai_prompt_versions WHERE name = :n AND config_json->>'prod_snapshot_sha256' = :s"),
            {"n": KEY, "s": SHA},
        )
        before = {r.id: r.template for r in db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY)}
        labels = {(l.label, l.version_id) for l in db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY)}
        sql = SQL_FILE.read_text(encoding="utf-8")
        _exec(db, sql)
        _exec(db, sql)
        db.expire_all()
        after = {r.id: r.template for r in db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY)}
        assert len(after) == len(before) + 1
        assert {k: v for k, v in after.items() if k in before} == before
        assert {(l.label, l.version_id) for l in db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY)} == labels
        assert not db.query(AIPromptLabel).filter(AIPromptLabel.version_id == _row(db).id).count()


def test_the_python_migration_skips_once_the_sql_has_run():
    """Crew copies that later run alembic must not get a second copy."""
    path = BACKEND / "alembic" / "versions" / "pdyn_0003_prod_identical.py"
    spec = importlib.util.spec_from_file_location("_t_pdyn_0003_b", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pg_session() as db:
        _run_sql(db)
        assert mod.apply(db.connection()) is None
