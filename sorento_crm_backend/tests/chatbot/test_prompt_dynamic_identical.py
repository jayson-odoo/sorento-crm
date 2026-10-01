"""Owner hand test #1405, item 3 (1 Oct 2026): a prompt version IDENTICAL in rendered
output to the current production text, using a registry variable wherever production
hard-codes that registry's list EXACTLY. Where a registry's current values differ from the
hard-coded text, the list stays literal and the difference is reported (never a silent
wording change). Saved unlabelled; never labelled, published or staged.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry, chatbot_prompt_vars as pv
from tests._pg_fixture import pg_session

KEY = "chatbot_semantic_parser"


@pytest.fixture(autouse=True)
def _fresh_cache():
    pv.clear_cache()
    ai_prompt_registry.bust_cache()
    yield
    pv.clear_cache()


def _render_template(db, template: str) -> str:
    values = {n: pv.render_value(db, n) for n in ai_prompt_registry.extract_tokens(template) & set(pv.VARIABLE_NAMES)}
    return ai_prompt_registry._substitute(template, values)


def test_an_exact_list_becomes_its_variable_and_a_differing_one_stays_literal_and_is_reported():
    with pg_session() as db:
        domains = pv.render_value(db, "domains")
        source = (
            f"domain_hint = ONE of: {domains} | null\n"
            '"suggested_team": "purchasing|customer_service"\n'  # not what the lane's list renders
            "Date {{current_date}}\n"
        )
        out, report = pv.identical_wording_layer(source, db)
        assert "domain_hint = ONE of: {{domains}} | null" in out
        assert '"suggested_team": "purchasing|customer_service"' in out
        assert "{{current_date}}" in out
        teams = [r for r in report if r["variable"] == "teams"]
        assert teams and teams[0]["action"] == "kept literal"
        assert "warehouse" in teams[0]["only_in_registry"]
        assert [r for r in report if r["variable"] == "domains"][0]["action"] == "replaced"


def test_the_rendered_output_is_identical_to_the_source_for_production():
    with pg_session() as db:
        prod = (
            db.query(AIPromptVersion)
            .join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
            .filter(AIPromptLabel.name == KEY, AIPromptLabel.label == "production")
            .one()
        )
        out, _report = pv.identical_wording_layer(prod.template, db)
        assert _render_template(db, out) == prod.template


def test_save_publishes_one_unlabelled_identical_version():
    import importlib

    script = importlib.import_module("scripts.prompt_dynamic_identical_version")
    with pg_session() as db:
        prod = (
            db.query(AIPromptVersion)
            .join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
            .filter(AIPromptLabel.name == KEY, AIPromptLabel.label == "production")
            .one()
        )
        labels_before = {(l.label, l.version_id) for l in db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY)}
        result = script.build(db, from_version=prod.version, save=True)
        assert result["identical"] is True
        row = db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY, AIPromptVersion.version == result["saved_version"]).one()
        assert _render_template(db, row.template) == prod.template
        assert db.query(AIPromptLabel).filter(AIPromptLabel.version_id == row.id).count() == 0
        assert {(l.label, l.version_id) for l in db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY)} == labels_before
