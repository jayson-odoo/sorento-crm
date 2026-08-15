"""Direct CRM -> n8n ``respond-close-convo`` webhook fired on a ticket resolve.

UAC AC-M3 (revised 2026-08-14, user direction "use same method as
respond-send-user"): when a CRM resolve commits AND the contact holds no other
OPEN intervention ticket, the CRM calls ``respond-close-convo`` directly with a
deterministic payload instead of leaving the flow to guess who closed the
conversation. The Respond-trigger lane gates on ``closedBySource``, so the API
close the CRM performs (the pre-existing best-effort RQ job, unchanged) cannot
double-run the flow, and a literal-"undefined" ``resolved_by`` becomes
structurally impossible on this lane.

Everything here mirrors ``crm_chat_outbound_webhook`` (S4.1) on purpose: one
integration_log outbox row per attempt (success AND failure), the AC-J6 shared
secret resolved AT SEND TIME so it never sits at rest in a readable table, and
the POST on a daemon thread so the resolve never waits on n8n.
"""
from __future__ import annotations

import logging
import threading
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.user import User
from app.schemas.integration import IntegrationLogCreate
from app.services.integration_service import IntegrationLogService, direct_send_retry_hold
from app.services.n8n_webhook_settings import (
    crm_webhook_auth_headers,
    get_n8n_close_convo_webhook_url,
)

logger = logging.getLogger(__name__)

INTEGRATION_CHANNEL = "n8n_crm_close_convo"
BUSINESS_TABLE = "conversation_sla_tracking"

# Closed enum, per the AC-M3 hardening note: the n8n Respond-trigger lane fails
# CLOSED on anything it does not know, so a future source cannot double-run the
# flow by default. The CRM only ever emits "crm".
CLOSED_BY_SOURCE_CRM = "crm"

# What the contact-facing close message falls back to when the resolver has no
# mapped Respond user id AND no team could be resolved. Never blank, never
# "undefined".
NEUTRAL_RESOLVER_NAME = "Customer Service"

DEFAULT_CATEGORY = "Resolved"
DEFAULT_SUMMARY = "Resolved from Sorento CRM SLA tracking."


def send_crm_close_convo_webhook_for_log(log_id: str) -> None:
    """POST the integration log payload to the close webhook (own DB session).

    The AC-J6 shared secret is resolved HERE, per send, and travels on the HTTP
    request only - it is never written to the log row. A manual resubmit comes
    back through this same function and therefore sends the CURRENT secret.
    """
    try:
        from app.database import SessionLocal

        bg_db = SessionLocal()
        try:
            IntegrationLogService(bg_db).send_webhook_for_log(
                log_id, extra_headers=crm_webhook_auth_headers() or None
            )
        finally:
            bg_db.close()
    except Exception as e:  # noqa: BLE001 - the resolve already committed
        logger.error(
            "respond-close-convo webhook failed for log %s: %s", log_id, e, exc_info=True
        )


def _iso_utc(value: Any) -> Optional[str]:
    """Aware UTC ISO-8601 with a ``Z`` suffix.

    Tracking columns store NAIVE UTC, so a naive value is stamped UTC rather
    than localized - the same rule the conversation event bus uses.
    """
    if not isinstance(value, datetime):
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_id(tracking_id: str, resolved_at_iso: Optional[str]) -> str:
    """Idempotency key (AC-M3 hardening 1): stable across retries of the SAME
    resolve, different for a re-resolve after an un-resolve."""
    return str(
        uuid_module.uuid5(uuid_module.NAMESPACE_URL, f"{tracking_id}:{resolved_at_iso or ''}")
    )


def build_close_convo_payload(
    *,
    tracking_id: str,
    contact: Optional[RespondContact],
    resolver: Optional[User],
    resolver_respond_user_id: Optional[str],
    resolved_at: Any,
    team_name: Optional[str],
    category: str = DEFAULT_CATEGORY,
    summary: str = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    """The deterministic close payload. See PLAN S4.5 for the wire contract."""
    resolved_at_iso = _iso_utc(resolved_at)
    resolver_name = (getattr(resolver, "name", None) or "").strip() or None
    team = (team_name or "").strip() or None
    return {
        "event": "ticket_resolved",
        "event_id": _event_id(str(tracking_id), resolved_at_iso),
        # The same discriminator respond-send-user uses: this lane only ever
        # carries real human CRM actions.
        "source": "User",
        "closedBySource": CLOSED_BY_SOURCE_CRM,
        "tracking_id": str(tracking_id),
        "contact": {
            "respond_io_id": (
                str(getattr(contact, "respond_io_id", None))
                if getattr(contact, "respond_io_id", None)
                else None
            ),
            "phone": getattr(contact, "phone_number", None),
        },
        "resolved_by": {
            # None when the CRM user has no Respond mapping - never a CRM
            # users.id UUID masquerading as a Respond user id (AC-J3 family).
            "respond_user_id": resolver_respond_user_id,
            "crm_user_id": str(resolver.id) if resolver is not None else None,
            "name": resolver_name,
            # AC-M3 hardening 3: what the contact-facing message renders when
            # there is no Respond user id. Always a readable string.
            "display_name": resolver_name or team or NEUTRAL_RESOLVER_NAME,
        },
        "resolved_at": resolved_at_iso,
        "team_name": team,
        "category": category,
        "summary": summary,
        # The gate the CRM already applied before calling: this was the
        # contact's LAST open conversation-scope ticket.
        "open_ticket_count": 0,
        "crm": {"business_table": BUSINESS_TABLE, "business_id": str(tracking_id)},
    }


def notify_ticket_resolved_close(
    db: Session,
    *,
    tracking_id: str,
    respond_contact_id: Optional[str],
    resolved_by_user_id: Optional[str],
    resolved_at: Any,
    team_name: Optional[str] = None,
) -> bool:
    """Tell n8n the contact's conversation can be closed (UAC AC-M3).

    Called ONCE per resolve, and only when the resolve emptied the contact's
    open-ticket set - a sibling ticket still open means the conversation is not
    finished, so nothing is sent.

    Best-effort post-commit: the resolve has ALREADY committed, so every failure
    here is caught and warned. Returns True when the webhook was handed off,
    False when it was skipped (URL not configured, contact unresolvable) or
    failed to enqueue.
    """
    try:
        url = get_n8n_close_convo_webhook_url()
        if not url:
            logger.warning(
                "respond-close-convo webhook skipped for tracking %s: "
                "N8N_CLOSE_CONVO_WEBHOOK_URL is not configured",
                tracking_id,
            )
            return False

        contact = (
            db.query(RespondContact).filter(RespondContact.id == str(respond_contact_id)).first()
            if respond_contact_id
            else None
        )
        if contact is None or not getattr(contact, "respond_io_id", None):
            logger.warning(
                "respond-close-convo webhook skipped for tracking %s: no Respond contact id",
                tracking_id,
            )
            return False

        resolver: Optional[User] = None
        if resolved_by_user_id and str(resolved_by_user_id).strip():
            resolver = (
                db.query(User).filter(User.id == str(resolved_by_user_id).strip()).first()
            )

        # Reused verbatim from the send lane: returns None for an unmapped user
        # AND for a mapping that was filled with a CRM users.id UUID.
        from app.services.crm_chat_outbound_webhook import resolve_sender_respond_user_id

        resolver_respond_user_id = resolve_sender_respond_user_id(db, resolved_by_user_id)

        payload = build_close_convo_payload(
            tracking_id=str(tracking_id),
            contact=contact,
            resolver=resolver,
            resolver_respond_user_id=resolver_respond_user_id,
            resolved_at=resolved_at,
            team_name=team_name,
        )

        integration_log = IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel=INTEGRATION_CHANNEL,
                business_table=BUSINESS_TABLE,
                business_id=str(tracking_id),
                external_reference=str(contact.respond_io_id),
                direction="outbound",
                endpoint=url,
                http_method="POST",
                status="pending",
                # No auth header here on purpose: the AC-J6 secret is resolved
                # at send time (send_webhook_for_log, from the row's channel).
                created_by=(
                    str(resolved_by_user_id).strip() if resolved_by_user_id else None
                ),
                # Held back from the retry sweeper while the thread below has
                # its turn at the POST.
                next_retry_at=direct_send_retry_hold(),
            ),
            request_payload_dict=payload,
        )
        log_id = str(integration_log.id)

        def _send_async() -> None:
            send_crm_close_convo_webhook_for_log(log_id)

        threading.Thread(target=_send_async, daemon=True).start()
        return True
    except Exception:  # noqa: BLE001 - the resolve already committed
        logger.warning(
            "respond-close-convo webhook failed for tracking %s", tracking_id, exc_info=True
        )
        return False
