"""AC-1034 (updated): `GET`/`PUT /api/v1/external/conversation-variables/{id}` carry
`{variables: {focus, open_question, ideation, access_levels, contains_flyer}}` - the SAME
`{"variables": {...}}` wrapper the chatbot engine itself reads and writes on
`respond_contacts.session_vars` (`app.services.conversation_variables_service`,
`engine._read_session_vars`), not a flat five-key body. `extra="forbid"` is enforced
INSIDE `variables`, so a legacy key such as `picker_domain` there is rejected, and a body
that omits the `variables` wrapper entirely is rejected too - the wrapper is part of the
contract, not an implementation detail this endpoint is free to unwrap.

RED until the coder's group D lands: today `ConversationStateOverwriteRequest` is still
the FLAT five-key model (no `variables` wrapper) `app/schemas/external/
conversation_variables.py` declares. This file is the target shape, not today's.

Reuses the `client` / `db` harness from `tests/test_chat_history_result_set.py`
(external API-key auth via `external_permissions_granted()`, blank Postgres schema).
"""
from __future__ import annotations

import uuid

from app.models.access import RespondContact
from tests.test_chat_history_result_set import client, db  # noqa: F401 - fixtures reused

RESPOND_IO_ID = "ZZT-convo-437264999"

FIVE_KEYS = {"focus", "open_question", "ideation", "access_levels", "contains_flyer"}

FIVE_KEY_VARIABLES = {
    "focus": None,
    "open_question": None,
    "ideation": None,
    "access_levels": [],
    "contains_flyer": False,
}


def _seed_contact(db, *, variables: dict = FIVE_KEY_VARIABLES) -> None:
    db.add(
        RespondContact(
            id=str(uuid.uuid4()),
            respond_io_id=RESPOND_IO_ID,
            phone_number="+60100000999",
            session_vars={"variables": variables},
        )
    )
    db.commit()


class TestConversationVariablesFiveKeyShape:
    def test_get_returns_the_variables_wrapper_with_only_the_five_keys_inside(self, client, db):
        _seed_contact(db)
        resp = client.get(f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}")
        assert resp.status_code == 200, resp.text
        session_vars = resp.json()["session_vars"]
        assert set(session_vars.keys()) == {"variables"}, sorted(session_vars.keys())
        assert set(session_vars["variables"].keys()) == FIVE_KEYS, sorted(
            session_vars["variables"].keys()
        )

    def test_a_get_body_put_back_round_trips(self, client, db):
        """The exact body a GET returns is a valid PUT body, and PUTting it changes
        nothing about the stored shape - the round trip AC-1034 promises."""
        _seed_contact(
            db,
            variables={
                "focus": {"domains": {"value": ["order"], "set_at_turn": 1, "set_at": None, "source": "reuse"}},
                "open_question": None,
                "ideation": None,
                "access_levels": ["dealer"],
                "contains_flyer": False,
            },
        )
        got = client.get(f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}")
        assert got.status_code == 200, got.text
        session_vars = got.json()["session_vars"]

        put = client.put(
            f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
            json=session_vars,
        )
        assert put.status_code == 200, put.text
        assert put.json()["session_vars"] == session_vars

    def test_put_rejects_a_legacy_key_inside_variables(self, client, db):
        _seed_contact(db)
        resp = client.put(
            f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
            json={"variables": {**FIVE_KEY_VARIABLES, "picker_domain": "master_products"}},
        )
        assert resp.status_code == 422, (
            f"expected 422 for a legacy key inside `variables`, got {resp.status_code}: {resp.text}"
        )

    def test_put_rejects_a_flat_five_key_body_with_no_variables_wrapper(self, client, db):
        """The wrapper is the contract, not an unwrap this endpoint is free to do for a
        caller that forgot it - the flat shape used to be accepted and is not any more."""
        _seed_contact(db)
        resp = client.put(
            f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
            json=FIVE_KEY_VARIABLES,
        )
        assert resp.status_code == 422, (
            f"expected 422 for a body with no `variables` wrapper, got {resp.status_code}: "
            f"{resp.text}"
        )

    def test_put_accepts_the_wrapped_five_key_shape(self, client, db):
        _seed_contact(db)
        resp = client.put(
            f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
            json={"variables": FIVE_KEY_VARIABLES},
        )
        assert resp.status_code == 200, resp.text
        session_vars = resp.json()["session_vars"]
        assert set(session_vars.keys()) == {"variables"}
        assert set(session_vars["variables"].keys()) == FIVE_KEYS
