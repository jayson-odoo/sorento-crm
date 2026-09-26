"""Telling the salesperson (r9 S4/D12-D13).

Before this, a price tag request moved through seven statuses and the person
who asked for the tags heard nothing at any of them: they found out by opening
the portal, or by asking. Every transition now reaches them on WhatsApp,
including the confirmations of their own actions - a message that says "you
approved it" is how somebody knows the button worked.

Two rules this module exists to keep:

* **A send never breaks a transition.** Respond.io being down is not a reason
  for an approve to fail, so everything here is wrapped and logged. The
  ``IntegrationLog`` row is written on success AND on failure, which is also
  the only evidence a lane stack (where sends are disabled) can show.
* **One place decides the words.** The copy table is here, keyed by the status
  the request landed on, so the same event cannot be phrased two ways by two
  callers.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: What `build_context_vars` and the template fallback know this send as.
USE_CASE = "price_tag_update"

#: The business table every log row is filed under, so a send is findable.
BUSINESS_TABLE = "price_tag_requests"


def _copy(event: str, *, doc_number: str, link: str, ctx: dict) -> Optional[str]:
    """One line per event (D12's copy table).

    Returns None for an event nobody needs to hear about, which is how a new
    status that says nothing to the salesperson stays silent by default.
    """
    print_by = ctx.get("print_by")
    tail = f" {link}" if link else ""

    if event == "submitted":
        return f"{doc_number} received. We will start designing shortly.{tail}"
    if event == "designing":
        who = ctx.get("assignee") or "the marketing team"
        return f"{doc_number} is being designed by {who}.{tail}"
    if event == "proof_ready":
        return f"{doc_number} design is ready for your review.{tail}"
    if event == "changes_requested":
        count = ctx.get("count")
        if count == 1:
            return f"You sent 1 change request on {doc_number}.{tail}"
        if count:
            return f"You sent {count} change requests on {doc_number}.{tail}"
        return f"You sent change requests on {doc_number}.{tail}"
    if event == "approved":
        if print_by == "self":
            return f"You approved {doc_number}. The PDF is being prepared.{tail}"
        return (
            f"You approved {doc_number}. The office will print and tell you "
            f"when it is ready.{tail}"
        )
    if event == "pdf_ready":
        return f"{doc_number} PDF is ready to download.{tail}"
    if event == "ready_for_collection":
        return f"{doc_number} tags are ready for collection at the office.{tail}"
    if event == "collected":
        if ctx.get("auto"):
            days = ctx.get("days")
            return (
                f"{doc_number} marked collected automatically after {days} days.{tail}"
            )
        return f"{doc_number} marked collected.{tail}"
    if event in {"rejected", "void"}:
        reason = (ctx.get("reason") or "").strip()
        if reason:
            return f"{doc_number} was rejected: {reason}{tail}"
        return f"{doc_number} was rejected.{tail}"
    return None


def _portal_link(db: Session, request) -> str:
    """The deep link that opens THIS request in the portal, or ''.

    A message with no link makes the salesperson go and find the request, which
    is the thing this feature exists to stop - but a link that cannot be
    resolved is not a reason to send nothing at all.
    """
    try:
        from app.services.portal_service import PortalService

        return (
            PortalService(db).submission_link(
                request.contact_id, "price_tag_request", str(request.id)
            )
            or ""
        )
    except Exception:  # pragma: no cover - a link is never worth an exception
        logger.warning("Could not build a portal link for %s", request.id)
        return ""


def notify_salesperson(db: Session, request, event: str, **ctx) -> None:
    """Tell the request's contact what just happened. Never raises.

    ``event`` is the status the request landed on (plus ``submitted`` and
    ``pdf_ready``, which are not statuses), so the copy table can be keyed off
    the transition itself rather than off a second vocabulary.
    """
    try:
        from app.services.respond_identifier import resolve_respond_io_id

        # D11: addressed by the contact's `respond_io_id`, not the internal
        # `RespondContact` uuid - the outbox resolves name/phone by
        # `respond_io_id`, so sending the uuid left the Contact column
        # unresolved everywhere it is read back. Falls back to the raw
        # contact_id when the contact has no `respond_io_id` yet, so nothing
        # that used to send now silently drops.
        identifier = resolve_respond_io_id(db, request.contact_id) or (
            str(request.contact_id or "")
        ).strip()
        if not identifier:
            return

        text = _copy(
            event,
            doc_number=request.doc_number,
            link=_portal_link(db, request),
            ctx={"print_by": request.print_by, **ctx},
        )
        if not text:
            return

        _send(db, request, identifier=identifier, text=text)
    except Exception:
        # A message is best effort, always: the transition it reports has
        # already happened and must not be undone by a messaging failure.
        logger.exception(
            "Price tag notification failed for %s (%s)",
            getattr(request, "id", None),
            event,
        )


def _send(db: Session, request, *, identifier: str, text: str) -> None:
    """The Respond.io send itself, mirrored to the outbound webhook and logged.

    The same path a purchase request update takes (``procurement_service.
    _send_purchase_request_contact_message``) - window-aware text or template,
    the CRM chat webhook so the conversation shows it, and an ``IntegrationLog``
    row either way.
    """
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService
    from app.services import respond_messaging_service

    log_service = IntegrationLogService(db)
    request_payload = {"message": {"type": "text", "text": text}}

    try:
        context_vars = respond_messaging_service.build_context_vars(
            db,
            use_case=USE_CASE,
            business_id=str(request.id),
            identifier=identifier,
        )
    except Exception:
        context_vars = None

    try:
        result = respond_messaging_service.send_text_or_template(
            db,
            identifier=identifier,
            text=text,
            use_case=USE_CASE,
            context_vars=context_vars,
        )
        response = result.get("response") if isinstance(result, dict) else None
        request_payload = (
            result.get("request_payload") if isinstance(result, dict) else None
        ) or request_payload

        try:
            from app.services.crm_chat_outbound_webhook import (
                enqueue_crm_chat_outbound_webhook,
            )

            enqueue_crm_chat_outbound_webhook(
                db,
                business_table=BUSINESS_TABLE,
                business_id=str(request.id),
                contact_respond_io_id=identifier,
                message_text=text,
                respond_api_response=response if isinstance(response, dict) else None,
            )
        except Exception:
            logger.warning(
                "Outbound chat webhook not enqueued for %s", request.id, exc_info=True
            )

        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table=BUSINESS_TABLE,
                business_id=str(request.id),
                external_reference=identifier,
                direction="outbound",
                endpoint=(
                    f"https://api.respond.io/v2/contact/id:{identifier}/message"
                ),
                http_method="POST",
                status="success",
                response_payload=str(response)[:50000] if response else None,
            ),
            request_payload_dict=request_payload,
        )
    except Exception as error:
        # Logged as a FAILED row rather than swallowed: on a lane stack (and on
        # prod during an outage) this row is the only evidence the message was
        # attempted at all.
        logger.exception("Respond.io send failed for price tag %s", request.id)
        try:
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table=BUSINESS_TABLE,
                    business_id=str(request.id),
                    external_reference=identifier,
                    direction="outbound",
                    endpoint=(
                        f"https://api.respond.io/v2/contact/id:{identifier}/message"
                    ),
                    http_method="POST",
                    status="failed",
                    error_message=str(error)[:2000],
                ),
                request_payload_dict=request_payload,
            )
        except Exception:
            logger.exception("Could not log the failed price tag send")


#: The two transitions the ASSIGNEE hears about in the CRM (D13). Everything
#: else is the salesperson's business, and a bell for it would be noise.
BELL_EVENTS = {
    "changes_requested": (
        "price_tag_changes_requested",
        "{doc} - the salesperson asked for changes",
    ),
    "approved": ("price_tag_approved", "{doc} approved"),
}


def ring_assignee(db: Session, request, event: str, *, round_no: int = 1) -> None:
    """One in-app notification for whoever is designing this (D13).

    Deduplicated per request + status + round, because marketing sending the
    same proof back twice inside one round is one thing that happened, not two.
    """
    entry = BELL_EVENTS.get(event)
    if not entry or not request.assigned_to_id:
        return
    event_type, title_template = entry

    try:
        from app.services.notification_service import NotificationService

        link = f"/dealer-kit/price-tag-requests/{request.id}"
        body = {
            "changes_requested": (
                f"Open the design to see what was asked for. {link}"
            ),
            "approved": (
                f"Print and mark it ready for collection. {link}"
                if request.print_by == "office"
                else f"The PDF export is queued. {link}"
            ),
        }[event]

        NotificationService(db).create_in_app_only(
            user_id=request.assigned_to_id,
            type="info",
            title=title_template.format(doc=request.doc_number),
            body=body,
            source_entity_type="price_tag_request",
            source_entity_id=str(request.id),
            dedup_key=f"{request.id}:{event}:{round_no}",
            event_type=event_type,
        )
    except Exception:
        logger.exception("Could not ring the assignee for %s", request.id)
