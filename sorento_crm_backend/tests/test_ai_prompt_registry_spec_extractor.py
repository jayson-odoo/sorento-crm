"""`spec_extractor` - its own `PROMPT_KEYS` entry, and the `dry_runnable` gate on the
assistant dry-run route (AC-B.6).

PR 4 contract: `documentation/plans/master-data/PLAN-spec-authoring-verification.md`
("PR 4 implementation contract"). Neither `PROMPT_KEYS["spec_extractor"]` nor
`PromptKeySpec.dry_runnable` exist yet, so most tests below fail immediately with a
`KeyError` or `AttributeError` - that IS the expected red state.

Fixture pattern copied from tests/test_ai_prompt_registry.py (`db`/`seeded`/`api`
fixtures, dependency-override + `UserPermissionService.check_user_has_permission`
monkeypatch).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.services import ai_prompt_registry
from app.services.ai_prompt_registry import PROMPT_KEYS, get_prompt, validate_template
from app.services.ai_prompt_seed import seed_prompt_registry
from app.services.ai_prompt_service import AIPromptService
from tests._pg_fixture import blank_session

_USER = {"id": str(uuid.uuid4())}


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        try:
            yield session
        finally:
            ai_prompt_registry.bust_cache()


@pytest.fixture
def seeded(db: Session) -> Session:
    ai_prompt_registry.bust_cache()
    seed_prompt_registry(db.get_bind())
    return db


@pytest.fixture
def api(seeded: Session, monkeypatch):
    from fastapi.testclient import TestClient

    import app.dependencies as deps
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield seeded

    app.dependency_overrides[deps.get_db] = _override_db
    app.dependency_overrides[deps.get_current_user] = lambda: {"id": "u-admin"}
    app.dependency_overrides[deps.get_current_user_or_api_key] = lambda: {"id": "u-admin"}
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        app.dependency_overrides.pop(deps.get_current_user, None)
        app.dependency_overrides.pop(deps.get_current_user_or_api_key, None)


# --------------------------------------------------------------------------- #
# the key itself
# --------------------------------------------------------------------------- #
def test_spec_extractor_is_registered_active_with_no_declared_variables():
    spec = PROMPT_KEYS["spec_extractor"]

    assert spec.active is True
    assert spec.variables == []
    fallback_text = spec.fallback()
    assert isinstance(fallback_text, str)
    assert fallback_text.strip(), "a mandatory hardcoded fallback must not be empty"


def test_validate_template_rejects_any_token_for_spec_extractor():
    """Zero declared variables means any `{{token}}` an editor types is unknown."""
    assert "spec_extractor" in PROMPT_KEYS, "must be registered before it declares zero variables"

    unknown, missing = validate_template("spec_extractor", "hello {{anything}}")

    assert unknown == ["anything"]
    assert missing == []


def test_get_prompt_falls_back_to_hardcoded_text_on_a_blank_db(db):
    rendered = get_prompt(db, "spec_extractor")

    assert rendered.version is None
    assert rendered.text.strip(), "fallback text must not be empty on an unseeded db"


# --------------------------------------------------------------------------- #
# dry_runnable
# --------------------------------------------------------------------------- #
def test_dry_runnable_true_for_assistant_pipeline_keys():
    for name in ("agent_system", "synthesizer", "semantic_parser"):
        assert PROMPT_KEYS[name].dry_runnable is True, name


def test_dry_runnable_false_for_non_assistant_keys():
    for name in ("spec_understanding", "spec_extractor", "scm_market_advisory", "ideate_extractor"):
        assert PROMPT_KEYS[name].dry_runnable is False, name


def test_list_keys_rows_carry_dry_runnable(db):
    rows = AIPromptService(db).list_keys()

    assert rows, "expected at least one registered prompt key"
    for row in rows:
        assert "dry_runnable" in row, row["name"]


def test_route_prompt_test_refuses_a_non_dry_runnable_key(api):
    """AC-B.6 / C10 - the assistant dry-run must not run a non-assistant key
    through the chat pipeline."""
    client, allow = api
    allow.add("system.ai_assistant_settings.edit")

    # A random id is enough: the dry_runnable gate must refuse before the route even
    # looks the version up.
    version_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/system/ai-assistant/prompts/spec_extractor/test",
        json={"message": "hello", "version_id": version_id},
    )

    assert response.status_code == 400, response.text
