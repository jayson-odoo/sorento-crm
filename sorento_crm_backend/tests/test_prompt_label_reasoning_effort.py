"""AGENTIC-REASONING-VIS round 2: the Prompts screen can set a label's reasoning effort, red first.

Before: `ai_prompt_labels.reasoning_effort` was read at runtime but nothing wrote it, and a key whose
production label was never seeded (`chatbot_agent` on a database that predates the key) answered 404
"no published production version", so the owner could set neither the model nor the effort.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from app.services.ai_prompt_seed import seed_prompt_registry
from app.services.ai_prompt_service import AIPromptService
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        try:
            ai_prompt_registry.bust_cache()
            seed_prompt_registry(session.get_bind())
            yield session
        finally:
            ai_prompt_registry.bust_cache()


def _unseed(db: Session, name: str) -> None:
    db.query(AIPromptLabel).filter(AIPromptLabel.name == name).delete()
    db.query(AIPromptVersion).filter(AIPromptVersion.name == name).delete()
    db.flush()
    ai_prompt_registry.bust_cache()


def test_the_effort_is_saved_and_read_at_runtime(db):
    AIPromptService(db).set_agent_model("chatbot_agent", label="production", provider=None, model=None, reasoning_effort="low")
    assert ai_prompt_registry.agent_reasoning_effort(db, "chatbot_agent") == "low"


def test_the_effort_shows_in_the_agent_list(db):
    AIPromptService(db).set_agent_model("chatbot_agent", label="production", provider=None, model=None, reasoning_effort="medium")
    row = next(r for r in AIPromptService(db).list_keys() if r["name"] == "chatbot_agent")
    assert row["reasoning_effort"] == "medium"


def test_a_blank_effort_clears_it(db):
    svc = AIPromptService(db)
    svc.set_agent_model("chatbot_agent", label="production", provider=None, model=None, reasoning_effort="low")
    svc.set_agent_model("chatbot_agent", label="production", provider=None, model=None, reasoning_effort="")
    assert ai_prompt_registry.agent_reasoning_effort(db, "chatbot_agent") is None


def test_saving_the_model_alone_keeps_the_effort(db):
    svc = AIPromptService(db)
    svc.set_agent_model("chatbot_agent", label="production", provider=None, model=None, reasoning_effort="low")
    svc.set_agent_model("chatbot_agent", label="production", provider="gemini", model="gemini-3.5-flash")
    assert ai_prompt_registry.agent_reasoning_effort(db, "chatbot_agent") == "low"


def test_an_unknown_effort_is_refused(db):
    with pytest.raises(AppException) as err:
        AIPromptService(db).set_agent_model(
            "chatbot_agent", label="production", provider=None, model=None, reasoning_effort="turbo"
        )
    assert err.value.status_code == 422


def test_a_key_with_no_production_label_gets_one_from_its_built_in_text(db):
    _unseed(db, "chatbot_agent")
    before = ai_prompt_registry.get_prompt(db, "chatbot_agent").text

    AIPromptService(db).set_agent_model("chatbot_agent", label="production", provider=None, model=None, reasoning_effort="low")

    ai_prompt_registry.bust_cache()
    assert ai_prompt_registry.agent_reasoning_effort(db, "chatbot_agent") == "low"
    # The agent reads the same prompt text as before: the built-in text, now as a published version.
    after = ai_prompt_registry.get_prompt(db, "chatbot_agent")
    assert after.text == before and after.version is not None


def test_a_staging_label_that_does_not_exist_is_still_refused(db):
    _unseed(db, "chatbot_agent")
    with pytest.raises(AppException) as err:
        AIPromptService(db).set_agent_model("chatbot_agent", label="staging", provider=None, model=None, reasoning_effort="low")
    assert err.value.status_code == 404


@pytest.fixture
def api(db: Session, monkeypatch):
    from fastapi.testclient import TestClient

    import app.dependencies as deps
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[deps.get_db] = _override_db
    app.dependency_overrides[deps.get_current_user] = lambda: {"id": "u-admin"}
    app.dependency_overrides[deps.get_current_user_or_api_key] = lambda: {"id": "u-admin"}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)
    try:
        yield TestClient(app), allow
    finally:
        for dep in (deps.get_db, deps.get_current_user, deps.get_current_user_or_api_key):
            app.dependency_overrides.pop(dep, None)


MODEL_URL = "/api/v1/system/ai-assistant/prompts/chatbot_agent/model"


def test_route_sets_the_effort_and_the_list_returns_it(api):
    client, allow = api
    allow.update({"system.ai_assistant_settings.edit", "system.ai_assistant_settings.view"})
    res = client.post(MODEL_URL, json={"label": "production", "provider": None, "model": None, "reasoning_effort": "low"})
    assert res.status_code == 200, res.text
    assert res.json()["reasoning_effort"] == "low"
    row = next(r for r in client.get("/api/v1/system/ai-assistant/prompts").json() if r["name"] == "chatbot_agent")
    assert row["reasoning_effort"] == "low"


def test_route_without_the_effort_key_keeps_it(api):
    client, allow = api
    allow.add("system.ai_assistant_settings.edit")
    client.post(MODEL_URL, json={"reasoning_effort": "low"})
    res = client.post(MODEL_URL, json={"provider": "gemini", "model": "gemini-3.5-flash"})
    assert res.status_code == 200, res.text
    assert res.json()["reasoning_effort"] == "low"


def test_route_refuses_without_the_edit_permission(api):
    client, allow = api
    allow.add("system.ai_assistant_settings.view")
    assert client.post(MODEL_URL, json={"reasoning_effort": "low"}).status_code == 403
