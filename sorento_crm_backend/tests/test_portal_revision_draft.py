"""Revision drafts: save-and-resume for an in-progress revision.

A draft never touches the entity - it lives entirely in `portal_revision_drafts`
until Send revision, which applies the SAME payload through `revise` and deletes
the draft row in the same transaction. Covers save/get (upsert, frozen-field
parity, policy parity with `revise`), discard (idempotent), staleness, and
ownership.

Run: pytest tests/test_portal_revision_draft.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.portal import PortalRevisionDraft, PortalToken
from app.services.portal_revision_service import PortalRevisionService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    CONTACT_SPACE,
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
    seed_token,
)

BASE = "/api/v1/public/portal"


@pytest.fixture(autouse=True)
def no_queue():
    """Never enqueue a real RQ job from a test: a worker in another worktree would
    pick it up."""
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _draft_row(db, kind: str, entity_id: str) -> PortalRevisionDraft | None:
    return (
        db.query(PortalRevisionDraft)
        .filter(
            PortalRevisionDraft.source_entity_type == kind,
            PortalRevisionDraft.source_entity_id == str(entity_id),
        )
        .first()
    )


def _draft_rows(db, kind: str, entity_id: str) -> list[PortalRevisionDraft]:
    return (
        db.query(PortalRevisionDraft)
        .filter(
            PortalRevisionDraft.source_entity_type == kind,
            PortalRevisionDraft.source_entity_id == str(entity_id),
        )
        .all()
    )


def _setup(db, kind="stock_inquiry", **entity_kwargs):
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, **entity_kwargs)
    return contact, seed_token(contact), row


# --------------------------------------------------------------------- save/get


def test_save_draft_stores_the_payload_and_reason(db):
    _contact, token, row = _setup(db)
    service = PortalRevisionService(db)

    result = service.save_draft(
        token,
        "stock_inquiry",
        str(row.id),
        {"item_description": "Draft description", "quantity": "9"},
        "Thinking about the quantity",
        row.revision_no,
    )

    assert result["fields"] == {"item_description": "Draft description", "quantity": "9"}
    assert result["reason"] == "Thinking about the quantity"
    assert result["base_revision_no"] == row.revision_no
    assert result["stale"] is False

    fetched = service.get_draft("stock_inquiry", str(row.id))
    assert fetched["fields"] == {"item_description": "Draft description", "quantity": "9"}
    assert fetched["reason"] == "Thinking about the quantity"
    assert fetched["base_revision_no"] == row.revision_no
    assert fetched["stale"] is False


def test_get_draft_is_none_when_there_is_no_draft(db):
    _contact, _token, row = _setup(db)
    assert PortalRevisionService(db).get_draft("stock_inquiry", str(row.id)) is None


# --------------------------------------------------------------------- upsert


def test_save_draft_is_an_upsert_leaving_exactly_one_row(db):
    _contact, token, row = _setup(db)
    service = PortalRevisionService(db)

    service.save_draft(
        token, "stock_inquiry", str(row.id), {"quantity": "5"}, "First thought", row.revision_no
    )
    service.save_draft(
        token, "stock_inquiry", str(row.id), {"quantity": "9"}, "Changed my mind", row.revision_no
    )

    rows = _draft_rows(db, "stock_inquiry", str(row.id))
    assert len(rows) == 1
    assert rows[0].payload_json == {"quantity": "9"}
    assert rows[0].reason == "Changed my mind"


# ------------------------------------------------------------- frozen fields


def test_save_draft_strips_frozen_fields_same_as_revise(db):
    """UAC AB1/AB2 parity: the requestor FK is a routing key, and a draft cannot
    smuggle it in any more than a sent revision can."""
    _contact, token, row = _setup(db)
    other = seed_contact(db, name="Somebody Else")
    service = PortalRevisionService(db)

    service.save_draft(
        token,
        "stock_inquiry",
        str(row.id),
        {
            "quantity": "9",
            "salesperson": other.name,
            "salesperson_contact_id": other.id,
        },
        "Trying to reassign",
        row.revision_no,
    )

    stored = _draft_row(db, "stock_inquiry", str(row.id))
    assert "salesperson" not in stored.payload_json
    assert "salesperson_contact_id" not in stored.payload_json
    assert stored.payload_json["quantity"] == "9"


# ------------------------------------------------------------------ policy


def test_save_draft_refuses_with_the_same_error_revise_would(db):
    """UAC B4 parity: no config row means the type is disabled (fails closed) -
    a draft that could never be sent must not be storable either, and the two
    paths must say exactly the same thing to the contact."""
    seed_system_settings(db)
    contact = seed_contact(db)  # deliberately no seed_config(db, "stock_inquiry")
    row = seed_entity(db, "stock_inquiry", contact)
    service = PortalRevisionService(db)
    token = seed_token(contact)

    with pytest.raises(HTTPException) as save_exc:
        service.save_draft(
            token, "stock_inquiry", str(row.id), {"quantity": "9"}, "Reason", row.revision_no
        )
    assert save_exc.value.status_code == 422

    with pytest.raises(HTTPException) as revise_exc:
        service.revise(token, "stock_inquiry", str(row.id), {"quantity": "9"}, "Reason", 0)
    assert revise_exc.value.status_code == 422

    assert save_exc.value.detail["message"] == revise_exc.value.detail["message"]
    assert _draft_row(db, "stock_inquiry", str(row.id)) is None


# ------------------------------------------------------------------ discard


def test_discard_draft_removes_the_row_and_is_idempotent(db):
    _contact, token, row = _setup(db)
    service = PortalRevisionService(db)
    service.save_draft(
        token, "stock_inquiry", str(row.id), {"quantity": "9"}, "Reason", row.revision_no
    )
    assert _draft_row(db, "stock_inquiry", str(row.id)) is not None

    service.discard_draft("stock_inquiry", str(row.id))
    assert _draft_row(db, "stock_inquiry", str(row.id)) is None

    # Second call: no error, still gone.
    service.discard_draft("stock_inquiry", str(row.id))
    assert _draft_row(db, "stock_inquiry", str(row.id)) is None


# ------------------------------------------------------------------- revise


def test_revise_leaves_no_draft_row_behind(db):
    _contact, token, row = _setup(db)
    service = PortalRevisionService(db)
    service.save_draft(
        token, "stock_inquiry", str(row.id), {"quantity": "9"}, "Reason", row.revision_no
    )
    assert _draft_row(db, "stock_inquiry", str(row.id)) is not None

    service.revise(
        token,
        "stock_inquiry",
        str(row.id),
        {"item_description": "Revised description", "quantity": "9"},
        "Wrong quantity, corrected it",
        row.revision_no,
    )

    assert _draft_row(db, "stock_inquiry", str(row.id)) is None


# ------------------------------------------------------------------ staleness


def test_get_draft_reports_stale_after_the_entitys_revision_lands(db):
    _contact, token, row = _setup(db)
    service = PortalRevisionService(db)
    service.save_draft(
        token, "stock_inquiry", str(row.id), {"quantity": "9"}, "Reason", row.revision_no
    )
    assert service.get_draft("stock_inquiry", str(row.id))["stale"] is False

    # A revision landed elsewhere (e.g. another device) after the draft was saved.
    row.revision_no = row.revision_no + 1
    db.commit()

    assert service.get_draft("stock_inquiry", str(row.id))["stale"] is True


# ------------------------------------------------------------------ ownership


def _persisted_token(db, contact) -> str:
    row = PortalToken(
        id=str(uuid.uuid4()),
        token=f"tok-{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id=CONTACT_SPACE,
        expires_at=datetime.utcnow() + timedelta(days=30),
        verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(row)
    db.commit()
    return row.token


def test_another_contacts_token_cannot_save_a_draft(db):
    _contact, _token, row = _setup(db)
    intruder = seed_contact(db, name="Intruder")
    service = PortalRevisionService(db)

    with pytest.raises(HTTPException) as exc:
        service.save_draft(
            seed_token(intruder),
            "stock_inquiry",
            str(row.id),
            {"quantity": "9"},
            "Not my form",
            row.revision_no,
        )
    assert exc.value.status_code in (403, 404)
    assert _draft_row(db, "stock_inquiry", str(row.id)) is None


@pytest.fixture
def client():
    from app.database import get_db

    with blank_session() as db:

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("app.services.queue_service.enqueue_job", return_value=None):
                with TestClient(app) as c:
                    yield c, db
        finally:
            app.dependency_overrides.clear()


def _http_setup(client, kind="stock_inquiry", **entity_kwargs):
    _c, db = client
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, **entity_kwargs)
    return row, {"X-Portal-Token": _persisted_token(db, contact)}


def test_another_contacts_token_cannot_discard_a_draft(client):
    """Mirrors the 403/404 path the rest of the portal makes (see
    test_portal_revision_routes.py::test_revise_is_refused_with_another_contacts_token).
    `discard_draft` itself takes no token - the route is what enforces ownership
    via `fetch_owned`, so this has to run over HTTP to actually exercise the
    guard."""
    c, db = client
    row, headers = _http_setup(client)

    put_response = c.put(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revision-draft",
        headers=headers,
        json={"reason": "Mine", "base_revision_no": 0, "fields": {"quantity": "9"}},
    )
    assert put_response.status_code == 200, put_response.text

    intruder = seed_contact(db, name="Intruder")
    intruder_headers = {"X-Portal-Token": _persisted_token(db, intruder)}

    response = c.delete(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revision-draft",
        headers=intruder_headers,
    )
    assert response.status_code in (403, 404)

    # The owner's draft must still be there - the intruder's refused call did not
    # discard it.
    still_there = c.get(
        f"{BASE}/submissions/stock_inquiry/{row.id}", headers=headers
    ).json()
    assert still_there["revision_draft"] is not None


def test_another_contacts_token_cannot_read_a_draft(client):
    """`portal_get_submission` runs `PortalService.get_submission` under the token
    BEFORE it reads the draft, so a foreign token 403/404s the whole call rather
    than returning a submission body carrying somebody else's `revision_draft`."""
    c, db = client
    row, headers = _http_setup(client)
    c.put(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revision-draft",
        headers=headers,
        json={"reason": "Mine", "base_revision_no": 0, "fields": {"quantity": "9"}},
    )

    intruder = seed_contact(db, name="Intruder")
    intruder_headers = {"X-Portal-Token": _persisted_token(db, intruder)}

    response = c.get(
        f"{BASE}/submissions/stock_inquiry/{row.id}", headers=intruder_headers
    )
    assert response.status_code in (403, 404)
