"""WU22: `POST /api/v1/external/chat/turn` refuses the CRM's own signed-webhook ingress marker.

Fixtures are the real-app ones from `test_chat_turn_endpoint.py`. No turn may run.
"""
from __future__ import annotations

import pytest

from tests.chatbot.test_chat_turn_endpoint import _TURN_URL, api_key, client, stub_engine_seams  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID

pytestmark = pytest.mark.usefixtures("_no_real_mcp_calls", "_stub_casual_llm")


def test_wu22_respond_webhook_ingress_is_refused_with_422_and_runs_no_turn(
    client, api_key, stub_engine_seams, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(
        "app.api.v1.external.chat.run_turn", lambda *a, **k: pytest.fail("a turn ran for a forged ingress")
    )
    resp = client.post(
        _TURN_URL,
        json={"envelope": {"message": {}, "contact": {"id": CONTACT_ID}, "ingress": "respond_webhook"}},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 422, resp.text


def test_wu22_an_ordinary_ingress_is_not_refused_on_that_ground(
    client, api_key, stub_engine_seams, monkeypatch  # noqa: F811
):
    class _R:
        status = "done"
        error = None

        def as_dict(self):
            return {"turn_id": "11111111-1111-1111-1111-111111111111", "branch_kind": "business_query", "actions": []}

    monkeypatch.setattr("app.api.v1.external.chat.run_turn", lambda *a, **k: _R())
    resp = client.post(
        _TURN_URL,
        json={"envelope": {"message": {}, "contact": {"id": CONTACT_ID}, "ingress": "webhook"}},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code != 422, resp.text
