"""N8N-RETIRE-A: the CRM executes a turn's send actions itself, in place of the n8n sender.

Each action becomes one or more steps (a long text is several). Every attempted step writes one
`integration_log` row under the same channel the n8n POST uses, so the trace screen and recovery
keep reading one place. A step with a `success` row is confirmed and never sent again, which is
what lets a retry resume at the first step not yet delivered.
Plan: documentation/plans/chatbot/PLAN-n8n-retire-a-bot-reply-12nov.md section 4b.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

from app.services.chatbot import direct_ingress

logger = logging.getLogger(__name__)

TEXT_PART_MAX_CHARS = 3900
QUICK_REPLY_PART_MAX_CHARS = 1024
_ATTACHMENT_TYPES = ("image", "video", "audio", "file")


def split_text(text: str, *, with_quick_replies: bool) -> list[str]:
    """Cut a reply to the n8n sendmsg chunk rule: paragraphs first, then lines, then a hard cut."""
    limit = QUICK_REPLY_PART_MAX_CHARS if with_quick_replies else TEXT_PART_MAX_CHARS
    parts = [p.strip() for p in _cut(text or "", limit, ("\n\n", "\n"))]
    return [p for p in parts if p]


def _cut(text: str, limit: int, seps: tuple[str, ...]) -> list[str]:
    if len(text) <= limit:
        return [text]
    if not seps:
        return [text[i : i + limit] for i in range(0, len(text), limit)]
    sep, rest = seps[0], seps[1:]
    units: list[str] = []
    for unit in text.split(sep):
        units.extend(_cut(unit, limit, rest))
    out: list[str] = []
    cur = ""
    for unit in units:
        joined = f"{cur}{sep}{unit}" if cur else unit
        if len(joined) <= limit:
            cur = joined
        else:
            out.append(cur)
            cur = unit
    if cur:
        out.append(cur)
    return out


def _reply_list(raw: Any) -> list[str]:
    items = raw.split(",") if isinstance(raw, str) else (raw or [])
    return [s for s in (str(i).strip() for i in items) if s]


def _attachment_type(att: dict[str, Any]) -> str:
    declared = str(att.get("attachmentType") or "").lower()
    if declared in _ATTACHMENT_TYPES:
        return declared
    major = str(att.get("mimeType") or "").split("/", 1)[0].lower()
    return major if major in ("image", "video", "audio") else "file"


def _steps(actions: list[dict[str, Any]], ident: str) -> list[tuple[str, str, dict, Callable]]:
    """(step key, kind, loggable detail, call(client)) in action order."""
    steps: list[tuple[str, str, dict, Callable]] = []
    for a, action in enumerate(actions):
        kind = action.get("kind")
        if action.get("dry_run"):
            continue
        if kind == "send_message":
            replies = _reply_list(action.get("quick_replies"))
            parts = split_text(str(action.get("text") or ""), with_quick_replies=bool(replies))
            for p, part in enumerate(parts):
                if replies and p == len(parts) - 1:
                    steps.append((f"{a}.{p}", kind, {"text": part, "replies": replies},
                                  lambda c, t=part, r=replies: c.send_quick_reply(ident, t, r)))
                else:
                    steps.append((f"{a}.{p}", kind, {"text": part},
                                  lambda c, t=part: c.send_message(ident, t)))
        elif kind == "send_attachments":
            for p, att in enumerate(action.get("attachments_src") or []):
                kind_, url, cap = _attachment_type(att), att.get("url"), att.get("caption")
                steps.append((f"{a}.{p}", kind, {"attachment_type": kind_, "url": url},
                              lambda c, k=kind_, u=url, cp=cap: c.send_attachment(ident, k, u, cp)))
        elif kind == "assign_conversation":
            uid = action.get("respond_user_id")
            steps.append((f"{a}.0", kind, {"respond_user_id": uid},
                          lambda c, u=uid: c.set_conversation_assignee(ident, u)))
        elif kind == "add_comment":
            mentions = " ".join(f"{{{{@user.{m}}}}}" for m in action.get("mention_user_ids") or [])
            body = f"{mentions}\n{action.get('text') or ''}" if mentions else str(action.get("text") or "")
            steps.append((f"{a}.0", kind, {"text": body},
                          lambda c, b=body: c.create_comment(ident, b)))
        elif kind == "update_contact_fields":
            fields = action.get("fields") or {}
            payload = {"custom_fields": [{"name": k, "value": v} for k, v in fields.items()]}
            steps.append((f"{a}.0", kind, {"fields": fields},
                          lambda c, pl=payload: c.update_contact(ident, pl)))
        # Unknown kinds are skipped, as the n8n sender does.
    return steps


def _confirmed_keys(db: Any, turn_id: str) -> set[str]:
    from app.models.integration import IntegrationLog

    rows = (
        db.query(IntegrationLog.request_payload)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == direct_ingress.INTEGRATION_CHANNEL,
            IntegrationLog.status == "success",
        )
        .all()
    )
    keys: set[str] = set()
    for (raw,) in rows:
        try:
            body = json.loads(raw or "{}")
        except ValueError:
            continue
        if body.get("sender") == "crm" and body.get("step"):
            keys.add(str(body["step"]))
    return keys


def _log_step(
    db: Any,
    turn_id: str,
    contact_id: str,
    key: str,
    kind: str,
    detail: dict,
    *,
    status_code: int | None,
    error: str | None,
    response: Any = None,
) -> None:
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService

    body = {"sender": "crm", "step": key, "kind": kind, **detail}
    try:
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel=direct_ingress.INTEGRATION_CHANNEL,
                business_table="chatbot.turns",
                business_id=turn_id,
                external_reference=contact_id,
                direction="outbound",
                endpoint=f"respond.io:{kind}",
                http_method="POST",
                request_headers=json.dumps({"Content-Type": "application/json"}),
                request_payload=json.dumps(body, default=str)[: direct_ingress.MAX_LOGGED_BODY_CHARS],
                response_payload=json.dumps(response, default=str)[:4000] if response else None,
                status_code=status_code,
                status="success" if error is None else "failed",
                error_message=error,
            )
        )
    except Exception:  # noqa: BLE001 - a log failure must not turn a sent message into a failure
        db.rollback()
        logger.warning("crm sender: failed to write the integration log", exc_info=True)


def _classify(exc: Exception) -> tuple[str, int | None, str]:
    """(SEND_REFUSED | SEND_TIMEOUT, HTTP status, plain reason) for a failed step."""
    from app.services.error_handler import AppException

    if isinstance(exc, AppException):
        return direct_ingress.SEND_REFUSED, None, "Messages to this contact are switched off."
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if 400 <= code < 500 and code != 408:
            return direct_ingress.SEND_REFUSED, code, f"Respond.io refused the request (HTTP {code})."
        return direct_ingress.SEND_TIMEOUT, code, f"Respond.io did not confirm the request (HTTP {code})."
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, ValueError)):
        return direct_ingress.SEND_REFUSED, None, "Respond.io could not be reached; nothing was sent."
    return direct_ingress.SEND_TIMEOUT, None, "Respond.io did not confirm the request."


def send(
    session_factory: Callable[[], Any],
    *,
    turn_id: str,
    contact_id: str,
    actions: list[dict[str, Any]],
    ctx: dict[str, Any] | None = None,
    client: Any = None,
) -> str:
    """Run the actions through Respond.io, resuming past confirmed steps. Never raises."""
    db = session_factory()
    try:
        ident = f"id:{contact_id}"
        if client is None:
            from app.services.integration_service import RespondClient

            client = RespondClient.for_identifier(db, ident)
        done = _confirmed_keys(db, turn_id)
        for key, kind, detail, call in _steps(actions, ident):
            if key in done:
                continue
            try:
                response = call(client)
            except Exception as exc:  # noqa: BLE001 - classified below, never propagated
                outcome, code, reason = _classify(exc)
                logger.warning("crm sender: turn %s step %s failed: %s", turn_id, key, exc)
                _log_step(db, turn_id, contact_id, key, kind, detail, status_code=code, error=reason)
                return outcome
            _log_step(db, turn_id, contact_id, key, kind, detail,
                      status_code=200, error=None, response=response)
        return direct_ingress.SEND_OK
    except Exception:  # noqa: BLE001
        logger.exception("crm sender: unexpected failure for turn %s", turn_id)
        return direct_ingress.SEND_HTTP_ERROR
    finally:
        db.close()
