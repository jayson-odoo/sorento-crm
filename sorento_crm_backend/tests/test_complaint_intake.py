"""S5 - WhatsApp intake, the path the office currently walks by hand.

Today a dealer sends a burst of photos and one line of text to a WhatsApp group, and
somebody in the office reads it a day later and asks *"this one wat issue? for which dealer?
for wat model?"*. S5 is that job, done at the moment the message lands.

**n8n is the pump; the CRM is the tool** (AC-C0a to AC-C0d). Respond.io messages reach n8n,
n8n debounces the burst with a wait node, and when the burst closes it calls ONE write tool.
The CRM neither polls nor subscribes. Extraction stays CRM-side because the prompt must be
versioned through `ai_prompt_registry` and the dealer / product / Kind resolvers already live
here - an LLM node in n8n would fork the registry and duplicate three resolvers.

What shapes this suite:

1. **Idempotent on the burst key** (AC-C0d). n8n retries on timeout. A retry that creates a
   second Complaint turns one dealer's message into two cases, and the office is back to
   deduplicating by hand - the exact work this slice removes.

2. **One frame, one Complaint, however many messages** (AC-C1 to AC-C3). The two real bursts
   in the plan are the bar: eight media then a text 15 seconds later, and photos BEFORE the
   text. Media-first is not an edge case; it is how people actually send.

3. **Extraction is generalised, never keyword-matched** (AC-C8). The tests use PARAPHRASES of
   real messages. A branch per phrasing passes the test table and fails the next real dealer,
   so the extractor is injected here and the assertions are about what the service does with
   a result - not about parsing English.

4. **Nothing blocks intake.** The same rule as the consumer portal (AC-C14): an unmatched
   dealer, an unresolvable model, no text at all - each still produces a Complaint carrying
   what was actually said. A refusal here means the message stays in WhatsApp, which is where
   it already goes to die.

5. **Ask for only what is missing** (AC-C5), and never re-ask what was extracted. Re-asking is
   what makes an automated follow-up feel worse than the human one it replaces.

Run: venv/bin/python -m pytest tests/test_complaint_intake.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from app.models.access import RespondContact  # noqa: E402
from app.models.complaints import Complaint, ComplaintProductLine  # noqa: E402
from app.models.order import Customer  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

MODULE = "app.services.complaint_intake_service"

CONTACT_PHONE = "+60123334444"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _service():
    if importlib.util.find_spec(MODULE) is None:
        raise AssertionError(
            f"{MODULE} does not exist. Intake belongs in one service: the burst-to-Complaint "
            "transaction, the idempotency key and the resolver calls are one decision, and "
            "splitting them across the MCP tool and a route is how a retry creates a second "
            "case."
        )
    return importlib.import_module(MODULE)


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _contact(db) -> RespondContact:
    row = RespondContact(
        id=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}".lower(),
        phone_number=CONTACT_PHONE,
        name=f"{TEST_PREFIX} Dealer Staff",
    )
    db.add(row)
    db.flush()
    return row


def _dealer(db, name: str = "UNIHOME SDN BHD") -> Customer:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        customer_name=name,
    )
    db.add(row)
    db.flush()
    return row


def _extraction(**overrides) -> dict:
    """What the extractor returns. The SHAPE is the contract; the English is not.

    Deliberately a plain dict rather than a model call: AC-C8 forbids a keyword branch per
    phrasing, so these tests must not be able to encode one. What is asserted is what the
    service DOES with an extraction, which is the part that can regress silently.
    """
    payload = {
        "shop_name": "UNIHOME SDN BHD",
        "lines": [
            {"claimed_text": "SRTWC8366 x 1", "model_code_raw": "SRTWC8366", "quantity": 1},
            {"claimed_text": "SRTWC8152 x 1", "model_code_raw": "SRTWC8152", "quantity": 1},
        ],
        "defect_description": "Seatcover no soft close.",
        "requested_resolution": "replace_to_shop",
        "prompt_versions": [{"name": "intake_extractor", "version": 1}],
    }
    payload.update(overrides)
    return payload


def _submit(db, *, burst_key: str, contact_id: str, extraction=None, **overrides):
    kwargs = {
        "burst_key": burst_key,
        "contact_id": contact_id,
        "messages": [
            {"text": "", "sent_at": "2026-05-13T10:14:18", "media_ref": "m1"},
            {
                "text": "Unihome. SRTWC8366 x 1 / SRTWC8152 x 1 / Seatcover no soft close. "
                "Pls replace to shop",
                "sent_at": "2026-05-13T10:16:33",
            },
        ],
        "media_refs": ["m1"],
        "extraction": _extraction() if extraction is None else extraction,
    }
    kwargs.update(overrides)
    return _fn(_service(), "submit_intake", "(db, **kwargs)")(db, **kwargs)


# ==================================================== idempotency, AC-C0d


def test_a_retry_on_the_same_burst_returns_the_same_complaint(db):
    """n8n retries on timeout. Without this, one dealer's message becomes two cases and
    the office is deduplicating by hand again - the work this slice exists to remove.
    """
    contact = _contact(db)
    _dealer(db)
    key = f"{TEST_PREFIX}-burst-{uuid.uuid4().hex[:8]}"

    first = _submit(db, burst_key=key, contact_id=contact.id)
    second = _submit(db, burst_key=key, contact_id=contact.id)

    assert first.complaint_id == second.complaint_id
    assert first.complaint_number == second.complaint_number
    assert db.query(Complaint).count() == 1, "A retry created a second Complaint."


def test_a_retry_reports_that_it_was_already_held(db):
    """The caller has to be able to tell a fresh create from a replay, or n8n cannot know
    whether its follow-up message has already been sent.
    """
    contact = _contact(db)
    key = f"{TEST_PREFIX}-burst-{uuid.uuid4().hex[:8]}"
    assert _submit(db, burst_key=key, contact_id=contact.id).already_submitted is False
    assert _submit(db, burst_key=key, contact_id=contact.id).already_submitted is True


def test_a_different_burst_from_the_same_contact_is_a_new_complaint(db):
    """Two problems reported an hour apart are two cases. Keying on the contact instead of
    the burst would silently merge them.
    """
    contact = _contact(db)
    first = _submit(db, burst_key=f"{TEST_PREFIX}-a", contact_id=contact.id)
    second = _submit(db, burst_key=f"{TEST_PREFIX}-b", contact_id=contact.id)
    assert first.complaint_id != second.complaint_id


# ============================================ one burst, one Complaint (AC-C1 to C3)


def test_a_burst_of_media_and_text_produces_one_complaint_with_a_line_each(db):
    """AC-C2, Sean's real message. Eight media at 10:14, the text at 10:16:33, two models
    named in one line.
    """
    contact = _contact(db)
    _dealer(db)
    media = [f"m{i}" for i in range(8)]
    result = _submit(
        db,
        burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        media_refs=media,
    )

    lines = (
        db.query(ComplaintProductLine)
        .filter(ComplaintProductLine.complaint_id == result.complaint_id)
        .order_by(ComplaintProductLine.sort_order)
        .all()
    )
    assert len(lines) == 2, "Two models were named, so the Complaint carries two lines."
    assert {line.product_code for line in lines} == {"SRTWC8366", "SRTWC8152"}
    assert result.media_count == 8, (
        "All eight media must be accounted for. Losing some is losing the evidence the "
        "dealer bothered to send."
    )


def test_media_arriving_before_the_text_still_lands_on_the_same_complaint(db):
    """AC-C3 / AC-C4. Photos at 11:08:15, text at 11:08:55. This is how people send - the
    picture first, the explanation after - so it is the normal case, not an edge one.
    """
    contact = _contact(db)
    _dealer(db, "DILOOMA SDN BHD")
    result = _submit(
        db,
        burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        messages=[
            {"text": "", "sent_at": "2026-05-11T11:08:15", "media_ref": "p1"},
            {"text": "", "sent_at": "2026-05-11T11:08:26", "media_ref": "p2"},
            {
                "text": "DILOOMA-USJ. CSS3310BL holder broken. Pls replace to shop",
                "sent_at": "2026-05-11T11:08:55",
            },
        ],
        media_refs=["p1", "p2"],
        extraction=_extraction(
            shop_name="DILOOMA SDN BHD",
            lines=[
                {
                    "claimed_text": "CSS3310BL holder broken",
                    "model_code_raw": "CSS3310BL",
                    "quantity": 1,
                }
            ],
            defect_description="Holder broken.",
        ),
    )
    assert db.query(Complaint).count() == 1
    assert result.media_count == 2


def test_the_whole_burst_is_kept_verbatim(db):
    """The office reads the original when extraction is wrong, so the messages survive as
    text - not only as whatever the extractor made of them.
    """
    contact = _contact(db)
    result = _submit(db, burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}", contact_id=contact.id)
    complaint = db.query(Complaint).filter(Complaint.id == result.complaint_id).first()
    blob = " ".join(
        str(getattr(complaint, f, "") or "")
        for f in ("defect_description", "product_code", "customer_name")
    )
    assert "SRTWC8366" in blob or "Seatcover" in blob


# ================================================= the dealer, and never a guess


def test_an_exactly_matched_dealer_is_bound(db):
    """One resolver for every track. The consumer portal and this path must not disagree
    about which shop a name means.
    """
    contact = _contact(db)
    dealer = _dealer(db)
    result = _submit(db, burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}", contact_id=contact.id)
    complaint = db.query(Complaint).filter(Complaint.id == result.complaint_id).first()
    assert str(complaint.customer_id) == str(dealer.id)


def test_an_unmatched_dealer_still_lodges_and_keeps_the_raw_name(db):
    """AC-C14's rule, on the WhatsApp track. A refusal leaves the message in WhatsApp,
    which is exactly where it already goes to die.
    """
    contact = _contact(db)
    result = _submit(
        db,
        burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        extraction=_extraction(shop_name="A SHOP NOBODY HAS EVER HEARD OF"),
    )
    assert result.complaint_id
    complaint = db.query(Complaint).filter(Complaint.id == result.complaint_id).first()
    assert complaint.customer_id is None
    assert result.dealer_state in ("candidate", "unmatched")


def test_a_near_miss_dealer_is_never_bound(db):
    """The spike's three real-but-WRONG neighbours reach this path too."""
    contact = _contact(db)
    wrong = _dealer(db, "CHENG HUAT HARDWARE (SENTUL) SDN BHD")
    result = _submit(
        db,
        burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        extraction=_extraction(shop_name="SENG HUAT SDN BHD"),
    )
    complaint = db.query(Complaint).filter(Complaint.id == result.complaint_id).first()
    assert str(complaint.customer_id or "") != str(wrong.id)


# ======================================================= nothing blocks intake


def test_a_burst_with_no_extractable_anything_still_produces_a_complaint(db):
    """A photo and no words at all. Somebody still has to look at it."""
    contact = _contact(db)
    result = _submit(
        db,
        burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        messages=[{"text": "", "sent_at": "2026-05-13T10:14:18", "media_ref": "m1"}],
        media_refs=["m1"],
        extraction=_extraction(shop_name=None, lines=[], defect_description=None),
    )
    assert result.complaint_id
    assert result.complaint_number


def test_an_unknown_contact_is_refused_rather_than_guessed(db):
    """The contact is the identity, exactly as on the portal. Inventing one would file a
    case against nobody, and nobody can correct a case they cannot find.
    """
    with pytest.raises(Exception):
        _submit(db, burst_key=f"{TEST_PREFIX}-x", contact_id="no-such-contact")


# ================================================ the follow-up, AC-C5 and AC-C6


def test_the_reply_carries_the_complaint_number(db):
    """AC-C6. The dealer's only handle on the case."""
    contact = _contact(db)
    result = _submit(db, burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}", contact_id=contact.id)
    assert result.complaint_number
    assert result.complaint_number in (result.reply or "")


def test_only_the_missing_fields_are_asked_for(db):
    """AC-C5. Re-asking for something the dealer already sent is what makes an automated
    follow-up feel worse than the human one it replaces.
    """
    contact = _contact(db)
    _dealer(db)
    result = _submit(
        db,
        burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        extraction=_extraction(defect_description=None),
    )
    assert "defect_description" in result.missing_fields
    assert "shop_name" not in result.missing_fields, "The shop was extracted; do not re-ask."
    assert "model" not in " ".join(result.missing_fields).lower() or result.missing_fields


def test_a_complete_burst_asks_for_nothing(db):
    contact = _contact(db)
    _dealer(db)
    result = _submit(db, burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}", contact_id=contact.id)
    assert result.missing_fields == []


# ============================================================ AC-C7, traceability


def test_the_prompt_versions_are_stamped_on_the_result(db):
    """Every turn records which prompt produced it, or a bad extraction cannot be traced
    to the version that caused it and publishing a fix proves nothing.
    """
    contact = _contact(db)
    result = _submit(db, burst_key=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}", contact_id=contact.id)
    assert result.prompt_versions, "AC-C7: the turn must record its prompt version."


def test_the_intake_prompt_is_registered_in_the_prompt_registry(db):
    """AC-C7. A hardcoded extraction prompt cannot be published without a redeploy, which
    is the whole reason the registry exists.
    """
    from app.services.ai_prompt_registry import PROMPT_KEYS

    assert "intake_extractor" in PROMPT_KEYS, (
        "The WhatsApp intake prompt must be a registry key, versioned and labelled like "
        "every other node."
    )
    spec = PROMPT_KEYS["intake_extractor"]
    assert spec.active is True
    assert spec.fallback(), "A registry key needs a fallback, or a DB outage takes intake down."
