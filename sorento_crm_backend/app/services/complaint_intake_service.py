"""S5 - a dealer's WhatsApp burst becomes a Complaint, at the moment it lands.

Today this is a person. A dealer sends eight photos and one line of text to a group, and
somebody in the office reads it a day later and asks *"this one wat issue? for which dealer?
for wat model?"*. That question is the requirement.

**n8n is the pump; the CRM is the tool** (AC-C0a to AC-C0d). Respond.io messages reach n8n,
n8n debounces the burst with a wait node, and when the burst closes it calls ONE write tool
with everything at once. The CRM neither polls nor subscribes, so there is no second message
pump to keep in step with the first.

**Extraction is CRM-side, not an n8n LLM node.** Two reasons, both structural: the prompt has
to be versioned and traceable through `ai_prompt_registry` (AC-C7), and the dealer, product
and Kind resolvers already live here. An LLM node in n8n would fork the registry and
duplicate three resolvers, and the day the two copies disagree the WhatsApp track and the
consumer portal name different dealers for the same shop.

**The extractor is injected.** `submit_intake` takes an `extraction` dict. AC-C8 forbids a
keyword branch per phrasing, and injection is what makes that testable: the tests assert what
this service DOES with an extraction, never how English was parsed. The live caller resolves
the prompt and calls the model; this module never does, which also means a model outage
degrades intake to "a Complaint carrying the raw text" rather than taking it down.

**Nothing blocks intake.** An unmatched dealer, an unresolvable model, a photo with no words:
each still produces a Complaint carrying what was actually said. A refusal here leaves the
message in WhatsApp, which is exactly where it already goes to die - so refusing is not the
safe option, it is the failure.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.complaints import Complaint, ComplaintProductLine
from app.services.dealer_resolution_service import STATE_RESOLVED, resolve_dealer
from app.services.error_handler import handle_not_found
from app.services.product_resolution_service import resolve_product

logger = logging.getLogger(__name__)

# The WhatsApp track: a dealer's own staff reporting, not the end user.
REPORTED_BY_DEALER = "dealer"
# Same reasoning as the portal: a burst is complete from the sender's point of view, so it
# enters as submitted rather than as a draft nobody will finish.
INTAKE_STATUS = "submitted"

# What a Complaint needs before CS can act without going back to the dealer. Kept as DATA
# because AC-C5 is "ask for ONLY what is missing" - a hardcoded question list would drift
# out of step with what is actually required and start re-asking.
REQUIRED_FIELDS = ("shop_name", "defect_description", "model")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class IntakeResult:
    """What n8n gets back, and what it says to the dealer."""

    complaint_id: str
    complaint_number: Optional[str]
    # True when this burst_key had already been submitted. n8n needs the difference: it
    # must not send the follow-up twice for one retried call.
    already_submitted: bool = False
    dealer_state: str = "unmatched"
    dealer_name: Optional[str] = None
    media_count: int = 0
    # Only what is genuinely absent (AC-C5). Never what was extracted.
    missing_fields: List[str] = field(default_factory=list)
    # The message n8n sends back into the same conversation (AC-C6).
    reply: Optional[str] = None
    prompt_versions: List[Dict[str, Any]] = field(default_factory=list)


def _find_existing(db: Session, burst_key: str) -> Optional[Complaint]:
    """The replay lookup, on an indexed column with a UNIQUE constraint behind it.

    The lookup alone is not the guarantee. Two n8n retries arriving together would both
    find nothing here and both insert, so `complaints.intake_burst_key` carries a partial
    unique index (migration 324) and the insert below catches the violation. The lookup is
    the fast path; the index is the correctness.
    """
    return (
        db.query(Complaint)
        .filter(Complaint.intake_burst_key == burst_key)
        .order_by(Complaint.created_at)
        .first()
    )


def _transcript(messages: List[Dict[str, Any]]) -> str:
    """The burst as text, in the order it was sent.

    Kept verbatim because it is what a human reads when the extraction is wrong, and
    because the sequence itself is evidence: photos before the words that explain them is
    the ordinary shape, and a transcript that reordered them would hide it.
    """
    out: List[str] = []
    for message in messages or []:
        stamp = str(message.get("sent_at") or "").strip()
        text = str(message.get("text") or "").strip()
        if not text and message.get("media_ref"):
            text = "[media]"
        if not text:
            continue
        out.append(f"{stamp} {text}".strip())
    return "\n".join(out)


def _missing(extraction: Dict[str, Any], resolved_lines: List[Dict[str, Any]]) -> List[str]:
    """Only what is absent. Asking for something the dealer already sent is what makes an
    automated follow-up feel worse than the human one it replaces.
    """
    def _blank(key: str) -> bool:
        return not str(extraction.get(key) or "").strip()

    missing: List[str] = []
    if _blank("shop_name"):
        missing.append("shop_name")
    if _blank("defect_description"):
        missing.append("defect_description")
    if not resolved_lines:
        missing.append("model")
    return missing


_FIELD_QUESTIONS = {
    "shop_name": "which shop this is for",
    "defect_description": "what the problem is",
    "model": "which model it is",
}


def _reply(complaint_number: Optional[str], missing: List[str]) -> str:
    """One sentence, in the shape the office already uses.

    The number always comes first (AC-C6) - it is the dealer's only handle on the case, and
    burying it under a question is how it gets lost in a busy group.
    """
    head = f"Logged as {complaint_number}." if complaint_number else "Logged."
    if not missing:
        return f"{head} We are on it."
    asks = [_FIELD_QUESTIONS.get(f, f) for f in missing]
    if len(asks) == 1:
        tail = asks[0]
    else:
        tail = ", ".join(asks[:-1]) + f" and {asks[-1]}"
    return f"{head} Could you also tell us {tail}?"


def submit_intake(
    db: Session,
    *,
    burst_key: str,
    contact_id: str,
    messages: Optional[List[Dict[str, Any]]] = None,
    media_refs: Optional[List[str]] = None,
    extraction: Optional[Dict[str, Any]] = None,
) -> IntakeResult:
    """One burst in, one Complaint out. Idempotent on `burst_key`."""
    messages = list(messages or [])
    media_refs = list(media_refs or [])
    extraction = dict(extraction or {})
    key = str(burst_key or "").strip()
    if not key:
        raise handle_not_found("Burst", burst_key)

    # -------------------------------------------------------------- the replay path
    # FIRST, before any resolution or write. n8n retries on timeout, and a retry that
    # re-resolves and re-writes would create the second Complaint this key exists to
    # prevent - and would do it after doing the work twice.
    existing = _find_existing(db, key)
    if existing is not None:
        return IntakeResult(
            complaint_id=str(existing.id),
            complaint_number=existing.complaint_number,
            already_submitted=True,
            media_count=len(media_refs),
            reply=_reply(existing.complaint_number, []),
            prompt_versions=list(extraction.get("prompt_versions") or []),
        )

    # ------------------------------------------------------------------- the sender
    # The contact is the identity, exactly as on the portal. Inventing one files a case
    # against nobody, and nobody can correct a case they cannot find.
    contact = db.query(RespondContact).filter(RespondContact.id == str(contact_id)).first()
    if contact is None:
        raise handle_not_found("Contact", contact_id)

    # ------------------------------------------------------------------- the dealer
    match = resolve_dealer(db, extraction.get("shop_name"))
    dealer_customer_id = match.customer_id if match.state == STATE_RESOLVED else None

    # -------------------------------------------------------------------- the lines
    resolved_lines: List[Dict[str, Any]] = []
    for index, raw in enumerate(extraction.get("lines") or []):
        claimed = str(raw.get("claimed_text") or "").strip() or None
        code = str(raw.get("model_code_raw") or "").strip() or None
        product = resolve_product(db, code or claimed)
        resolved_lines.append(
            {
                "sort_order": index,
                "claimed_text": claimed,
                # NOT NULL on the table. The claimed text is the honest fallback.
                "product_code": code or claimed or "UNSPECIFIED",
                # NULL whenever the code was ambiguous - a base code covering several
                # variants resolves the Kind, never the variant (AC-C17).
                "product_id": product.product_id,
                "quantity": raw.get("quantity"),
            }
        )

    transcript = _transcript(messages)

    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_date=_utcnow().date(),
        status=INTAKE_STATUS,
        reported_by_role=REPORTED_BY_DEALER,
        # Only a resolved dealer. A candidate here would attribute the fault to a shop
        # that never sold the product, on the record CS acts from.
        customer_id=dealer_customer_id,
        # What was printed, kept whatever the match verdict, so CS can finish the job the
        # resolver could not (AC-C14).
        customer_name=(extraction.get("shop_name") or None),
        contact_id=str(contact.id),
        contact_number=contact.phone_number,
        contact_person=contact.name,
        defect_description=extraction.get("defect_description") or None,
        product_code=", ".join(
            line["product_code"] for line in resolved_lines if line["product_code"]
        )
        or None,
        intake_burst_key=key,
        # The burst itself, verbatim. The office reads this when the extraction is wrong.
        intake_transcript=transcript or None,
    )
    db.add(complaint)
    try:
        db.flush()
    except IntegrityError:
        # Lost the race: another retry inserted this burst_key between our lookup and our
        # flush. The unique index is what makes that a caught duplicate instead of a second
        # Complaint, and returning the winner is the same answer the fast path gives.
        db.rollback()
        winner = _find_existing(db, key)
        if winner is None:
            raise
        return IntakeResult(
            complaint_id=str(winner.id),
            complaint_number=winner.complaint_number,
            already_submitted=True,
            media_count=len(media_refs),
            reply=_reply(winner.complaint_number, []),
            prompt_versions=list(extraction.get("prompt_versions") or []),
        )

    for line in resolved_lines:
        db.add(
            ComplaintProductLine(
                id=str(uuid.uuid4()),
                complaint_id=complaint.id,
                product_code=line["product_code"],
                claimed_text=line["claimed_text"],
                product_id=line["product_id"],
                quantity=str(line["quantity"]) if line["quantity"] is not None else None,
                sort_order=line["sort_order"],
            )
        )
    db.flush()

    _assign_number(db, complaint)
    db.commit()

    missing = _missing(extraction, resolved_lines)
    return IntakeResult(
        complaint_id=str(complaint.id),
        complaint_number=complaint.complaint_number,
        already_submitted=False,
        dealer_state=match.state,
        dealer_name=match.customer_name or match.printed_name,
        media_count=len(media_refs),
        missing_fields=missing,
        reply=_reply(complaint.complaint_number, missing),
        prompt_versions=list(extraction.get("prompt_versions") or []),
    )


def _assign_number(db: Session, complaint: Complaint) -> None:
    """Reuse the portal's numbering, so a WhatsApp complaint is numbered like every other
    one. A second generator produces a second series nobody can reconcile.
    """
    from app.services.portal_service import PortalService

    try:
        PortalService(db)._assign_document_number_if_missing("complaint", complaint)
    except Exception as exc:  # noqa: BLE001
        # A missing number is a nuisance; a failed intake over it loses the dealer's
        # message entirely.
        logger.warning("Complaint numbering failed for intake %s: %s", complaint.id, exc)
