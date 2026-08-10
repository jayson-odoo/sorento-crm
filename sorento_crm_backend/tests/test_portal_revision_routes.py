"""The revision endpoints, over HTTP.

The contract, not the service: a field the service returns but the route's
response_model does not declare is silently stripped by FastAPI, and the symptom is
a portal that renders nothing with no error anywhere. So every declared field is
asserted here, on the wire.

Routes covered:
  GET  /api/v1/public/portal/submissions/{kind}/{id}            -> + revision block
  GET  /api/v1/public/portal/submissions/{kind}/{id}/revisions
  POST /api/v1/public/portal/submissions/{kind}/{id}/revise
  GET  /api/v1/procurement/stock-inquiries/{id}/revisions       (office, read-only)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.portal import PortalToken
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    CONTACT_SPACE,
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
)

BASE = "/api/v1/public/portal"


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


def _setup(client, kind="stock_inquiry", **entity_kwargs):
    _c, db = client
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, **entity_kwargs)
    return row, {"X-Portal-Token": _persisted_token(db, contact)}


POLICY_KEYS = {
    "enabled",
    "allowed",
    "used",
    "max",
    "remaining",
    "blocked_reason",
    # The confirm dialog names the restart destination from config (UAC E1a); see
    # tests/test_revision_restart_stage_label.py for what it resolves to.
    "restart_stage_label",
}


def test_get_submission_carries_the_whole_revision_block(client):
    c, _db = client
    row, headers = _setup(client)

    response = c.get(f"{BASE}/submissions/stock_inquiry/{row.id}", headers=headers)
    assert response.status_code == 200
    revision = response.json()["revision"]
    assert set(revision) == POLICY_KEYS
    assert revision["allowed"] is True
    assert revision["used"] == 0


def test_get_submission_explains_why_it_cannot_be_revised(client):
    c, _db = client
    row, headers = _setup(client, status="closed")

    revision = c.get(
        f"{BASE}/submissions/stock_inquiry/{row.id}", headers=headers
    ).json()["revision"]
    assert revision["allowed"] is False
    assert revision["blocked_reason"]


def test_revise_round_trip(client):
    c, _db = client
    row, headers = _setup(client)

    response = c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        headers=headers,
        json={
            "reason": "Customer changed the quantity",
            "expected_revision_no": 0,
            "fields": {"quantity": "12"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision_no"] == 1
    assert body["revision"]["used"] == 1
    assert body["revision"]["remaining"] == 2
    assert body["submission"]["quantity"] == "12"
    assert body["submission"]["status"] == "pending_project_sales"


def test_revise_refuses_a_stale_revision_no(client):
    c, _db = client
    row, headers = _setup(client, revision_no=1)

    response = c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        headers=headers,
        json={"reason": "Trying again", "expected_revision_no": 0, "fields": {}},
    )
    assert response.status_code == 409


def test_revise_refuses_a_blank_reason_before_it_reaches_the_service(client):
    c, _db = client
    row, headers = _setup(client)

    response = c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        headers=headers,
        json={"reason": "", "expected_revision_no": 0, "fields": {}},
    )
    assert response.status_code == 422


def test_revision_history_declares_every_field(client):
    c, _db = client
    row, headers = _setup(client)
    c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        headers=headers,
        json={
            "reason": "Wrong product code on the original",
            "expected_revision_no": 0,
            "fields": {"product_code": "SRT-NEW"},
        },
    )

    response = c.get(f"{BASE}/submissions/stock_inquiry/{row.id}/revisions", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["label"] for item in items] == ["Original (reconstructed)", "Revision 1"]
    latest = items[1]
    assert {
        "id",
        "version_no",
        "revision_no",
        "kind",
        "label",
        "reason",
        "submitted_at",
        "submitted_by",
        "is_reconstructed",
        "snapshot",
        "attachments",
        "invalidated",
        "voided_stage_code",
        "voided_assignee_name",
        # Every stage this revision voided, not only the newest: a form can have two
        # stages open at once and both handlers are told to stop.
        "voided_stages",
        "changes",
    } == set(latest)
    change = next(c for c in latest["changes"] if c["field"] == "product_code")
    assert change["to"] == "SRT-NEW"
    assert set(change) == {"field", "label", "from", "to"}


def test_history_is_not_readable_with_another_contacts_token(client):
    c, db = client
    row, _headers = _setup(client)
    intruder = seed_contact(db, name="Intruder")
    headers = {"X-Portal-Token": _persisted_token(db, intruder)}

    response = c.get(f"{BASE}/submissions/stock_inquiry/{row.id}/revisions", headers=headers)
    assert response.status_code in (403, 404)


def test_revise_is_refused_with_another_contacts_token(client):
    c, db = client
    row, _headers = _setup(client)
    intruder = seed_contact(db, name="Intruder")
    headers = {"X-Portal-Token": _persisted_token(db, intruder)}

    response = c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        headers=headers,
        json={"reason": "Not my form", "expected_revision_no": 0, "fields": {}},
    )
    assert response.status_code in (403, 404)


def test_a_revision_needs_a_token_at_all(client):
    c, _db = client
    row, _headers = _setup(client)
    response = c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        json={"reason": "No token here", "expected_revision_no": 0, "fields": {}},
    )
    assert response.status_code == 401


def test_a_file_only_an_old_revision_references_stays_readable(client):
    """UAC G6/I2a: a file dropped during a revision loses its live link but stays in
    that revision's snapshot. Authorisation has to follow it there, or history
    previews 404 on exactly the files history exists to show."""
    from app.api.v1.public.portal import _portal_can_read_attachment
    from app.models.portal import PortalFormRevision
    from app.models.resources import Attachment

    c, db = client
    row, headers = _setup(client)
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename="quote.pdf",
        stored_filename="quote.pdf",
        file_path="portal/quote.pdf",
        uploader_kind="contact",
    )
    db.add(attachment)
    # No EntityAttachmentLink at all: this is the "removed in a later revision" shape.
    db.add(
        PortalFormRevision(
            id=str(uuid.uuid4()),
            source_entity_type="stock_inquiry",
            source_entity_id=str(row.id),
            version_no=0,
            revision_no=0,
            kind="original",
            snapshot_json={},
            attachments_json=[
                {"attachment_id": str(attachment.id), "link_id": None, "filename": "quote.pdf"}
            ],
        )
    )
    db.commit()

    token = headers["X-Portal-Token"]
    from app.models.portal import PortalToken as _PortalToken

    owner_token = db.query(_PortalToken).filter(_PortalToken.token == token).one()
    assert _portal_can_read_attachment(db, owner_token, str(attachment.id)) is True

    intruder = seed_contact(db, name="Intruder")
    intruder_token = db.query(_PortalToken).filter(
        _PortalToken.token == _persisted_token(db, intruder)
    ).one()
    assert _portal_can_read_attachment(db, intruder_token, str(attachment.id)) is False


def test_office_route_reads_the_same_lineage(client):
    """UAC H2/H3/H5: the office reads the identical payload, and only reads it."""
    from app.dependencies import get_current_user, get_current_user_or_api_key

    c, _db = client
    row, headers = _setup(client)
    c.post(
        f"{BASE}/submissions/stock_inquiry/{row.id}/revise",
        headers=headers,
        json={"reason": "Corrected the quantity", "expected_revision_no": 0, "fields": {}},
    )

    actor = {"id": str(uuid.uuid4()), "email": "office@example.test", "role": "admin"}
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_current_user_or_api_key] = lambda: actor

    response = c.get(f"/api/v1/procurement/stock-inquiries/{row.id}/revisions")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["label"] for item in items] == ["Original (reconstructed)", "Revision 1"]
    assert items[1]["reason"] == "Corrected the quantity"
