"""PROMPT-DYNAMIC, owner goal of 1 Oct 2026: every hard-coded list becomes a variable whose
render is byte-identical to the owner's text. These pin the two FORMAT gaps found against the
owner's production file: given rows whose CONTENT matches the text, the renderer must give the
owner's exact layout (statuses: arrows aligned and wrapped at 89 columns with a 4-space
continuation; domain words: wrapped at 89 columns).
"""
from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.services import chatbot_prompt_vars as pv
from tests._pg_fixture import pg_session

SNAPSHOT = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "data" / "chatbot_semantic_parser.prod-20261001.txt"


@pytest.fixture(autouse=True)
def _fresh_cache():
    pv.clear_cache()
    yield
    pv.clear_cache()


def _owner(start: str, end: str) -> str:
    src = SNAPSHOT.read_text(encoding="utf-8")
    s = src.index(start)
    return src[s : src.index(end, s)].rstrip("\n")


def test_statuses_render_the_owner_layout_from_rows_that_match_his_content():
    owner = _owner('  - "outstanding" -> orders NOT', "  - null -> DEFAULT")
    with pg_session() as db:
        db.execute(text("DELETE FROM chatbot_status_words WHERE value NOT IN ('outstanding', 'delivered')"))
        db.execute(
            text("UPDATE chatbot_status_words SET trigger_words = :w WHERE value = 'outstanding'"),
            {"w": ["outstanding", "pending", "not delivered", "undelivered", "not yet delivered", "still pending",
                   "open orders", "belum hantar", "belum sampai", "tak hantar lagi"]},
        )
        db.execute(
            text("UPDATE chatbot_status_words SET trigger_words = :w WHERE value = 'delivered'"),
            {"w": ["delivered", "completed", "done", "sudah hantar", "sudah sampai"]},
        )
        db.flush()
        assert pv.render_value(db, "statuses") == owner


def test_domain_words_render_the_owner_layout_from_rows_that_match_his_content():
    owner = _owner("stock, incoming, ETA", " - in any language")
    words = [w.strip() for w in owner.replace("\n", " ").split(",")]
    with pg_session() as db:
        db.execute(text("UPDATE chatbot_domains SET switch_words = '{}'"))
        db.execute(text("UPDATE chatbot_status_words SET trigger_words = '{}'"))
        db.execute(
            text("UPDATE chatbot_domains SET switch_words = :w WHERE name = 'master_products'"), {"w": words}
        )
        db.flush()
        assert pv.render_value(db, "domain_words") == owner


def test_a_short_status_list_stays_on_one_line_and_long_ones_never_split_a_word():
    with pg_session() as db:
        db.execute(text("DELETE FROM chatbot_status_words WHERE value <> 'delivered'"))
        db.flush()
        out = pv.render_value(db, "statuses")
        assert "\n" not in out and out.startswith('  - "delivered" -> ')
        db.execute(
            text("UPDATE chatbot_status_words SET trigger_words = :w WHERE value = 'delivered'"),
            {"w": [f"word number {i}" for i in range(30)]},
        )
        db.flush()
        pv.clear_cache()
        lines = pv.render_value(db, "statuses").splitlines()
        assert len(lines) > 1
        assert all(len(line) <= 89 for line in lines)
        assert all(line.startswith("    ") for line in lines[1:])
        assert all('"word number' in line for line in lines[1:])
