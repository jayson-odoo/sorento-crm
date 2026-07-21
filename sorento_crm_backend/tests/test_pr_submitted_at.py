"""purchase_requests.submitted_at — auto-stamped on every portal submit.

The PR/SF document's top "Date" = submitted date. It is stamped in
PortalService.submit_draft (the sole place PR/SF reach status='submitted') and
RE-stamped on resubmit-after-rejection, mirroring approved_at which also resets
per approval cycle. See docs/plans/PLAN-pr-sf-three-dates.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.procurement import PurchaseRequestHeader
from app.models.portal import PortalToken
import app.services.form_sla_service as form_sla_service_mod
from app.services.portal_service import PortalService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite over a hand-listed subset of the procurement tables.
    """
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _neutralize_side_effects(monkeypatch):
    """submit_draft generates document numbers, fires notifications + SLA events,
    and re-serializes via get_submission — none relevant to the date stamp."""
    monkeypatch.setattr(
        PortalService, "_assign_document_number_if_missing", lambda self, kind, row: None
    )
    monkeypatch.setattr(PortalService, "_post_submit_notify", lambda self, *a, **kw: None)
    monkeypatch.setattr(
        PortalService, "get_submission", lambda self, token, kind, sid: {"id": sid}
    )
    monkeypatch.setattr(
        form_sla_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )


def _seed(db, kind="sponsorship_form"):
    token = PortalToken(
        id=str(uuid.uuid4()),
        token="tok_" + uuid.uuid4().hex,
        contact_id="contact-1",
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=kind,
        status="draft",
        source="portal",
        contact_id="contact-1",
        space_id="space-1",
        portal_draft_at=datetime.utcnow(),
    )
    db.add_all([token, header])
    db.commit()
    return token, header


def test_submit_stamps_submitted_at(db):
    token, header = _seed(db)
    assert header.submitted_at is None

    PortalService(db).submit_draft(token, "sponsorship_form", str(header.id))

    db.refresh(header)
    assert header.status == "submitted"
    assert header.submitted_at is not None


def test_resubmit_after_rejection_restamps_submitted_at(db):
    token, header = _seed(db)
    svc = PortalService(db)
    svc.submit_draft(token, "sponsorship_form", str(header.id))
    db.refresh(header)

    # Force the first submit older so the re-stamp is unambiguously newer, and
    # put the row in the rejected state a resubmit starts from.
    older = header.submitted_at - timedelta(days=1)
    header.submitted_at = older
    header.approval_status = "rejected"
    header.status = "rejected"
    db.commit()

    svc.submit_draft(token, "sponsorship_form", str(header.id))

    db.refresh(header)
    assert header.status == "submitted"
    assert header.submitted_at > older  # re-stamped to the latest submit
    assert header.approval_status is None  # rejection cleared on resubmit
