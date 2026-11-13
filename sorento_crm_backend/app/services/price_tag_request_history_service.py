"""STANDARD-HISTORY wave 5: one price tag request's History tab.

Read-only. Every event comes from data already recorded, in the wave 1 event shape
(`schemas/order_inquiry_history.py`), newest first:

- the portal submissions (`PortalRevisionService.list_revisions`, its `changes` as they are),
- status, assignee and print-by changes (`audit_logs` UPDATE rows of the request),
- line price changes (`audit_logs` UPDATE rows of its lines: promotion, price, price type),
- design saves (`page_version` rows of the request's page),
- change requests (`price_tag_review_comments`, one event per review round).

Any other column change and every line / tag / part INSERT or DELETE row is not an event.

UAC: `documentation/plans/audit/standard-history-w5-acceptance-criteria.md` AC-W5-1 to W5-4.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.marketing import Promotion
from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
from app.services import price_tag_review_service
from app.services.history_common import audit_actor, contact_names
from app.services.history_common import history_event as _event
from app.services.history_common import history_line as _entry
from app.services.order_inquiry_history_service import AUTOMATIC
from app.services.portal_revision_service import PortalRevisionService
from app.services.price_tag_request_service import (
    PRINT_BY_OFFICE,
    PRINT_BY_SELF,
    PriceTagRequestService,
)
from app.services.project_service import resolve_user_names

#: The screen's words (`sorento_crm_frontend/lib/price-tag-status.ts`), one map on this side.
STATUS_LABEL = {
    "new": "New",
    "designing": "Designing",
    "proof_ready": "Design Ready",
    "changes_requested": "Changes Requested",
    "approved": "Approved",
    "ready_for_collection": "Ready for collection",
    "collected": "Collected",
    "rejected": "Rejected",
    "void": "Void",
    "draft": "Draft",
}
_PRINT_BY_LABEL = {PRINT_BY_OFFICE: "Office prints", PRINT_BY_SELF: "Salesperson prints"}
_PRICE_TYPE_LABEL = {"list": "List price", "selling": "Selling price"}
_REVISION_KIND = {"original": "submitted", "revision": "revised", "resubmission": "resubmitted"}
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def history_for_price_tag_request(db: Session, request_id: str) -> List[dict]:
    request = db.query(PriceTagRequest).filter(PriceTagRequest.id == str(request_id)).first()
    if request is None:
        return []
    events: List[dict] = []
    events += _revisions(db, request)
    events += _header_changes(db, request)
    events += _line_prices(db, request)
    events += _design_saves(db, request)
    events += _review_rounds(db, request)
    names = resolve_user_names(db, {e["_actor_id"] for e in events if e.get("_actor_id")})
    for event in events:
        actor_id = event.pop("_actor_id", None)
        if event.get("actor") is None:
            event["actor"] = names.get(actor_id) or AUTOMATIC
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return events


def _status_label(code: Optional[str]) -> str:
    code = (code or "").strip().lower()
    return STATUS_LABEL.get(code) or code.replace("_", " ").capitalize()


def _text(value: Any) -> str:
    """A snapshot value in words: lists joined, an ISO date as dd/mm/yyyy."""
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(v) for v in value if v is not None)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    match = _ISO_DATE.match(text)
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}" if match else text


def _change_text(change: dict) -> str:
    label, before, after = change.get("label"), change.get("from"), change.get("to")
    if before is None:
        return f"{label}: {_text(after)}"
    if after is None:
        return f"{label}: {_text(before)}"
    return f"{label}: {_text(before)} → {_text(after)}"


def _revisions(db: Session, request: PriceTagRequest) -> List[dict]:
    out = []
    for revision in PortalRevisionService(db).list_revisions("price_tag_request", request.id):
        kind = _REVISION_KIND.get(revision.get("kind"))
        if kind is None:
            continue
        if kind == "revised":
            title = f"Revised, revision {revision.get('revision_no')}"
            if revision.get("reason"):
                title += f": {revision['reason']}"
        else:
            title = "Submitted" if kind == "submitted" else "Resubmitted"
        event_id = f"revision-{revision['id']}"
        lines = [
            _entry(i, event_id, None, None, None, _change_text(change))
            for i, change in enumerate(revision.get("changes") or [])
        ]
        out.append(_event(event_id, kind, revision.get("submitted_at"), None, title, lines,
                          actor=revision.get("submitted_by")))
    return out


def _header_changes(db: Session, request: PriceTagRequest) -> List[dict]:
    audits = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "price_tag_requests",
            AuditLog.entity_id == str(request.id),
            AuditLog.action == "UPDATE",
        )
        .all()
    )
    audits = [a for a in audits if {"status", "assigned_to_id", "print_by"} & set(a.new_values or {})]
    if not audits:
        return []
    actors = audit_actor(db, audits)
    assignees = resolve_user_names(
        db, {str((a.new_values or {}).get("assigned_to_id")) for a in audits if (a.new_values or {}).get("assigned_to_id")}
    )
    out = []
    for audit in audits:
        new, old = audit.new_values or {}, audit.old_values or {}
        actor = actors.get(str(audit.id))
        base = f"audit-{audit.id}"
        if "status" in new:
            title = (
                f"Status: {_status_label(old['status'])} → {_status_label(new['status'])}"
                if old.get("status") else f"Status: {_status_label(new['status'])}"
            )
            out.append(_event(f"{base}:status", "status_changed", audit.changed_at, audit.user_id, title, [], actor=actor))
        if "assigned_to_id" in new:
            assignee = new.get("assigned_to_id")
            if assignee:
                name = assignees.get(str(assignee))
                title = f"Assigned to {name}" if name else "Assigned"
            else:
                title = "Unassigned"
            out.append(_event(f"{base}:assigned", "assigned", audit.changed_at, audit.user_id, title, [], actor=actor))
        if "print_by" in new:
            label = _PRINT_BY_LABEL.get(new.get("print_by"))
            title = f"Printing: {label}" if label else "Printing: not chosen"
            out.append(_event(f"{base}:print_by", "print_by", audit.changed_at, audit.user_id, title, [], actor=actor))
    return out


_LINE_PRICE_FIELDS = ("promotion_id", "manual_sell_price", "price_type")


def _line_prices(db: Session, request: PriceTagRequest) -> List[dict]:
    audits = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "price_tag_request_lines",
            AuditLog.action == "UPDATE",
            AuditLog.root_entity_type == "price_tag_requests",
            AuditLog.root_entity_id == str(request.id),
        )
        .all()
    )
    audits = [
        a for a in audits
        if set(_LINE_PRICE_FIELDS) & (set(a.new_values or {}) | set(a.old_values or {}))
    ]
    if not audits:
        return []
    items = _line_items(db, {str(a.entity_id) for a in audits})
    promotion_ids = {
        str(v)
        for a in audits
        for v in ((a.old_values or {}).get("promotion_id"), (a.new_values or {}).get("promotion_id"))
        if v
    }
    promotions = (
        {str(i): d for i, d in db.query(Promotion.id, Promotion.description).filter(Promotion.id.in_(list(promotion_ids))).all() if d}
        if promotion_ids
        else {}
    )
    actors = audit_actor(db, audits)

    def promotion(value) -> str:
        return (promotions.get(str(value)) or "a removed promotion") if value else "none"

    def price(value) -> str:
        return str(value) if value is not None else "none"

    def price_type(value) -> str:
        return _PRICE_TYPE_LABEL.get(value, str(value)) if value else "request default"

    words = {"promotion_id": ("promotion", promotion), "manual_sell_price": ("price", price),
             "price_type": ("price type", price_type)}
    out = []
    for audit in audits:
        new, old = audit.new_values or {}, audit.old_values or {}
        event_id = f"audit-{audit.id}"
        item = items.get(str(audit.entity_id)) or "Line"
        lines = []
        for field in _LINE_PRICE_FIELDS:
            if field not in new and field not in old:
                continue
            word, fmt = words[field]
            lines.append(_entry(len(lines), event_id, None, item, None,
                                f"{word} {fmt(old.get(field))} → {fmt(new.get(field))}"))
        out.append(_event(event_id, "line_price", audit.changed_at, audit.user_id, "Line price changed", lines,
                          actor=actors.get(str(audit.id))))
    return out


def _line_items(db: Session, line_ids) -> Dict[str, str]:
    """`line id -> product code / set code`, two queries for every line of the events."""
    from app.models.product import Product
    from app.models.product_set import ProductSet

    lines = db.query(PriceTagRequestLine).filter(PriceTagRequestLine.id.in_(list(line_ids))).all()
    product_ids = {l.product_id for l in lines if l.product_id}
    set_ids = {l.product_set_id for l in lines if l.product_set_id}
    products = (
        dict(db.query(Product.id, Product.product_code).filter(Product.id.in_(list(product_ids))).all())
        if product_ids else {}
    )
    sets = (
        dict(db.query(ProductSet.id, ProductSet.set_code).filter(ProductSet.id.in_(list(set_ids))).all())
        if set_ids else {}
    )
    out = {}
    for line in lines:
        code = products.get(line.product_id) if line.product_id else sets.get(line.product_set_id)
        if code:
            out[str(line.id)] = code
    return out


def _design_saves(db: Session, request: PriceTagRequest) -> List[dict]:
    if not request.page_id:
        return []
    out = []
    for version in PriceTagRequestService.list_page_versions(db, request.page_id):
        title = f"Design saved, version {version.version}"
        if version.commit_message:
            title += f": {version.commit_message}"
        out.append(_event(f"design-{version.version}", "design_saved", version.created_at,
                          str(version.created_by) if version.created_by else None, title, []))
    return out


def _review_rounds(db: Session, request: PriceTagRequest) -> List[dict]:
    rounds: Dict[int, list] = {}
    for comment in price_tag_review_service.list_comments(db, request.id):
        rounds.setdefault(comment.round, []).append(comment)
    if not rounds:
        return []
    firsts = {n: comments[0] for n, comments in rounds.items()}
    contacts = contact_names(db, {c.author_contact_id for c in firsts.values() if c.author_contact_id})
    out = []
    for round_no, comments in rounds.items():
        first = firsts[round_no]
        count = len(comments)
        title = f"Changes requested: {count} comment" + ("" if count == 1 else "s")
        actor = contacts.get(str(first.author_contact_id)) if first.author_contact_id else None
        out.append(_event(f"review-round-{round_no}", "changes_requested", first.created_at,
                          None if actor else (str(first.author_user_id) if first.author_user_id else None),
                          title, [], actor=actor))
    return out
