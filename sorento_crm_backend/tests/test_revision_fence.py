"""The revision fence: 409 on a write aimed at a superseded version (UAC C-bis).

Every office write on a revisable form carries the ``revision_no`` the client was
looking at, in ``X-Revision-No``. When it no longer matches, the write is refused
with 409 and NOTHING is written - the whole point being that a contact revision
voided the stage the office user was mid-way through, and their tab is holding a
version that no longer exists (CB1/CB2).

What is pinned here:

* 409 on a stale header and 200 on a current one, on **every gated endpoint** and
  **all three revisable types** (CB3);
* no side effect on a refusal - the row is untouched;
* the fence and the S3d response status gate are **independent** (AC O4): a write
  can be refused by either, and passing one never bypasses the other;
* a type whose config row is disabled is not fenced (CB4) - complaint, today;
* a request with no header is not fenced, which is what keeps the integration
  principals (n8n, MCP, external API) working.

Postgres only, on an empty scratch schema, seeding its own chain under a marker.

Run: venv/bin/pytest tests/test_revision_fence.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.complaints import Complaint
from app.models.portal import PortalRevisionConfig
from app.models.procurement import PurchaseRequestHeader, StockInquiry
from tests._pg_fixture import blank_session

MARKER = "ZZT-FENCE"
HEADER = "X-Revision-No"

SI_BASE = "/api/v1/procurement/stock-inquiries"
PR_BASE = "/api/v1/procurement/purchase-requests"
CMP_BASE = "/api/v1/complaints-management/complaints"

# A ':' in the last segment passes straight through resolve_send_identifier, so a
# reply path finds a sendable identifier without seeding a RespondContact.
INBOX_URL = "https://app.respond.io/space/364817/inbox/id:60123"


@pytest.fixture
def client():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db

    with blank_session() as db:

        def _override_get_db():
            yield db

        def _override_current_user():
            return {"id": str(uuid.uuid4()), "email": "staff@test.com", "name": "Jay"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_current_user
        try:
            with patch("app.services.queue_service.enqueue_job", return_value=None):
                with TestClient(app) as c:
                    yield c, db
        finally:
            app.dependency_overrides.clear()


# ------------------------------------------------------------------ seeding
# Nothing is borrowed from an existing table: the config seed lives in the
# migration body, so a create_all schema has the table and no rows, and a missing
# row means disabled (fail closed).


def _config(db, source_entity_type: str, *, is_enabled: bool = True) -> PortalRevisionConfig:
    row = PortalRevisionConfig(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        is_enabled=is_enabled,
        max_revisions=3,
        allowed_statuses=["pending_purchasing", "submitted", "responded"],
    )
    db.add(row)
    db.commit()
    return row


def _inquiry(db, *, revision_no: int, status: str = "pending_purchasing") -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"{MARKER}-SI-{uuid.uuid4().hex[:6]}",
        status=status,
        salesperson=f"{MARKER} salesperson",
        product_code=f"{MARKER}-P",
        item_description="Free standing bath tub mixer",
        quantity="4",
        purchasing_response="the answer to the superseded version",
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
        revision_no=revision_no,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request(db, *, revision_no: int, request_type="purchase_request") -> PurchaseRequestHeader:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_number=f"{MARKER}-PR-{uuid.uuid4().hex[:6]}",
        request_type=request_type,
        status="submitted",
        source="portal",
        customer_name=f"{MARKER} customer",
        project_title=f"{MARKER} project",
        purpose=f"{MARKER} purpose",
        requested_by=f"{MARKER} requester",
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
        revision_no=revision_no,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _complaint(db, *, status: str = "submitted") -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{MARKER}-CMP-{uuid.uuid4().hex[:6]}",
        customer_name=f"{MARKER} customer",
        status=status,
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _stale(revision_no: int) -> dict:
    return {HEADER: str(revision_no)}


# ------------------------------------------------------------- stale -> 409
# One case per gated endpoint, so a route that loses its dependency fails here
# rather than in production.

SI_WRITES = [
    ("put", "", {"json": {"remark": f"{MARKER} edited"}}),
    ("post", "/update-and-reply", {"json": {"purchasing_response": f"{MARKER} reply"}}),
    ("post", "/submit-for-project-sales", {}),
    ("post", "/project-sales-approve", {}),
    ("post", "/project-sales-reject", {"json": {"reason": f"{MARKER} no"}}),
    ("post", "/purchasing-reject", {"json": {"reason": f"{MARKER} no"}}),
    ("post", "/reopen", {"json": {"reason": f"{MARKER} again"}}),
    ("post", "/void", {"json": {"void_reason": f"{MARKER} void"}}),
    ("post", "/attachments", {"json": {"attachment_id": str(uuid.uuid4())}}),
    ("delete", "", {}),
]


@pytest.mark.parametrize("method,suffix,kwargs", SI_WRITES)
def test_stale_revision_is_refused_on_every_stock_inquiry_write(client, method, suffix, kwargs):
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2)

    response = getattr(c, method)(f"{SI_BASE}/{row.id}{suffix}", headers=_stale(1), **kwargs)

    assert response.status_code == 409, response.text
    message = response.json()["message"]
    assert "revised while you were working on it" in message
    assert "revision 2" in message
    assert "—" not in message and "–" not in message  # no em / en dashes

    # Nothing happened: same status, same response, still there.
    db.rollback()
    db.refresh(row)
    assert row.status == "pending_purchasing"
    assert row.purchasing_response == "the answer to the superseded version"


PR_WRITES = [
    ("put", "", {"json": {"project_title": f"{MARKER} edited"}}),
    ("post", "/update-and-reply", {"json": {"reply_message": f"{MARKER} hello"}}),
    ("post", "/set-pending-approval", {}),
    ("post", "/reject-submitted", {"json": {"rejection_reason": f"{MARKER} no"}}),
    ("post", "/approval-decision", {"json": {"action": "approved"}}),
    ("post", "/process", {}),
    ("post", "/close", {}),
    ("post", "/void", {"json": {"void_reason": f"{MARKER} void"}}),
    ("post", "/send-approval-link", {"json": {"approver_email": "a@b.test"}}),
    ("post", "/attachments", {"json": {"attachment_id": str(uuid.uuid4())}}),
    ("delete", "", {}),
]


@pytest.mark.parametrize("method,suffix,kwargs", PR_WRITES)
def test_stale_revision_is_refused_on_every_purchase_request_write(
    client, method, suffix, kwargs
):
    c, db = client
    _config(db, "purchase_request")
    row = _request(db, revision_no=2)

    response = getattr(c, method)(f"{PR_BASE}/{row.id}{suffix}", headers=_stale(1), **kwargs)

    assert response.status_code == 409, response.text
    assert "purchase request was revised" in response.json()["message"]

    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"
    assert row.project_title == f"{MARKER} project"


def test_stale_revision_is_refused_on_a_sponsorship_form(client):
    """PR and SF share one table and one route family, and are separate config
    rows - so the fence must resolve the type off the row, not the route."""
    c, db = client
    _config(db, "sponsorship_form")
    row = _request(db, revision_no=1, request_type="sponsorship_form")

    response = c.put(
        f"{PR_BASE}/{row.id}",
        headers=_stale(0),
        json={"project_title": f"{MARKER} edited"},
    )

    assert response.status_code == 409, response.text
    assert "sponsorship form was revised" in response.json()["message"]


def test_a_sponsorship_form_is_not_fenced_by_the_purchase_request_config(client):
    """Enabling PR must not silently arm SF. Separate rows, separate decisions."""
    c, db = client
    _config(db, "purchase_request")  # SF has NO config row -> not revisable
    row = _request(db, revision_no=1, request_type="sponsorship_form")

    response = c.put(
        f"{PR_BASE}/{row.id}",
        headers=_stale(0),
        json={"project_title": f"{MARKER} edited"},
    )

    assert response.status_code == 200, response.text


# ------------------------------------------------------------ current -> 200


def test_a_current_revision_passes_on_stock_inquiry(client):
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2)

    response = c.put(
        f"{SI_BASE}/{row.id}", headers=_stale(2), json={"remark": f"{MARKER} edited"}
    )

    assert response.status_code == 200, response.text
    db.refresh(row)
    assert row.remark == f"{MARKER} edited"


def test_a_current_revision_passes_on_purchase_request(client):
    c, db = client
    _config(db, "purchase_request")
    row = _request(db, revision_no=2)

    response = c.put(
        f"{PR_BASE}/{row.id}",
        headers=_stale(2),
        json={"project_title": f"{MARKER} edited"},
    )

    assert response.status_code == 200, response.text
    db.refresh(row)
    assert row.project_title == f"{MARKER} edited"


def test_revision_zero_is_a_real_expectation_not_a_missing_one(client):
    """An unrevised record still fences: 0 is the value, not "unknown"."""
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=0)

    assert (
        c.put(f"{SI_BASE}/{row.id}", headers=_stale(0), json={"remark": "ok"}).status_code
        == 200
    )
    assert (
        c.put(f"{SI_BASE}/{row.id}", headers=_stale(1), json={"remark": "no"}).status_code
        == 409
    )


# --------------------------------------------------------- not fenced at all


def test_a_request_with_no_header_is_not_fenced(client):
    """What keeps n8n / MCP / the external API working: no expectation, no fence."""
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2)

    response = c.put(f"{SI_BASE}/{row.id}", json={"remark": f"{MARKER} edited"})

    assert response.status_code == 200, response.text


def test_a_disabled_type_is_not_fenced(client):
    """CB4: revisability is config-driven, so complaint costs nothing today."""
    c, db = client
    _config(db, "complaint", is_enabled=False)
    row = _complaint(db)

    response = c.put(
        f"{CMP_BASE}/{row.id}",
        headers=_stale(7),
        json={"customer_name": f"{MARKER} renamed"},
    )

    assert response.status_code == 200, response.text
    db.refresh(row)
    assert row.customer_name == f"{MARKER} renamed"


def test_a_type_with_no_config_row_is_not_fenced(client):
    """A missing row means disabled (fail closed on revising, open on writing)."""
    c, db = client
    row = _inquiry(db, revision_no=2)

    response = c.put(
        f"{SI_BASE}/{row.id}", headers=_stale(1), json={"remark": f"{MARKER} edited"}
    )

    assert response.status_code == 200, response.text


def test_the_complaint_fence_arms_itself_when_the_config_is_enabled(client):
    """The wiring is real, not decorative: flip the checkbox and it fences.

    Complaints carry no revision_no column, so the current revision reads 0 -
    which is exactly right for a type that cannot be revised yet.
    """
    c, db = client
    _config(db, "complaint", is_enabled=True)
    row = _complaint(db)

    stale = c.put(
        f"{CMP_BASE}/{row.id}", headers=_stale(3), json={"customer_name": "no"}
    )
    current = c.put(
        f"{CMP_BASE}/{row.id}",
        headers=_stale(0),
        json={"customer_name": f"{MARKER} renamed"},
    )

    assert stale.status_code == 409, stale.text
    assert current.status_code == 200, current.text


def test_a_read_is_never_fenced(client):
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2)

    assert c.get(f"{SI_BASE}/{row.id}", headers=_stale(1)).status_code == 200


def test_an_unknown_record_still_404s_rather_than_409ing(client):
    """The fence owns staleness, not existence - the route's own error stands."""
    c, db = client
    _config(db, "stock_inquiry")

    response = c.put(
        f"{SI_BASE}/{uuid.uuid4()}", headers=_stale(1), json={"remark": "x"}
    )

    assert response.status_code == 404, response.text


# ----------------------------------------- independent of the S3d status gate
# AC O4. Two checks on two different axes: the status gate asks "is this record
# still in the stage that wants a response", the fence asks "is this the version
# you were looking at". Passing one must never bypass the other.


def test_the_status_gate_still_refuses_when_the_revision_is_current(client):
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2, status="rejected")

    response = c.put(
        f"{SI_BASE}/{row.id}",
        headers=_stale(2),  # current revision - the fence is satisfied
        json={"purchasing_response": f"{MARKER} a brand new answer"},
    )

    assert response.status_code == 422, response.text
    assert "purchasing response" in response.json()["message"]
    db.rollback()
    db.refresh(row)
    assert row.purchasing_response == "the answer to the superseded version"


def test_the_fence_still_refuses_when_the_status_gate_would_allow_it(client):
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2, status="pending_purchasing")

    response = c.put(
        f"{SI_BASE}/{row.id}",
        headers=_stale(1),  # stale - the status gate would have allowed this write
        json={"purchasing_response": f"{MARKER} a brand new answer"},
    )

    assert response.status_code == 409, response.text
    db.rollback()
    db.refresh(row)
    assert row.purchasing_response == "the answer to the superseded version"


def test_both_gates_pass_and_the_response_is_written(client):
    c, db = client
    _config(db, "stock_inquiry")
    row = _inquiry(db, revision_no=2, status="pending_purchasing")

    response = c.put(
        f"{SI_BASE}/{row.id}",
        headers=_stale(2),
        json={"purchasing_response": f"{MARKER} a brand new answer"},
    )

    assert response.status_code == 200, response.text
    db.refresh(row)
    assert row.purchasing_response == f"{MARKER} a brand new answer"


def test_stale_header_on_never_revised_record_does_not_claim_a_revision():
    """A mismatch against revision 0 must not read "revised ... see revision 0".

    Found by a live probe, not by any unit test: every fence test asserted the 409
    status and the sentence shape, none asserted the sentence made sense. When the
    record has never been revised there IS no revision to reload to, so the copy
    names only what is certain.
    """
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "app" / "services" / "revision_fence.py"
    text = source.read_text()
    assert "has changed since you opened it" in text, (
        "the revision-0 branch of the fence conflict message is missing"
    )
    # The self-contradictory phrasing must not be reachable when current == 0.
    branch = re.search(r"if current == 0:(.+?)raise handle_conflict\(\s*\n\s*f\"This \{label\} was revised", text, re.S)
    assert branch is not None, "the revision-0 branch must sit before the 'was revised' message"
