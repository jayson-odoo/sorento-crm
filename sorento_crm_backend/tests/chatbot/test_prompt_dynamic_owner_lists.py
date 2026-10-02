"""PROMPT-DYNAMIC, owner answers of 2 Oct 2026 (PLAN-prompt-dynamic-30sep, "Owner answers"):

- answer 2 (D-B2): the domain words are a curated list in the DB (`chatbot_domain_words`),
  seeded with the owner's 19 words in his order, rendered in his exact layout;
- answer 4 (D-B4): the status lists keep his subsets through a row tag
  (`chatbot_status_words.prompt_lists`): `{{statuses}}` and `{{status_values}}` give
  `outstanding` and `delivered` only, and the new `{{status_field_values}}` gives line 778,
  `outstanding|delivered|sales_report`.

Every list below must reproduce the owner's production file byte for byte.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.services import ai_prompt_registry, chatbot_prompt_vars as pv
from tests._pg_fixture import pg_session

BACKEND = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = BACKEND / "alembic" / "data" / "chatbot_semantic_parser.prod-20261001.txt"


def _migration():
    path = BACKEND / "alembic" / "versions" / "pdyn_0004_prompt_lists.py"
    spec = importlib.util.spec_from_file_location("_t_pdyn_0004", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_cache():
    pv.clear_cache()
    yield
    pv.clear_cache()


def _owner(start: str, end: str) -> str:
    src = SNAPSHOT.read_text(encoding="utf-8")
    s = src.index(start)
    return src[s : src.index(end, s)].rstrip("\n")


def _seeded(db) -> None:
    _migration().apply(db.connection())
    db.flush()
    pv.clear_cache()


def test_domain_words_render_the_owner_curated_list_from_the_table():
    with pg_session() as db:
        _seeded(db)
        assert pv.render_value(db, "domain_words") == _owner("stock, incoming, ETA", " - in any language")


def test_statuses_render_only_the_rows_tagged_for_the_bullets():
    with pg_session() as db:
        _seeded(db)
        out = pv.render_value(db, "statuses")
        assert '"outstanding"' in out and '"delivered"' in out
        assert "so_outstanding" not in out and "sales_report" not in out


def test_status_values_and_status_field_values_are_the_owner_subsets():
    with pg_session() as db:
        _seeded(db)
        assert pv.render_value(db, "status_values") == "outstanding|delivered"
        assert pv.render_value(db, "status_field_values") == "outstanding|delivered|sales_report"
        assert pv.render_value(db, "order_status_values").startswith("outstanding|delivered|so_outstanding")


def test_with_the_seeds_the_owner_file_swaps_these_lists_and_still_renders_byte_identical():
    source = SNAPSHOT.read_text(encoding="utf-8")
    with pg_session() as db:
        _seeded(db)
        # The statuses bullets match only when the rows carry the owner's words (the
        # sandbox may hold a hand-test word on a sales row, which is untagged anyway).
        template, report = pv.identical_wording_layer(source, db)
        replaced = {(r["variable"], r["line"]) for r in report if r["action"] == "replaced"}
        assert {
            ("domain_words", 87),
            ("statuses", 643),
            ("status_values", 770),
            ("status_field_values", 778),
            ("order_status_values", 821),
            ("teams", 773),
            ("entity_kinds_detail", 1677),
        } <= replaced
        values = {
            n: pv.render_value(db, n) for n in ai_prompt_registry.extract_tokens(template) & set(pv.VARIABLE_NAMES)
        }
        assert ai_prompt_registry._substitute(template, values) == source


def test_the_migration_is_idempotent_and_never_overrides_an_owner_edit():
    mod = _migration()
    with pg_session() as db:
        mod.apply(db.connection())
        db.execute(text("UPDATE chatbot_status_words SET prompt_lists = '{statuses}' WHERE value = 'delivered'"))
        db.execute(text("UPDATE chatbot_domain_words SET sort_order = 999 WHERE word = 'GRN'"))
        count = db.execute(text("SELECT count(*) FROM chatbot_domain_words")).scalar()
        mod.apply(db.connection())
        assert db.execute(text("SELECT prompt_lists FROM chatbot_status_words WHERE value = 'delivered'")).scalar() == [
            "statuses"
        ]
        assert db.execute(text("SELECT sort_order FROM chatbot_domain_words WHERE word = 'GRN'")).scalar() == 999
        assert db.execute(text("SELECT count(*) FROM chatbot_domain_words")).scalar() == count


def test_the_seed_words_are_the_owner_words_in_his_order():
    owner = _owner("stock, incoming, ETA", " - in any language")
    assert list(_migration().DOMAIN_WORDS) == [w.strip() for w in owner.replace("\n", " ").split(",")]
