"""S3 - the three consumer intake routes.

    GET  /api/v1/public/portal/lodge/kinds      the tiled chooser
    POST /api/v1/public/portal/lodge/resolve    "did I get this right?", writes nothing
    POST /api/v1/public/portal/lodge            submit

The service-level guarantees are pinned in `test_consumer_lodge.py`; this file covers what
only the HTTP layer can get wrong.

**Auth is the first of those.** Every one of these routes is portal-token scoped. An
unauthenticated lodge endpoint is an invitation to fill the complaint table with junk, and
the consumer arrives from a WhatsApp link that already carries a token, so requiring one
costs the journey nothing.

**The token is the identity, not the body** - and the PHONE is what that means. Overriding
`respond_contact_id` alone was not enough: `ensure_profile` keys the ConsumerProfile on the
normalised phone, so while the body supplied it, any valid token could type a stranger's
number and write consent, a review row and a purchase onto their ledger, then read their
dealer and warranty verdicts back out of the response. Both the contact id and the phone now
come from the resolved token. The body's phone is optional and ignored.

**`resolve` must write nothing.** It is called every time the consumer edits the shop name,
because the Phase 1 prototype pre-fills an editable form rather than a read-only
confirmation. If it wrote, a consumer fixing a typo three times would leave three of
everything.

Run: venv/bin/python -m pytest tests/test_lodge_endpoints.py -q -p no:randomly
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app.database import get_db  # noqa: E402
from app.models.access import RespondContact  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402
from app.models.consumers import ConsumerProfile  # noqa: E402
from app.models.portal import PortalToken  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

BASE = "/api/v1/public/portal/lodge"
PHONE = "+60129998877"


@pytest.fixture
def stack():
    """An isolated blank schema, with the app's `get_db` handing out THAT session.

    Deliberately not a transaction on the shared database: `lodge_complaint` commits,
    so a shared-DB session could not be rolled back afterwards and the tests would
    leave real complaints behind. A blank schema is also the only honest check that
    the routes seed what they need rather than borrowing production rows.
    """
    from scripts.seed_warranty_policy_v15 import seed as seed_warranty
    from app.services.consent_notice_service import seed_consent_notices

    with blank_session() as db:
        # Both are prerequisites of the journey rather than test scaffolding: no
        # published notice means the lodge must refuse, and no Kinds means the tiled
        # chooser has nothing to show.
        seed_consent_notices(db)
        seed_warranty(db)
        db.commit()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(stack):
    return stack[0]


@pytest.fixture
def db(stack):
    return stack[1]


@pytest.fixture
def token(db):
    """A live portal token and its contact. Marker-prefixed, and torn down by the
    fixture's rollback - never by an unscoped DELETE.
    """
    from datetime import datetime, timedelta

    contact = RespondContact(
        id=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}".lower(),
        phone_number=PHONE,
        name=f"{TEST_PREFIX} Consumer",
    )
    db.add(contact)
    db.flush()
    row = PortalToken(
        id=str(uuid.uuid4()),
        token=f"{TEST_PREFIX}{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id=f"{TEST_PREFIX}-space",
        expires_at=datetime.utcnow() + timedelta(days=1),
        # `resolve_token` refuses an unverified token: admin-issued links start
        # unverified and the contact must pass OTP once. A consumer following a
        # WhatsApp link has already done that by the time they reach the form.
        verified_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def _headers(token) -> dict:
    return {"X-Portal-Token": token.token}


def _payload(**overrides) -> dict:
    payload = {
        "phone": PHONE,
        "full_name": f"{TEST_PREFIX} Consumer",
        "shop_name": "A SHOP THAT DOES NOT EXIST IN CUSTOMERS AT ALL",
        "purchase_date": "2025-10-16",
        "dealer_document_number": f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        "site_address": "12 Jalan Contoh, Puchong",
        "lines": [
            {
                "claimed_text": "SRTWC8152 WATER CLOSET",
                "model_code_raw": "SRTWC8152",
                "quantity": 1,
                "fault_description": "Water keeps running after flushing.",
            }
        ],
    }
    payload.update(overrides)
    return payload


# ========================================================================= auth


def test_every_route_refuses_without_a_token(client):
    """A public write with no auth is a junk-data faucet."""
    assert client.get(f"{BASE}/kinds").status_code in (401, 403, 422)
    assert client.post(f"{BASE}/resolve", json={"lines": []}).status_code in (401, 403, 422)
    assert client.post(BASE, json=_payload()).status_code in (401, 403, 422)


def test_a_bad_token_is_refused(client):
    r = client.get(f"{BASE}/kinds", headers={"X-Portal-Token": "not-a-real-token"})
    assert r.status_code in (401, 403, 404)


def test_the_token_supplies_the_contact_and_the_body_cannot_override_it(client, token, db):
    """Confused deputy. A valid token must not be able to lodge against another contact."""
    other = f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}".lower()
    r = client.post(BASE, json=_payload(respond_contact_id=other), headers=_headers(token))
    assert r.status_code == 200, r.text

    complaint = (
        db.query(Complaint).filter(Complaint.id == r.json()["complaint_id"]).first()
    )
    assert complaint is not None
    assert complaint.contact_id != other, (
        "The body's contact id reached the row. A valid token could then lodge "
        "complaints against anybody."
    )


def test_a_phone_in_the_body_cannot_lodge_against_a_stranger(client, token, db):
    """The confused deputy that the contact-id check above did NOT close.

    `ensure_profile` keys the ConsumerProfile on the normalised PHONE, not on
    `respond_contact_id`. While the body supplied the phone, any valid token could type
    somebody else's number and write consent, a name-conflict review row and a purchase
    onto that stranger's ledger - then read their dealer and warranty verdicts back out of
    the response. Overriding only the contact id was not enough, because the contact id is
    not what the profile is keyed on.
    """
    stranger = "+60195550001"
    r = client.post(BASE, json=_payload(phone=stranger), headers=_headers(token))
    assert r.status_code == 200, r.text

    hijacked = (
        db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == stranger).first()
    )
    assert hijacked is None, (
        "A profile was created or reused for a phone the caller merely typed. The token's "
        "own contact is the only identity a portal lodgement may assert."
    )

    mine = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).first()
    assert mine is not None, "The lodgement must land on the TOKEN's consumer."
    assert str(r.json()["complaint_id"])


# ======================================================================== kinds


def test_the_chooser_returns_kinds_with_a_label_each(client, token):
    """A tile with no label is unclickable in practice, so the label falls back to the
    internal name rather than rendering empty.
    """
    r = client.get(f"{BASE}/kinds", headers=_headers(token))
    assert r.status_code == 200, r.text
    kinds = r.json()["kinds"]
    assert kinds, "The chooser is the only way an unresolved line gets a Kind."
    assert all(k["label"] for k in kinds)
    assert all("icon" in k for k in kinds), (
        "The icon field ships null today (Sorento accepted text-only tiles). It must "
        "still be in the contract so artwork needs no contract change."
    )


# ====================================================================== resolve


def test_resolve_writes_nothing(client, token, db):
    """Called on every edit of the shop name. If it wrote, correcting a typo three
    times would leave three of everything.
    """
    before = db.query(Complaint).count(), db.query(ConsumerProfile).count()
    r = client.post(
        f"{BASE}/resolve",
        json={"shop_name": "TOTAL HOME DIY SDN BHD", "lines": _payload()["lines"]},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    assert (db.query(Complaint).count(), db.query(ConsumerProfile).count()) == before


def test_resolve_answers_with_a_dealer_state_not_a_score(client, token):
    """A float invites every caller to invent a cutoff, and the cutoff somebody invents
    eventually pre-fills one of the three real-but-wrong dealers the spike found.
    """
    r = client.post(
        f"{BASE}/resolve",
        json={"shop_name": "A SHOP THAT DOES NOT EXIST IN CUSTOMERS AT ALL", "lines": []},
        headers=_headers(token),
    )
    dealer = r.json()["dealer"]
    assert dealer["state"] in ("resolved", "candidate", "unmatched")
    assert "score" not in dealer
    if dealer["state"] != "resolved":
        assert dealer["customer_id"] is None, (
            "Only a resolved dealer carries an id. A candidate shown as a fact is how a "
            "purchase gets attributed to a shop that never sold it."
        )


def test_resolve_keeps_the_printed_name_whatever_the_verdict(client, token):
    printed = "SOME SHOP THAT IS NOT IN THE CUSTOMER TABLE"
    r = client.post(
        f"{BASE}/resolve", json={"shop_name": printed, "lines": []}, headers=_headers(token)
    )
    assert r.json()["dealer"]["printed_name"] == printed


def test_resolve_handles_free_text_instead_of_a_model_code(client, token):
    """AC-C16. "the tap in my kitchen" is a valid thing to type and an invalid thing to
    resolve. The Kind chooser is what answers it, so the line must be flagged for it.
    """
    r = client.post(
        f"{BASE}/resolve",
        json={
            "shop_name": None,
            "lines": [{"claimed_text": "the tap in my kitchen", "quantity": 1}],
        },
        headers=_headers(token),
    )
    line = r.json()["lines"][0]
    assert line["state"] == "unmatched"
    assert line["product_id"] is None
    assert line["needs_kind"] is True


# ======================================================================== lodge


def test_a_lodgement_returns_a_number_and_a_verdict(client, token):
    r = client.post(BASE, json=_payload(), headers=_headers(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["complaint_id"]
    assert "warranty" in body, "The verdict is the value exchanged for the data."
    assert body["dealer_state"] in ("resolved", "candidate", "unmatched")


def test_a_lodgement_with_nothing_resolvable_still_succeeds(client, token):
    """AC-C14, over HTTP. No shop, no date, no model code: a consumer with a broken
    toilet is not the person to punish for a bad OCR result.
    """
    r = client.post(
        BASE,
        json=_payload(
            shop_name=None,
            purchase_date=None,
            dealer_document_number=None,
            lines=[{"claimed_text": "toilet leaking", "fault_description": "leaking"}],
        ),
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["complaint_id"]


def test_a_lodgement_with_no_lines_at_all_still_succeeds(client, token):
    """The consumer may not know what the thing is called. That is what CS is for."""
    r = client.post(BASE, json=_payload(lines=[]), headers=_headers(token))
    assert r.status_code == 200, r.text


def test_a_lodgement_needs_no_phone_in_the_body_at_all(client, token, db):
    """The inverse of the hijack test, and the reason the body's phone is now optional.

    The token's contact supplies the identity, so a body that omits the phone entirely is
    the CORRECT shape - the portal has no business asking a consumer for a number Sorento
    already has (Phase 0: anything knowable is never asked for). This started life as
    "without a phone the lodgement is refused", which was true only while the body was
    trusted, and asserting it now would lock in the hole.
    """
    payload = _payload()
    payload.pop("phone")
    r = client.post(BASE, json=payload, headers=_headers(token))
    assert r.status_code == 200, r.text

    profile = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).first()
    assert profile is not None, "The token's own phone must have supplied the identity."
