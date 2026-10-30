"""AGENTIC-REASONING-VIS round 2 (owner, 31 Oct 00:35: "low effort for agent"), red first.

The agent runs at reasoning effort `low` when its `chatbot_agent` label sets none, so the model thinks and the
console has Thinking to show; an effort set on the label still wins. Providers are stubs; no live LLM call.
"""
from __future__ import annotations

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from tests.chatbot.agent.test_agent_loop import (  # noqa: F401 - helpers and fixtures, not tests
    ScriptedProvider,
    answer,
    contact,
    db,
    run,
)


def _label(db, effort):
    version = AIPromptVersion(
        name="chatbot_agent", version=1, template=ai_prompt_registry.PROMPT_KEYS["chatbot_agent"].fallback()
    )
    db.add(version)
    db.flush()
    db.add(AIPromptLabel(name="chatbot_agent", label="production", version_id=version.id, reasoning_effort=effort))
    db.flush()
    ai_prompt_registry.bust_cache()


def test_the_agent_thinks_at_low_effort_when_no_label_exists(db, contact):
    provider = ScriptedProvider([answer("Hello.")])
    run(db, contact, provider)
    assert [s["effort"] for s in provider.seen] == ["low"]


def test_the_agent_thinks_at_low_effort_when_its_label_sets_none(db, contact):
    _label(db, None)
    provider = ScriptedProvider([answer("Hello.")])
    run(db, contact, provider)
    assert [s["effort"] for s in provider.seen] == ["low"]


@pytest.mark.parametrize("effort", ["medium", "none"])
def test_an_effort_on_the_label_still_wins(db, contact, effort):
    _label(db, effort)
    provider = ScriptedProvider([answer("Hello.")])
    run(db, contact, provider)
    assert [s["effort"] for s in provider.seen] == [effort]


def test_the_production_provider_resolves_low_effort_by_default(db, monkeypatch):
    from app.services import llm_provider
    from app.services.chatbot.agent import loop

    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda cfg, name: "k")
    _client, name, model, effort = loop._resolve_provider(db)
    assert (name, model, effort) == (loop.DEFAULT_PROVIDER, loop.DEFAULT_MODEL, "low")
