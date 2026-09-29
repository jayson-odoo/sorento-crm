"""Chatbot stock ask v2, Slice S2 (contact toggles) - AC-SA201 to AC-SA204.

`documentation/plans/chatbot/PLAN-chatbot-stock-ask-v2-24sep.md` "S2 - Contact toggles",
`documentation/plans/chatbot/chatbot-stock-ask-v2-24sep-acceptance-criteria.md` AC-SA201
to AC-SA205 (AC-SA205 is the frontend vitest, `ContactChatbotSection.test.tsx`).

**RIGHT NOW every test here is RED**: migration `sa2_0002_contact_toggles` does not
exist, `respond_contacts` carries no `notify_salesman` / `packing_list_allowed`
columns, `ContactChatbotUpdate` does not accept either field, `contact_to_response_dict`
does not list either key, and `Profile` (`app/services/chatbot/turn/state.py`) has no
`notify_salesman` / `packing_list_allowed` attribute at all.

Modelled directly on `tests/chatbot/test_rearch_s6_stock_allowed.py`, the closest sibling
(same migration shape - one new boolean column on `respond_contacts` - same route, same
dict builder, same `_PROFILE_COLUMNS` / `load_profile` pair), except R7 defaults BOTH new
columns OFF (`chatbot_stock_allowed` defaults true; these two do not).

Column-level tests run on the blank scratch schema (`Base.metadata.create_all` picks up a
new `RespondContact` column for free once the coder adds it to the model - no real Alembic
migration needed for THESE tests to go green). `load_profile` tests use the
`tests.chatbot.conftest.session_factory` fixture directly, the same one
`test_rearch_s6_stock_allowed.py`'s engine tests use.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.services.user_service import UserPermissionService

from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - reuses the blank-schema fixture

BASE = "/api/v1/user-management/contacts"
CONTACT_VIEW = "user_management.contacts.view"
CONTACT_EDIT = "user_management.contacts.edit"

_GRANTS: set[str] = {CONTACT_VIEW, CONTACT_EDIT}
_ACTOR: dict = {"id": None, "name": "ZZT Contact Toggles Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(CONTACT_VIEW)
    _GRANTS.add(CONTACT_EDIT)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(db):  # noqa: F811 - fixture shadow is the point
    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _seed_contact(db, *, respond_io_id: str | None = None) -> str:
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {
            "cid": respond_io_id or f"ZZT-{uuid.uuid4().hex[:8]}",
            "phone": f"+6001{uuid.uuid4().hex[:7]}",
            "sv": json.dumps({}),
        },
    )
    db.commit()
    return db.execute(text("SELECT id FROM respond_contacts ORDER BY created_at DESC LIMIT 1")).scalar()


# --------------------------------------------------------------------------------- #
# Column-level: both default false (blank schema / create_all) - AC-SA202
# --------------------------------------------------------------------------------- #


def test_new_row_inserted_without_the_columns_reads_both_false(db):
    """R7: both toggles default OFF, unlike `chatbot_stock_allowed` (default true)."""
    contact_id = _seed_contact(db)
    row = db.execute(
        text("SELECT notify_salesman, packing_list_allowed FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).first()
    assert row[0] is False, row
    assert row[1] is False, row


# --------------------------------------------------------------------------------- #
# Route surface: PUT .../contacts/{id}/chatbot, GET contact - AC-SA201, AC-SA202
# --------------------------------------------------------------------------------- #


def test_put_chatbot_notify_salesman_persists_leaves_packing_list_untouched(db, client):
    contact_id = _seed_contact(db)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["notify_salesman"] is True, body
    assert body["packing_list_allowed"] is False, body

    stored = db.execute(
        text("SELECT notify_salesman, packing_list_allowed FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).first()
    assert stored[0] is True, stored
    assert stored[1] is False, stored


def test_put_chatbot_packing_list_allowed_leaves_previously_set_notify_salesman_alone(db, client):
    """Absent = leave alone, both directions: a PUT mentioning only
    `packing_list_allowed` must not reset `notify_salesman` back to its default."""
    contact_id = _seed_contact(db)
    resp1 = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp1.status_code == 200, resp1.text

    resp2 = client.put(f"{BASE}/{contact_id}/chatbot", json={"packing_list_allowed": True})
    assert resp2.status_code == 200, resp2.text
    body = resp2.json()
    assert body["notify_salesman"] is True, body
    assert body["packing_list_allowed"] is True, body


def test_get_contact_detail_returns_both_toggle_keys(db, client):
    """Through `ContactService.contact_to_response_dict` - the ONE manual dict builder
    for a contact response, also used by the list endpoint."""
    contact_id = _seed_contact(db)
    resp = client.get(f"{BASE}/{contact_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "notify_salesman" in body, body
    assert "packing_list_allowed" in body, body
    assert body["notify_salesman"] is False, body
    assert body["packing_list_allowed"] is False, body


def test_put_chatbot_toggle_without_edit_grant_is_403(db, client):
    contact_id = _seed_contact(db)
    _GRANTS.discard(CONTACT_EDIT)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------------- #
# `load_profile`: workspace row, NULL-workspace fallback, unknown contact - AC-SA204
# --------------------------------------------------------------------------------- #


def _set_toggles(
    session_factory, *, contact_respond_id: str, notify_salesman: bool, packing_list_allowed: bool
) -> None:
    db = session_factory()
    db.execute(
        text(
            "UPDATE respond_contacts SET notify_salesman = :n, packing_list_allowed = :p "
            "WHERE respond_io_id = :c"
        ),
        {"n": notify_salesman, "p": packing_list_allowed, "c": contact_respond_id},
    )
    db.commit()


def _seed_workspace_scoped_contact(session_factory, *, space_id: str) -> tuple[str, str]:
    """Returns (contact_respond_id, workspace_id) for a contact whose row is scoped to
    a real `respond_workspaces` row - the shape `_profile_rows`'s scoped branch reads."""
    db = session_factory()
    workspace_id = str(uuid.uuid4())
    contact_respond_id = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, api_key_ciphertext) "
            "VALUES (:id, :space_id, 'x')"
        ),
        {"id": workspace_id, "space_id": space_id},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, workspace_id, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, :wid, CAST(:sv AS jsonb))"
        ),
        {
            "cid": contact_respond_id,
            "phone": f"+6002{uuid.uuid4().hex[:7]}",
            "wid": workspace_id,
            "sv": json.dumps({}),
        },
    )
    db.commit()
    return contact_respond_id, workspace_id


def _seed_null_workspace_contact(session_factory) -> str:
    db = session_factory()
    contact_respond_id = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_respond_id, "phone": f"+6003{uuid.uuid4().hex[:7]}", "sv": json.dumps({})},
    )
    db.commit()
    return contact_respond_id


def test_load_profile_returns_toggles_for_a_workspace_scoped_row(session_factory):
    from app.services.chatbot import turn_runtime

    space_id = f"ZZT-SPACE-{uuid.uuid4().hex[:6]}"
    contact_respond_id, _workspace_id = _seed_workspace_scoped_contact(session_factory, space_id=space_id)
    _set_toggles(
        session_factory,
        contact_respond_id=contact_respond_id,
        notify_salesman=True,
        packing_list_allowed=True,
    )

    db = session_factory()
    profile, _recall = turn_runtime.load_profile(db, contact_respond_id, space_id=space_id)
    assert profile.notify_salesman is True, profile
    assert profile.packing_list_allowed is True, profile


def test_load_profile_null_workspace_fallback_returns_persisted_values(session_factory):
    """A contact seeded with `workspace_id IS NULL`, looked up with a `space_id` that
    matches no scoped row, must fall through `_profile_rows`'s NULL-workspace branch and
    still return the persisted values, not the dataclass defaults."""
    from app.services.chatbot import turn_runtime

    contact_respond_id = _seed_null_workspace_contact(session_factory)
    _set_toggles(
        session_factory,
        contact_respond_id=contact_respond_id,
        notify_salesman=True,
        packing_list_allowed=False,
    )

    db = session_factory()
    profile, _recall = turn_runtime.load_profile(
        db, contact_respond_id, space_id=f"ZZT-NO-MATCHING-SPACE-{uuid.uuid4().hex[:6]}"
    )
    assert profile.notify_salesman is True, profile
    assert profile.packing_list_allowed is False, profile


def test_load_profile_unknown_contact_returns_false_for_both(session_factory):
    """Unknown contact -> false for both (no `respond_contacts` row to have switched
    either toggle on)."""
    from app.services.chatbot import turn_runtime

    db = session_factory()
    profile, _recall = turn_runtime.load_profile(
        db, f"ZZT-unknown-{uuid.uuid4().hex[:8]}", space_id=f"ZZT-SPACE-{uuid.uuid4().hex[:6]}"
    )
    assert profile.notify_salesman is False, profile
    assert profile.packing_list_allowed is False, profile
