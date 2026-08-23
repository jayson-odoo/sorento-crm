"""The two model routes, including who is allowed to call them.

The permission pair is the point of the file. Both routes are reached from the
chatbot media settings page as well as the AI assistant page, so gating them on
`system.ai_assistant_settings.*` alone would 403 the operator who holds
`user_management.settings.*` - exactly the person sent to fix a degraded model
that a provider has retired.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.llm_provider import ProviderModel
from app.services.provider_model_catalog import CatalogResult


@pytest.fixture
def make_client(monkeypatch):
    """A client whose caller holds exactly the permission slugs given."""
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.user_service import UserPermissionService

    def _build(slugs: set[str]):
        monkeypatch.setattr(
            UserPermissionService, "get_user_role_slugs", lambda self, uid: set()
        )
        monkeypatch.setattr(
            UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(slugs)
        )
        app.dependency_overrides[get_db] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
        # The system router carries the base module guard, which resolves the
        # caller through its own dependency: without this the request is a 401
        # before either route body runs.
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": "u1"}
        return TestClient(app)

    try:
        yield _build
    finally:
        app.dependency_overrides.clear()


def _stub_list(monkeypatch, result: CatalogResult):
    monkeypatch.setattr(
        "app.api.v1.system.ai_assistant.list_provider_models",
        lambda db, provider: result,
    )


def test_the_list_route_carries_the_models_and_where_they_came_from(make_client, monkeypatch):
    _stub_list(
        monkeypatch,
        CatalogResult(
            provider="gemini",
            models=[ProviderModel("gemini-3.5-flash", "Gemini 3.5 Flash")],
            source="live",
        ),
    )
    client = make_client({"system.ai_assistant_settings.view"})

    response = client.get("/api/v1/system/ai-assistant/models", params={"provider": "gemini"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "live"
    assert body["models"] == [{"value": "gemini-3.5-flash", "label": "Gemini 3.5 Flash"}]


def test_a_fallback_list_reaches_the_screen_with_its_reason(make_client, monkeypatch):
    _stub_list(
        monkeypatch,
        CatalogResult(
            provider="gemini",
            models=[ProviderModel("gemini-2.5-flash", "Gemini 2.5 Flash")],
            source="fallback",
            message="Could not reach gemini: timeout",
        ),
    )
    client = make_client({"user_management.settings.view"})

    response = client.get("/api/v1/system/ai-assistant/models", params={"provider": "gemini"})

    assert response.status_code == 200
    assert response.json()["source"] == "fallback"
    assert "timeout" in response.json()["message"]


def test_the_settings_permission_is_enough_for_both_routes(make_client, monkeypatch):
    """The media settings page holds this pair and no assistant permission."""
    monkeypatch.setattr(
        "app.api.v1.system.ai_assistant.probe_model",
        lambda db, provider, model, with_image=False: (True, "OK", 12),
    )
    client = make_client({"user_management.settings.edit"})

    response = client.post(
        "/api/v1/system/ai-assistant/test-model",
        json={"provider": "gemini", "model": "gemini-3.5-flash-lite"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "OK", "latency_ms": 12}


def test_a_failing_probe_is_a_200_carrying_the_providers_refusal(make_client, monkeypatch):
    """Not a 4xx: the probe SUCCEEDED at telling us the model does not work, and
    the operator needs the provider's sentence rather than an error envelope."""
    monkeypatch.setattr(
        "app.api.v1.system.ai_assistant.probe_model",
        lambda db, provider, model, with_image=False: (
            False,
            "Gemini call failed (404): This model models/gemini-2.5-flash-lite is no "
            "longer available to new users.",
            340,
        ),
    )
    client = make_client({"system.ai_assistant_settings.edit"})

    response = client.post(
        "/api/v1/system/ai-assistant/test-model",
        json={"provider": "gemini", "model": "gemini-2.5-flash-lite"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "no longer available to new users" in response.json()["message"]


def test_a_caller_with_neither_permission_is_refused(make_client):
    client = make_client({"order_management.orders.view"})

    listing = client.get("/api/v1/system/ai-assistant/models", params={"provider": "gemini"})
    probe = client.post(
        "/api/v1/system/ai-assistant/test-model",
        json={"provider": "gemini", "model": "gemini-2.5-flash"},
    )

    assert listing.status_code == 403
    assert probe.status_code == 403


def test_a_view_only_caller_cannot_spend_money_on_a_probe(make_client):
    client = make_client({"system.ai_assistant_settings.view"})

    response = client.post(
        "/api/v1/system/ai-assistant/test-model",
        json={"provider": "gemini", "model": "gemini-2.5-flash"},
    )

    assert response.status_code == 403


def test_the_image_flag_reaches_the_probe(make_client, monkeypatch):
    """The media page's fields set it, and a dropped flag would certify a
    text-only model for the image lane - the plain probe cannot tell them apart."""
    seen: list[bool] = []
    monkeypatch.setattr(
        "app.api.v1.system.ai_assistant.probe_model",
        lambda db, provider, model, with_image=False: (
            seen.append(with_image) or (True, "OK", 5)
        ),
    )
    client = make_client({"user_management.settings.edit"})

    client.post(
        "/api/v1/system/ai-assistant/test-model",
        json={"provider": "openai", "model": "gpt-4o", "with_image": True},
    )
    client.post(
        "/api/v1/system/ai-assistant/test-model",
        json={"provider": "openai", "model": "gpt-4o"},
    )

    assert seen == [True, False]
