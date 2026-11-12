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
import struct
import time
from datetime import datetime, timezone
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


# The live n8n sendmsg chunker, ported line for line. Lengths are UTF-16 code units (JavaScript's
# string length) and the byte cap is UTF-8.
BUTTON_PART_MAX_BYTES = 1000
_JS_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
    "\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def _to_units(value: str) -> list[int]:
    raw = value.encode("utf-16-le", "surrogatepass")
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))


def _from_units(units: list[int]) -> str:
    return struct.pack(f"<{len(units)}H", *units).decode("utf-16-le", "surrogatepass")


def _utf8_len(units: list[int]) -> int:
    return len(_from_units(units).encode("utf-8", "surrogatepass"))


def _trim_units(units: list[int]) -> list[int]:
    return _to_units(_from_units(units).strip(_JS_WHITESPACE))


def _last_index(units: list[int], ch: str, start: int) -> int:
    """JavaScript `lastIndexOf(ch, start)`: the match may sit AT `start`."""
    for i in range(min(start, len(units) - 1), -1, -1):
        if units[i] == ord(ch):
            return i
    return -1


def split_text(text: str, *, with_quick_replies: bool) -> list[str]:
    """Cut a reply into the parts n8n's sendmsg would send, part for part."""
    limit, floor = (QUICK_REPLY_PART_MAX_CHARS, 450) if with_quick_replies else (TEXT_PART_MAX_CHARS, 800)
    byte_cap = BUTTON_PART_MAX_BYTES if with_quick_replies else None

    def too_big(units: list[int]) -> bool:
        return len(units) > limit or (byte_cap is not None and _utf8_len(units) > byte_cap)

    rest = _trim_units(_to_units(text or ""))
    parts: list[str] = []
    while too_big(rest):
        lim = min(limit, len(rest))
        while byte_cap is not None and lim > 1 and _utf8_len(rest[:lim]) > byte_cap:
            lim = int(lim * 0.9)
        at = _last_index(rest, "\n", lim)
        if at < floor:
            at = _last_index(rest, " ", lim)
        if at < floor:
            at = lim
        if 0 < at < len(rest) and 0xD800 <= rest[at - 1] <= 0xDBFF:
            at -= 1
        parts.append(_from_units(_trim_units(rest[:at])))
        rest = _trim_units(rest[at:])
    if rest:
        parts.append(_from_units(rest))
    return [p for p in parts if p]


MAX_BUTTONS = 10


def _button_labels(raw: Any) -> list[str]:
    """Quick-reply labels: split on commas, trimmed (agreed difference from n8n, which keeps a
    leading space on buttons 2..n), empty ones dropped, at most 10."""
    items = raw.split(",") if isinstance(raw, str) else (raw or [])
    return [s for s in (str(i).strip() for i in items) if s][:MAX_BUTTONS]


FAILURE_REPLY_TEXT = (
    "Sorry, I couldn't process that just now \u2014 something went wrong on our side. "
    "Please try again in a moment."
)


def _attachment_list(raw: Any) -> list[dict[str, Any]]:
    """`attachments_src` is a list, or an envelope `{"attachments": [...]}`; urls are sent once."""
    items = raw.get("attachments") if isinstance(raw, dict) else raw
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for att in items if isinstance(items, list) else []:
        url = att.get("url") if isinstance(att, dict) else None
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(att)
    return out


def _presign(db: Any, url: str, filename: str | None = None) -> str:
    """A one hour signed copy of a `cdn-sorento` url, in process, through the storage path the
    /external/presigned-url route uses. Any other url, or a signing failure, gives the url back
    (agreed difference: n8n drops the file on a failure, the customer still gets it here)."""
    if "cdn-sorento" not in (url or ""):
        return url
    try:
        from app.api.v1.external.presigned_url import _normalize_to_s3_key, _provider_for_attachment, _resolve_attachment
        from app.services import storage_router

        key = _normalize_to_s3_key(url)
        provider = _provider_for_attachment(_resolve_attachment(db, url, key), url)
        signed = storage_router.resolve_signed_url(key, provider=provider, expires_in=PRESIGN_SECONDS, strict=True)
        return signed or url
    except Exception:  # noqa: BLE001
        logger.warning("crm sender: could not presign a file", exc_info=True)
        return url


PRESIGN_SECONDS = 3600


class _Lazy:
    """The presigned url, worked out once and only when a step actually runs."""

    def __init__(self, make: Callable[[], str]):
        self._make, self._value = make, None

    def get(self) -> str:
        if self._value is None:
            self._value = self._make()
        return self._value


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
    # A file respond.io refuses is sent as this bare link instead (text), and the run goes on.
    link: Callable[[], str] | None = None


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


def _steps(
    actions: list[dict[str, Any]],
    ident: str,
    prefix: str = "",
    presign: Callable[[str], str] | None = None,
) -> list[Step]:
    """The steps, in action order. `prefix` keeps a side message (the failure reply) off the
    turn's own step keys; `presign` signs a file url when its step runs."""
    steps: list[Step] = []
    for a, action in enumerate(actions):
        kind = action.get("kind")
        if action.get("dry_run"):
            continue
        if kind == "send_message":
            replies = _button_labels(action.get("quick_replies"))
            parts = split_text(str(action.get("text") or ""), with_quick_replies=bool(replies))
            for p, part in enumerate(parts):
                if replies and p == len(parts) - 1:
                    steps.append(Step(f"{prefix}{a}.{p}", kind, {"text": part, "replies": replies},
                                      lambda c, t=part, r=replies: c.send_quick_reply(ident, t, r),
                                      _text_is(part)))
                else:
                    steps.append(Step(f"{prefix}{a}.{p}", kind, {"text": part},
                                      lambda c, t=part: c.send_message(ident, t), _text_is(part)))
        elif kind == "send_attachments":
            for p, att in enumerate(_attachment_list(action.get("attachments_src"))):
                kind_, url, cap = _attachment_type(att), att.get("url"), att.get("caption")
                name = att.get("filename")
                signed = _Lazy(lambda u=url, n=name: presign(u, n) if presign else u)
                # A video travels with its original url; image and file with the signed one.
                send_url = (lambda u=url: u) if kind_ == "video" else signed.get
                steps.append(Step(f"{prefix}{a}.{p}", action.get("kind"), {"attachment_type": kind_, "url": url},
                                  lambda c, k=kind_, f=send_url, cp=cap, n=name: c.send_attachment(
                                      ident, k, f(), cp, filename=n),
                                  _url_is(url), link=signed.get))
        elif kind == "assign_conversation":
            uid = action.get("respond_user_id")
            if uid is None or not str(uid).strip():
                continue  # n8n errors on an empty id; here it is never sent
            steps.append(Step(f"{prefix}{a}.0", kind, {"respond_user_id": uid},
                              lambda c, u=uid: c.set_conversation_assignee(ident, u), idempotent=True))
        elif kind == "add_comment":
            mentions = " ".join(f"{{{{@user.{m}}}}}" for m in action.get("mention_user_ids") or [])
            body = f"{mentions}\n{action.get('text') or ''}" if mentions else str(action.get("text") or "")
            steps.append(Step(f"{prefix}{a}.0", kind, {"text": body},
                              lambda c, b=body: c.create_comment(ident, b)))
        # update_contact_fields sends nothing in n8n, so nothing here; unknown kinds are skipped too.
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


def _step_row(turn_id: str, contact_id: str, key: str, kind: str, detail: dict, *, attempted_at: str,
              confirmed_by: str | None = None, unknown: bool = False) -> dict:
    # `attempted_at` is the ORIGINAL attempt's time, copied unchanged onto every later row of
    # the step: the lookup window starts there, never at a later row's own time.
    body = {"sender": "crm", "step": key, "kind": kind, "attempted_at": attempted_at, **detail}
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
    """(latest row of this step when its outcome is unknown, the ORIGINAL attempt's epoch), else
    (None, None). Unknown = a `processing` stamp with no result, or a failure flagged unknown."""
    from datetime import datetime, timezone

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
        try:
            at = datetime.fromisoformat(str(body["attempted_at"]))
            at = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at
            return row, at.timestamp()
        except (KeyError, ValueError):
            created = row.created_at
            return row, (created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created).timestamp()
    return None, None


def last_failure_reason(db: Any, turn_id: str, since: Any = None) -> str | None:
    """The plain reason on the turn's latest failed CRM step row (only rows from `since` on)."""
    from app.models.integration import IntegrationLog

    row = (
        db.query(IntegrationLog.error_message)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == direct_ingress.INTEGRATION_CHANNEL,
            IntegrationLog.request_payload.contains('"sender": "crm"'),
            IntegrationLog.status == "failed",
            *([IntegrationLog.created_at >= since] if since is not None else []),
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
    step_prefix: str = "",
) -> str:
    """Run the actions through Respond.io, resuming past confirmed steps. Never raises.

    Each attempt writes a `processing` stamp first and a result row after (the stamp is then
    dropped), so a process that dies mid-request leaves a stamp the next run looks up."""
    if not str(turn_id or "").strip() or not str(contact_id or "").strip():
        return direct_ingress.SEND_REFUSED  # n8n throws without either id; nothing is sent
    if any(isinstance(a, dict) and a.get("dry_run") for a in actions or []):
        return direct_ingress.SEND_OK  # n8n drops the whole body when any action is a dry run
    db = session_factory()
    try:
        ident = f"id:{contact_id}"
        if client is None:
            from app.services.integration_service import RespondClient

            # The way the live path builds it for this contact (`direct_ingress._lookup_contact`).
            client = RespondClient.for_identifier(db, contact_id)
        done = confirmed_keys(db, turn_id)
        for step in _steps(actions, ident, step_prefix, lambda u, n=None: _presign(db, u) if "cdn-sorento" in (u or "") else u):
            if step.key in done:
                continue
            # An earlier attempt with an unknown result: ask the conversation before sending again.
            prior, prior_at = _prior_attempt(db, turn_id, step.key)
            attempted_at = prior_at if prior_at is not None else time.time()
            iso = datetime.fromtimestamp(attempted_at, timezone.utc).isoformat()

            def row_for(**kw: Any) -> dict:
                return _step_row(turn_id, contact_id, step.key, step.kind, step.detail, attempted_at=iso, **kw)

            base = row_for()

            if prior is not None and step.matches is not None:
                try:
                    found = _in_conversation(client, ident, step, attempted_at)
                except Exception:  # noqa: BLE001
                    logger.warning("crm sender: lookup failed for turn %s", turn_id, exc_info=True)
                    if prior.status == "processing":
                        row = _write_row(db, row_for(unknown=True),
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
            response, failure = _attempt(client, step)
            if failure is None:
                if not _finalise(db, base, stamp, status="success", status_code=200, response=_kept_response(response)):
                    return direct_ingress.SEND_HTTP_ERROR
                _link_message_id(db, turn_id, contact_id, response)
                continue
            outcome, code, reason = failure
            if outcome == direct_ingress.SEND_REFUSED:
                _finalise(db, base, stamp, status="failed", status_code=code, error=reason)
                if step.link is None or code is None:
                    return outcome
                # A file respond.io refused goes out as its bare link (n8n does the same); a
                # connection failure is not turned into a link, the drain retries it.
                stamp = _write_row(db, base, status="processing")
                if stamp is None:
                    return direct_ingress.SEND_HTTP_ERROR
                link = step.link()
                response, failure = _attempt(client, step._replace(call=lambda c, u=link: c.send_message(ident, u)))
                if failure is None:
                    if not _finalise(db, base, stamp, status="success", status_code=200,
                                     response=_kept_response(response)):
                        return direct_ingress.SEND_HTTP_ERROR
                    _link_message_id(db, turn_id, contact_id, response)
                    continue
                _finalise(db, row_for(unknown=failure[0] != direct_ingress.SEND_REFUSED), stamp, status="failed",
                          status_code=failure[1], error=failure[2])
                return failure[0]
            # Unknown: the request may have left.
            unknown_base = row_for(unknown=True)
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
                db, row_for(confirmed_by="lookup"),
                stamp, status="success",
            ):
                return direct_ingress.SEND_HTTP_ERROR
        return direct_ingress.SEND_OK
    except Exception:  # noqa: BLE001
        logger.exception("crm sender: unexpected failure for turn %s", turn_id)
        return direct_ingress.SEND_HTTP_ERROR
    finally:
        db.close()
