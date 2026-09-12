"""AC-1030: `GET /api/v1/system/chatbot/turns?ingress=shadow` - filter + summary.

With the Shadow filter on, the list returns only `ingress = "shadow"` rows and the
response carries a `summary`: `{count, branch_parity, asks_parity}` computed over the
filtered rows. `response_model` silently drops an undeclared field (LESSONS-LEARNT), so
this asserts the key survives serialization, not just that the route computes it.

RED: `list_turns` (`app/api/v1/system/chatbot.py`) has no `ingress` query parameter and
`ChatbotTurnListResponse` declares no `summary` field, so an unfiltered call returns every
row and the key is simply absent.

Reuses the auth/db harness from `tests/chatbot/test_turns_admin_api.py` (`client`, `db`,
the autouse `_permissions`), the same way `test_complete_turn.py` reuses
`test_chat_turn_endpoint.py`'s fixtures.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.chatbot_turn import ChatbotTurn
from tests.chatbot.test_turns_admin_api import (  # noqa: F401 - fixtures reused by name
    VIEW,
    _GRANTS,
    _permissions,
    client,
    db,
)

BASE = "/api/v1/system/chatbot/turns"


def _contact(label: str = "") -> str:
    return f"ZZT-shadowlist-{label}-{uuid.uuid4().hex[:8]}"


def _seed(
    db,
    *,
    contact_respond_id: str,
    ingress: str = "webhook",
    shadow_of: str | None = None,
    message_id: str | None = None,
    status: str = "done",
) -> ChatbotTurn:
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_respond_id,
        message_id=message_id or f"ZZT-msg-{uuid.uuid4().hex[:6]}",
        ingress=ingress,
        shadow_of=shadow_of,
        envelope={"message": {"messageId": message_id}, "contact": {"id": contact_respond_id}},
        status=status,
        stage="remembered",
        branch_kind="business_query",
        error=None,
        attempt=1,
        trace=[],
        response=None if ingress == "shadow" else {"reply": {"text": "ok"}},
    )
    turn.created_at = datetime.now(timezone.utc)
    db.add(turn)
    db.commit()
    return turn


class TestShadowFilterAndSummary:
    def test_ingress_shadow_returns_only_shadow_rows_with_a_summary(self, client, db):
        contact = _contact("a")
        live = _seed(db, contact_respond_id=contact, ingress="webhook", message_id="ZZT-live-1")
        # The shadow row names the live message via `shadow_of`, not by SHARING its
        # `message_id` - the unique index is `(contact_respond_id, message_id, attempt,
        # is_test)` with no `ingress` column in it, so an identical message_id collides.
        _seed(
            db,
            contact_respond_id=contact,
            ingress="shadow",
            shadow_of=live.message_id,
            message_id="ZZT-live-1-shadow",
        )

        resp = client.get(BASE, params={"ingress": "shadow", "contact_respond_id": contact})
        assert resp.status_code == 200, resp.text
        body = resp.json()

        ingresses = {row["ingress"] for row in body["items"]}
        assert ingresses == {"shadow"}, (
            f"expected only shadow rows, got ingresses={ingresses} "
            f"(items={[r.get('ingress') for r in body['items']]})"
        )

        assert "summary" in body, (
            f"the ingress=shadow response has no 'summary' key (keys={sorted(body)})"
        )
        assert set(body["summary"]) >= {"count", "branch_parity", "asks_parity"}
