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
import time
from typing import Any, Callable, NamedTuple

import httpx

from app.services.chatbot import direct_ingress

logger = logging.getLogger(__name__)

# How long before a step's first attempt a message may have been created and still be that step's.
LOOKUP_SLACK_SECONDS = 5
SENT_MSG_KEY = "chatbot:sent-msg:{}"
SENT_MSG_TTL_SECONDS = 24 * 3600

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


class Step(NamedTuple):
    key: str
    kind: str
    detail: dict
    call: Callable[[Any], Any]
    # An unknown outcome on a message step is looked up in the conversation with this test.
    matches: Callable[[dict], bool] | None = None
    # Assign and contact fields can simply be sent again.
    idempotent: bool = False


def covers(row: Any, contact_id: str) -> bool:
    """Does the "Bot replies sent by" switch put this contact on the CRM sender?"""
    mode = str(getattr(row, "chatbot_reply_sender_mode", None) or "n8n")
    listed = direct_ingress.listed_contacts(getattr(row, "chatbot_reply_sender_contacts", None))
    return mode == "all" or (mode == "contacts" and contact_id in listed)


def _message_body(item: dict) -> dict:
    inner = item.get("message")
    return inner if isinstance(inner, dict) else {}


def _text_is(part: str) -> Callable[[dict], bool]:
    return lambda item: str(_message_body(item).get("text") or "").strip() == part


def _url_is(url: Any) -> Callable[[dict], bool]:
    def match(item: dict) -> bool:
        att = _message_body(item).get("attachment")
        return isinstance(att, dict) and att.get("url") == url

    return match


def _steps(actions: list[dict[str, Any]], ident: str) -> list[Step]:
    """The steps, in action order."""
    steps: list[Step] = []
    for a, action in enumerate(actions):
        kind = action.get("kind")
        if action.get("dry_run"):
            continue
        if kind == "send_message":
            replies = _reply_list(action.get("quick_replies"))
            parts = split_text(str(action.get("text") or ""), with_quick_replies=bool(replies))
            for p, part in enumerate(parts):
                if replies and p == len(parts) - 1:
                    steps.append(Step(f"{a}.{p}", kind, {"text": part, "replies": replies},
                                      lambda c, t=part, r=replies: c.send_quick_reply(ident, t, r),
                                      _text_is(part)))
                else:
                    steps.append(Step(f"{a}.{p}", kind, {"text": part},
                                      lambda c, t=part: c.send_message(ident, t), _text_is(part)))
        elif kind == "send_attachments":
            for p, att in enumerate(action.get("attachments_src") or []):
                kind_, url, cap = _attachment_type(att), att.get("url"), att.get("caption")
                steps.append(Step(f"{a}.{p}", kind, {"attachment_type": kind_, "url": url},
                                  lambda c, k=kind_, u=url, cp=cap: c.send_attachment(ident, k, u, cp),
                                  _url_is(url)))
        elif kind == "assign_conversation":
            uid = action.get("respond_user_id")
            steps.append(Step(f"{a}.0", kind, {"respond_user_id": uid},
                              lambda c, u=uid: c.set_conversation_assignee(ident, u), idempotent=True))
        elif kind == "add_comment":
            mentions = " ".join(f"{{{{@user.{m}}}}}" for m in action.get("mention_user_ids") or [])
            body = f"{mentions}\n{action.get('text') or ''}" if mentions else str(action.get("text") or "")
            steps.append(Step(f"{a}.0", kind, {"text": body},
                              lambda c, b=body: c.create_comment(ident, b)))
        elif kind == "update_contact_fields":
            fields = action.get("fields") or {}
            payload = {"custom_fields": [{"name": k, "value": v} for k, v in fields.items()]}
            steps.append(Step(f"{a}.0", kind, {"fields": fields},
                              lambda c, pl=payload: c.update_contact(ident, pl), idempotent=True))
        # Unknown kinds are skipped, as the n8n sender does.
    return steps


def confirmed_keys(db: Any, turn_id: str) -> set[str]:
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


def has_crm_rows(db: Any, turn_id: str) -> bool:
    """Did the CRM sender already start this turn? Then it finishes on this path."""
    from app.models.integration import IntegrationLog

    return (
        db.query(IntegrationLog.id)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == direct_ingress.INTEGRATION_CHANNEL,
            IntegrationLog.request_payload.contains('"sender": "crm"'),
        )
        .first()
        is not None
    )


def all_confirmed(db: Any, turn_id: str, actions: list[dict[str, Any]]) -> bool:
    """Is every step of these actions confirmed sent? Recovery counts a CRM row done only then."""
    return {st.key for st in _steps(actions, "")} <= confirmed_keys(db, turn_id)


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
    confirmed_by: str | None = None,
) -> None:
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService

    body = {"sender": "crm", "step": key, "kind": kind, **detail}
    if confirmed_by:
        body["confirmed_by"] = confirmed_by
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


def _link_message_id(db: Any, turn_id: str, contact_id: str, response: Any) -> None:
    """Tie the id Respond returned to the turn, so the `message.sent` webhook (the one writer of
    the chat row) can stamp it. Best effort: the log row already holds the id."""
    message_id = response.get("messageId") if isinstance(response, dict) else None
    if message_id in (None, ""):
        return
    try:
        from sqlalchemy import text

        from app.services import queue_service

        queue_service.redis_conn.set(SENT_MSG_KEY.format(message_id), turn_id, ex=SENT_MSG_TTL_SECONDS)
        # The webhook row may have landed before this send returned.
        db.execute(
            text(
                "UPDATE chat_histories SET chatbot_turn_id = :t WHERE contact_id = :c "
                "AND message_id = :m AND chatbot_turn_id IS NULL"
            ),
            {"t": turn_id, "c": contact_id, "m": str(message_id)},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("crm sender: could not link message %s to turn %s", message_id, turn_id, exc_info=True)


def _in_conversation(client: Any, ident: str, step: Step, attempted_at: float) -> bool:
    """Is there an OUTGOING message of this step's, created since just before it was tried?"""
    payload = client.list_messages(ident, limit=20) or {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("data") or []
    window = time.time() - attempted_at + LOOKUP_SLACK_SECONDS
    for item in items:
        if not isinstance(item, dict) or str(item.get("traffic") or "").lower() != "outgoing":
            continue
        age = direct_ingress.message_age_seconds(item)
        if age is not None and age <= window and step.matches(item):
            return True
    return False


def _attempt(client: Any, step: Step) -> tuple[Any, tuple[str, int | None, str] | None]:
    """(response, None) when sent, else (None, (outcome, status, reason))."""
    try:
        return step.call(client), None
    except Exception as exc:  # noqa: BLE001 - classified, never propagated
        logger.warning("crm sender: step %s failed: %s", step.key, exc)
        return None, _classify(exc)


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
        done = confirmed_keys(db, turn_id)
        for step in _steps(actions, ident):
            if step.key in done:
                continue
            log = lambda **kw: _log_step(db, turn_id, contact_id, step.key, step.kind, step.detail, **kw)  # noqa: E731
            attempted_at = time.time()
            response, failure = _attempt(client, step)
            if failure is None:
                log(status_code=200, error=None, response=response)
                _link_message_id(db, turn_id, contact_id, response)
                continue
            outcome, code, reason = failure
            if outcome == direct_ingress.SEND_REFUSED:
                log(status_code=code, error=reason)
                return outcome
            # Unknown: the request may have left.
            if step.idempotent:
                log(status_code=code, error=reason)
                response, failure = _attempt(client, step)
                if failure is None:
                    log(status_code=200, error=None, response=response)
                    continue
                log(status_code=failure[1], error=failure[2])
                return direct_ingress.SEND_REFUSED
            if step.matches is None:
                log(status_code=code, error=reason)
                return direct_ingress.SEND_TIMEOUT
            try:
                found = _in_conversation(client, ident, step, attempted_at)
            except Exception:  # noqa: BLE001
                logger.warning("crm sender: lookup failed for turn %s", turn_id, exc_info=True)
                log(status_code=code, error="Not confirmed: Respond.io could not be asked whether it arrived.")
                return direct_ingress.SEND_TIMEOUT
            if not found:
                log(status_code=code, error=reason)
                return direct_ingress.SEND_REFUSED
            log(status_code=None, error=None, confirmed_by="lookup")
        return direct_ingress.SEND_OK
    except Exception:  # noqa: BLE001
        logger.exception("crm sender: unexpected failure for turn %s", turn_id)
        return direct_ingress.SEND_HTTP_ERROR
    finally:
        db.close()
