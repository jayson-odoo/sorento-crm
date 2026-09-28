"""Ideation status update (#1355): pull the shared service's idea status-event feed and
send the approved ``ideation_status_update`` WhatsApp template to the requester.

Plan: documentation/plans/ideation/PLAN-ideation-status-update-29sep.md (UAC AC-IS001
onward). The shared service publishes the feed; the CRM pulls it and owns the send, so
templates, opt-outs and the integration log stay in one place (the same split as the
``ideation_draft_reminder`` sent by ``ideation_turn_service``).

One tick (``poll_ideation_status_events``, every 60 s from the scheduler):

1. ``GET {base}/ideation/intake/status-events?after=<cursor>&limit=100&includeTest=true``
   with the workspace key already used for ``create-idea``. ``includeTest=true`` so a
   test idea's move is logged; the ``is_test`` guard below, not the feed filter, is
   what keeps a test idea from messaging anyone.
2. Events in ascending ``seq``. Each one ends in exactly one ``integration_log`` row
   (``business_table='ideation_status_events'``, ``business_id=<event_id>``) committed
   together with the cursor move, so the cursor never runs ahead of a handled event.
   An ``event_id`` that already has its row is skipped (at-least-once feed); a partial
   unique index makes that a database guarantee.
3. Guards in order: ``is_test`` -> never send; unknown kind; no requester phone;
   no Respond.io contact for the phone; contact opted out (``outbound_enabled``);
   then the template through ``send_template_for_use_case`` - always the template,
   never free text, whether or not the 24h window is open. No valid mapping ->
   ``TemplateSendSkipped`` -> logged, the poller goes on.

Never raises out of the tick: a feed failure leaves the cursor for the next tick, a
failed log write rolls back and stops the tick with the cursor on the last handled
event.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.ideation_status_event import IdeationStatusEventCursor
from app.models.integration import IntegrationLog
from app.services.ideation_turn_service import _resolve_ideation_config
from app.utils.phone_normalize import normalize_phone

logger = logging.getLogger(__name__)

USE_CASE = "ideation_status_update"
BUSINESS_TABLE = "ideation_status_events"
_FEED_PATH = "/ideation/intake/status-events"
_PAGE_LIMIT = 100
_TIMEOUT_SECONDS = 15
_REF_MAX = 255  # integration_log.external_reference is String(255)
_KINDS = ("status_changed", "merged", "unmerged")

# Log row outcomes. Never "pending"/"processing": the integration-log retry sweeper
# re-sends those, and an ideation status row must never be re-sent by it.
_SUCCESS = "success"
_SKIPPED = "skipped"
_FAILED = "failed"


class IdeationFeedError(Exception):
    """The status-event feed could not be read (transport, non-2xx, malformed body)."""


def fetch_status_events(base_url: str, api_key: str, *, after: int, limit: int) -> dict[str, Any]:
    """One page of the feed. Raises ``IdeationFeedError`` on any failure."""
    url = base_url.rstrip("/") + _FEED_PATH
    params = {"after": after, "limit": limit, "includeTest": "true"}
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            resp = client.get(url, params=params, headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise IdeationFeedError(f"status-events request failed: {exc}") from exc
    except ValueError as exc:
        raise IdeationFeedError(f"status-events returned a malformed body: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise IdeationFeedError("status-events returned no events list")
    return data


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


def _feed_key(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def get_cursor(db: Session, base_url: str) -> int:
    row = db.get(IdeationStatusEventCursor, _feed_key(base_url))
    return int(row.after_seq) if row is not None else 0


def set_cursor(db: Session, base_url: str, seq: int) -> None:
    """Stage the cursor move; the caller commits it with the event's log row."""
    key = _feed_key(base_url)
    row = db.get(IdeationStatusEventCursor, key)
    if row is None:
        db.add(IdeationStatusEventCursor(feed_base_url=key, after_seq=int(seq)))
    else:
        row.after_seq = int(seq)


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def _seq(event: Any) -> int | None:
    """An int ``seq``, or a string of digits; anything else (floats, bools) is unusable."""
    if not isinstance(event, dict):
        return None
    raw = event.get("seq")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _event_uuid(raw: Any) -> str:
    """``business_id`` is a UUID column. The contract says ``event_id`` is a uuid; an
    off-contract id maps to a stable uuid5 so it still dedupes and still gets a row."""
    value = str(raw or "").strip()
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ideation-status-event:{value}"))


def _already_seen(db: Session, event_uuid: str) -> bool:
    return (
        db.query(IntegrationLog.id)
        .filter(
            IntegrationLog.business_table == BUSINESS_TABLE,
            IntegrationLog.business_id == event_uuid,
        )
        .first()
        is not None
    )


def _idea_ref(ref: Any) -> str:
    if isinstance(ref, dict):
        return str(ref.get("idea_number") or ref.get("title") or "").strip() or "another idea"
    return "another idea"


def _idea_label(event: dict[str, Any]) -> str:
    return str(event.get("idea_number") or event.get("idea_title") or "").strip()


def build_context_vars(event: dict[str, Any]) -> dict[str, Any]:
    """Template variables (Appendix A): {{1}} idea number (falls back to the title),
    {{2}} the new status, or the merged / separated wording, {{3}} the track link.
    ``message`` is the whole suggested sentence for a single-slot template."""
    kind = event.get("kind")
    status = str(event.get("status_label") or "").strip()
    if kind == "merged":
        status = f"combined with {_idea_ref(event.get('merged_into'))}"
    elif kind == "unmerged":
        separated = f"handled separately again from {_idea_ref(event.get('separated_from'))}"
        status = f"{separated}, now {status}" if status else separated
    idea = _idea_label(event)
    track_url = str(event.get("track_url") or "").strip()
    message = f"Update on your idea {idea}: it is now {status}."
    if track_url:
        message += f" Track it here: {track_url}"
    return {
        "idea_number": idea,
        "status_label": status,
        "track_url": track_url,
        "message": message,
    }


def _find_contact(db: Session, phone: str) -> RespondContact | None:
    """The requester's Respond contact: exact phone first, then digits only, so
    ``+60 12-345 6789`` and ``60123456789`` are the same person."""
    contact = db.query(RespondContact).filter(RespondContact.phone_number == phone).first()
    if contact is not None:
        return contact
    digits = normalize_phone(phone)
    if not digits:
        return None
    # Two rows can differ only in formatting; the oldest is the deterministic pick.
    return (
        db.query(RespondContact)
        .filter(func.regexp_replace(RespondContact.phone_number, r"\D", "", "g") == digits)
        .order_by(RespondContact.created_at, RespondContact.id)
        .first()
    )


def _mapped_template_name(db: Session) -> str | None:
    from app.services.respond_template_service import get_default_row

    row = get_default_row(db, USE_CASE)
    if row is None:
        return None
    if row.template is not None:
        return row.template.name
    return row.template_name_snapshot


# ---------------------------------------------------------------------------
# Handling one event
# ---------------------------------------------------------------------------


def _skip(code: str, message: str) -> dict[str, Any]:
    return {"status": _SKIPPED, "error_code": code, "error_message": message}


def _handle_event(db: Session, event: dict[str, Any], template_name: str | None) -> dict[str, Any]:
    """Decide and, when every guard passes, send. Returns the log row's outcome
    fields. Send errors are caught here; anything else propagates (the caller
    rolls back and stops the tick without moving the cursor)."""
    from app.services.respond_messaging_service import (
        TemplateSendSkipped,
        send_template_for_use_case,
    )

    if event.get("is_test"):
        return _skip("IS_TEST", "test idea: never sent to a requester")
    if event.get("kind") not in _KINDS:
        return _skip("UNKNOWN_KIND", f"unknown event kind {event.get('kind')!r}")
    phone = str(event.get("requester_phone") or "").strip()
    if not phone:
        return _skip("NO_REQUESTER_PHONE", "event carries no requester_phone")
    contact = _find_contact(db, phone)
    if contact is None or not (contact.respond_io_id or "").strip():
        return _skip("UNKNOWN_CONTACT", f"no Respond.io contact for {phone}")
    if not contact.outbound_enabled:
        return _skip("OPTED_OUT", "the requester's outbound messaging is switched off")

    context_vars = build_context_vars(event)
    try:
        result = send_template_for_use_case(
            db,
            identifier=contact.respond_io_id.strip(),
            use_case=USE_CASE,
            context_vars=context_vars,
        )
    except TemplateSendSkipped as exc:
        return {**_skip("NO_TEMPLATE", str(exc)), "template": template_name}
    except Exception as exc:  # noqa: BLE001 - a send error is logged, never raised
        logger.warning(
            "ideation status update: send failed for event %s", event.get("event_id"), exc_info=True
        )
        return {
            "status": _FAILED,
            "error_code": "SEND_FAILED",
            "error_message": str(exc)[:2000],
            "template": template_name,
            "parameters": _attempted_parameters(exc),
        }
    return {
        "status": _SUCCESS,
        "template": result.get("template_name"),
        "parameters": result.get("params"),
        "response": result.get("response"),
        "respond_io_id": contact.respond_io_id,
    }


def _attempted_parameters(exc: Exception) -> Any:
    """The resolved parameters ``send_template_for_use_case`` stamps on a send error."""
    payload = getattr(exc, "request_payload", None)
    if isinstance(payload, dict) and isinstance(payload.get("message"), dict):
        return payload["message"].get("parameters")
    return None


def _commit_handled(db: Session, base_url: str, event: dict[str, Any], row: dict[str, Any]) -> None:
    """The event's one log row and the cursor move, in one commit."""
    payload = {
        "event_id": event.get("event_id"),
        "seq": _seq(event),
        "kind": event.get("kind"),
        "idea_number": _idea_label(event) or None,
        "use_case": USE_CASE,
        "template": row.get("template"),
        "requester_phone": event.get("requester_phone"),
        "is_test": bool(event.get("is_test")),
    }
    if row.get("parameters") is not None:
        payload["parameters"] = row["parameters"]
    if row.get("respond_io_id"):
        payload["respond_io_id"] = row["respond_io_id"]
    response = row.get("response")
    db.add(
        IntegrationLog(
            integration_channel="respond_io",
            business_table=BUSINESS_TABLE,
            business_id=_event_uuid(event.get("event_id")),
            external_reference=(_idea_label(event)[:_REF_MAX] or None),
            direction="outbound",
            endpoint=USE_CASE,
            http_method="POST",
            request_payload=json.dumps(payload, default=str),
            status=row["status"],
            status_code=200 if row["status"] == _SUCCESS else None,
            response_payload=(json.dumps(response, default=str) if response is not None else None),
            error_code=row.get("error_code"),
            error_message=(row.get("error_message") or None) and str(row["error_message"])[:2000],
        )
    )
    set_cursor(db, base_url, _seq(event))
    db.commit()


def _commit_sent_fallback(db: Session, base_url: str, event: dict[str, Any], row: dict[str, Any]) -> None:
    """A template already went out but its full row would not commit. Record a
    minimal, capped row plus the cursor move, so the next tick never sends it again
    (reviewer round 1: an unrecordable success was re-sent every tick)."""
    db.add(
        IntegrationLog(
            integration_channel="respond_io",
            business_table=BUSINESS_TABLE,
            business_id=_event_uuid(event.get("event_id")),
            direction="outbound",
            endpoint=USE_CASE,
            http_method="POST",
            request_payload=json.dumps(
                {"event_id": str(event.get("event_id"))[:100], "seq": _seq(event), "use_case": USE_CASE}
            ),
            status=_SUCCESS,
            error_code="LOG_DEGRADED",
            error_message="sent; the full log row could not be written, see the application log",
        )
    )
    set_cursor(db, base_url, _seq(event))
    db.commit()


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------


def poll_ideation_status_events(
    db: Session,
    *,
    fetch: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One page of the feed, handled in ascending ``seq``. Never raises."""
    summary: dict[str, Any] = {"sent": 0, "skipped": 0, "failed": 0, "seen": 0, "stopped": False}
    fetch = fetch or fetch_status_events
    try:
        config = _resolve_ideation_config(db)
        if not (config.base_url and config.api_key):
            return summary
        base_url = config.base_url
        after = get_cursor(db, base_url)
        page = fetch(base_url, config.api_key, after=after, limit=_PAGE_LIMIT)
        template_name = _mapped_template_name(db)
    except Exception:  # noqa: BLE001 - outage: cursor untouched, next tick retries
        db.rollback()
        logger.warning("ideation status update: feed read failed", exc_info=True)
        return summary

    events = []
    for event in page.get("events") or []:
        seq = _seq(event)
        if seq is None:
            logger.error("ideation status update: event without a usable seq ignored: %r", event)
            continue
        if seq > after:
            events.append(event)
    events.sort(key=_seq)

    for event in events:
        row = None
        try:
            if _already_seen(db, _event_uuid(event.get("event_id"))):
                set_cursor(db, base_url, _seq(event))
                db.commit()
                summary["seen"] += 1
                continue
            row = _handle_event(db, event, template_name)
            row.setdefault("template", template_name)
            _commit_handled(db, base_url, event, row)
        except Exception:  # noqa: BLE001 - cannot record it: stop, cursor stays put
            db.rollback()
            logger.exception(
                "ideation status update: could not record event %s (seq %s)",
                event.get("event_id"),
                _seq(event),
            )
            recorded = False
            if row is not None and row.get("status") == _SUCCESS:
                try:
                    _commit_sent_fallback(db, base_url, event, row)
                    recorded = True
                except Exception:  # noqa: BLE001
                    db.rollback()
                    logger.exception(
                        "ideation status update: event %s was SENT but could not be recorded; "
                        "the next tick may send it again",
                        event.get("event_id"),
                    )
            if not recorded:
                summary["stopped"] = True
                break
        summary[{"success": "sent", "skipped": "skipped", "failed": "failed"}[row["status"]]] += 1
    return summary
