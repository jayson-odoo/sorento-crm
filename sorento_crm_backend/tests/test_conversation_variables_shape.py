"""AC-1034: `GET`/`PUT /api/v1/external/conversation-variables/{id}` carry the five-key
shape; no compatibility shim, no legacy key accepted.

Today `ConversationStateOverwriteRequest` is `RootModel[dict[str, Any]]` - fully
arbitrary JSON, no `SessionVars` validation at all - so a legacy key such as
`picker_domain` is accepted and stored wholesale.

Reuses the `client` / `db` harness from `tests/test_chat_history_result_set.py`
(external API-key auth via `external_permissions_granted()`, blank Postgres schema).
"""
from __future__ import annotations

import uuid

from app.models.access import RespondContact
from tests.test_chat_history_result_set import client, db  # noqa: F401 - fixtures reused

RESPOND_IO_ID = "ZZT-convo-437264999"

FIVE_KEYS = {"focus", "open_question", "ideation", "access_levels", "contains_flyer"}


def _seed_contact(db) -> None:
    db.add(
        RespondContact(
            id=str(uuid.uuid4()),
            respond_io_id=RESPOND_IO_ID,
            phone_number="+60100000999",
            session_vars={
                "focus": None,
                "open_question": None,
                "ideation": None,
                "access_levels": [],
                "contains_flyer": False,
            },
        )
    )
    db.commit()


class TestConversationVariablesFiveKeyShape:
    def test_get_returns_only_the_five_keys(self, client, db):
        _seed_contact(db)
        resp = client.get(f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}")
        assert resp.status_code == 200, resp.text
        body = resp.json()["session_vars"]
        assert set(body.keys()) == FIVE_KEYS, sorted(body.keys())

    def test_put_rejects_a_legacy_key(self, client, db):
        _seed_contact(db)
        resp = client.put(
            f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
            json={"picker_domain": "master_products"},
        )
        assert resp.status_code == 422, (
            f"expected 422 for a legacy key, got {resp.status_code}: {resp.text}"
        )

    def test_put_accepts_the_five_key_shape(self, client, db):
        _seed_contact(db)
        resp = client.put(
            f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
            json={
                "focus": None,
                "open_question": None,
                "ideation": None,
                "access_levels": [],
                "contains_flyer": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert set(resp.json()["session_vars"].keys()) == FIVE_KEYS
