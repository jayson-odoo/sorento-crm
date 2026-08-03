"""S3 - a Consumer lodging a complaint, as one transaction.

**The complaint is the occasion; the purchase ledger is what Sorento keeps.** Sorento sells
through dealers and therefore does not know who owns its products. This is the one moment a
consumer volunteers all of it - who they are, which shop, that shop's document number, the
date, the product, the receipt image - in exchange for something they want, which is an
answer about their warranty. If a lodgement can succeed while dropping any of that, the
module has collected a complaint and thrown away the reason it exists.

**Why one service rather than the route composing six calls.** Profile, consent, purchase,
complaint, lines and verdict either all land or none do. Spread across a route handler, the
first step that raises leaves a provisional profile with no complaint, or a complaint whose
consumer never consented - and neither is visible to anyone until a CS agent finds it weeks
later. It is also the only way the CS review screen and any later dealer-track path reach
the same result for the same receipt.

**Nothing blocks submission** (AC-C14). No dealer match, no readable date, no photos, no
model code: every one of those lodges. A consumer with a broken toilet is not the person to
punish for a bad OCR result, and the alternative - refusing until the form is complete - is
the thing that stops the ledger being built at all. What cannot be read is carried verbatim
for CS instead of being demanded from the consumer.

**One thing does block it, and it is consent.** No published notice means no lawful basis to
collect any of this, so `record_consent` raises and the whole transaction rolls back. That
is the single exception to the paragraph above, and it protects the consumer rather than the
form.

Three resolutions run here, and each has a deliberate failure mode:

  dealer   `dealer_resolution_service`. Only `resolved` is written; a `candidate` is a real
           but WRONG shop 3 times in 38 and is kept as text, never as `customer_id`.
  kind     by stable code. Decides cover on its own (ADR-0010), so this is the one that
           matters for the verdict.
  product  exact code match only. `SRTWC8152` matches three variants, so it stays NULL and
           CS picks (AC-C17). Guessing one attaches the wrong part's warranty term.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.complaints import Complaint, ComplaintProductLine
from app.models.warranty import WarrantyProductKind
from app.services import consumer_service
from app.services.dealer_resolution_service import STATE_RESOLVED, resolve_dealer

logger = logging.getLogger(__name__)

# The consumer track. `end_user` is the vocabulary in party_service.REPORTED_BY_ROLES.
REPORTED_BY_CONSUMER = "end_user"
# AC-C14 again, in the status graph: a lodgement arrives complete from the consumer's
# point of view, so it enters as submitted rather than as a draft nobody will finish.
LODGE_STATUS = "submitted"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class LodgeResult:
    """What the consumer holds at the end, and what CS receives with it."""

    complaint_id: str
    complaint_number: Optional[str]
    consumer_profile_id: Optional[str]
    purchase_id: Optional[str] = None
    # `resolved` / `candidate` / `unmatched`, echoed so the confirmation screen can say
    # what was understood without the consumer having to check.
    dealer_state: str = "unmatched"
    dealer_name: Optional[str] = None
    # One entry per line. Empty when nothing could be assessed, which is a normal
    # outcome and not an error: no date means no verdict.
    warranty: List[Dict[str, Any]] = field(default_factory=list)


def _as_date(value: Any) -> Optional[date]:
    """A date, or nothing. Never today's date as a stand-in.

    An invented purchase date is a guess wearing every warranty verdict computed from
    it, and on screen it is indistinguishable from one read off a receipt.
    """
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        logger.info("Unparseable purchase date %r, lodging without one.", value)
        return None


def _kind_id(db: Session, kind_code: Optional[str]) -> Optional[str]:
    if not kind_code:
        return None
    row = (
        db.query(WarrantyProductKind)
        .filter(WarrantyProductKind.code == str(kind_code).strip())
        .first()
    )
    return str(row.id) if row is not None else None


def _product_id(db: Session, model_code: Optional[str]) -> Optional[str]:
    """The exact variant, or NULL.

    Exact code match only, and only when it is UNIQUE. A base code matching three
    variants resolves to none of them (AC-C17): the Kind carries the cover, and picking
    one of the three would put another part's warranty term on this line.
    """
    code = (model_code or "").strip()
    if not code:
        return None
    from app.models.product import Product

    matches = (
        db.query(Product.id).filter(Product.product_code.ilike(code)).limit(2).all()
    )
    return str(matches[0][0]) if len(matches) == 1 else None


def _quantity_int(value: Any) -> Optional[int]:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def lodge_complaint(db: Session, payload: Dict[str, Any]) -> LodgeResult:
    """Everything one consumer submission leaves behind.

    Raises only when consent cannot lawfully be recorded. Every other gap is carried
    rather than refused.
    """
    lines_in: List[Dict[str, Any]] = list(payload.get("lines") or [])

    # ---------------------------------------------------------------- the consumer
    profile = consumer_service.ensure_profile(
        db,
        phone=payload.get("phone"),
        full_name=payload.get("full_name"),
        respond_contact_id=payload.get("respond_contact_id"),
        provisional=True,
    )
    # Before anything personal is written beyond the profile itself. The portal is the
    # one surface that actually renders the notice, so it is the one place this may be
    # stamped, and it fails closed.
    consumer_service.record_consent(db, profile)

    # ------------------------------------------------------------------ the dealer
    match = resolve_dealer(db, payload.get("shop_name"))
    dealer_customer_id = match.customer_id if match.state == STATE_RESOLVED else None

    # ----------------------------------------------------- resolve the claimed lines
    resolved: List[Dict[str, Any]] = []
    for index, raw in enumerate(lines_in):
        claimed = (raw.get("claimed_text") or "").strip() or None
        model_code = (raw.get("model_code_raw") or "").strip() or None
        kind_code = (raw.get("kind_code") or "").strip() or None
        resolved.append(
            {
                "sort_order": index,
                "claimed_text": claimed,
                # NOT NULL on the table since long before this module. The claimed text
                # is the honest fallback - it is what a CS agent will read anyway.
                "product_code": model_code or claimed or "UNSPECIFIED",
                "model_code_raw": model_code,
                "kind_code": kind_code,
                "kind_id": _kind_id(db, kind_code),
                "product_id": _product_id(db, model_code),
                "quantity": _quantity_int(raw.get("quantity")),
                "fault_description": (raw.get("fault_description") or "").strip() or None,
            }
        )

    # ---------------------------------------------------------------- the purchase
    # Only with a date. `record_purchase` refuses without one, and rightly: cover is
    # computed from nothing else. A dated receipt arriving later fills this in.
    purchase = None
    purchase_date = _as_date(payload.get("purchase_date"))
    if purchase_date is not None:
        # A purchase line needs its Kind (NOT NULL, and it is what keeps the row
        # assessable after the warranty module is uninstalled). Lines with no Kind stay
        # on the complaint for CS and simply do not enter the ledger yet.
        ledger_lines = [
            {
                "product_id": line["product_id"],
                "kind_code": line["kind_code"],
                "claimed_text": line["claimed_text"],
                "quantity": line["quantity"],
            }
            for line in resolved
            if line["kind_code"]
        ]
        purchase = consumer_service.record_purchase(
            db,
            purchase_date=purchase_date,
            customer_id=dealer_customer_id,
            dealer_document_number=payload.get("dealer_document_number"),
            consumer_profile_id=str(profile.id),
            proof_attachment_id=payload.get("proof_attachment_id"),
            # Deliberately NO registration_source, which leaves `registered_at` NULL for
            # `ensure_registration_on_complaint` to stamp as `auto_on_complaint`.
            #
            # The first version passed `self` on the reasoning that the consumer typed it
            # in themselves. That confuses WHO entered the purchase with WHY, and the why
            # is the whole rule: `BONUS_EARNING_REGISTRATION_SOURCES` excludes
            # `auto_on_complaint` so that the registration a CLAIM creates lengthens
            # nobody's cover (AC-L35). Stamping `self` here handed clause 26's bonus
            # months to every consumer who lodged a complaint, which is the entire
            # population the bonus was meant to distinguish between - a consumer who
            # registered on purpose earned nothing extra.
            purchase_date_source=payload.get("purchase_date_source")
            or consumer_service.PURCHASE_DATE_SOURCE_STATED,
            lines=ledger_lines,
        )

    # --------------------------------------------------------------- the complaint
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_date=_utcnow().date(),
        status=LODGE_STATUS,
        reported_by_role=REPORTED_BY_CONSUMER,
        # Only a resolved dealer. A candidate here would attribute the fault to a shop
        # that never sold the product, on the record CS acts from.
        customer_id=dealer_customer_id,
        # What was REPORTED, never the dealer's address (AC-B3): deriving it from the
        # customer record sends a technician to a shop.
        site_address=payload.get("site_address"),
        site_contact_name=payload.get("full_name"),
        site_contact_phone=profile.phone_e164,
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        contact_number=profile.phone_e164,
        contact_person=payload.get("full_name"),
        contact_id=payload.get("respond_contact_id"),
        defect_description=payload.get("defect_description"),
        delivery_order_number=payload.get("dealer_document_number"),
    )
    db.add(complaint)
    db.flush()

    # Queried, NOT read off a `purchase.lines` relationship - `ConsumerPurchase` has no
    # such attribute, and `getattr(purchase, "lines", [])` silently produced an empty map
    # here, so every complaint line was written with a NULL `consumer_purchase_line_id`
    # and AC-L16's "the assessment reaches its purchase DATE through this line" resolved
    # to nothing. Caught by the Consumer 360 tests, which are the first thing to actually
    # read the link back.
    purchase_line_by_kind: Dict[str, Any] = {}
    if purchase is not None:
        from app.models.consumers import ConsumerPurchaseLine

        for row in (
            db.query(ConsumerPurchaseLine)
            .filter(ConsumerPurchaseLine.purchase_id == purchase.id)
            .order_by(ConsumerPurchaseLine.sort_order)
            .all()
        ):
            purchase_line_by_kind.setdefault(row.kind_code, row)

    for line in resolved:
        held = purchase_line_by_kind.get(line["kind_code"])
        db.add(
            ComplaintProductLine(
                id=str(uuid.uuid4()),
                complaint_id=complaint.id,
                product_code=line["product_code"],
                claimed_text=line["claimed_text"],
                product_id=line["product_id"],
                kind_id=line["kind_id"],
                fault_description=line["fault_description"],
                quantity=str(line["quantity"]) if line["quantity"] is not None else None,
                sort_order=line["sort_order"],
                # AC-L16. The assessment reaches its purchase DATE through this, never
                # through the complaint.
                consumer_purchase_line_id=str(held.id) if held is not None else None,
            )
        )
    db.flush()

    _assign_number(db, complaint)
    db.commit()

    return LodgeResult(
        complaint_id=str(complaint.id),
        complaint_number=complaint.complaint_number,
        consumer_profile_id=str(profile.id),
        purchase_id=str(purchase.id) if purchase is not None else None,
        dealer_state=match.state,
        dealer_name=match.customer_name or match.printed_name,
        warranty=_assess(db, str(complaint.id)),
    )


def _assign_number(db: Session, complaint: Complaint) -> None:
    """Reuse the portal's numbering, so a consumer complaint is numbered like every
    other one. A second generator would produce a second series that nobody can reconcile.
    """
    from app.services.portal_service import PortalService

    try:
        PortalService(db)._assign_document_number_if_missing("complaint", complaint)
    except Exception as exc:  # noqa: BLE001
        # A missing number is a nuisance; a failed lodgement over it is a lost sale
        # record and a consumer with nothing.
        logger.warning("Complaint numbering failed for %s: %s", complaint.id, exc)


def _assess(db: Session, complaint_id: str) -> List[Dict[str, Any]]:
    """The verdict, computed. It is the value exchanged for the data, and the consumer
    is never asked to state it.

    Best-effort by design: it runs AFTER the lodgement has committed, so a policy
    engine that cannot answer must not turn a stored complaint into a 500 the consumer
    reads as "it did not go through" - they would submit again.
    """
    from app.services.warranty_assessment_service import (
        assess_complaint_line,
        ensure_registration_on_complaint,
    )

    out: List[Dict[str, Any]] = []
    try:
        ensure_registration_on_complaint(db, complaint_id)
        lines = (
            db.query(ComplaintProductLine)
            .filter(ComplaintProductLine.complaint_id == complaint_id)
            .order_by(ComplaintProductLine.sort_order)
            .all()
        )
        for line in lines:
            for row in assess_complaint_line(db, str(line.id)):
                out.append(
                    {
                        "complaint_product_line_id": str(line.id),
                        "claimed_text": line.claimed_text,
                        "part_name": row.part_name,
                        "verdict": row.computed_verdict,
                        # `computed_expiry`, NOT `expires_on` - there is no such column.
                        # The first version read the wrong name, the AttributeError was
                        # swallowed by the best-effort catch below, and every lodgement
                        # returned `warranty: []` with only a log line to show for it. The
                        # consumer never got the answer they gave their data for.
                        "expires_on": (
                            row.computed_expiry.isoformat() if row.computed_expiry else None
                        ),
                        # A lifetime term has no expiry, so a null date here is not a
                        # missing value and must not read as one.
                        "is_lifetime": bool(row.is_lifetime),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Warranty assessment failed for complaint %s: %s", complaint_id, exc)
    return out
