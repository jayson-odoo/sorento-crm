"""Writing to the consumer ledger (Group L).

One module owns every write, for the same reason `warranty_service` owns every
verdict: three intake paths are already known - the portal, staff typing into a
complaint, and an n8n message pump - and the moment two of them normalise a phone
or build a dedupe key their own way the ledger holds one person twice and nobody
can tell which row is real.

The rulings encoded here, each one a place the obvious version is wrong:

1. **Normalise the phone BEFORE looking anything up.** Normalising correctly and
   then querying on the raw string is a real and invisible way to fail AC-L8, and
   it produces the same split the E.164 column exists to prevent.

2. **Junk normalises to NOTHING, never to `+60`.** A normaliser that strips
   non-digits and prefixes the country code turns "not a phone" into `+60`, and
   every unparseable intake then dedupes onto ONE shared profile holding a dozen
   strangers' purchases. That failure is silent and permanent.

3. **A conflicting name is queued, never resolved.** A household shares a handset,
   so `Miss Ong daughter` arriving on a phone holding `Ong Mei Ling` is genuinely
   ambiguous. Auto-picking either direction rewrites somebody's purchase history
   into a fiction that reads as fact.

4. **Link, never reject** (AC-L19). The packing-list precedent rejected on a triple
   match, which was right for a staff import; the submitter here is a consumer with
   a broken toilet, and refusing their complaint because we think we have seen
   their receipt is not a thing this system may do. A collision returns the EXISTING
   purchase, never nothing and never an error.

5. **An incomplete key still writes, flagged** (AC-L20). The dealer is routinely
   unresolved and OCR routinely finds no document number, and neither may block
   intake (AC-C14). The consequence is accepted rather than hidden: two receipts
   from one dealer on one day where only one is numbered are NOT duplicates under
   the partial index and both write, so near-duplicates exist by design and
   `dedupe_pending` is the only thing pointing at them.

6. **Value is captured as printed and nothing more** (fork 4). No tax handling, no
   discount allocation, no per-unit derivation: normalising a photographed
   third-party receipt produces false precision that will be wrong in a way nobody
   can explain, and a number we invented is indistinguishable on screen from one we
   read. `line_value` therefore stays NULL in the normal case.

7. **Value is OMITTED, not nulled, for a reader without the permission** (AC-L24).
   `None` reads as "the receipt showed no total", which is a different fact and a
   wrong one - it tells a CS agent the dealer sold it for nothing.

8. **Erasure severs reachability, not just the name** (fork 6). Clearing the name
   while leaving `respond_contact_id` in place means one join recovers the person,
   and leaving `phone_e164` means the next intake silently re-identifies the row
   that was erased. The purchase survives, because a lifetime ceramic claim years
   later needs the date of sale.
   **Stated gap:** `respond_contacts` itself is NOT scrubbed. That row is shared
   with complaints, chat history, SLA and the portal, so removing it is a much
   larger decision than this module owns, and residual reachability through those
   modules is real.

9. **No implicit back-link.** A purchase written with no identity does not acquire
   one when a profile later appears on the same phone: a shared household number
   makes that a stranger's receipt on somebody's record, attached silently, years
   later, at the moment they authenticate. Attaching an orphan purchase is a
   deliberate act by CS - recorded here as a gap, because nothing in Group L asks
   for the surface that would do it.

This module holds no send path of any kind and must not grow one. Under fork 6's
service-only consent these profiles are an analytics asset, not a contact list, and
a provisional profile is a phone a staff member typed that has consented to nothing.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.consumers import (
    ConsumerProfile,
    ConsumerProfileReview,
    ConsumerPurchase,
    ConsumerPurchaseLine,
)
from app.models.resources import Attachment
from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Vocabulary                                                                    #
# --------------------------------------------------------------------------- #

# Fork 6, as a closed set rather than a free-text column. A lawful-basis field with
# no lawful basis is worse than no field, and a second value appearing quietly in
# one intake path is how the service-only door gets propped open. Adding marketing
# needs fresh consent from each person, not a new member here.
CONSENT_PURPOSE_WARRANTY_SERVICE = "warranty_service"
CONSENT_PURPOSES = frozenset({CONSENT_PURPOSE_WARRANTY_SERVICE})

# PDPA 2010 s.7(2): the collection notice must exist in Bahasa Malaysia AND English,
# and `consent_notice_version` records WHICH wording a person saw. The wording now
# lives in `consent_notices` (migration 322) rather than in a constant here - a
# literal recorded a version of nothing, which made the one question a consent record
# exists to answer unanswerable.
#
# A profile created by a STAFF-SIDE path is stamped with NOTHING, because nobody was
# shown anything. Claiming otherwise would assert that a person read a notice that was
# never on their screen, which is the specific lie this column exists to prevent. The
# portal stamps it through `record_consent` at the moment it displays the notice.

# Where a registration came from. `auto_on_complaint` is the AC-D8 path and is the
# reason this vocabulary exists at all: only a DELIBERATE act by the consumer earns
# clause 26's bonus months, and the earning set lives beside the assessor in
# app/services/warranty_assessment_service.py.
REGISTRATION_SOURCE_SELF = "self"
REGISTRATION_SOURCE_AUTO_ON_COMPLAINT = "auto_on_complaint"
REGISTRATION_SOURCES = ("self", "auto_on_complaint", "smc", "ecommerce")

# AC-D12. Where the purchase date came from - a fact about the receipt.
PURCHASE_DATE_SOURCE_STATED = "stated"
PURCHASE_DATE_SOURCE_OCR = "ocr"
PURCHASE_DATE_SOURCES = ("stated", "ocr")

# Country calling codes for the regions this system actually sees. A region with no
# entry means "only an already-plus-prefixed number is understood", which is honest:
# guessing a country for a bare national number is how a Singapore mobile becomes a
# Malaysian one.
_REGION_CALLING_CODES = {"MY": "60", "SG": "65"}

# E.164 allows at most 15 digits; the shortest plausible international number here
# is well above 7. Both bounds exist so junk cannot become a phone.
_E164_MIN_DIGITS = 8
_E164_MAX_DIGITS = 15

_NON_DIGITS = re.compile(r"\D")
_NON_ALNUM = re.compile(r"[^0-9A-Z]")


# --------------------------------------------------------------------------- #
# Normalisation                                                                 #
# --------------------------------------------------------------------------- #


def normalize_phone_e164(raw: Optional[str], *, default_region: str = "MY") -> Optional[str]:
    """`raw` as E.164, or None when it is not a phone number at all.

    The existing ``app/utils/phone_normalize.py`` is digits-only and cannot satisfy
    AC-L8: it produces a bare digit string, so `0166372304` and `+60166372304` still
    do not meet. This returns the canonical `+60166372304` for every spelling of one
    Malaysian mobile, leaves an already-international number alone (a Singapore
    number is never rewritten to `+60`), and returns None for junk.

    Returning None rather than a best guess is the whole point. A guess becomes a
    profile, and a shared junk profile accumulates strangers' purchases.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    had_plus = text.startswith("+") or text.startswith("00")
    digits = _NON_DIGITS.sub("", text)
    if not digits:
        return None

    if text.startswith("00"):
        digits = digits[2:]

    if had_plus:
        candidate = digits
    else:
        calling_code = _REGION_CALLING_CODES.get((default_region or "").upper())
        if digits.startswith("0"):
            # The national form staff actually type. The trunk zero is not part of
            # the international number.
            national = digits.lstrip("0")
            if not national or not calling_code:
                return None
            candidate = f"{calling_code}{national}"
        elif calling_code and digits.startswith(calling_code):
            candidate = digits
        elif calling_code:
            candidate = f"{calling_code}{digits}"
        else:
            candidate = digits

    if not (_E164_MIN_DIGITS <= len(candidate) <= _E164_MAX_DIGITS):
        return None
    return f"+{candidate}"


def normalize_document_number(raw: Optional[str]) -> Optional[str]:
    """A dealer's document number, reduced to what is stable about it.

    Case, whitespace and separators are exactly what varies between an OCR read, a
    staff retype and the dealer's own printing, and none of them mean a different
    document. Nothing else is stripped: leading zeros and year segments genuinely
    distinguish documents, so `INV-0001` stays different from `INV-001`.

    The risk this creates is real and accepted rather than hidden: under "link,
    never reject" a FALSE collision refuses nothing - it attaches the second
    complaint to the FIRST purchase, and therefore to the first purchase's DATE. An
    over-eager normaliser mis-dates a warranty rather than annoying somebody, which
    is why the rule stops here.

    An absent number is None, NEVER `""`: an empty string would collide every
    unnumbered receipt from one dealer on one day into a single row.
    """
    if raw is None:
        return None
    cleaned = _NON_ALNUM.sub("", str(raw).strip().upper())
    return cleaned or None


def _utcnow() -> datetime:
    """Naive UTC, matching every other timestamp column in this schema."""
    return datetime.utcnow()


def _as_decimal(value: Any) -> Optional[Decimal]:
    """A printed total, kept exactly as printed.

    `Decimal(str(...))` rather than `float(...)`: a receipt total that arrives as a
    string must not acquire binary-float noise on the way to a NUMERIC column.
    """
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise handle_validation_error(f"{value!r} is not a value that can be recorded.")


# --------------------------------------------------------------------------- #
# Profiles (AC-L4 to AC-L10)                                                    #
# --------------------------------------------------------------------------- #


def _surviving(profile: ConsumerProfile, db: Session) -> ConsumerProfile:
    """Follow a merge chain to the profile that is still current (AC-L10).

    Bounded: a cycle is impossible through the service but a hand-edited row could
    build one, and a `while` with no ceiling would hang the intake rather than
    answer it.
    """
    seen = {profile.id}
    current = profile
    for _ in range(10):
        if current.merged_into_id is None:
            return current
        if current.merged_into_id in seen:
            logger.warning("consumer profile merge chain loops at %s", current.id)
            return current
        nxt = (
            db.query(ConsumerProfile)
            .filter(ConsumerProfile.id == current.merged_into_id)
            .first()
        )
        if nxt is None:
            return current
        seen.add(nxt.id)
        current = nxt
    return current


def ensure_profile(
    db: Session,
    *,
    phone: str,
    full_name: Optional[str] = None,
    respond_contact_id: Optional[str] = None,
    provisional: bool = True,
) -> ConsumerProfile:
    """The profile for this phone, created provisionally if it is new (AC-L5, AC-L8).

    Resolution is on the NORMALISED phone, never on whatever the contact row happens
    to spell. A name that conflicts with the one already held goes to the review
    queue and is not applied (AC-L9); a name arriving where none was held is simply
    filled in, which is not a conflict.

    Raises rather than inventing a profile when the phone cannot be normalised: the
    caller's purchase can still be written with no profile at all (fork 2), which is
    the honest outcome. Silently creating a junk-phone profile would pool strangers.
    """
    e164 = normalize_phone_e164(phone)
    if not e164:
        raise handle_validation_error(
            "A consumer profile needs a phone number that can be normalised to E.164."
        )

    incoming_name = (full_name or "").strip() or None
    existing = (
        db.query(ConsumerProfile).filter(ConsumerProfile.phone_e164 == e164).first()
    )
    if existing is not None:
        profile = _surviving(existing, db)
        if incoming_name:
            held = (profile.full_name or "").strip()
            if not held:
                profile.full_name = incoming_name
            elif held.casefold() != incoming_name.casefold():
                _queue_name_conflict(db, profile, incoming_name=incoming_name, phone_e164=e164)
        if respond_contact_id and not profile.respond_contact_id:
            profile.respond_contact_id = respond_contact_id
        db.flush()
        return profile

    profile = ConsumerProfile(
        id=str(uuid.uuid4()),
        respond_contact_id=respond_contact_id,
        phone_e164=e164,
        full_name=incoming_name,
        consent_purpose=CONSENT_PURPOSE_WARRANTY_SERVICE,
        # Deliberately unstamped: see the note beside CONSENT_PURPOSES. This path runs
        # from staff and n8n contact, where no notice is ever displayed.
        consent_notice_version=None,
        consent_recorded_at=None,
        is_provisional=bool(provisional),
        confirmed_at=None if provisional else _utcnow(),
    )
    db.add(profile)
    db.flush()
    return profile


def _queue_name_conflict(
    db: Session,
    profile: ConsumerProfile,
    *,
    incoming_name: str,
    phone_e164: Optional[str],
) -> Optional[ConsumerProfileReview]:
    """Record a name conflict once, for a human to decide (AC-L9).

    De-duplicated on the unresolved incoming name: the same intake repeating does
    not deepen the queue, and a review list that grows a row per message is a review
    list nobody opens.
    """
    already = (
        db.query(ConsumerProfileReview)
        .filter(ConsumerProfileReview.profile_id == profile.id)
        .filter(ConsumerProfileReview.resolved_at.is_(None))
        .filter(func.lower(ConsumerProfileReview.incoming_name) == incoming_name.casefold())
        .first()
    )
    if already is not None:
        return already
    review = ConsumerProfileReview(
        id=str(uuid.uuid4()),
        profile_id=profile.id,
        incoming_name=incoming_name,
        incoming_phone_e164=phone_e164,
        existing_name=profile.full_name,
        reason=(
            "A different name arrived on a phone that already holds one. One handset "
            "is often one household, so this is a human decision either way."
        ),
    )
    db.add(review)
    db.flush()
    return review


def promote_profile_on_otp(
    db: Session,
    *,
    respond_contact_id: Optional[str] = None,
    phone: Optional[str] = None,
) -> Optional[ConsumerProfile]:
    """Promote a provisional profile the first time its phone authenticates (AC-L6).

    Deterministic, with no human judgement: completing an OTP login IS the proof.
    Called from the only code that completes one; a promotion nothing calls leaves
    `is_provisional` true forever and quietly degrades AC-L7's headline count to
    "everyone is provisional".

    Returns None when there is nothing to promote, and never raises for that -
    most contacts have no consumer profile at all.
    """
    profile = None
    if respond_contact_id:
        profile = (
            db.query(ConsumerProfile)
            .filter(ConsumerProfile.respond_contact_id == respond_contact_id)
            .first()
        )
    if profile is None:
        e164 = normalize_phone_e164(phone)
        if e164:
            profile = (
                db.query(ConsumerProfile)
                .filter(ConsumerProfile.phone_e164 == e164)
                .first()
            )
    if profile is None:
        return None

    profile = _surviving(profile, db)
    if profile.anonymised_at is not None:
        # An erased person must not be re-identified by logging in.
        return None
    if profile.is_provisional:
        profile.is_provisional = False
        profile.confirmed_at = _utcnow()
        if respond_contact_id and not profile.respond_contact_id:
            profile.respond_contact_id = respond_contact_id
        db.flush()
    return profile


def count_consumers(
    db: Session,
    *,
    include_provisional: bool = False,
    profile_ids: Optional[Sequence[str]] = None,
) -> int:
    """How many consumers we actually have (AC-L7).

    Provisional profiles are excluded by default - staff typing a phone must not
    inflate the number - and merged-away profiles always are, or retaining the
    losing row (AC-L10) would count one person twice.

    `profile_ids` exists so a caller can scope the question. The local database is a
    copy of production, so an unscoped count is both meaningless and slow in tests.
    """
    query = db.query(func.count(ConsumerProfile.id)).filter(
        ConsumerProfile.merged_into_id.is_(None)
    )
    if not include_provisional:
        query = query.filter(ConsumerProfile.is_provisional.is_(False))
    if profile_ids is not None:
        query = query.filter(ConsumerProfile.id.in_(list(profile_ids)))
    return int(query.scalar() or 0)


def merge_profiles(
    db: Session,
    *,
    surviving_id: str,
    losing_id: str,
    actor_user_id: Optional[str] = None,
) -> ConsumerProfile:
    """Two rows, one person (AC-L10). Purchases follow the survivor.

    The losing row is RETAINED with `merged_into_id` set rather than deleted. Split
    is out of scope, so there is no second chance - and "where did this consumer go"
    is the question somebody asks the day after a merge went wrong, which a deleted
    row cannot answer.
    """
    if surviving_id == losing_id:
        raise handle_validation_error("A profile cannot be merged into itself.")
    surviving = (
        db.query(ConsumerProfile).filter(ConsumerProfile.id == surviving_id).first()
    )
    if surviving is None:
        raise handle_not_found("Consumer profile", surviving_id)
    losing = db.query(ConsumerProfile).filter(ConsumerProfile.id == losing_id).first()
    if losing is None:
        raise handle_not_found("Consumer profile", losing_id)

    # Moved row by row rather than by a bulk UPDATE: the ORM path is company-scoped
    # and audited, and a bulk update is neither.
    for purchase in (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.consumer_profile_id == losing.id)
        .all()
    ):
        purchase.consumer_profile_id = surviving.id

    losing.merged_into_id = surviving.id
    losing.merged_at = _utcnow()
    losing.merged_by = actor_user_id
    db.flush()
    return surviving


def anonymise_profile(
    db: Session, profile_id: str, *, actor_user_id: Optional[str] = None
) -> ConsumerProfile:
    """Erase the person, keep the purchase (fork 6).

    Every identifying field goes, INCLUDING `respond_contact_id` and `phone_e164`.
    Leaving the contact link means one join recovers the name and the number, so the
    erasure would be cosmetic; leaving the phone means the next intake dedupes onto
    this row and quietly re-identifies it.

    The purchases stay, with their dates: a lifetime ceramic warranty may be claimed
    years later and the claim is decided from the date of sale.

    **Not done here, and it matters:** the `respond_contacts` row itself is not
    scrubbed. It is shared with complaints, chat history, SLA tracking and the
    portal, and deleting it is a far larger decision than this module owns.
    """
    profile = db.query(ConsumerProfile).filter(ConsumerProfile.id == profile_id).first()
    if profile is None:
        raise handle_not_found("Consumer profile", profile_id)

    profile.full_name = None
    profile.email = None
    profile.addresses = None
    profile.phone_e164 = None
    profile.respond_contact_id = None
    profile.anonymised_at = _utcnow()
    profile.anonymised_by = actor_user_id
    db.flush()
    return profile


# --------------------------------------------------------------------------- #
# Purchases (AC-L11 to AC-L22)                                                  #
# --------------------------------------------------------------------------- #


def _next_purchase_number(db: Session, purchase_date: date) -> str:
    """`CP{year}-NNNN`, where the year is the PURCHASE's.

    A 2015 receipt entered in 2026 must not be numbered CP2026: it would read as a
    2026 sale on every report that groups by the number.

    The scan runs across ALL companies on purpose. `consumer_purchases` is
    company-scoped, so a scoped max would let two companies mint the same number and
    collide on the global unique constraint - which is the constraint that makes the
    number quotable in the first place.
    """
    prefix = f"CP{purchase_date.year}-"
    with company_scope(db, None):
        highest = (
            db.query(func.max(ConsumerPurchase.purchase_number))
            .filter(ConsumerPurchase.purchase_number.like(f"{prefix}%"))
            .scalar()
        )
    sequence = 1
    if highest:
        tail = str(highest)[len(prefix) :]
        if tail.isdigit():
            sequence = int(tail) + 1
    return f"{prefix}{sequence:04d}"


def _kind_code_for(db: Session, kind_id: str) -> str:
    """The stable code of the Kind this line was written against (AC-L36).

    Read at write time and stored, so the line keeps its meaning after the warranty
    module is uninstalled and `kind_id` goes NULL. S2's seed upserts Kinds on this
    same code, so a reinstall re-links the ledger rather than losing it.

    Imported inside the function on purpose. The ledger's TABLE foreign-keys the
    Kind vocabulary, but the MODULE graph runs the other way (fork 7): `consumers`
    declares no dependency on `warranty` and must still import cleanly when the
    engine is not installed. A call-time read fails loudly for one write; an
    import-time dependency would fail the whole module.
    """
    from app.models.warranty import WarrantyProductKind

    code = (
        db.query(WarrantyProductKind.code)
        .filter(WarrantyProductKind.id == kind_id)
        .scalar()
    )
    if not code:
        raise handle_validation_error(
            "That product kind does not exist, so the purchase line would carry no "
            "record of what was bought."
        )
    return code


def _apply_lines(
    db: Session, purchase: ConsumerPurchase, lines: Iterable[Dict[str, Any]]
) -> List[ConsumerPurchaseLine]:
    """Add the products on this receipt, skipping ones the header already holds.

    A second complaint citing a receipt we already have (AC-L18) usually repeats the
    same products, and appending them again would double the ledger's view of what
    was bought. A genuinely new product on a known receipt still lands.

    `line_value` is never derived here (fork 4) - only ever taken if a caller
    actually read one off the document.
    """
    existing = (
        db.query(ConsumerPurchaseLine)
        .filter(ConsumerPurchaseLine.purchase_id == purchase.id)
        .all()
    )
    seen = {
        (row.kind_code, (row.claimed_text or "").strip().casefold()) for row in existing
    }
    written: List[ConsumerPurchaseLine] = []
    order = len(existing)
    for raw in lines or ():
        kind_id = raw.get("kind_id")
        kind_code = (raw.get("kind_code") or "").strip() or None
        if not kind_id and not kind_code:
            raise handle_validation_error(
                "Every purchase line needs a product kind: cover is resolved from it, "
                "and a line without one can never be assessed."
            )
        if kind_code is None:
            kind_code = _kind_code_for(db, kind_id)
        claimed = raw.get("claimed_text")
        # Keyed on the CODE, not the id: the code is the part that survives, so two
        # citations of one receipt still recognise each other after a purge.
        key = (kind_code, (claimed or "").strip().casefold())
        if key in seen:
            continue
        seen.add(key)
        line = ConsumerPurchaseLine(
            id=str(uuid.uuid4()),
            purchase_id=purchase.id,
            product_id=raw.get("product_id"),
            kind_id=kind_id,
            kind_code=kind_code,
            claimed_text=claimed,
            quantity=raw.get("quantity"),
            line_value=_as_decimal(raw.get("line_value")),
            sort_order=order,
        )
        order += 1
        db.add(line)
        written.append(line)
    db.flush()
    return written


def record_purchase(
    db: Session,
    *,
    purchase_date: date,
    customer_id: Optional[str] = None,
    dealer_document_number: Optional[str] = None,
    consumer_profile_id: Optional[str] = None,
    total_value: Any = None,
    currency: Optional[str] = None,
    proof_attachment_id: Optional[str] = None,
    registration_source: Optional[str] = None,
    purchase_date_source: str = PURCHASE_DATE_SOURCE_STATED,
    lines: Iterable[Dict[str, Any]] = (),
) -> ConsumerPurchase:
    """Write one purchase event, or return the one already held (AC-L17 to AC-L20).

    NEVER raises on a duplicate and never returns None. When all three parts of the
    dedupe key are present and they match an existing header, the products are
    merged into THAT header and it is returned - a second complaint months later
    citing a receipt already in the ledger links, it does not double-count.

    An incomplete key writes anyway and is flagged `dedupe_pending` for the CS review
    list. That is what makes two same-day receipts from one dealer - one numbered,
    one not - both survive: they are not duplicates under the partial index, and
    swallowing the second would run the second product's cover from the wrong header.
    """
    if purchase_date is None:
        raise handle_validation_error(
            "A purchase needs its date: it is the only thing cover is computed from."
        )
    if registration_source is not None and registration_source not in REGISTRATION_SOURCES:
        raise handle_validation_error(
            f"{registration_source!r} is not a registration source. "
            f"Expected one of {', '.join(REGISTRATION_SOURCES)}."
        )
    if purchase_date_source not in PURCHASE_DATE_SOURCES:
        raise handle_validation_error(
            f"{purchase_date_source!r} is not a purchase-date source. "
            f"Expected one of {', '.join(PURCHASE_DATE_SOURCES)}."
        )

    document_norm = normalize_document_number(dealer_document_number)
    key_is_complete = bool(customer_id and document_norm)

    if key_is_complete:
        existing = (
            db.query(ConsumerPurchase)
            .filter(ConsumerPurchase.customer_id == customer_id)
            .filter(ConsumerPurchase.dealer_document_number_norm == document_norm)
            .filter(ConsumerPurchase.purchase_date == purchase_date)
            .first()
        )
        if existing is not None:
            _apply_lines(db, existing, lines)
            # The receipt image and the consumer are filled in if this citation
            # carried them and the held row did not. Nothing already recorded is
            # overwritten: the first reading is not automatically the worse one.
            if proof_attachment_id and not existing.proof_attachment_id:
                existing.proof_attachment_id = proof_attachment_id
            if consumer_profile_id and not existing.consumer_profile_id:
                existing.consumer_profile_id = consumer_profile_id
            db.flush()
            return existing

    purchase = ConsumerPurchase(
        id=str(uuid.uuid4()),
        purchase_number=_next_purchase_number(db, purchase_date),
        consumer_profile_id=consumer_profile_id,
        customer_id=customer_id,
        dealer_document_number=dealer_document_number,
        dealer_document_number_norm=document_norm,
        purchase_date=purchase_date,
        purchase_date_source=purchase_date_source,
        total_value=_as_decimal(total_value),
        currency=currency,
        proof_attachment_id=proof_attachment_id,
        registration_source=registration_source,
        # A registration recorded at the moment it happens. Whether it EARNS
        # anything is a separate question, answered by the assessor.
        registered_at=_utcnow() if registration_source else None,
        dedupe_pending=not key_is_complete,
    )
    db.add(purchase)
    db.flush()
    _apply_lines(db, purchase, lines)
    return purchase


def list_dedupe_pending(
    db: Session, *, purchase_ids: Optional[Sequence[str]] = None
) -> List[ConsumerPurchase]:
    """The CS review list (AC-L20). A flag nobody reads is not a review process."""
    query = db.query(ConsumerPurchase).filter(ConsumerPurchase.dedupe_pending.is_(True))
    if purchase_ids is not None:
        query = query.filter(ConsumerPurchase.id.in_(list(purchase_ids)))
    return query.order_by(ConsumerPurchase.created_at.desc()).all()


def find_purchases_by_file_hash(db: Session, file_hash: str) -> List[ConsumerPurchase]:
    """Purchases whose proof is byte-identical (AC-L21).

    Free, and independent of the dedupe key - which is what makes it worth having.
    It catches the one case the key structurally cannot: the same photograph
    uploaded twice with the document number misread differently each time.
    """
    if not file_hash:
        return []
    return (
        db.query(ConsumerPurchase)
        .join(Attachment, Attachment.id == ConsumerPurchase.proof_attachment_id)
        .filter(Attachment.file_hash == file_hash)
        .all()
    )


def purchases_for_profile(db: Session, profile_id: str) -> List[ConsumerPurchase]:
    """What this consumer owns, and which dealers sold it to them (AC-L28)."""
    return (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.consumer_profile_id == profile_id)
        .order_by(ConsumerPurchase.purchase_date.desc())
        .all()
    )


def purchases_for_dealer(db: Session, customer_id: str) -> List[ConsumerPurchase]:
    """Which consumers this dealer sold to (AC-L28).

    The sell-through the dealer channel currently hides. A different question from
    the one above, with a different owner: the first is a CS agent on a live call,
    this one is commercial.
    """
    return (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.customer_id == customer_id)
        .order_by(ConsumerPurchase.purchase_date.desc())
        .all()
    )


def value_coverage(db: Session, *, customer_id: Optional[str] = None) -> Dict[str, int]:
    """`value known on N of M purchases` (AC-L25).

    Reported alongside any total, so a figure built from half the receipts is never
    read as complete.
    """
    query = db.query(
        func.count(ConsumerPurchase.id),
        func.count(ConsumerPurchase.total_value),
    )
    if customer_id is not None:
        query = query.filter(ConsumerPurchase.customer_id == customer_id)
    total, known = query.one()
    return {"total": int(total or 0), "known": int(known or 0)}


def serialize_purchase(purchase: ConsumerPurchase, *, can_view_value: bool) -> Dict[str, Any]:
    """A purchase as the API renders it, with value OMITTED when not permitted.

    Omitted, not nulled (AC-L24). `None` means "the receipt showed no total", which
    is a different fact from "you may not see it" - and serialising the first when
    you mean the second tells a CS agent the dealer sold it for nothing. The
    currency goes with it: on its own it leaks nothing useful while still implying a
    value is held.

    Everything else stays visible. Hiding the whole purchase would take the DATE
    away from the CS agent who needs it, which is the only field the verdict depends
    on.
    """
    payload: Dict[str, Any] = {
        "id": purchase.id,
        "purchase_number": purchase.purchase_number,
        "purchase_date": purchase.purchase_date.isoformat() if purchase.purchase_date else None,
        "purchase_date_source": purchase.purchase_date_source,
        "dealer_document_number": purchase.dealer_document_number,
        "customer_id": purchase.customer_id,
        "consumer_profile_id": purchase.consumer_profile_id,
        "proof_attachment_id": purchase.proof_attachment_id,
        "registered_at": purchase.registered_at.isoformat() if purchase.registered_at else None,
        "registration_source": purchase.registration_source,
        "dedupe_pending": bool(purchase.dedupe_pending),
    }
    if can_view_value:
        payload["total_value"] = purchase.total_value
        payload["currency"] = purchase.currency
    return payload


def record_consent(db, profile, *, notice_key: str = "consumer_intake"):
    """Stamp the notice a person was actually shown onto their profile.

    Called by the portal at the moment of submission, never by a staff-side path: the
    stamp asserts "this human read these words", and the only place that is true is a
    screen that rendered them.

    Raises when no notice is published, because collecting personal data with nothing
    lawful on screen is the failure PDPA s.7 describes, and failing closed here is
    cheaper than discovering it in an audit.
    """
    from app.services.consent_notice_service import current_notice, stamp_for
    from app.services.error_handler import AppException

    notice = current_notice(db, notice_key)
    if notice is None:
        raise AppException(
            status_code=409,
            message=(
                "No published consent notice exists, so personal data must not be "
                "collected. Publish the collection notice first."
            ),
            code="consent_notice_missing",
        )
    profile.consent_purpose = CONSENT_PURPOSE_WARRANTY_SERVICE
    profile.consent_notice_version = stamp_for(notice)
    profile.consent_recorded_at = _utcnow()
    db.flush()
    return profile
