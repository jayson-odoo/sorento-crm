"""Dealer writes on WhatsApp (AGENTIC-WA-W2 slice 1, plan `PLAN-agentic-wa-w2-01nov.md`).

A contact principal (no linked CRM user) gets the writes a dealer makes on the contact portal, through the
portal's OWN service calls under a transient, never-persisted `PortalToken` of the contact (the pattern of
`api/v1/my_requests.py`). The portal's checks are the permission model, so nothing here reads a user slug:

- the form switch per contact (`portal_form_visibility_service.require_form_visible`);
- the row is the contact's own (contact id + space id of the token, in every service read);
- the portal's required fields on submit.

Every write is proposed first and runs on the contact's next-turn "yes" (`actions.confirm`); a console turn
writes nothing (owner W2-Q3 (a)). Each write has an undo: a note is removed, and a stock inquiry is withdrawn
within `WITHDRAW_MINUTES` of its submit while no staff member has touched it (W2-Q2 (a)).
"""
from __future__ import annotations

import html
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from app.services.chatbot.agent.tools import ToolResult, _collect_uuids, cap_result
from app.services.chatbot.agent.writes import MAX_NOTE_CHARS, UserRead, WriteDef, _diff, _line, _route_failure

LIST = "crm_my_requests_list"
NOTE_ADD = "crm_my_request_note_add"
NOTE_REMOVE = "crm_my_request_note_remove"
SI_CREATE = "crm_stock_inquiry_create"
SI_WITHDRAW = "crm_stock_inquiry_withdraw"
# AGENTIC-WA-S2: a warranty / complaint claim with the dealer's chat photos.
CHAT_PHOTOS = "crm_my_chat_photos"
CP_CREATE = "crm_complaint_create"
CP_WITHDRAW = "crm_complaint_withdraw"
CP_PHOTOS_ADD = "crm_complaint_photos_add"
CP_PHOTO_REMOVE = "crm_complaint_photo_remove"
COMPLAINT = "complaint"
#: S2-Q5 (owner pending). "allow": a second open claim on the same DO and product goes through and its confirm
#: line names the earlier one. "refuse": refused at proposal with the note offer. One word either way.
DUPLICATE_CLAIMS = "allow"
#: The chat photos a claim may carry: the newest of the last day (S2-Q1 (a): only what the bot stored).
PHOTO_WINDOW_HOURS = 24
MAX_CHAT_PHOTOS = 10
#: `app.tasks.media_tasks.CHATBOT_MEDIA_ATTACHMENT_TYPE_CODE`, the type the media lane stores photos under.
CHAT_MEDIA_TYPE = "chatbot_media"
COULD_NOT_READ = "could not be read"
_BUSINESS_TZ = ZoneInfo("Asia/Kuala_Lumpur")

STOCK_INQUIRY = "stock_inquiry"
#: The portal's comment kinds (`portal_service.SUPPORTED_TYPES`), in the order the list shows them.
NOTE_KINDS = ("stock_inquiry", "complaint", "purchase_request", "sponsorship_form")
KIND_WORDS = {
    "stock_inquiry": "stock inquiry",
    "complaint": "complaint",
    "purchase_request": "purchase request",
    "sponsorship_form": "sponsorship form",
}
WITHDRAW_MINUTES = 10
MAX_LIST_ROWS = 20
MAX_OWN_NOTES = 5
TEST_NOTE = "Test turn: nothing was sent."
WITHDRAW_REFUSED = "It is with the team now, so I can't withdraw it. I can add a note to it instead."
_TOKEN_NAMESPACE = uuid.UUID("5f0b9a3e-6c1d-4e7a-9b2f-0a2c0000a002")
_TAGS = re.compile(r"<[^>]+>")


# ------------------------------------------------------------------ the contact's portal token


def _token(ctx):
    """The contact's portal identity for this call: transient, never added to the session."""
    from app.models.portal import PortalToken

    return PortalToken(
        id=str(uuid.uuid5(_TOKEN_NAMESPACE, str(ctx.contact_pk))),
        contact_id=str(ctx.contact_pk),
        space_id=ctx.space_id,
        is_impersonation=False,
    )


def run_as_contact(db, ctx, fn, *, tool_name: str | None = None) -> Any:
    """`fn(token)` under the contact's portal company scope and the contact as the audit actor. The previous
    scope comes back even when `fn` raises."""
    from app.audit_context import AuditActor, actor_scope
    from app.models.base import get_company_scope, set_company_scope
    from app.services.company_scope_resolver import portal_contact_scope

    actor = AuditActor(actor_type="contact", auth_method="agent", contact_id=str(ctx.contact_pk), tool_name=tool_name)
    previous = get_company_scope(db)
    set_company_scope(db, portal_contact_scope(db, str(ctx.contact_pk)))
    try:
        with actor_scope(actor, db=db):
            return fn(_token(ctx))
    finally:
        set_company_scope(db, previous)


# ------------------------------------------------------------------ who is offered what


def _kinds_for(db, contact_pk: str, contact_respond_id: str) -> set[str]:
    """The portal kinds a contact may use here: none when its respond.io id sits on more than one contact row
    (a namesake row fails closed, as W1's reads do)."""
    from app.services.chatbot.agent.access import _row_count
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    if not contact_pk or _row_count(db, contact_respond_id) > 1:
        return set()
    return set(resolve_visible_form_types(db, str(contact_pk))) & set(NOTE_KINDS)


def _visible_kinds(db, ctx) -> set[str]:
    """`_kinds_for` of the context's contact; none for a user principal (slice 1)."""
    if getattr(ctx, "principal", "user") != "contact":
        return set()
    return _kinds_for(db, ctx.contact_pk, ctx.contact_respond_id)


def _open_names(kinds: set[str]) -> list[str]:
    names = [LIST, NOTE_ADD, NOTE_REMOVE] if kinds else []
    if STOCK_INQUIRY in kinds:
        names += [SI_CREATE, SI_WITHDRAW]
    if COMPLAINT in kinds:
        names += [CHAT_PHOTOS, CP_CREATE, CP_WITHDRAW, CP_PHOTOS_ADD, CP_PHOTO_REMOVE]
    return names


def offered(db, ctx) -> list[str]:
    """The dealer tools this context may use, in a fixed order; [] for a user principal (slice 1)."""
    return _open_names(_visible_kinds(db, ctx))


def offered_for_contact(db, contact_respond_id: str) -> list[str]:
    """`offered` for the router, which has no agent context: the same rule from the contact row. Reads only:
    it stamps no session scope (the turn may still go to the bot)."""
    from app.services.chatbot.agent.access import eligible_contact

    contact, user, refusal = eligible_contact(db, contact_respond_id)
    if refusal is not None or contact is None or user is not None:
        return []
    return _open_names(_kinds_for(db, str(contact.id), contact_respond_id))


def may_use(db, ctx, name: str) -> bool:
    return name in offered(db, ctx)


def is_portal_tool(name: Any) -> bool:
    return isinstance(name, str) and (name in PORTAL_WRITES or name in PORTAL_READS)


# ------------------------------------------------------------------ shared reads


def _require_kind(db, token, kind: Any) -> str:
    from app.services.error_handler import handle_validation_error
    from app.services.portal_form_visibility_service import require_form_visible

    if kind not in NOTE_KINDS:
        raise handle_validation_error(f"kind must be one of: {', '.join(NOTE_KINDS)}.")
    require_form_visible(db, token.contact_id, kind)
    return kind


def _number(db, kind: str, row) -> str:
    from app.services.form_comment_service import FormCommentService

    return FormCommentService(db)._number(kind, row) or "(no number)"


def _plain_text(body: Any) -> str:
    return html.unescape(_TAGS.sub(" ", str(body or ""))).strip()


def _own_notes(db, kind: str, entity_id: str, contact_id: str) -> list[dict]:
    from app.models.entity_conversation import EntityConversationMessage as Msg
    from app.services.form_comment_service import FORM_COMMENT_SCOPE

    rows = (
        db.query(Msg)
        .filter(
            Msg.scope == FORM_COMMENT_SCOPE, Msg.entity_type == kind, Msg.entity_id == str(entity_id),
            Msg.author_contact_id == str(contact_id), Msg.deleted_at.is_(None),
        )
        .order_by(Msg.created_at.desc(), Msg.id.desc())
        .limit(MAX_OWN_NOTES)
        .all()
    )
    return [
        {"id": str(m.id), "text": _plain_text(m.body_html)[:300], "at": m.created_at.isoformat() if m.created_at else None}
        for m in rows
    ]


def _my_requests(db, ctx, args: dict) -> ToolResult:
    from app.services.portal_service import PortalService

    unknown = sorted(k for k in args if k not in ("kind", "search"))
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    kinds = _visible_kinds(db, ctx)
    wanted = args.get("kind")
    if wanted is not None:
        if wanted not in NOTE_KINDS:
            return ToolResult("invalid", message=f"kind must be one of: {', '.join(NOTE_KINDS)}.")
        if wanted not in kinds:
            return ToolResult("denied", message=f"The {KIND_WORDS[wanted]} form is not available for this customer.")
        kinds = {wanted}
    search = args.get("search")
    if search is not None and not isinstance(search, str):
        return ToolResult("invalid", message="search must be text.")

    def read(token) -> list[dict]:
        service = PortalService(db)
        rows: list[dict] = []
        for kind in (k for k in NOTE_KINDS if k in kinds):
            for item in service.list_submissions(token, kind, q=search):
                if item.get("is_draft"):
                    continue
                rows.append({
                    "kind": kind,
                    "id": item.get("id"),
                    "number": item.get("document_number") or item.get("reference"),
                    "status": item.get("status"),
                    "product_code": item.get("product_code"),
                    "title": item.get("title"),
                    "submitted": item.get("created_at"),
                    "my_notes": _own_notes(db, kind, item.get("id"), token.contact_id),
                    **({"my_photos": _own_files(db, item.get("id"), token.contact_id)} if kind == COMPLAINT else {}),
                })
        rows.sort(key=lambda r: r.get("submitted") or "", reverse=True)
        return rows[:MAX_LIST_ROWS]

    try:
        rows = run_as_contact(db, ctx, read, tool_name=LIST)
    except Exception as exc:  # noqa: BLE001 - a refusal is a result the model can read
        return _route_failure(exc)
    data, more = cap_result({"requests": rows})
    return ToolResult("ok", data=data, more=more)


def run_read(db, ctx, name: str, args: Any, seen_ids: set[str]) -> ToolResult:
    """One dealer read. The ids in its result join the turn's seen ids."""
    read = PORTAL_READS.get(name)
    if read is None or not may_use(db, ctx, name):
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    if not isinstance(args, dict):
        return ToolResult("invalid", message="Arguments must be an object of named values.")
    out = read.run(db, ctx, args)
    if out.status == "ok":
        _collect_uuids(out.data, seen_ids)
    return out


def _test_result() -> dict:
    return {"id": None, "after": {"state": "test"}, "note": TEST_NOTE}


# ------------------------------------------------------------------ note on an own request


def _note_target(db, token, args: dict):
    from app.services.form_comment_service import FormCommentService
    from app.services.uuid_path_param import validate_uuid_path

    kind = _require_kind(db, token, args.get("kind"))
    sid = validate_uuid_path(str(args.get("submission_id")), resource="Request")
    service = FormCommentService(db)
    # The contact's own row or a 404, exactly as the portal's comment route.
    row = service._load_row(kind, sid, contact_id=token.contact_id, space_id=token.space_id)
    return kind, sid, service, row


def _note_add_read_before(db, token, args: dict) -> dict:
    kind, _sid, service, row = _note_target(db, token, args)
    service._require_open(row)
    service._clean(args.get("text"), [])
    return {"_show": {"kind": KIND_WORDS[kind], "number": _number(db, kind, row)}}


def _note_add_summary(args: dict, before: dict) -> str:
    return f'Add this note to your {before["kind"]} {before["number"]}: "{_line(args["text"])}"'


def _note_add_execute(db, token, args: dict) -> dict:
    if args.get("_is_test"):
        return _test_result()
    kind, sid, service, _row = _note_target(db, token, args)
    out = service.add_contact_comment(kind, sid, token.contact_id, token.space_id, args["text"], [], None, None)
    return {"id": str(out["comment"]["id"]), "after": {"note": "added"}}


def _note_add_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"{shown.get('kind')} {shown.get('number')}", [("Notes", None, f'Added "{_line(args["text"])}"')])


def _note_remove_target(db, token, args: dict):
    from app.services.error_handler import handle_unprocessable
    from app.services.uuid_path_param import validate_uuid_path

    kind, sid, service, row = _note_target(db, token, args)
    cid = validate_uuid_path(str(args.get("comment_id")), resource="Note")
    msg = service._load_comment(kind, sid, cid)
    if msg.deleted_at is not None:
        raise handle_unprocessable("This note was already removed.")
    service._require_modifier(msg, {"contact_id": token.contact_id})
    return kind, sid, cid, service, row, msg


def _note_remove_read_before(db, token, args: dict) -> dict:
    kind, _sid, _cid, _service, row, msg = _note_remove_target(db, token, args)
    return {"_show": {"kind": KIND_WORDS[kind], "number": _number(db, kind, row), "text": _plain_text(msg.body_html)[:120]}}


def _note_remove_summary(args: dict, before: dict) -> str:
    return f'Remove your note "{before["text"]}" from your {before["kind"]} {before["number"]}.'


def _note_remove_execute(db, token, args: dict) -> dict:
    if args.get("_is_test"):
        return _test_result()
    kind, sid, cid, service, row, _msg = _note_remove_target(db, token, args)
    service.delete_comment(kind, sid, cid, {"contact_id": token.contact_id}, row=row)
    return {"id": cid, "after": {"note": "removed"}}


def _note_remove_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"{shown.get('kind')} {shown.get('number')}", [("Notes", f'"{shown.get("text")}"', "Removed")])


# ------------------------------------------------------------------ stock inquiry


def _quantity(value: Any) -> str:
    from app.services.error_handler import handle_validation_error

    text = _line(value)
    try:
        number = float(text)
    except ValueError:
        raise handle_validation_error("quantity must be a number of pieces.")
    if number <= 0:
        raise handle_validation_error("quantity must be more than 0.")
    return str(int(number)) if number.is_integer() else text


def _needed_by(value: Any) -> date | None:
    from app.services.error_handler import handle_validation_error

    if value in (None, ""):
        return None
    try:
        day = date.fromisoformat(str(value).strip())
    except ValueError:
        raise handle_validation_error("delivery_date must be a date as YYYY-MM-DD.")
    if day < date.today():
        raise handle_validation_error("delivery_date is in the past.")
    return day


def _product(db, code: Any):
    """The active, chat-searchable product of that code in this session's scopes (brand + company)."""
    from sqlalchemy import func

    from app.models.product import Product, chat_searchable_products
    from app.services.error_handler import handle_validation_error

    wanted = _line(code).upper()
    row = (
        db.query(Product)
        .filter(chat_searchable_products(), Product.is_active.is_(True), func.upper(Product.product_code) == wanted)
        .first()
        if wanted else None
    )
    if row is None:
        raise handle_validation_error(f"There is no product {wanted or '(blank)'} in this customer's range.")
    return row


def _si_read_before(db, token, args: dict) -> dict:
    from app.services.portal_form_visibility_service import require_form_visible

    require_form_visible(db, token.contact_id, STOCK_INQUIRY)
    product = _product(db, args.get("product_code"))
    qty = _quantity(args.get("quantity"))
    day = _needed_by(args.get("delivery_date"))
    return {"_show": {"code": product.product_code, "name": product.product_name or "", "quantity": qty,
                      "day": f"{day.day} {day.strftime('%b %Y')}" if day else ""}}


def _si_summary(args: dict, before: dict) -> str:
    parts = [f"{before['code']} ({_line(before['name'])})" if before.get("name") else before["code"], f"{before['quantity']} pcs"]
    if before.get("day"):
        parts.append(f"needed by {before['day']}")
    if _line(args.get("project_name")):
        parts.append(f"project {_line(args['project_name'])}")
    if _line(args.get("project_customer")):
        parts.append(f"for {_line(args['project_customer'])}")
    if _line(args.get("remark")):
        parts.append(f'note "{_line(args["remark"])}"')
    return f"Send a stock inquiry to the project sales team: {', '.join(parts)}, requested by you."


def _si_execute(db, token, args: dict) -> dict:
    from app.services.portal_service import PortalService

    if args.get("_is_test"):
        return _test_result()
    product = _product(db, args.get("product_code"))
    day = _needed_by(args.get("delivery_date"))
    payload = {
        "product_code": product.product_code,
        "item_description": product.product_name,
        "quantity": _quantity(args.get("quantity")),
        # "Requested by you": the contact itself, which the portal's requestor list always holds.
        "salesperson_contact_id": token.contact_id,
    }
    if day:
        payload["delivery_date"] = day.isoformat()
    for key in ("project_name", "project_customer", "remark"):
        if _line(args.get(key)):
            payload[key] = _line(args[key])
    service = PortalService(db)
    draft = service.create_or_update_draft(token, STOCK_INQUIRY, payload)
    sid = str(draft["id"])
    try:
        sent = service.submit_draft(token, STOCK_INQUIRY, sid)
    except Exception:
        # No stray draft is left behind by a refused submit.
        db.rollback()
        try:
            service.delete_draft(token, STOCK_INQUIRY, sid)
        except Exception:  # noqa: BLE001 - the submit's own refusal is the one to report
            db.rollback()
        raise
    from app.models.procurement import StockInquiry

    row = db.get(StockInquiry, sid)
    number = _number(db, STOCK_INQUIRY, row) if row is not None else str(sent.get("document_number") or "")
    return {
        "id": sid,
        "after": {"number": number, "status": row.status if row is not None else sent.get("status")},
        "note": (
            f"Stock inquiry {number} is with the project sales team. "
            f"Reply undo within {WITHDRAW_MINUTES} minutes to withdraw it."
        ),
    }


def _si_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"stock inquiry {after.get('number')}", [("Status", "Not sent", "With the project sales team")])


# ------------------------------------------------------------------ withdraw a fresh stock inquiry


def _untouched_or_refuse(db, token, kind: str, row, *, own_files_ok: bool = False) -> tuple[list, list]:
    """The W2-Q2 withdraw rule, for any portal kind: the row's history and SLA stages when it is the first
    submission, at most `WITHDRAW_MINUTES` old, and nobody but the contact has touched it (no comment by
    anyone else, no touched stage, no form action, no file; `own_files_ok` lets the contact's OWN uploads
    through, which a claim carries from the start). Refuses with `WITHDRAW_REFUSED` otherwise. The row's
    own fields (status, responses) are the caller's check."""
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.entity_conversation import EntityConversationMessage as Msg
    from app.models.portal import PortalFormRevision
    from app.models.resources import Attachment
    from app.models.sla import ConversationSLATracking, SlaFormAction, SlaTakeoverRequest
    from app.models.ticket_comment import ConversationTicketComment
    from app.services.error_handler import handle_conflict
    from app.services.form_comment_service import FORM_COMMENT_SCOPE

    sid = str(row.id)
    history = (
        db.query(PortalFormRevision)
        .filter(PortalFormRevision.source_entity_type == kind, PortalFormRevision.source_entity_id == sid)
        .all()
    )
    others = (
        db.query(Msg.id)
        .filter(
            Msg.scope == FORM_COMMENT_SCOPE, Msg.entity_type == kind, Msg.entity_id == sid,
            (Msg.author_contact_id.is_(None)) | (Msg.author_contact_id != token.contact_id),
        )
        .first()
    )
    # The submit itself opens the form's SLA stage when one is configured (`portal_service` emits `submit`):
    # such a stage is untouched until someone responds, takes it, escalates, resolves or voids it.
    trackers = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type == kind, ConversationSLATracking.source_entity_id == sid)
        .all()
    )
    ticket = next(
        (
            t for t in trackers
            if t.is_responded or t.responded_at is not None or t.handled_by_id or t.escalated_at is not None
            or t.is_resolved or t.resolved_at is not None or t.voided_at is not None
        ),
        None,
    )
    stage_ids = [str(t.id) for t in trackers]
    if ticket is None and stage_ids:
        # A staff comment or a takeover request on the stage is staff activity too (they would cascade away).
        busy = (
            db.query(ConversationTicketComment.id).filter(ConversationTicketComment.tracking_id.in_(stage_ids)).first()
            or db.query(SlaTakeoverRequest.id).filter(SlaTakeoverRequest.tracking_id.in_(stage_ids)).first()
        )
        if busy is not None:
            ticket = busy
    action = (
        db.query(SlaFormAction.id)
        .filter(SlaFormAction.source_entity_type == kind, SlaFormAction.source_entity_id == sid)
        .first()
    )
    files = db.query(EntityAttachmentLink.id).filter(
        EntityAttachmentLink.entity_type == kind, EntityAttachmentLink.entity_id == sid
    )
    if own_files_ok:
        # Only a file the contact itself uploaded may stay; anyone else's file (staff) is a touch.
        own = db.query(Attachment.id).filter(
            Attachment.uploader_kind == "contact", Attachment.uploaded_by_contact_id == token.contact_id
        )
        files = files.filter(~EntityAttachmentLink.attachment_id.in_(own))
    fresh = (
        len(history) == 1
        and history[0].kind == "original"
        and history[0].submitted_at is not None
        and datetime.utcnow() - history[0].submitted_at <= timedelta(minutes=WITHDRAW_MINUTES)
    )
    if not (fresh and others is None and ticket is None and action is None and files.first() is None):
        raise handle_conflict(WITHDRAW_REFUSED)
    return history, trackers


def _hard_delete(db, token, kind: str, row, trackers: list) -> None:
    """Hard delete (D7): the row and what points at it, so no bell, open stage or history entry names a
    missing request. A stage's own children (events, comments) go with it (ON DELETE CASCADE)."""
    from sqlalchemy import and_, false, or_

    from app.models.entity_conversation import EntityConversationMessage as Msg
    from app.models.notification import Notification
    from app.models.portal import PortalFormRevision
    from app.models.procurement import ViewToken
    from app.services.form_comment_service import FORM_COMMENT_SCOPE

    sid = str(row.id)
    stage_ids = [str(t.id) for t in trackers]
    db.query(Notification).filter(
        or_(
            and_(Notification.source_entity_type == kind, Notification.source_entity_id == sid),
            Notification.source_entity_id.in_(stage_ids) if stage_ids else false(),
        )
    ).delete(synchronize_session=False)
    for tracker in trackers:
        db.delete(tracker)
    db.query(PortalFormRevision).filter(
        PortalFormRevision.source_entity_type == kind, PortalFormRevision.source_entity_id == sid
    ).delete(synchronize_session=False)
    # Only the contact's own notes: a staff comment racing the delete is never removed with them.
    db.query(Msg).filter(
        Msg.scope == FORM_COMMENT_SCOPE, Msg.entity_type == kind, Msg.entity_id == sid,
        Msg.author_contact_id == token.contact_id,
    ).delete(synchronize_session=False)
    # The public view link the submit minted for this row.
    db.query(ViewToken).filter(ViewToken.entity_type == kind, ViewToken.entity_id == sid).delete(
        synchronize_session=False
    )
    db.delete(row)


def _withdraw_target(db, token, args: dict, *, lock: bool = False) -> tuple[Any, list, list]:
    """The contact's own inquiry and its history, when it may still be withdrawn; refusals otherwise."""
    from app.models.procurement import StockInquiry
    from app.services import submission_status
    from app.services.error_handler import handle_conflict, handle_not_found
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.uuid_path_param import validate_uuid_path

    require_form_visible(db, token.contact_id, STOCK_INQUIRY)
    sid = validate_uuid_path(str(args.get("submission_id")), resource="Stock inquiry")
    query = db.query(StockInquiry).filter(
        StockInquiry.id == sid, StockInquiry.contact_id == token.contact_id, StockInquiry.space_id == token.space_id
    )
    # The delete holds the row while it re-checks "untouched", so a staff reply cannot land in between.
    row = (query.with_for_update(of=StockInquiry) if lock else query).first()
    if row is None or row.portal_draft_at is not None:
        raise handle_not_found("Stock inquiry", sid)
    history, trackers = _untouched_or_refuse(db, token, STOCK_INQUIRY, row)
    untouched = (
        (row.status or "").strip().lower() == submission_status.SI_REVIEW_STAGE
        and not _line(row.purchasing_response)
        and not row.last_responded_by
        and row.last_responded_at is None
    )
    if not untouched:
        raise handle_conflict(WITHDRAW_REFUSED)
    return row, history, trackers


def _withdraw_read_before(db, token, args: dict) -> dict:
    row, history, _trackers = _withdraw_target(db, token, args)
    minutes = max(1, int((datetime.utcnow() - history[0].submitted_at).total_seconds() // 60))
    return {"status": row.status, "_show": {"number": _number(db, STOCK_INQUIRY, row), "minutes": minutes}}


def _withdraw_summary(args: dict, before: dict) -> str:
    unit = "minute" if before["minutes"] == 1 else "minutes"
    return (
        f"Withdraw stock inquiry {before['number']} (sent {before['minutes']} {unit} ago). It is deleted and the "
        "project sales team no longer sees it."
    )


def _withdraw_execute(db, token, args: dict, confirmed: dict) -> dict:
    if args.get("_is_test"):
        return _test_result()
    row, _history, trackers = _withdraw_target(db, token, args, lock=True)
    sid = str(row.id)
    _hard_delete(db, token, STOCK_INQUIRY, row, trackers)
    db.commit()
    return {"id": sid, "after": {"state": "withdrawn"}}


def _withdraw_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"stock inquiry {shown.get('number')}", [("Status", "With the project sales team", "Withdrawn")])


# ------------------------------------------------------------------ warranty / complaint claim (AGENTIC-WA-S2)


def _sent_at(stamp: datetime | None) -> str:
    """A stored (naive UTC) time as the dealer reads it: "2 Nov 10:02", business time."""
    if stamp is None:
        return ""
    local = stamp.replace(tzinfo=timezone.utc).astimezone(_BUSINESS_TZ)
    return f"{local.day} {local.strftime('%b %H:%M')}"


def _chat_photo_query(db, contact_id: str):
    """The contact's own photos the media lane stored from its chat (`media_tasks._store_media_bytes`), last day."""
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment, AttachmentType

    since = datetime.utcnow() - timedelta(hours=PHOTO_WINDOW_HOURS)
    return (
        db.query(Attachment)
        .join(EntityAttachmentLink, EntityAttachmentLink.attachment_id == Attachment.id)
        .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(
            EntityAttachmentLink.entity_type == "chatbot_turn", AttachmentType.code == CHAT_MEDIA_TYPE,
            Attachment.uploader_kind == "contact", Attachment.uploaded_by_contact_id == str(contact_id),
            Attachment.mime_type.ilike("image/%"), Attachment.is_deleted.is_(False), Attachment.created_at >= since,
        )
    )


def _photo_read(db, att) -> str:
    """What the bot read on the photo (its stored media read), or COULD_NOT_READ. The stored file name starts with
    the media ledger row's id (`media_tasks._store_media_bytes`), which leads to the read."""
    from app.models.media import MediaExtractionJob

    usage_id = (att.original_filename or "")[:36]
    try:
        uuid.UUID(usage_id)
    except ValueError:
        return COULD_NOT_READ
    job = db.query(MediaExtractionJob).filter(MediaExtractionJob.usage_id == usage_id).first()
    result = job.result if job is not None and job.status == "completed" else None
    if not isinstance(result, dict):
        return COULD_NOT_READ
    raws = [_line(e.get("raw")) for e in result.get("entities") or [] if isinstance(e, dict) and _line(e.get("raw"))]
    parts = [", ".join(raws)] if raws else []
    for key in ("notes", "caption"):
        if _line(result.get(key)):
            parts.append(_line(result[key]))
    return "; ".join(parts)[:160] or "nothing readable"


def _chat_photos(db, ctx, args: dict) -> ToolResult:
    if args:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, sorted(args)))}.")
    from app.models.resources import Attachment

    def read(token) -> list[dict]:
        rows = (
            _chat_photo_query(db, token.contact_id)
            .order_by(Attachment.created_at.desc(), Attachment.id.desc())
            .limit(MAX_CHAT_PHOTOS)
            .all()
        )
        return [{"id": str(a.id), "sent": _sent_at(a.created_at), "shows": _photo_read(db, a)} for a in rows]

    try:
        rows = run_as_contact(db, ctx, read, tool_name=CHAT_PHOTOS)
    except Exception as exc:  # noqa: BLE001
        return _route_failure(exc)
    return ToolResult("ok", data={"photos": rows})


def _own_files(db, entity_id: Any, contact_id: str) -> list[dict]:
    """The contact's own files on one of its complaints (ids for the photo remove)."""
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    rows = (
        db.query(EntityAttachmentLink.id, Attachment.created_at)
        .join(Attachment, Attachment.id == EntityAttachmentLink.attachment_id)
        .filter(
            EntityAttachmentLink.entity_type == COMPLAINT, EntityAttachmentLink.entity_id == str(entity_id),
            Attachment.uploader_kind == "contact", Attachment.uploaded_by_contact_id == str(contact_id),
        )
        .order_by(Attachment.created_at.asc())
        .limit(MAX_CHAT_PHOTOS)
        .all()
    )
    return [{"id": str(link_id), "added": _sent_at(at)} for link_id, at in rows]


def _photos(db, token, ids: Any, *, entity_id: str | None) -> list:
    """The chosen chat photos (attachment rows), each the contact's own and passing the portal attachment type
    (extension, size, count on the complaint) exactly as a portal upload would."""
    from app.api.v1.public.portal import _check_quota, _ext
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment
    from app.services.error_handler import handle_not_found, handle_validation_error
    from app.services.portal_service import PortalService
    from app.services.uuid_path_param import validate_uuid_path

    if ids in (None, []):
        return []
    wanted: list[str] = []
    for value in ids:
        pid = validate_uuid_path(str(value), resource="Photo")
        if pid not in wanted:
            wanted.append(pid)
    found = {str(a.id): a for a in _chat_photo_query(db, token.contact_id).filter(Attachment.id.in_(wanted)).all()}
    photos = []
    for pid in wanted:
        if pid not in found:
            raise handle_not_found("Photo", pid)
        photos.append(found[pid])
    kind_type = PortalService(db).get_portal_attachment_type()
    for att in photos:
        _check_quota(db, kind_type, COMPLAINT, entity_id or str(uuid.uuid4()), int(att.file_size_bytes or 0),
                     _ext(att.original_filename, att.mime_type))
    cap = kind_type.max_count_per_entity
    if cap is not None:
        existing = 0
        if entity_id:
            existing = db.query(EntityAttachmentLink.id).filter(
                EntityAttachmentLink.entity_type == COMPLAINT, EntityAttachmentLink.entity_id == entity_id
            ).count()
        if existing + len(photos) > cap:
            raise handle_validation_error(f"Attachment limit reached ({cap}).")
    return photos


def _photo_show(db, photos: list) -> list[dict]:
    return [{"sent": _sent_at(a.created_at), "shows": _photo_read(db, a)} for a in photos]


def _photo_words(shown: list[dict]) -> str:
    if not shown:
        return "no photos"
    return "; ".join(f"photo {n} ({p['sent']}): {p['shows']}" for n, p in enumerate(shown, 1))


def _store_photos(db, token, sid: str, photos: list) -> list[dict]:
    """Each chat photo through the portal's own upload body (bytes copied from OUR storage, never respond.io's
    short-lived link). On a failure the files stored so far are removed and the error is raised."""
    from app.api.v1.public.portal import store_portal_upload
    from app.services.storage_router import extract_key, get_backend

    stored: list[dict] = []
    try:
        for att in photos:
            data = get_backend(att.storage_provider).download_file(extract_key(att.file_path) or att.file_path)
            stored.append(store_portal_upload(db, token, COMPLAINT, sid, data, att.original_filename, att.mime_type))
    except Exception:
        db.rollback()
        _discard_files(db, [s["attachment_id"] for s in stored])
        raise
    return stored


def _discard_files(db, attachment_ids: list[str]) -> None:
    """Hard delete files this tool stored: links, rows and objects. Best effort on the objects."""
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment
    from app.services.storage_router import delete_object_best_effort, extract_key

    if not attachment_ids:
        return
    rows = db.query(Attachment).filter(Attachment.id.in_(attachment_ids)).all()
    objects = [(r.storage_provider, extract_key(r.file_path) or r.file_path) for r in rows]
    objects += [(r.storage_provider, extract_key(r.thumbnail_path)) for r in rows if r.thumbnail_path]
    db.query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id.in_(attachment_ids)).delete(
        synchronize_session=False
    )
    for r in rows:
        db.delete(r)
    db.commit()
    for provider, key in objects:
        delete_object_best_effort(provider, key)


def _own_orders(db, token, numbers: Any) -> list:
    """Each DO as the EXACT number of an order of one of the contact's own linked customer accounts. Anything
    else is the plain not-found, naming nobody (helper fix 1: never the portal picker's partial search)."""
    from sqlalchemy import func, select

    from app.models.access import RespondContactCustomer
    from app.models.order import Order
    from app.services.error_handler import AppException, handle_validation_error

    if not isinstance(numbers, list) or not [n for n in numbers if _line(n)]:
        raise handle_validation_error("delivery_order_numbers needs at least one DO number.")
    own = select(RespondContactCustomer.customer_id).where(RespondContactCustomer.contact_id == str(token.contact_id))
    orders: list = []
    for raw in numbers:
        typed = _line(raw)
        if not typed:
            continue
        row = (
            db.query(Order)
            .filter(Order.customer_id.in_(own), func.upper(func.trim(Order.order_number)) == typed.upper())
            .first()
        )
        if row is None:
            raise AppException(status_code=404, message=f"Delivery order {typed[:60]} not found.", code="NOT_FOUND")
        if row not in orders:
            orders.append(row)
    return orders


def _claim_lines(db, orders: list, args: dict) -> list[dict]:
    """The claimed products, each on one of the DOs, with the product type the portal form derives."""
    from app.models.order import OrderLine
    from app.models.product import Product, ProductCategory
    from app.services.error_handler import handle_validation_error

    codes = [c for c in (args.get("product_codes") or []) if _line(c)]
    if not codes:
        raise handle_validation_error("product_codes needs at least one product code from the DO.")
    quantities = args.get("quantities") or []
    on_do = {
        code.upper(): (code, ctype)
        for code, ctype in db.query(Product.product_code, ProductCategory.category_code)
        .join(OrderLine, OrderLine.product_id == Product.id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(OrderLine.order_id.in_([o.id for o in orders]))
        .all()
    }
    lines: list[dict] = []
    seen: set[str] = set()
    for n, raw in enumerate(codes):
        hit = on_do.get(_line(raw).upper())
        if hit is None:
            numbers = ", ".join(o.order_number for o in orders)
            raise handle_validation_error(f"{_line(raw)[:60]} is not on delivery order {numbers}.")
        if hit[0] in seen:
            continue
        seen.add(hit[0])
        qty = _quantity(quantities[n]) if n < len(quantities) and _line(quantities[n]) else None
        lines.append({"product_code": hit[0], "quantity": qty, "product_type": hit[1]})
    return lines


_LOOKUPS = (
    ("within_warranty", "within warranty"),
    ("complaint_type", "complaint type"),
    ("defects_discovered", "defects discovered"),
    ("customer_type", "customer type"),
)


def _lookup(db, column: str, value: Any) -> tuple[str | None, str | None]:
    """(value, label) of a complaint lookup: an active option matched on value or label; an omitted one takes the
    binding default the portal form pre-selects, except within warranty, which only the dealer says (S2-Q3)."""
    from app.models.lookup import LookupBinding, LookupOption
    from app.services.error_handler import handle_validation_error

    binding = (
        db.query(LookupBinding)
        .filter(LookupBinding.tenant_id.is_(None), LookupBinding.table_name == "complaints",
                LookupBinding.column_name == column)
        .first()
    )
    typed = _line(value)
    if binding is None:
        return (typed or None), (typed or None)
    options = (
        db.query(LookupOption)
        .filter(LookupOption.set_id == binding.set_id, LookupOption.is_active.is_(True))
        .order_by(LookupOption.sort_order)
        .all()
    )
    if not typed:
        if column == "within_warranty":
            return None, None
        hit = next((o for o in options if o.value == binding.default_value), None)
        return (hit.value, hit.label) if hit else (None, None)
    hit = next((o for o in options if typed.casefold() in (o.value.casefold(), o.label.casefold())), None)
    if hit is None:
        label = dict(_LOOKUPS)[column]
        raise handle_validation_error(f"{label} must be one of: {', '.join(o.label for o in options)}.")
    return hit.value, hit.label


def _claim(db, token, args: dict) -> dict:
    """The claim as the portal form would submit it, with the form's own pre-fills (S2-Q3 (a)); refused when a
    required field is still empty (`portal_required_fields`, the submit's own list)."""
    from app.services.error_handler import handle_validation_error
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.portal_required_fields import missing_on_submit
    from app.services.portal_service import PortalService

    require_form_visible(db, token.contact_id, COMPLAINT)
    orders = _own_orders(db, token, args.get("delivery_order_numbers"))
    lines = _claim_lines(db, orders, args)
    contact = PortalService(db).get_contact(token)
    name = _line(contact.name) or _line(f"{contact.first_name or ''} {contact.last_name or ''}")
    debtors: list[str] = []
    for o in orders:
        debtor = _line(o.debtor_name) or _line(getattr(o.customer, "customer_name", None) if o.customer_id else None)
        if debtor and debtor not in debtors:
            debtors.append(debtor)
    payload: dict[str, Any] = {
        "delivery_order_number": ",".join(o.order_number for o in orders),
        "customer_name": ", ".join(debtors),
        "contact_person": _line(args.get("contact_person")) or name,
        "contact_number": _line(args.get("contact_number")) or _line(contact.phone_number),
        "complaint_date": date.today().isoformat(),
        "salesperson": name,
        "defect_description": str(args.get("defect_description") or "").strip(),
        "product_lines": lines,
    }
    for key in ("customer_address", "project_title"):
        if _line(args.get(key)):
            payload[key] = str(args[key]).strip()
    labels: dict[str, str] = {}
    for column, _label in _LOOKUPS:
        payload[column], labels[column] = _lookup(db, column, args.get(column))
    missing = missing_on_submit(
        COMPLAINT, SimpleNamespace(**{**payload, "product_code": ", ".join(l["product_code"] for l in lines)})
    )
    if missing:
        raise handle_validation_error(f"Still missing: {', '.join(missing)}. Ask the customer for it.")
    return {"payload": payload, "labels": labels, "orders": orders, "lines": lines}


_CLOSED_COMPLAINT = ("draft", "rejected", "processed_by_cs", "closed", "resolved", "void", "voided", "cancelled")


def _open_complaints(db, token):
    from sqlalchemy import func

    from app.models.complaints import Complaint

    return db.query(Complaint).filter(
        Complaint.contact_id == str(token.contact_id), Complaint.space_id == token.space_id,
        Complaint.portal_draft_at.is_(None), Complaint.resolved_at.is_(None), Complaint.voided_at.is_(None),
        func.lower(func.coalesce(Complaint.status, "")).notin_(_CLOSED_COMPLAINT),
    )


def _earlier_claim(db, token, claim: dict) -> str:
    """S2-Q5: the sentence about an open claim of the contact on the same DO and product ("" when none). Under
    `DUPLICATE_CLAIMS == "refuse"` it refuses instead."""
    from app.services.error_handler import handle_conflict

    def parts(text: Any) -> set[str]:
        return {p.strip().upper() for p in str(text or "").split(",") if p.strip()}

    dos = {o.order_number.strip().upper() for o in claim["orders"]}
    codes = {l["product_code"].upper() for l in claim["lines"]}
    for row in _open_complaints(db, token).order_by(*_newest(db)).limit(50).all():
        if dos & parts(row.delivery_order_number) and codes & parts(row.product_code):
            number = _number(db, COMPLAINT, row)
            day = _sent_at(row.created_at).rsplit(" ", 1)[0] if row.created_at else "earlier"
            if DUPLICATE_CLAIMS == "refuse":
                raise handle_conflict(
                    f"You already sent complaint {number} for this on {day}. I can add a note to it instead."
                )
            return f"Note: you already sent complaint {number} for this on {day}; this sends a second claim."
    return ""


def _newest(db):
    from app.models.complaints import Complaint

    return (Complaint.created_at.desc(), Complaint.id.desc())


def _cp_read_before(db, token, args: dict) -> dict:
    claim = _claim(db, token, args)
    photos = _photos(db, token, args.get("photo_ids"), entity_id=None)
    payload, labels = claim["payload"], claim["labels"]
    return {"_show": {
        "dos": ", ".join(o.order_number for o in claim["orders"]),
        "lines": ", ".join(f"{l['product_code']} x{l['quantity']}" if l["quantity"] else l["product_code"]
                           for l in claim["lines"]),
        "description": payload["defect_description"][:300],
        **{column: labels[column] or "" for column, _label in _LOOKUPS},
        "customer": payload["customer_name"],
        "contact": f"{payload['contact_person']} {payload['contact_number']}",
        "photos": _photo_show(db, photos),
        "earlier": _earlier_claim(db, token, claim),
    }}


def _cp_summary(args: dict, before: dict) -> str:
    parts = [f"DO {before['dos']}", before["lines"], f'"{_line(before["description"])}"',
             f"within warranty: {before['within_warranty']}"]
    for column, label in _LOOKUPS[1:]:
        if before.get(column):
            parts.append(f"{label}: {before[column]}")
    parts += [f"customer {before['customer']}", f"contact {before['contact']}", _photo_words(before["photos"])]
    text = "File a warranty / complaint claim: " + "; ".join(_line(p) for p in parts) + "."
    return f"{text} {before['earlier']}" if before.get("earlier") else text


def _cp_execute(db, token, args: dict) -> dict:
    from app.models.complaints import Complaint
    from app.services.portal_service import PortalService

    if args.get("_is_test"):
        return _test_result()
    claim = _claim(db, token, args)
    photos = _photos(db, token, args.get("photo_ids"), entity_id=None)
    service = PortalService(db)
    sid = str(service.create_or_update_draft(token, COMPLAINT, claim["payload"])["id"])
    stored: list[dict] = []
    try:
        stored = _store_photos(db, token, sid, photos)
        service.submit_draft(token, COMPLAINT, sid)
    except Exception:
        # No stray draft or file is left behind by a refused submit.
        db.rollback()
        try:
            _discard_files(db, [s["attachment_id"] for s in stored])
            service.delete_draft(token, COMPLAINT, sid)
        except Exception:  # noqa: BLE001 - the submit's own refusal is the one to report
            db.rollback()
        raise
    row = db.get(Complaint, sid)
    number = _number(db, COMPLAINT, row)
    return {
        "id": sid,
        "after": {"number": number, "status": row.status, "photos": len(stored)},
        "note": f"Complaint {number} is with the team. Reply undo within {WITHDRAW_MINUTES} minutes to withdraw it.",
    }


def _cp_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"complaint {after.get('number')}", [("Status", "Not sent", "With the team")])


# ------------------------------------------------------------------ withdraw a fresh claim


def _cp_withdraw_target(db, token, args: dict, *, lock: bool = False):
    from app.models.complaints import Complaint
    from app.services import submission_status
    from app.services.error_handler import handle_conflict, handle_not_found
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.uuid_path_param import validate_uuid_path

    require_form_visible(db, token.contact_id, COMPLAINT)
    sid = validate_uuid_path(str(args.get("submission_id")), resource="Complaint")
    query = db.query(Complaint).filter(
        Complaint.id == sid, Complaint.contact_id == token.contact_id, Complaint.space_id == token.space_id
    )
    row = (query.with_for_update(of=Complaint) if lock else query).first()
    if row is None or row.portal_draft_at is not None:
        raise handle_not_found("Complaint", sid)
    history, trackers = _untouched_or_refuse(db, token, COMPLAINT, row, own_files_ok=True)
    untouched = (
        (row.status or "").strip().lower() == submission_status.SUBMITTED
        and not _line(row.technical_team_response)
        and not row.last_responded_by and row.last_responded_at is None
        and row.resolved_at is None and row.voided_at is None and row.rejected_at is None
        and row.root_cause_id is None and row.resolution_id is None
    )
    if not untouched:
        raise handle_conflict(WITHDRAW_REFUSED)
    return row, history, trackers


def _cp_withdraw_read_before(db, token, args: dict) -> dict:
    row, history, _trackers = _cp_withdraw_target(db, token, args)
    minutes = max(1, int((datetime.utcnow() - history[0].submitted_at).total_seconds() // 60))
    return {"status": row.status, "_show": {"number": _number(db, COMPLAINT, row), "minutes": minutes}}


def _cp_withdraw_summary(args: dict, before: dict) -> str:
    unit = "minute" if before["minutes"] == 1 else "minutes"
    return (
        f"Withdraw complaint {before['number']} (sent {before['minutes']} {unit} ago). It is deleted, with its "
        "photos, and the team no longer sees it."
    )


def _cp_withdraw_execute(db, token, args: dict, confirmed: dict) -> dict:
    from app.models.entity_attachment import EntityAttachmentLink

    if args.get("_is_test"):
        return _test_result()
    row, _history, trackers = _cp_withdraw_target(db, token, args, lock=True)
    sid = str(row.id)
    files = [
        str(a) for (a,) in db.query(EntityAttachmentLink.attachment_id)
        .filter(EntityAttachmentLink.entity_type == COMPLAINT, EntityAttachmentLink.entity_id == sid).all()
    ]
    _hard_delete(db, token, COMPLAINT, row, trackers)
    db.flush()
    # Only the contact's own files can be here (`_untouched_or_refuse`); they go with the claim.
    _discard_files(db, files)
    return {"id": sid, "after": {"state": "withdrawn"}}


def _cp_withdraw_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"complaint {shown.get('number')}", [("Status", "With the team", "Withdrawn")])


# ------------------------------------------------------------------ later photos (S2-Q4 (a)) and their undo


def _open_claim(db, token, args: dict):
    from app.models.complaints import Complaint
    from app.services.error_handler import handle_conflict, handle_not_found
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.uuid_path_param import validate_uuid_path

    require_form_visible(db, token.contact_id, COMPLAINT)
    sid = validate_uuid_path(str(args.get("submission_id")), resource="Complaint")
    row = (
        db.query(Complaint)
        .filter(Complaint.id == sid, Complaint.contact_id == token.contact_id, Complaint.space_id == token.space_id)
        .first()
    )
    if row is None or row.portal_draft_at is not None:
        raise handle_not_found("Complaint", sid)
    if _open_complaints(db, token).filter(Complaint.id == sid).first() is None:
        raise handle_conflict(f"Complaint {_number(db, COMPLAINT, row)} is closed, so it takes no more photos.")
    return row


def _add_targets(db, token, args: dict):
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment
    from app.services.error_handler import handle_validation_error

    row = _open_claim(db, token, args)
    sid = str(row.id)
    if not args.get("photo_ids"):
        raise handle_validation_error("photo_ids needs at least one photo from crm_my_chat_photos.")
    photos = _photos(db, token, args.get("photo_ids"), entity_id=sid)
    # A chat photo keeps its stored name on the portal copy, so one already on the claim is recognised.
    on_claim = {
        n for (n,) in db.query(Attachment.original_filename)
        .join(EntityAttachmentLink, EntityAttachmentLink.attachment_id == Attachment.id)
        .filter(EntityAttachmentLink.entity_type == COMPLAINT, EntityAttachmentLink.entity_id == sid).all()
    }
    for n, att in enumerate(photos, 1):
        if att.original_filename in on_claim:
            raise handle_validation_error(f"The photo sent {_sent_at(att.created_at)} is already on this complaint.")
    return row, photos


def _photos_add_read_before(db, token, args: dict) -> dict:
    row, photos = _add_targets(db, token, args)
    return {"_show": {"number": _number(db, COMPLAINT, row), "photos": _photo_show(db, photos)}}


def _photos_add_summary(args: dict, before: dict) -> str:
    n = len(before["photos"])
    return f"Add {n} photo{'' if n == 1 else 's'} to your complaint {before['number']}: {_photo_words(before['photos'])}."


def _photos_add_execute(db, token, args: dict) -> dict:
    if args.get("_is_test"):
        return _test_result()
    row, photos = _add_targets(db, token, args)
    stored = _store_photos(db, token, str(row.id), photos)
    return {"id": str(row.id), "after": {"photos": len(stored)}}


def _photos_add_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"complaint {shown.get('number')}", [("Photos", None, f"Added {after.get('photos')}")])


def _photo_remove_target(db, token, args: dict):
    from app.api.v1.public.portal import removable_attachment_link
    from app.models.complaints import Complaint
    from app.models.resources import Attachment
    from app.services.error_handler import handle_not_found
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.uuid_path_param import validate_uuid_path

    require_form_visible(db, token.contact_id, COMPLAINT)
    sid = validate_uuid_path(str(args.get("submission_id")), resource="Complaint")
    fid = validate_uuid_path(str(args.get("file_id")), resource="Photo")
    row = (
        db.query(Complaint)
        .filter(Complaint.id == sid, Complaint.contact_id == token.contact_id, Complaint.space_id == token.space_id)
        .first()
    )
    if row is None:
        raise handle_not_found("Complaint", sid)
    # The portal's own remove rule: the contact's own row, the form visible, never a staff upload.
    link = removable_attachment_link(db, token, fid)
    if link.entity_type != COMPLAINT or str(link.entity_id) != sid:
        raise handle_not_found("Photo", fid)
    att = db.get(Attachment, link.attachment_id)
    return row, link, att


def _photo_remove_read_before(db, token, args: dict) -> dict:
    row, _link, att = _photo_remove_target(db, token, args)
    when = _sent_at(att.created_at) if att is not None else ""
    return {"_show": {"number": _number(db, COMPLAINT, row), "when": when}}


def _photo_remove_summary(args: dict, before: dict) -> str:
    return f"Remove your photo added {before['when']} from your complaint {before['number']}."


def _photo_remove_execute(db, token, args: dict) -> dict:
    from app.api.v1.public.portal import remove_attachment_link

    if args.get("_is_test"):
        return _test_result()
    _row, link, _att = _photo_remove_target(db, token, args)
    remove_attachment_link(db, token, str(link.id))
    return {"id": str(link.id), "after": {"photo": "removed"}}


def _photo_remove_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"complaint {shown.get('number')}", [("Photos", f"added {shown.get('when')}", "Removed")])


# ------------------------------------------------------------------ registry

_KIND_PROP = {"type": "string", "enum": list(NOTE_KINDS)}
_STR_LIST = {"type": "array", "items": {"type": "string", "maxLength": 100}, "maxItems": 20}

PORTAL_READS: dict[str, UserRead] = {
    LIST: UserRead(
        name=LIST,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": LIST,
                "description": (
                    "The customer's own submitted requests (stock inquiries, complaints, purchase requests, "
                    "sponsorship forms), newest first, each with its id, number, status and the customer's own "
                    "notes with their ids. Use it to find the request the customer means before adding or "
                    "removing a note, or withdrawing a stock inquiry. Optional kind and search text."
                ),
                "parameters": {"type": "object", "properties": {"kind": _KIND_PROP, "search": {"type": "string"}}},
            },
        },
        run=_my_requests,
    ),
    CHAT_PHOTOS: UserRead(
        name=CHAT_PHOTOS,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": CHAT_PHOTOS,
                "description": (
                    f"The photos the customer sent in this chat in the last {PHOTO_WINDOW_HOURS} hours, newest "
                    f"first (at most {MAX_CHAT_PHOTOS}), each with its id, the time it was sent and what it shows "
                    "(or that it could not be read). Use it to pick the photo_ids of a complaint claim: only the "
                    "photos the customer means for that claim."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        run=_chat_photos,
    ),
}

PORTAL_WRITES: dict[str, WriteDef] = {
    NOTE_ADD: WriteDef(
        name=NOTE_ADD,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": NOTE_ADD,
                "description": (
                    "Propose adding a note from the customer to one of their own submitted requests; the team "
                    "handling it sees the note. Nothing is sent until the customer confirms. submission_id must "
                    "come from crm_my_requests_list. Use the customer's own words."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": _KIND_PROP,
                        "submission_id": {"type": "string"},
                        "text": {"type": "string", "maxLength": MAX_NOTE_CHARS},
                    },
                    "required": ["kind", "submission_id", "text"],
                },
            },
        },
        read_before=_note_add_read_before,
        summary=_note_add_summary,
        execute=_note_add_execute,
        record_key="submission_id",
        changes=_note_add_changes,
        note_in_reply=True,
        runs_as="contact",
    ),
    NOTE_REMOVE: WriteDef(
        name=NOTE_REMOVE,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": NOTE_REMOVE,
                "description": (
                    "Propose removing one of the customer's own notes from one of their requests (the undo of "
                    "a note). Nothing changes until the customer confirms. submission_id and comment_id must "
                    "come from crm_my_requests_list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": _KIND_PROP, "submission_id": {"type": "string"}, "comment_id": {"type": "string"},
                    },
                    "required": ["kind", "submission_id", "comment_id"],
                },
            },
        },
        read_before=_note_remove_read_before,
        summary=_note_remove_summary,
        execute=_note_remove_execute,
        record_key="comment_id",
        changes=_note_remove_changes,
        note_in_reply=True,
        runs_as="contact",
    ),
    SI_CREATE: WriteDef(
        name=SI_CREATE,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": SI_CREATE,
                "description": (
                    "Propose sending a stock inquiry (availability / lead time of one product) from the customer "
                    "to the project sales team, who reply to the customer here. Nothing is sent until the "
                    "customer confirms. Use only what the customer said: product_code and quantity are needed; "
                    "delivery_date (YYYY-MM-DD), project_name, project_customer and remark only when the customer "
                    "gave them. Call once per product."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_code": {"type": "string", "maxLength": 100},
                        "quantity": {"type": "string", "maxLength": 20},
                        "delivery_date": {"type": "string", "maxLength": 10},
                        "project_name": {"type": "string", "maxLength": 200},
                        "project_customer": {"type": "string", "maxLength": 200},
                        "remark": {"type": "string", "maxLength": 1000},
                    },
                    "required": ["product_code", "quantity"],
                },
            },
        },
        read_before=_si_read_before,
        summary=_si_summary,
        execute=_si_execute,
        record_key="",
        changes=_si_changes,
        note_in_reply=True,
        runs_as="contact",
    ),
    SI_WITHDRAW: WriteDef(
        name=SI_WITHDRAW,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": SI_WITHDRAW,
                "description": (
                    f"Propose withdrawing (deleting) one of the customer's stock inquiries: the undo of sending "
                    f"one, possible only within {WITHDRAW_MINUTES} minutes of sending and before the team has "
                    "touched it. Nothing changes until the customer confirms. submission_id must come from "
                    "crm_my_requests_list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}},
                    "required": ["submission_id"],
                },
            },
        },
        read_before=_withdraw_read_before,
        summary=_withdraw_summary,
        execute=_withdraw_execute,
        record_key="submission_id",
        changes=_withdraw_changes,
        execute_takes_before=True,
        note_in_reply=True,
        runs_as="contact",
    ),
    CP_CREATE: WriteDef(
        name=CP_CREATE,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": CP_CREATE,
                "description": (
                    "Propose filing a warranty claim / product complaint from the customer to the team, with the "
                    "photos they sent in this chat. Nothing is sent until the customer confirms. Use only what the "
                    "customer said: delivery_order_numbers (the DO), product_codes on that DO (quantities in the "
                    "same order when given), defect_description in the customer's own words, and within_warranty "
                    "as the customer said it (never guess it; ask). complaint_type, defects_discovered, "
                    "customer_type, contact_person / contact_number (only a site contact the customer names), "
                    "customer_address and project_title only when given. photo_ids come from crm_my_chat_photos."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "delivery_order_numbers": _STR_LIST,
                        "product_codes": _STR_LIST,
                        "quantities": _STR_LIST,
                        "defect_description": {"type": "string", "maxLength": MAX_NOTE_CHARS},
                        "within_warranty": {"type": "string", "maxLength": 100},
                        "complaint_type": {"type": "string", "maxLength": 100},
                        "defects_discovered": {"type": "string", "maxLength": 100},
                        "customer_type": {"type": "string", "maxLength": 100},
                        "contact_person": {"type": "string", "maxLength": 200},
                        "contact_number": {"type": "string", "maxLength": 50},
                        "customer_address": {"type": "string", "maxLength": 1000},
                        "project_title": {"type": "string", "maxLength": 200},
                        "photo_ids": _STR_LIST,
                    },
                    "required": ["delivery_order_numbers", "product_codes", "defect_description", "within_warranty"],
                },
            },
        },
        read_before=_cp_read_before,
        summary=_cp_summary,
        execute=_cp_execute,
        record_key="",
        changes=_cp_changes,
        note_in_reply=True,
        runs_as="contact",
    ),
    CP_WITHDRAW: WriteDef(
        name=CP_WITHDRAW,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": CP_WITHDRAW,
                "description": (
                    f"Propose withdrawing (deleting) one of the customer's complaints: the undo of filing one, "
                    f"possible only within {WITHDRAW_MINUTES} minutes of sending and before the team has touched "
                    "it. Nothing changes until the customer confirms. submission_id must come from "
                    "crm_my_requests_list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}},
                    "required": ["submission_id"],
                },
            },
        },
        read_before=_cp_withdraw_read_before,
        summary=_cp_withdraw_summary,
        execute=_cp_withdraw_execute,
        record_key="submission_id",
        changes=_cp_withdraw_changes,
        execute_takes_before=True,
        note_in_reply=True,
        runs_as="contact",
    ),
    CP_PHOTOS_ADD: WriteDef(
        name=CP_PHOTOS_ADD,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": CP_PHOTOS_ADD,
                "description": (
                    "Propose adding photos the customer sent in this chat to one of their own open complaints. "
                    "Nothing changes until the customer confirms. submission_id comes from crm_my_requests_list, "
                    "photo_ids from crm_my_chat_photos."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}, "photo_ids": _STR_LIST},
                    "required": ["submission_id", "photo_ids"],
                },
            },
        },
        read_before=_photos_add_read_before,
        summary=_photos_add_summary,
        execute=_photos_add_execute,
        record_key="submission_id",
        changes=_photos_add_changes,
        runs_as="contact",
    ),
    CP_PHOTO_REMOVE: WriteDef(
        name=CP_PHOTO_REMOVE,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": CP_PHOTO_REMOVE,
                "description": (
                    "Propose removing one photo the customer added to one of their complaints (the undo of "
                    "adding it). Nothing changes until the customer confirms. submission_id and file_id come from "
                    "crm_my_requests_list (my_photos)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}, "file_id": {"type": "string"}},
                    "required": ["submission_id", "file_id"],
                },
            },
        },
        read_before=_photo_remove_read_before,
        summary=_photo_remove_summary,
        execute=_photo_remove_execute,
        record_key="file_id",
        changes=_photo_remove_changes,
        runs_as="contact",
    ),
}

#: What the loop adds to a dealer write's arguments (never the model: `_args_problem` refuses unknown keys).
LOOP_ARGS = ("_is_test",)
