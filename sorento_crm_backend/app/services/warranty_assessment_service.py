"""Writing the engine's answer down against a real complaint (AC-D8, AC-D10 to D12).

`warranty_service` computes cover from plain values and touches no purchase row.
This module is the moment that answer becomes an artifact CS reads and acts on,
which is where every dangerous decision in the slice lives. One module owns it for
the same reason one module owns the engine: the CS verdict panel, the consumer
portal and the auto-assessment on intake are three callers, and two of them writing
their own row is two answers to one question.

Four rulings, each a place composing the obvious pieces produces a wrong system.

1. **One row per (complaint product line, TERM)** (AC-L30). A Water Closet resolves
   to three terms at once and they disagree on the expiry, the defect scope and who
   pays for the callout. A single row per line holds one of the three, so CS reads
   the ceramic body's `covered` and dispatches against a seat cover whose two years
   had run out.

2. **An auto-created registration earns ZERO bonus months** (AC-L35). Clause 26
   gives the booster pump 24 months plus 12 for ONLINE REGISTRATION - a deliberate
   act by the consumer that Sorento gets consumer data for. AC-D8 auto-creates a
   registration when a complaint is lodged. Composed without thinking, lodging a
   complaint buys the complainant a third year of cover Sorento never sold, at the
   exact moment of the claim, in the direction that makes the claim succeed, and
   nobody would ever see it happen: the panel would simply read "covered to 2027" on
   a pump bought in 2024. `registered_at` records that a registration EXISTS, which
   is what clause 3(b) is about; `registration_source` records whether a HUMAN chose
   to register, which is what clause 26 pays for. The earning set is declared as
   data below, because a boolean derived inline from `registered_at is not None`
   cannot tell the two apart and IS the bug.

3. **AC-D8 stamps an existing purchase and never creates one.** Registration is a
   timestamp on a purchase now, so "auto-created if absent" can only mean "the
   purchase exists and `registered_at` is NULL". With no purchase there is no
   purchase date, and the only dates available - today's, the complaint's -
   fabricate the single number every verdict is computed from, in the customer's
   favour by years. Nothing is created, the complaint is never blocked (AC-C14), and
   the verdict is `unknown` until a receipt arrives.

4. **`is_recommendation` is SNAPSHOTTED, never re-read** (AC-D12). The provenance
   of the date is a fact about the receipt and lives on the purchase; the assessment
   copies it at compute time. When CS later confirms the date with the dealer the
   purchase's provenance improves, and every verdict a human already acted on must
   keep saying what it said at the time.

Re-assessing is idempotent and NEVER destroys a human decision. A delete-and-rewrite
recompute is the obvious implementation and it silently removes the confirmed
verdict, its reason and the name of whoever took responsibility for it, on the next
page load.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.complaints import Complaint, ComplaintProductLine
from app.models.consumers import ConsumerPurchase, ConsumerPurchaseLine
from app.models.warranty import WarrantyAssessment, WarrantyProductKind
from app.services import warranty_service
from app.services.error_handler import handle_not_found, handle_validation_error
from app.services.warranty_service import VERDICTS, VERDICT_UNKNOWN, WarrantyVerdict

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Vocabulary                                                                    #
# --------------------------------------------------------------------------- #

# AC-D8. What an automatic registration is called, so it can be told apart from one
# a consumer chose to make.
REGISTRATION_SOURCE_AUTO_ON_COMPLAINT = "auto_on_complaint"

# AC-L35, and the most important six lines in this slice. Declared as DATA rather
# than derived from a timestamp: `auto_on_complaint` is deliberately ABSENT, so the
# registration this service creates lengthens nobody's cover. Adding a member here
# is a decision somebody makes on purpose; a derived boolean is a decision nobody
# ever made.
BONUS_EARNING_REGISTRATION_SOURCES = frozenset({"self", "smc", "ecommerce"})

# AC-D12. A date a machine read off a photograph of a third-party document makes the
# verdict a RECOMMENDATION, never a determination.
RECOMMENDATION_DATE_SOURCES = frozenset({"ocr"})


# --------------------------------------------------------------------------- #
# Reading the purchase behind a complaint line                                  #
# --------------------------------------------------------------------------- #


def _utcnow() -> datetime:
    return datetime.utcnow()


def _complaint_line(db: Session, complaint_product_line_id: str) -> ComplaintProductLine:
    line = (
        db.query(ComplaintProductLine)
        .filter(ComplaintProductLine.id == complaint_product_line_id)
        .first()
    )
    if line is None:
        raise handle_not_found("Complaint product line", complaint_product_line_id)
    return line


def _purchase_for_line(
    db: Session, line: ComplaintProductLine
) -> Tuple[Optional[ConsumerPurchaseLine], Optional[ConsumerPurchase]]:
    """The purchase line this complaint line points at, if any (AC-L16).

    Reached through the LINE, never through the complaint: cover is per product and
    per part, and a complaint naming two products has two different dates behind it.
    """
    purchase_line_id = getattr(line, "consumer_purchase_line_id", None)
    if not purchase_line_id:
        return None, None
    purchase_line = (
        db.query(ConsumerPurchaseLine)
        .filter(ConsumerPurchaseLine.id == purchase_line_id)
        .first()
    )
    if purchase_line is None:
        return None, None
    purchase = (
        db.query(ConsumerPurchase)
        .filter(ConsumerPurchase.id == purchase_line.purchase_id)
        .first()
    )
    return purchase_line, purchase


def _resolve_kind_id(db: Session, purchase_line: ConsumerPurchaseLine) -> Optional[str]:
    """The live Kind for a purchase line, falling back to its snapshotted code.

    AC-L36. `kind_id` goes NULL when a warranty purge removes the Kind row, and
    `kind_code` is what survives - so a ledger that outlived an uninstall still
    resolves once the module is reinstalled and the seed upserts the same codes.

    `warranty_service.resolve` takes a `kind_id` and nothing else, and it is NOT
    given a code-shaped signature here: the engine's contract is deliberately narrow
    and one caller widening it is how two callers end up disagreeing. The code is
    turned back into an id at this boundary instead.

    Returns None when neither reaches a Kind, which the caller renders as one
    `unknown` verdict rather than an empty panel.
    """
    if purchase_line.kind_id:
        return purchase_line.kind_id
    code = (purchase_line.kind_code or "").strip()
    if not code:
        return None
    return (
        db.query(WarrantyProductKind.id)
        .filter(WarrantyProductKind.code == code)
        .scalar()
    )


def earns_registration_bonus(purchase: ConsumerPurchase) -> bool:
    """Whether clause 26's bonus months apply to this purchase (AC-L35).

    Both halves are required: a registration must EXIST, and it must have come from
    a source that represents a consumer choosing to register. The auto-stamp created
    when a complaint is lodged satisfies the first and deliberately fails the second.
    """
    if purchase is None or purchase.registered_at is None:
        return False
    return (purchase.registration_source or "") in BONUS_EARNING_REGISTRATION_SOURCES


# --------------------------------------------------------------------------- #
# AC-D8 - the registration a complaint creates                                  #
# --------------------------------------------------------------------------- #


def ensure_registration_on_complaint(
    db: Session, complaint_id: str
) -> List[ConsumerPurchase]:
    """Register the purchases this complaint reaches, if they are not already.

    Registration is never a precondition of cover (ADR-0010, the BRD over policy
    clause 3(b)), so this creates the registration rather than demanding one.

    It stamps only purchases that EXIST and are unregistered. It never creates a
    purchase: with no receipt there is no purchase date, and a date we invented is a
    guess wearing every verdict computed from it. Returns only what it newly stamped,
    so a second call on the same complaint reports nothing and the registration date
    never drifts - two complaints against one purchase is the ordinary case.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None:
        raise handle_not_found("Complaint", complaint_id)

    lines = (
        db.query(ComplaintProductLine)
        .filter(ComplaintProductLine.complaint_id == complaint_id)
        .all()
    )
    stamped: List[ConsumerPurchase] = []
    seen: set = set()
    for line in lines:
        _, purchase = _purchase_for_line(db, line)
        if purchase is None or purchase.id in seen:
            continue
        seen.add(purchase.id)
        if purchase.registered_at is not None:
            continue
        purchase.registered_at = _utcnow()
        purchase.registration_source = REGISTRATION_SOURCE_AUTO_ON_COMPLAINT
        stamped.append(purchase)

    if stamped:
        db.commit()
    return stamped


# --------------------------------------------------------------------------- #
# AC-D10 - computing and storing the verdicts                                   #
# --------------------------------------------------------------------------- #


def _verdicts_for(
    db: Session,
    line: ComplaintProductLine,
    *,
    as_of: Optional[date],
) -> Tuple[Sequence[WarrantyVerdict], bool]:
    """Every promise this complaint line's product carries, plus the AC-D12 flag.

    With no purchase behind the line the engine cannot be called at all, and the
    answer is exactly one `unknown` - never an empty sequence, which every screen
    renders as "not covered" and CS reads as a refusal.
    """
    purchase_line, purchase = _purchase_for_line(db, line)
    if purchase_line is None or purchase is None:
        return (
            [
                WarrantyVerdict(
                    verdict=VERDICT_UNKNOWN,
                    reason=(
                        "No purchase is linked to this complaint line yet, so there is "
                        "no purchase date to compute cover from."
                    ),
                )
            ],
            False,
        )

    is_recommendation = (
        purchase.purchase_date_source or ""
    ) in RECOMMENDATION_DATE_SOURCES

    kind_id = _resolve_kind_id(db, purchase_line)
    if kind_id is None:
        return (
            [
                WarrantyVerdict(
                    verdict=VERDICT_UNKNOWN,
                    reason=(
                        "The product kind recorded on this purchase line "
                        f"({purchase_line.kind_code}) is not in the warranty "
                        "vocabulary, so no term can be matched to it."
                    ),
                )
            ],
            is_recommendation,
        )

    verdicts = warranty_service.resolve(
        db,
        kind_id=kind_id,
        purchase_date=purchase.purchase_date,
        defect_type_id=getattr(line, "defect_type_id", None),
        registered=earns_registration_bonus(purchase),
        as_of=as_of,
    )
    return verdicts, is_recommendation


def _apply_verdict(
    row: WarrantyAssessment, verdict: WarrantyVerdict, *, is_recommendation: bool
) -> None:
    """Copy an engine answer onto a stored row, touching nothing a human wrote.

    `confirmed_verdict`, `confirmed_by`, `confirmed_at` and `override_reason` are
    never assigned here. That is AC-D11's whole content.
    """
    row.computed_verdict = verdict.verdict
    row.computed_expiry = verdict.expiry
    row.computed_at = _utcnow()
    row.computed_reason = verdict.reason
    row.part_name = verdict.part_name
    row.is_lifetime = bool(verdict.is_lifetime)
    row.installation_included = bool(verdict.installation_included)
    row.bonus_months_applied = int(verdict.bonus_months_applied or 0)
    row.policy_id = verdict.policy_id
    row.policy_version = verdict.policy_version
    row.is_recommendation = bool(is_recommendation)
    row.updated_at = _utcnow()


def assess_complaint_line(
    db: Session,
    complaint_product_line_id: str,
    *,
    as_of: Optional[date] = None,
) -> List[WarrantyAssessment]:
    """Store one verdict per part for this complaint line, and return them.

    Idempotent on (line, term): re-assessing updates the computed side in place
    rather than writing a second row, so reopening a complaint does not double the
    panel CS reads.

    Rows for terms the engine no longer returns are removed ONLY when nobody has
    confirmed them. A confirmed row is history: somebody put their name to it, and a
    policy edit is not a reason to delete their decision.
    """
    line = _complaint_line(db, complaint_product_line_id)
    verdicts, is_recommendation = _verdicts_for(db, line, as_of=as_of)

    existing: Dict[Optional[str], WarrantyAssessment] = {}
    for row in (
        db.query(WarrantyAssessment)
        .filter(WarrantyAssessment.complaint_product_line_id == line.id)
        .all()
    ):
        existing[row.term_id] = row

    stored: List[WarrantyAssessment] = []
    for verdict in verdicts:
        row = existing.pop(verdict.term_id, None)
        if row is None:
            row = WarrantyAssessment(
                id=str(uuid.uuid4()),
                complaint_product_line_id=line.id,
                term_id=verdict.term_id,
            )
            db.add(row)
        _apply_verdict(row, verdict, is_recommendation=is_recommendation)
        stored.append(row)

    for orphan in existing.values():
        if orphan.confirmed_verdict is None:
            db.delete(orphan)

    db.commit()
    # A stable order, so the CS panel does not reshuffle between page loads. Sorted
    # in Python rather than by the database, so it cannot shift with the server's
    # collation.
    stored.sort(key=lambda row: ((row.part_name or ""), (row.term_id or "")))
    return stored


def assessments_for_line(
    db: Session, complaint_product_line_id: str
) -> List[WarrantyAssessment]:
    """What is already stored for this line, without recomputing anything."""
    rows = (
        db.query(WarrantyAssessment)
        .filter(WarrantyAssessment.complaint_product_line_id == complaint_product_line_id)
        .all()
    )
    rows.sort(key=lambda row: ((row.part_name or ""), (row.term_id or "")))
    return rows


# --------------------------------------------------------------------------- #
# AC-D11 - the human decision                                                   #
# --------------------------------------------------------------------------- #


def confirm_assessment(
    db: Session,
    assessment_id: str,
    *,
    verdict: str,
    actor_user_id: str,
    reason: Optional[str] = None,
) -> WarrantyAssessment:
    """Record what a human decided, beside what the engine computed.

    A reason is mandatory only when the two DISAGREE. Refused rather than defaulted:
    a blank reason stored as `""` satisfies a NOT NULL and tells the next reader
    nothing, which is the failure the AC is about. Demanding a reason to AGREE would
    train CS to type "ok" and destroy the signal that makes the real ones worth
    reading.

    The computed side is never touched. Six months later the question is "what did
    the engine say, and who decided otherwise", and an overwritten row answers
    neither half.
    """
    row = (
        db.query(WarrantyAssessment).filter(WarrantyAssessment.id == assessment_id).first()
    )
    if row is None:
        raise handle_not_found("Warranty assessment", assessment_id)

    if verdict not in VERDICTS:
        raise handle_validation_error(
            f"{verdict!r} is not a warranty verdict. Expected one of "
            f"{', '.join(sorted(VERDICTS))}."
        )
    if not actor_user_id:
        raise handle_validation_error("Somebody must own every confirmed verdict.")

    cleaned_reason = (reason or "").strip() or None
    is_override = verdict != row.computed_verdict
    if is_override and not cleaned_reason:
        raise handle_validation_error(
            "Disagreeing with the computed verdict needs a reason: it is the only "
            "record of why this claim was decided differently."
        )

    row.confirmed_verdict = verdict
    row.confirmed_by = actor_user_id
    row.confirmed_at = _utcnow()
    row.override_reason = cleaned_reason
    row.updated_at = _utcnow()
    db.commit()
    return row
