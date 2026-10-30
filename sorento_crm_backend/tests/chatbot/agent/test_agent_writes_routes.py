"""AGENTIC-P3 slice 1, test 17: the console's confirm and cancel endpoints.

Same auth harness as `test_agent_routes.py` (the console turn tests' `_permissions` and `client`):
both routes sit on the same `system.chat_history.view` slug as `/agent/turn`. `actions.confirm` and
`actions.cancel` are replaced where the route may have bound them, so these tests pin the route
shapes (200 body keys, 409 detail code and reason, 403, 422), not the action logic (that is
`test_agent_writes.py`). One test drives the real `actions.confirm` for an unknown action id.
"""
from __future__ import annotations

import uuid

import pytest

from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures + helpers
    VIEW,
    _GRANTS,
    _permissions,
    client,
)

BASE = "/api/v1/system/chatbot/agent/actions"
ACTION_ID = "33333333-3333-3333-3333-333333333333"
STEPS = [{"summary": "Mark SRT-1 for Acme done", "status": "done", "error": None}]
REASONS = ["not_found", "not_newest", "expired", "not_proposed", "entry_refused", "changed"]


def _url(verb: str, action_id: str = ACTION_ID) -> str:
    return f"{BASE}/{action_id}/{verb}"


@pytest.fixture()
def patch_actions(monkeypatch):
    """Replace `actions.confirm` / `actions.cancel` wherever the route may have bound them.
    Returns a recorder: `.calls` (verb, args, kwargs) and `.box` with the result or exception."""
    import app.api.v1.system.chatbot as route_mod
    from app.services.chatbot.agent import actions

    class Recorder:
        calls: list = []
        box: dict = {}

    rec = Recorder()
    rec.calls = []
    rec.box = {"exc": None}

    def make(verb):
        def fake(*args, **kwargs):
            rec.calls.append((verb, args, kwargs))
            if rec.box["exc"] is not None:
                raise rec.box["exc"]
            return actions.ActionOutcome(
                action_id=ACTION_ID,
                status="executed" if verb == "confirm" else "cancelled",
                reply_text="Done." if verb == "confirm" else "Cancelled.",
                steps=[dict(s) for s in STEPS],
            )

        return fake

    for verb in ("confirm", "cancel"):
        monkeypatch.setattr(actions, verb, make(verb))
        monkeypatch.setattr(route_mod, verb, make(verb), raising=False)
    return rec


def _passed(rec, verb):
    """Every value the route handed to the (fake) action function, positional and keyword."""
    (_, args, kwargs), = [c for c in rec.calls if c[0] == verb]
    return list(args), kwargs


def test_confirm_returns_the_outcome_fields_and_passes_the_console_context(client, patch_actions):
    resp = client.post(_url("confirm"), json={"contact_respond_id": "ZZT-C1"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"action_id", "status", "reply_text", "steps"}
    assert body["action_id"] == ACTION_ID
    assert body["status"] == "executed"
    assert body["reply_text"] == "Done."
    assert body["steps"] == STEPS
    args, kwargs = _passed(patch_actions, "confirm")
    assert "ZZT-C1" in args + list(kwargs.values())
    assert ACTION_ID in args + list(kwargs.values())
    assert kwargs.get("via") == "console"


def test_cancel_returns_the_outcome_fields(client, patch_actions):
    resp = client.post(_url("cancel"), json={"contact_respond_id": "ZZT-C1"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"action_id", "status", "reply_text", "steps"}
    assert body["status"] == "cancelled"
    assert body["action_id"] == ACTION_ID
    args, kwargs = _passed(patch_actions, "cancel")
    assert "ZZT-C1" in args + list(kwargs.values())
    assert ACTION_ID in args + list(kwargs.values())


@pytest.mark.parametrize("verb", ["confirm", "cancel"])
def test_without_the_console_permission_the_route_is_403_and_nothing_runs(client, patch_actions, verb):
    _GRANTS.discard(VIEW)

    resp = client.post(_url(verb), json={"contact_respond_id": "ZZT-C1"})

    assert resp.status_code == 403
    assert patch_actions.calls == []


@pytest.mark.parametrize("verb", ["confirm", "cancel"])
@pytest.mark.parametrize("reason", REASONS)
def test_a_refusal_is_a_409_action_refused_with_the_reason(client, patch_actions, verb, reason):
    from app.services.chatbot.agent.actions import ActionRefused

    patch_actions.box["exc"] = ActionRefused(reason)

    resp = client.post(_url(verb), json={"contact_respond_id": "ZZT-C1"})

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {"code": "action_refused", "reason": reason}


@pytest.mark.parametrize("verb", ["confirm", "cancel"])
@pytest.mark.parametrize(
    "body",
    [{}, {"contact_respond_id": ""}, {"contact_respond_id": 7}],
    ids=["missing", "empty", "not a string"],
)
def test_the_body_is_validated(client, patch_actions, verb, body):
    assert client.post(_url(verb), json=body).status_code == 422
    assert patch_actions.calls == []


@pytest.mark.parametrize("verb", ["confirm", "cancel"])
def test_an_unknown_action_for_a_real_agent_contact_is_a_409_not_found(client, session_factory, verb):
    """No patching: the real function answers an action id that does not exist."""
    from tests.chatbot.agent._seed import seed_agent_contact

    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()

    resp = client.post(_url(verb, str(uuid.uuid4())), json={"contact_respond_id": contact["respond_id"]})

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {"code": "action_refused", "reason": "not_found"}
