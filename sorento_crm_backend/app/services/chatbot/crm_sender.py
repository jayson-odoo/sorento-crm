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
    # A quick-reply message carries its words in `title`, a plain one in `text`.
    def match(item: dict) -> bool:
        body = _message_body(item)
        return part in (str(body.get("text") or "").strip(), str(body.get("title") or "").strip())

    return match


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


def has_sender_rows(db: Any, turn_id: str) -> bool:
    """Did any sender (n8n or CRM) already try this turn?"""
    from app.models.integration import IntegrationLog

    return (
        db.query(IntegrationLog.id)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == direct_ingress.INTEGRATION_CHANNEL,
        )
        .first()
        is not None
    )


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


def _step_row(turn_id: str, contact_id: str, key: str, kind: str, detail: dict, *, confirmed_by: str | None = None,
              unknown: bool = False) -> dict:
    body = {"sender": "crm", "step": key, "kind": kind, **detail}
    if confirmed_by:
        body["confirmed_by"] = confirmed_by
    if unknown:
        body["unknown"] = True
    return {
        "integration_channel": direct_ingress.INTEGRATION_CHANNEL,
        "business_table": "chatbot.turns",
        "business_id": turn_id,
        "external_reference": contact_id,
        "direction": "outbound",
        "endpoint": f"respond.io:{kind}",
        "http_method": "POST",
        "request_headers": json.dumps({"Content-Type": "application/json"}),
        "request_payload": json.dumps(body, default=str)[: direct_ingress.MAX_LOGGED_BODY_CHARS],
    }


def _write_row(db: Any, base: dict, *, status: str, status_code: int | None = None,
               error: str | None = None, response: Any = None) -> Any:
    """Write one integration_log row; the row, or None when the write failed."""
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService

    try:
        return IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                **base,
                response_payload=json.dumps(response, default=str) if response else None,
                status_code=status_code,
                status=status,
                error_message=error,
            )
        )
    except Exception:  # noqa: BLE001 - a log failure must not raise out of the sender
        db.rollback()
        logger.warning("crm sender: failed to write the integration log", exc_info=True)
        return None


def _drop_stamp(db: Any, stamp: Any) -> None:
    """The result row exists, so the pre-attempt stamp has nothing left to say."""
    if stamp is None:
        return
    try:
        db.delete(stamp)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("crm sender: could not drop a step stamp", exc_info=True)


def _finalise(db: Any, base: dict, stamp: Any, **kw: Any) -> bool:
    """Write the attempt's result row and drop its stamp. False when the result was not written."""
    row = _write_row(db, base, **kw)
    if row is None:
        return False
    _drop_stamp(db, stamp)
    return True


def _prior_attempt(db: Any, turn_id: str, key: str) -> tuple[Any, float | None]:
    """(latest row of this step, its age in seconds by the database clock), or (None, None)."""
    from sqlalchemy import text

    from app.models.integration import IntegrationLog

    rows = (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == direct_ingress.INTEGRATION_CHANNEL,
            IntegrationLog.request_payload.contains('"sender": "crm"'),
        )
        .order_by(IntegrationLog.created_at.desc(), IntegrationLog.id)
        .all()
    )
    for row in rows:
        try:
            body = json.loads(row.request_payload or "{}")
        except ValueError:
            continue
        if str(body.get("step")) != key:
            continue
        unknown = row.status == "processing" or (row.status == "failed" and bool(body.get("unknown")))
        if not unknown:
            return None, None
        age = db.execute(
            text("SELECT EXTRACT(EPOCH FROM (now() - created_at)) FROM integration_log WHERE id = :i"),
            {"i": row.id},
        ).scalar()
        return row, float(age or 0.0)
    return None, None


def last_failure_reason(db: Any, turn_id: str) -> str | None:
    """The plain reason on the turn's latest failed CRM step row."""
    from app.models.integration import IntegrationLog

    row = (
        db.query(IntegrationLog.error_message)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == direct_ingress.INTEGRATION_CHANNEL,
            IntegrationLog.request_payload.contains('"sender": "crm"'),
            IntegrationLog.status == "failed",
        )
        .order_by(IntegrationLog.created_at.desc())
        .first()
    )
    return row[0] if row else None


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
    the chat row) can stamp it. Best effort: the log row already holds the id. Redis and the
    chat row are separate tries: either one failing leaves the other."""
    message_id = response.get("messageId") if isinstance(response, dict) else None
    if message_id in (None, ""):
        return
    try:
        from app.services import queue_service

        queue_service.redis_conn.set(SENT_MSG_KEY.format(message_id), turn_id, ex=SENT_MSG_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("crm sender: could not record message %s in redis", message_id, exc_info=True)
    try:
        from sqlalchemy import text

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


def _kept_response(response: Any) -> dict:
    """What a success row keeps of Respond's answer: the message id and the status, nothing
    of the contact or message body."""
    kept: dict[str, Any] = {}
    if isinstance(response, dict) and response.get("messageId") not in (None, ""):
        kept["messageId"] = response["messageId"]
    kept["status_code"] = 200
    return kept


_NOT_CONFIRMED = "Not confirmed: Respond.io could not be asked whether it arrived."


def send(
    session_factory: Callable[[], Any],
    *,
    turn_id: str,
    contact_id: str,
    actions: list[dict[str, Any]],
    ctx: dict[str, Any] | None = None,
    client: Any = None,
) -> str:
    """Run the actions through Respond.io, resuming past confirmed steps. Never raises.

    Each attempt writes a `processing` stamp first and a result row after (the stamp is then
    dropped), so a process that dies mid-request leaves a stamp the next run looks up."""
    db = session_factory()
    try:
        ident = f"id:{contact_id}"
        if client is None:
            from app.services.integration_service import RespondClient

            # The way the live path builds it for this contact (`direct_ingress._lookup_contact`).
            client = RespondClient.for_identifier(db, contact_id)
        done = confirmed_keys(db, turn_id)
        for step in _steps(actions, ident):
            if step.key in done:
                continue
            base = _step_row(turn_id, contact_id, step.key, step.kind, step.detail)

            # An earlier attempt with an unknown result: ask the conversation before sending again.
            prior, age = _prior_attempt(db, turn_id, step.key)
            if prior is not None and step.matches is not None:
                try:
                    found = _in_conversation(client, ident, step, time.time() - (age or 0.0))
                except Exception:  # noqa: BLE001
                    logger.warning("crm sender: lookup failed for turn %s", turn_id, exc_info=True)
                    if prior.status == "processing":
                        row = _write_row(db, _step_row(turn_id, contact_id, step.key, step.kind, step.detail,
                                                       unknown=True),
                                         status="failed", error=_NOT_CONFIRMED)
                        if row is not None:
                            _drop_stamp(db, prior)
                    return direct_ingress.SEND_TIMEOUT
                if found:
                    # The earlier attempt's own row becomes the confirmed one (no second row).
                    try:
                        body = json.loads(prior.request_payload or "{}")
                        body.pop("unknown", None)
                        body["confirmed_by"] = "lookup"
                        prior.request_payload = json.dumps(body, default=str)
                        prior.status, prior.error_message = "success", None
                        db.commit()
                    except Exception:  # noqa: BLE001
                        db.rollback()
                        logger.warning("crm sender: could not confirm step %s", step.key, exc_info=True)
                        return direct_ingress.SEND_HTTP_ERROR
                    continue

            stamp = _write_row(db, base, status="processing")
            if stamp is None:
                return direct_ingress.SEND_HTTP_ERROR
            if prior is not None and prior.status == "processing":
                _drop_stamp(db, prior)
            attempted_at = time.time()
            response, failure = _attempt(client, step)
            if failure is None:
                if not _finalise(db, base, stamp, status="success", status_code=200, response=_kept_response(response)):
                    return direct_ingress.SEND_HTTP_ERROR
                _link_message_id(db, turn_id, contact_id, response)
                continue
            outcome, code, reason = failure
            if outcome == direct_ingress.SEND_REFUSED:
                _finalise(db, base, stamp, status="failed", status_code=code, error=reason)
                return outcome
            # Unknown: the request may have left.
            unknown_base = _step_row(turn_id, contact_id, step.key, step.kind, step.detail, unknown=True)
            if step.idempotent:
                _finalise(db, unknown_base, stamp, status="failed", status_code=code, error=reason)
                stamp = _write_row(db, base, status="processing")
                response, failure = _attempt(client, step)
                if failure is None:
                    if not _finalise(db, base, stamp, status="success", status_code=200,
                                     response=_kept_response(response)):
                        return direct_ingress.SEND_HTTP_ERROR
                    continue
                _finalise(db, base, stamp, status="failed", status_code=failure[1], error=failure[2])
                return direct_ingress.SEND_REFUSED
            if step.matches is None:
                _finalise(db, unknown_base, stamp, status="failed", status_code=code, error=reason)
                return direct_ingress.SEND_TIMEOUT
            try:
                found = _in_conversation(client, ident, step, attempted_at)
            except Exception:  # noqa: BLE001
                logger.warning("crm sender: lookup failed for turn %s", turn_id, exc_info=True)
                _finalise(db, unknown_base, stamp, status="failed", status_code=code, error=_NOT_CONFIRMED)
                return direct_ingress.SEND_TIMEOUT
            if not found:
                _finalise(db, base, stamp, status="failed", status_code=code, error=reason)
                return direct_ingress.SEND_REFUSED
            if not _finalise(
                db, _step_row(turn_id, contact_id, step.key, step.kind, step.detail, confirmed_by="lookup"),
                stamp, status="success",
            ):
                return direct_ingress.SEND_HTTP_ERROR
        return direct_ingress.SEND_OK
    except Exception:  # noqa: BLE001
        logger.exception("crm sender: unexpected failure for turn %s", turn_id)
        return direct_ingress.SEND_HTTP_ERROR
    finally:
        db.close()
