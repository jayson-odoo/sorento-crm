"""Status gate for the two stage-output responses (UAC section O).

Two surfaces in the system record an office answer ON the record itself: the
``purchasing_response`` on a stock inquiry and the ``technical_team_response``
on a complaint. Both are stage output, i.e. the answer a stage asked for, so
they may only be written while the record is still in that stage. Writing one
onto a closed, rejected or voided record leaves an answer that reads as current
even though nobody asked for it, and (on the reply path) stamps
``last_responded_by`` / ``last_responded_at`` as if the stage had just been
served.

**Ordinary chat is deliberately NOT gated (AC O2).** Messaging a contact about a
closed or rejected record keeps working exactly as it does today, through
``POST /{entity}/{id}/conversation/send-message``
(``app/api/v1/_respond_chat_template_routes.py``), which never touches the
entity. That endpoint is the split: the plain send stays open at any status, the
response write is what this module refuses. The gate is on the stage output,
never on the conversation.

The allowed statuses are not a new invention. They are the same response-stage
sets the two services already used to decide whether a reply may move the status
forward, hoisted here so the status flip and the write gate cannot drift apart:

* stock inquiry: ``{"pending_purchasing", "responded"}`` (was inline in
  ``StockInquiryService.update_inquiry_and_reply`` as
  ``transition_to_responded_workflow``).
* complaint: ``ComplaintService._RESPONSE_STAGE_STATUSES``.

This is a NEW restriction on live behaviour: neither path had a status guard
before. See UAC ``documentation/plans/UAC-portal-submission-revisions.md``
section O.
"""
from __future__ import annotations

from typing import Optional

from app.services.error_handler import handle_unprocessable

STOCK_INQUIRY = "stock_inquiry"
COMPLAINT = "complaint"

# The column each type's response lives in. Documentation + a single place to
# look when a third response surface ever appears.
RESPONSE_FIELDS: dict[str, str] = {
    STOCK_INQUIRY: "purchasing_response",
    COMPLAINT: "technical_team_response",
}

# Types that LOOK like a third response surface and deliberately are not.
#
# ``purchase_request`` / ``sponsorship_form`` (one table, discriminated by
# ``request_type``) also expose ``POST /{id}/update-and-reply``, so they read
# like one. They are not. ``purchase_requests`` has **no response column** - no
# ``purchasing_response`` equivalent, and no ``last_responded_by`` /
# ``last_responded_at`` - and ``PurchaseRequestUpdateAndReply`` adds exactly one
# field to the header update schema: ``reply_message``, a transient free-text
# message that is sent to the contact and never stored. The dialog behind it
# says so in as many words: "This message will be sent to the conversation in
# Respond."
#
# That endpoint is therefore an office edit plus a CHAT SEND, not stage output.
# Gating it by status would block messaging a contact about a closed or
# rejected request, which is exactly what AC O2 forbids. What PR / SF actually
# need against a superseded revision is the revision fence (AC CB1 / CB3) - a
# different check on a different axis, owned elsewhere.
#
# ``ticket`` has two more update-and-reply routes and is outside this feature
# entirely (not a revisable type).
#
# Listed rather than merely omitted so the next person does not have to re-derive
# this from the schema, and so the fail-open below is a decision instead of an
# oversight.
NO_RESPONSE_SURFACE: tuple[str, ...] = (
    "purchase_request",
    "sponsorship_form",
    "ticket",
)

# Statuses in which the response is the thing the record is waiting for.
# A type absent from this map is not gated at all.
ALLOWED_RESPONSE_STATUSES: dict[str, tuple[str, ...]] = {
    # Purchasing answers only once project sales has approved it through to
    # purchasing; "responded" stays open so an answer can be corrected or
    # re-sent while the inquiry is still at that stage.
    STOCK_INQUIRY: ("pending_purchasing", "responded"),
    # The complaint lifecycle is submitted -> responded -> approved | rejected,
    # then approved -> processed_by_cs | closed. The technical team answers in
    # the first leg only; every later state is a decision that the answer must
    # not be rewritten under.
    COMPLAINT: ("new", "submitted", "updated", "responded"),
}

# Wording for the statuses this gate can actually block, so the sentence reads
# like the pill on the screen. Anything missing falls back to the raw status
# with underscores removed.
_STATUS_LABELS: dict[str, dict[str, str]] = {
    STOCK_INQUIRY: {
        "new": "new",
        "pending_project_sales": "pending project sales",
        "rejected": "rejected",
        "voided": "voided",
    },
    COMPLAINT: {
        "approved": "approved",
        "rejected": "rejected",
        "processed_by_cs": "processed by CS",
        "closed": "closed",
    },
}

# One sentence, plain words, and it ends with what to do instead.
_BLOCKED_MESSAGES: dict[str, str] = {
    STOCK_INQUIRY: (
        "The purchasing response can only be saved while this stock inquiry is with "
        "purchasing, and it is now {label}, so use Chat Records if you just need to "
        "message the contact."
    ),
    COMPLAINT: (
        "The technical team response can only be saved while this complaint is still "
        "waiting for one, and it is now {label}, so use Chat Records if you just need "
        "to message the customer."
    ),
}


def _norm_status(status: Optional[str]) -> str:
    return (status or "").strip().lower()


def _status_label(source_entity_type: str, status: Optional[str]) -> str:
    raw = _norm_status(status)
    if not raw:
        return "in an unknown state"
    return _STATUS_LABELS.get(source_entity_type, {}).get(raw, raw.replace("_", " "))


def normalize_response_text(value: Optional[str]) -> str:
    """Comparable form of a response body. ``None`` and blank are the same thing."""
    return (value or "").strip()


def response_text_changed(current: Optional[str], incoming: Optional[str]) -> bool:
    """Whether ``incoming`` actually rewrites the stored response.

    The edit forms post the whole entity, response column included, so a save
    that leaves the response alone must stay legal at any status. Only a real
    change is a response write.
    """
    return normalize_response_text(current) != normalize_response_text(incoming)


def is_response_status_allowed(source_entity_type: str, status: Optional[str]) -> bool:
    """True when the response may be written at ``status``.

    A type with no configured statuses is not gated (fail open): only the two
    known response surfaces carry this restriction.
    """
    allowed = ALLOWED_RESPONSE_STATUSES.get(source_entity_type)
    if allowed is None:
        return True
    return _norm_status(status) in allowed


def response_blocked_reason(source_entity_type: str, status: Optional[str]) -> Optional[str]:
    """The human sentence for a refused response write, or None when allowed."""
    if is_response_status_allowed(source_entity_type, status):
        return None
    template = _BLOCKED_MESSAGES.get(source_entity_type)
    if not template:
        return None
    return template.format(label=_status_label(source_entity_type, status))


def assert_response_write_allowed(source_entity_type: str, status: Optional[str]) -> None:
    """Refuse a response write outside the type's response stage (AC O1).

    Raises a 422 ``AppException`` carrying one plain sentence. Ordinary chat
    never reaches here.
    """
    reason = response_blocked_reason(source_entity_type, status)
    if reason:
        raise handle_unprocessable(reason)
