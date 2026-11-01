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
from datetime import date, datetime, timedelta
from typing import Any

from app.services.chatbot.agent.tools import ToolResult, _collect_uuids, cap_result
from app.services.chatbot.agent.writes import MAX_NOTE_CHARS, UserRead, WriteDef, _diff, _line, _route_failure

LIST = "crm_my_requests_list"
NOTE_ADD = "crm_my_request_note_add"
NOTE_REMOVE = "crm_my_request_note_remove"
SI_CREATE = "crm_stock_inquiry_create"
SI_WITHDRAW = "crm_stock_inquiry_withdraw"

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


def _withdraw_target(db, token, args: dict) -> tuple[Any, list]:
    """The contact's own inquiry and its history, when it may still be withdrawn; refusals otherwise."""
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.entity_conversation import EntityConversationMessage as Msg
    from app.models.portal import PortalFormRevision
    from app.models.procurement import StockInquiry
    from app.models.sla import ConversationSLATracking, SlaFormAction
    from app.services import submission_status
    from app.services.error_handler import handle_conflict, handle_not_found
    from app.services.form_comment_service import FORM_COMMENT_SCOPE
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.uuid_path_param import validate_uuid_path

    require_form_visible(db, token.contact_id, STOCK_INQUIRY)
    sid = validate_uuid_path(str(args.get("submission_id")), resource="Stock inquiry")
    row = (
        db.query(StockInquiry)
        .filter(StockInquiry.id == sid, StockInquiry.contact_id == token.contact_id, StockInquiry.space_id == token.space_id)
        .first()
    )
    if row is None or row.portal_draft_at is not None:
        raise handle_not_found("Stock inquiry", sid)
    history = (
        db.query(PortalFormRevision)
        .filter(PortalFormRevision.source_entity_type == STOCK_INQUIRY, PortalFormRevision.source_entity_id == sid)
        .all()
    )
    others = (
        db.query(Msg.id)
        .filter(
            Msg.scope == FORM_COMMENT_SCOPE, Msg.entity_type == STOCK_INQUIRY, Msg.entity_id == sid,
            (Msg.author_contact_id.is_(None)) | (Msg.author_contact_id != token.contact_id),
        )
        .first()
    )
    # The submit itself opens the form's SLA stage when one is configured (`portal_service` emits `submit`):
    # such a stage is untouched until someone responds, takes it, escalates, resolves or voids it.
    trackers = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type == STOCK_INQUIRY, ConversationSLATracking.source_entity_id == sid)
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
    action = (
        db.query(SlaFormAction.id)
        .filter(SlaFormAction.source_entity_type == STOCK_INQUIRY, SlaFormAction.source_entity_id == sid)
        .first()
    )
    files = (
        db.query(EntityAttachmentLink.id)
        .filter(EntityAttachmentLink.entity_type == STOCK_INQUIRY, EntityAttachmentLink.entity_id == sid)
        .first()
    )
    fresh = (
        len(history) == 1
        and history[0].kind == "original"
        and history[0].submitted_at is not None
        and datetime.utcnow() - history[0].submitted_at <= timedelta(minutes=WITHDRAW_MINUTES)
    )
    untouched = (
        (row.status or "").strip().lower() == submission_status.SI_REVIEW_STAGE
        and not _line(row.purchasing_response)
        and not row.last_responded_by
        and row.last_responded_at is None
        and others is None and ticket is None and action is None and files is None
    )
    if not (fresh and untouched):
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
    from sqlalchemy import and_, false, or_

    from app.models.entity_conversation import EntityConversationMessage as Msg
    from app.models.notification import Notification
    from app.models.portal import PortalFormRevision
    from app.services.form_comment_service import FORM_COMMENT_SCOPE

    if args.get("_is_test"):
        return _test_result()
    row, _history, trackers = _withdraw_target(db, token, args)
    sid = str(row.id)
    # Hard delete (D7): the row and what points at it, so no bell, open stage or history entry names a missing
    # request. A stage's own children (events, comments) go with it (ON DELETE CASCADE).
    stage_ids = [str(t.id) for t in trackers]
    db.query(Notification).filter(
        or_(
            and_(Notification.source_entity_type == STOCK_INQUIRY, Notification.source_entity_id == sid),
            Notification.source_entity_id.in_(stage_ids) if stage_ids else false(),
        )
    ).delete(synchronize_session=False)
    for tracker in trackers:
        db.delete(tracker)
    db.query(PortalFormRevision).filter(
        PortalFormRevision.source_entity_type == STOCK_INQUIRY, PortalFormRevision.source_entity_id == sid
    ).delete(synchronize_session=False)
    db.query(Msg).filter(
        Msg.scope == FORM_COMMENT_SCOPE, Msg.entity_type == STOCK_INQUIRY, Msg.entity_id == sid
    ).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return {"id": sid, "after": {"state": "withdrawn"}}


def _withdraw_changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    if after.get("state") == "test":
        return []
    return _diff(f"stock inquiry {shown.get('number')}", [("Status", "With the project sales team", "Withdrawn")])


# ------------------------------------------------------------------ registry

_KIND_PROP = {"type": "string", "enum": list(NOTE_KINDS)}

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
}

#: What the loop adds to a dealer write's arguments (never the model: `_args_problem` refuses unknown keys).
LOOP_ARGS = ("_is_test",)
