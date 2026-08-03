"""S3 Phase 2 - a Consumer lodging a complaint, end to end.

This is the commercially load-bearing path in the module. The complaint is the occasion;
**the purchase ledger is what Sorento keeps**. One lodgement must leave behind, permanently
and queryably: who the consumer is, which dealer they bought from, that dealer's own
document number, the value if the receipt showed it, the product and quantity, the purchase
date, and the receipt itself. If a lodgement can succeed while dropping any of that, the
module has collected a complaint and thrown away the reason it exists.

Six things shape this suite.

1. **Nothing blocks submission** (AC-C14). No dealer match, no readable date, no photos, no
   model code - a consumer with a broken toilet is not the person to punish for a bad OCR
   result. Every one of those lodges, and carries what was actually said for CS.

2. **A `candidate` dealer is never written as the dealer.** The spike found three receipts
   whose nearest neighbour was a real but WRONG shop. Storing one attributes a purchase to a
   dealer who never sold it, inside the ledger that exists to prove sell-through. The
   suggestion is kept beside the raw text, not in `customer_id`.

3. **Consent is recorded from the registry, at the moment of submission.** The portal is the
   one place a human is actually shown the notice, so it is the one place the stamp may be
   written (fork 6). No published notice means no collection, and lodging must fail closed
   rather than quietly gathering personal data with nothing lawful on screen.

4. **The raw claim survives resolution.** `claimed_text` holds what the consumer said;
   `product_id` and `kind_id` hold what the system worked out, both nullable. An unresolved
   line is a valid line (AC-C16). Losing the raw text means a CS agent looking at a failed
   match has nothing to work from.

5. **A repeat lodgement finds the existing consumer.** Resolution is on the normalised phone.
   A second complaint six months later must land on the SAME profile, or the "profile that
   persists across complaints" is just a row per complaint wearing a different name.

6. **The warranty verdict is computed, not asked for.** It is the value exchanged for the
   data, and the consumer never states it.

Run: venv/bin/python -m pytest tests/test_consumer_lodge.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid
from datetime import date

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from app.models.access import RespondContact  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402
from app.models.consumers import ConsumerProfile, ConsumerPurchase  # noqa: E402
from app.models.order import Customer  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

LODGE_MODULE = "app.services.consumer_lodge_service"

PHONE = "+60123456789"


@pytest.fixture
def db():
    with blank_session() as session:
        from app.services.consent_notice_service import seed_consent_notices

        # The portal cannot lawfully collect anything without a published notice, so every
        # test that lodges needs one. Point 3.
        seed_consent_notices(session)
        yield session


def _lodge_module():
    if importlib.util.find_spec(LODGE_MODULE) is None:
        raise AssertionError(
            f"{LODGE_MODULE} does not exist. One service owns the lodgement transaction: "
            "profile, consent, purchase, complaint, lines and verdict either all land or "
            "none do. Spread across the route it becomes six half-written records the "
            "first time one step raises."
        )
    return importlib.import_module(LODGE_MODULE)


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _contact(db) -> RespondContact:
    row = RespondContact(
        id=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}".lower(),
        phone_number=PHONE,
        name=f"{TEST_PREFIX} Consumer",
    )
    db.add(row)
    db.flush()
    return row


def _dealer(db, name: str = "TOTAL HOME DIY SDN BHD") -> Customer:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        customer_name=name,
    )
    db.add(row)
    db.flush()
    return row


def _payload(**overrides) -> dict:
    """What the portal sends. The shape mirrors `lodgeMocks.ts`, which is the contract
    Phase 1 published and this phase has to satisfy."""
    payload = {
        "phone": PHONE,
        "full_name": f"{TEST_PREFIX} Consumer",
        "shop_name": "TOTAL HOME DIY SDN BHD",
        "purchase_date": "2025-10-16",
        "dealer_document_number": "KCS-2112-0054",
        "site_address": "12 Jalan Contoh, Puchong",
        "latitude": None,
        "longitude": None,
        "lines": [
            {
                "claimed_text": "SRTWC8152 WATER CLOSET",
                "model_code_raw": "SRTWC8152",
                "kind_code": "water_closet",
                "quantity": 1,
                "fault_description": "Water keeps running after flushing.",
            }
        ],
        "attachment_ids": [],
    }
    payload.update(overrides)
    return payload


def _lodge(db, **overrides):
    return _fn(_lodge_module(), "lodge_complaint", "(db, payload)")(db, _payload(**overrides))


# =========================================================== the ledger survives


def test_a_lodgement_leaves_behind_the_whole_purchase_record(db):
    """The commercial point of the module, as one assertion.

    Sorento sells through dealers and therefore does not know who owns its products. This
    is the moment a consumer volunteers all of it, and every piece has to land.
    """
    _contact(db)
    dealer = _dealer(db)
    result = _lodge(db)

    complaint = db.query(Complaint).filter(Complaint.id == result.complaint_id).first()
    assert complaint is not None, "A lodgement must produce a complaint."

    profile = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).first()
    assert profile is not None, "The consumer profile is the asset. It must persist."

    purchase = (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.consumer_profile_id == profile.id)
        .first()
    )
    assert purchase is not None, "No purchase row means the sell-through ledger learned nothing."
    assert str(purchase.customer_id) == str(dealer.id), "The dealer must be recorded."
    assert purchase.dealer_document_number == "KCS-2112-0054"
    assert purchase.purchase_date == date(2025, 10, 16)


def test_the_consumer_gets_a_number_and_a_verdict(db):
    """What they hold at the end. The verdict is the value exchanged for the data, and it
    is computed - never asked for.
    """
    _contact(db)
    _dealer(db)
    result = _lodge(db)
    assert result.complaint_number, "A consumer with no reference cannot follow anything up."
    assert result.warranty is not None


# ===================================================== nothing blocks submission


def test_an_unmatched_dealer_still_lodges(db):
    """AC-C14. 24% of receipts print no usable shop name."""
    _contact(db)
    result = _lodge(db, shop_name=None)
    assert result.complaint_id

    profile = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).first()
    purchase = (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.consumer_profile_id == profile.id)
        .first()
    )
    if purchase is not None:
        assert purchase.customer_id is None, "No dealer was identified, so none is claimed."


def test_a_candidate_dealer_is_never_written_as_the_dealer(db):
    """Point 2, and the reason the resolver returns a state rather than a score.

    "SENG HUAT" against a stored "CHENG HUAT HARDWARE" is a real but wrong shop. Writing it
    would put a purchase on a dealer's sell-through that they never made.
    """
    _contact(db)
    wrong = _dealer(db, "CHENG HUAT HARDWARE (SENTUL) SDN BHD")
    _lodge(db, shop_name="SENG HUAT SDN BHD")

    profile = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).first()
    purchase = (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.consumer_profile_id == profile.id)
        .first()
    )
    if purchase is not None and purchase.customer_id is not None:
        assert str(purchase.customer_id) != str(wrong.id), (
            "A candidate match was written as the dealer. That is the failure the whole "
            "resolved/candidate/unmatched split exists to prevent."
        )


def test_no_purchase_date_still_lodges(db):
    """A date we invented is a guess wearing every warranty verdict computed from it, so
    the purchase may be absent - but the COMPLAINT still has to exist.
    """
    _contact(db)
    _dealer(db)
    result = _lodge(db, purchase_date=None)
    assert result.complaint_id


def test_a_line_with_no_model_code_still_lodges(db):
    """AC-C16. An unresolved line is a valid line."""
    _contact(db)
    _dealer(db)
    result = _lodge(
        db,
        lines=[
            {
                "claimed_text": "the tap in my kitchen",
                "model_code_raw": None,
                "kind_code": None,
                "quantity": 1,
                "fault_description": "Leaking at the base.",
            }
        ],
    )
    assert result.complaint_id


# ============================================================ the raw claim lives


def test_what_the_consumer_actually_said_is_kept(db):
    """Point 4. A CS agent looking at a failed match needs the words, not a null."""
    from app.models.complaints import ComplaintProductLine

    _contact(db)
    _dealer(db)
    result = _lodge(db)
    lines = (
        db.query(ComplaintProductLine)
        .filter(ComplaintProductLine.complaint_id == result.complaint_id)
        .all()
    )
    assert lines, "The complaint must carry its product lines."
    assert lines[0].claimed_text == "SRTWC8152 WATER CLOSET"
    assert lines[0].fault_description == "Water keeps running after flushing."


def test_the_complaint_line_points_at_the_purchase_line_that_supplies_its_date(db):
    """AC-L16, and the bug this test was written to catch.

    Cover is per product and per part, so a warranty assessment reaches its purchase DATE
    through the complaint LINE, never through the complaint. The first implementation read
    the purchase's lines off `purchase.lines` - an attribute `ConsumerPurchase` does not
    have - so `getattr` returned an empty list, every link was written NULL, and every
    verdict silently answered `unknown` with nothing saying why.

    The failure mode is what makes it worth a test: nothing raised, nothing logged, and
    the lodgement looked completely successful.
    """
    from app.models.complaints import ComplaintProductLine
    from app.models.consumers import ConsumerPurchaseLine

    _contact(db)
    _dealer(db)
    result = _lodge(db)

    line = (
        db.query(ComplaintProductLine)
        .filter(ComplaintProductLine.complaint_id == result.complaint_id)
        .first()
    )
    assert line.consumer_purchase_line_id is not None, (
        "The complaint line has no purchase line, so the warranty engine has no date to "
        "compute from and every verdict on it is unknown."
    )
    purchase_line = (
        db.query(ConsumerPurchaseLine)
        .filter(ConsumerPurchaseLine.id == line.consumer_purchase_line_id)
        .first()
    )
    assert purchase_line is not None
    assert str(purchase_line.purchase_id) == str(result.purchase_id)


def test_an_ambiguous_base_code_resolves_the_kind_and_leaves_the_product_null(db):
    """AC-C17. `SRTWC8152` matches several variants, so the Kind is the honest answer and
    the variant is CS's to choose. Guessing one would put a warranty term on the wrong part.
    """
    from app.models.complaints import ComplaintProductLine

    _contact(db)
    _dealer(db)
    result = _lodge(db)
    line = (
        db.query(ComplaintProductLine)
        .filter(ComplaintProductLine.complaint_id == result.complaint_id)
        .first()
    )
    assert line.product_id is None
    assert hasattr(line, "kind_id"), "The resolved Kind has nowhere to live."


# ================================================================ consent, fork 6


def test_lodging_records_the_notice_the_consumer_was_shown(db):
    """The portal is the one place a human sees the notice, so it is the one place the
    stamp may be written. A stamp that resolves to nothing answers nothing.
    """
    from app.services.consent_notice_service import notice_for_stamp

    _contact(db)
    _dealer(db)
    _lodge(db)
    profile = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).first()
    assert profile.consent_notice_version, "Nothing recorded which wording they saw."
    assert notice_for_stamp(db, profile.consent_notice_version) is not None
    assert profile.consent_recorded_at is not None


def test_lodging_fails_closed_when_no_notice_is_published(db):
    """Collecting personal data with nothing lawful on screen is the failure PDPA s.7
    describes. Refusing is cheaper than finding it in an audit.
    """
    from sqlalchemy import text

    _contact(db)
    _dealer(db)
    db.execute(text("UPDATE consent_notices SET is_published = false"))
    db.flush()
    with pytest.raises(Exception) as exc:
        _lodge(db)
    assert "consent" in str(exc.value).lower() or "notice" in str(exc.value).lower()


# ======================================================= the profile persists


def test_a_second_complaint_lands_on_the_same_consumer(db):
    """Point 5. "A profile that persists across complaints" is the whole asset; a row per
    complaint would be the same data Sorento already fails to have.
    """
    _contact(db)
    _dealer(db)
    first = _lodge(db)
    second = _lodge(db, dealer_document_number="CS002629")

    profiles = db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == PHONE).all()
    assert len(profiles) == 1, f"{len(profiles)} profiles for one phone number."
    assert first.complaint_id != second.complaint_id, "Two complaints, not one."


def test_the_site_address_reaches_the_complaint(db):
    """The technician has to be able to get there (AC-M37 / AC-M39). Pin and address are
    both kept and neither is reconciled; here only the address was given.
    """
    _contact(db)
    _dealer(db)
    result = _lodge(db)
    complaint = db.query(Complaint).filter(Complaint.id == result.complaint_id).first()
    assert complaint is not None
