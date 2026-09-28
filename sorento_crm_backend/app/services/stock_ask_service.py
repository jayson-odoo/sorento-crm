"""Chatbot stock ask v2 (PLAN-chatbot-stock-ask-v2-24sep.md): what happens after a stock ask
is answered.

S4 (R8): when the asking contact's "Notify salesman" is on, the customer's sales agent gets
one WhatsApp message per answered product for `too_big`, `in_stock` and `no_incoming` (never
`incoming`, R6 B3). The chain is dealer contact -> customer (`resolve_customer`) ->
`customers.sales_agent_id` -> `sales_agents.contact_id` -> that contact's `respond_io_id`. A
missing link is a skip with its reason and a warning, never a raise. The send goes through
`send_text_or_template` (the `stock_ask_salesman` template outside the 24-hour window, the
same wording as plain text inside it) and every attempt writes one `integration_log` row.

Core, not the chatbot package: the engine calls in here once the turn row is closed, and the
RQ job (`app/tasks/stock_ask_tasks.py`) runs the send. Nothing here imports
`app.services.chatbot` (`tests/chatbot/test_import_boundary.py`).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.services.queue_service import enqueue_job
from app.services.respond_messaging_service import send_text_or_template

logger = logging.getLogger(__name__)

USE_CASE = "stock_ask_salesman"
#: R6: B1, B2 and B4 notify the agent; B3 (`incoming`) never does.
NOTIFIED_BRANCHES = frozenset({"too_big", "in_stock", "no_incoming"})
ANSWERED_BRANCHES = frozenset({"too_big", "in_stock", "incoming", "no_incoming"})

_OUTCOME = {
    "in_stock": "in stock",
    "too_big": "too big",
    "no_incoming": "no stock no incoming",
}
_MALAYSIA = timezone(timedelta(hours=8))


def outcome_phrase(branch: str, *, cap_unset: bool = False, category_name: Optional[str] = None) -> str:
    """R8's outcome slot. B1 with no X set on the product or its category reads "no cap set
    for <category>" so the agent knows why the bot would not answer."""
    if branch == "too_big" and cap_unset:
        return f"no cap set for {category_name or 'this category'}"
    return _OUTCOME.get(branch, branch)


def asked_at_label(moment: datetime) -> str:
    """dd/mm/yyyy HH:MM on the Malaysia wall clock."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_MALAYSIA).strftime("%d/%m/%Y %H:%M")


def default_text(ctx: dict[str, Any]) -> str:
    """The wording sent in-window when no template is mapped (plan sample (a))."""
    return (
        f"Stock ask - {ctx['customer_name']} (contact: {ctx['contact_name']}) asked about "
        f"{ctx['product']}, qty {ctx['quantity']}, outcome: {ctx['outcome']}. "
        f"Asked at {ctx['asked_at']}."
    )


def answered_entries(entries: Iterable[Any]) -> list[dict[str, Any]]:
    """The `stock_availability` entries that carry an answer: a branch and the dealer's
    quantity. An entry still owing a quantity has no branch and is not an ask yet."""
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict) or entry.get("branch") not in ANSWERED_BRANCHES:
            continue
        qty = entry.get("requested_qty")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            continue
        out.append(entry)
    return out


def answer_line(reply_text: str, entry: dict[str, Any]) -> str:
    """The exact line the dealer was sent for this entry: R14 starts every answer line
    with "<code> x <Q>:", so the line is found by that prefix in the reply."""
    label = entry.get("product_code") or entry.get("product_name") or ""
    prefix = f"{label} x {entry.get('requested_qty')}:"
    for line in (reply_text or "").splitlines():
        if line.strip().startswith(prefix):
            return line.strip()
    return prefix


def _write_company_id(db: Session, customer: Any) -> Optional[str]:
    """The ask belongs to its customer's company; an ask with no customer takes the
    turn's own company scope (the asking contact's company)."""
    if customer is not None:
        return customer.company_id
    from app.models.base import get_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID, resolve_write_company_id

    return resolve_write_company_id(get_company_scope(db), ambiguous=DEFAULT_COMPANY_ID)


def after_answered_turn(
    db: Session,
    *,
    turn_id: str,
    contact_id: Optional[str],
    notify_salesman: bool,
    entries: Iterable[Any],
    reply_text: str = "",
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Run once a LIVE turn's row is closed (the engine never calls this on a dry run).

    S5: one `stock_asks` row per answered entry, state open, with the exact line the dealer
    was sent. S4: one `notify_salesman` job per B1 / B2 / B4 row when the contact's toggle
    is on and a customer is known; every other row records why it was not sent. Returns the
    facts it enqueued. The dealer's reply has already been handed back by then.
    """
    from app.models.order import Customer
    from app.models.stock_ask import StockAsk
    from app.services.contact_customer_service import resolve_customer

    answered = answered_entries(entries)
    if not answered:
        return []
    moment = now or datetime.now(timezone.utc)
    customer_id = resolve_customer(db, contact_id) if contact_id else None
    customer = (
        db.query(Customer).filter(Customer.id == customer_id).first() if customer_id else None
    )
    company_id = _write_company_id(db, customer)

    rows: list[tuple[StockAsk, dict[str, Any], bool]] = []
    for entry in answered:
        branch = entry["branch"]
        if branch not in NOTIFIED_BRANCHES:
            reason: Optional[str] = "not_notified_branch"
        elif not notify_salesman:
            reason = "toggle_off"
        elif customer is None:
            reason = "no_customer"
        else:
            reason = None
        ask = StockAsk(
            company_id=company_id,
            customer_id=customer.id if customer is not None else None,
            contact_id=contact_id,
            product_id=entry.get("product_id"),
            product_code=(entry.get("product_code") or entry.get("product_name") or "")[:100],
            quantity=entry["requested_qty"],
            branch=branch,
            answer_summary=answer_line(reply_text, entry),
            notified_agent=False,
            notify_skip_reason=reason,
            state="open",
        )
        db.add(ask)
        rows.append((ask, entry, reason is None))
    db.commit()

    enqueued = []
    for ask, entry, notify in rows:
        if not notify:
            continue
        facts = {
            "ask_id": ask.id,
            "customer_id": ask.customer_id,
            "company_id": ask.company_id,
            "turn_id": turn_id,
            "contact_id": contact_id,
            "product_id": entry.get("product_id"),
            "product_code": ask.product_code,
            "product_name": entry.get("product_name"),
            "quantity": ask.quantity,
            "branch": ask.branch,
            "cap_unset": bool(entry.get("cap_unset")),
            "category_name": entry.get("category_name"),
            "asked_at": moment.isoformat(),
        }
        from app.tasks.stock_ask_tasks import notify_salesman as notify_job

        enqueue_job(notify_job, facts, queue_name="respond_io", job_timeout=180)
        enqueued.append(facts)
    return enqueued


def _record_outcome(db: Session, facts: dict[str, Any], *, sent: bool, reason: Optional[str]) -> None:
    """S5: the job's outcome on the ask row (`notified_agent`, or why not)."""
    ask_id = facts.get("ask_id")
    if not ask_id:
        return
    from app.models.stock_ask import StockAsk

    try:
        db.query(StockAsk).filter(StockAsk.id == ask_id).update(
            {"notified_agent": sent, "notify_skip_reason": None if sent else reason},
            synchronize_session=False,
        )
        db.commit()
    except Exception:  # noqa: BLE001 - the send already happened or was logged
        db.rollback()
        logger.warning("stock ask %s: could not record the notification outcome", ask_id)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


def _contact_label(contact: Any) -> str:
    """The contact's display name. It comes off their own WhatsApp profile, so control
    characters and line breaks are folded to one space and the length is capped before it
    reaches another person's message (security review, lane PR #1333)."""
    raw = (
        getattr(contact, "name", None)
        or " ".join(filter(None, [getattr(contact, "first_name", None), getattr(contact, "last_name", None)]))
        or getattr(contact, "phone_number", None)
        or "-"
    )
    return _CONTROL_CHARS.sub(" ", str(raw)).strip()[:100] or "-"


def _recipient(
    db: Session, contact_id: Optional[str], customer_id: Optional[str] = None
) -> tuple[Any, Any, Any, Optional[str]]:
    """(dealer contact, customer, agent's Respond contact, skip reason).

    `customer_id` is the customer the ask row was written against, in the turn's own
    company scope. When the job carries it, it is used as is: resolving the contact's
    customer again here, later and under another scope, could pick a different customer
    (security review, lane PR #1333)."""
    from app.models.access import RespondContact
    from app.models.order import Customer
    from app.models.sales_agent import SalesAgent
    from app.services.contact_customer_service import resolve_customer

    dealer = (
        db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if contact_id
        else None
    )
    if customer_id is None and contact_id:
        customer_id = resolve_customer(db, contact_id)
    customer = (
        db.query(Customer).filter(Customer.id == customer_id).first() if customer_id else None
    )
    if customer is None:
        return dealer, None, None, "no_customer"
    agent = (
        db.query(SalesAgent).filter(SalesAgent.id == customer.sales_agent_id).first()
        if customer.sales_agent_id
        else None
    )
    if agent is None:
        return dealer, customer, None, "no_sales_agent"
    agent_contact = (
        db.query(RespondContact).filter(RespondContact.id == agent.contact_id).first()
        if agent.contact_id
        else None
    )
    if agent_contact is None:
        return dealer, customer, None, "agent_has_no_contact"
    if not agent_contact.respond_io_id:
        return dealer, customer, agent_contact, "agent_contact_has_no_respond_id"
    return dealer, customer, agent_contact, None


def _log(
    db: Session,
    *,
    facts: dict[str, Any],
    identifier: str,
    status: str,
    request_payload: dict,
    status_code: Optional[int] = None,
    response_payload: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService

    IntegrationLogService(db).create_integration_log(
        IntegrationLogCreate(
            integration_channel="respond_io",
            # S5: the ask row, once there is one; a job enqueued before S5 names the turn.
            business_table="stock_asks" if facts.get("ask_id") else "chatbot_turns",
            business_id=facts.get("ask_id") or facts["turn_id"],
            external_reference=identifier,
            direction="outbound",
            endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message",
            http_method="POST",
            status=status,
            status_code=status_code,
            response_payload=response_payload,
            error_message=error_message,
        ),
        request_payload_dict=request_payload,
    )


def notify_salesman(db: Session, facts: dict[str, Any]) -> dict[str, Any]:
    """The job body: resolve the agent, send, log. Never raises.

    Returns `{"status": "sent", "sent_as": ...}`, `{"status": "skipped", "reason": ...}` or
    `{"status": "failed", "error": ...}`.
    """
    try:
        dealer, customer, agent_contact, reason = _recipient(
            db, facts.get("contact_id"), facts.get("customer_id")
        )
    except Exception as exc:  # noqa: BLE001 - a broken read is a failed attempt, not a crash
        logger.warning("stock ask %s: recipient lookup failed: %s", facts.get("turn_id"), exc)
        db.rollback()
        _record_outcome(db, facts, sent=False, reason="send_failed")
        return {"status": "failed", "error": str(exc)}
    if reason is not None:
        logger.warning(
            "stock ask %s (%s x %s): salesman not notified, %s",
            facts.get("turn_id"),
            facts.get("product_code"),
            facts.get("quantity"),
            reason,
        )
        _record_outcome(db, facts, sent=False, reason=reason)
        return {"status": "skipped", "reason": reason}

    name = facts.get("product_name")
    code = facts.get("product_code") or ""
    asked_at = facts.get("asked_at")
    moment = datetime.fromisoformat(asked_at) if asked_at else datetime.now(timezone.utc)
    ctx = {
        "outcome": outcome_phrase(
            facts.get("branch") or "",
            cap_unset=bool(facts.get("cap_unset")),
            category_name=facts.get("category_name"),
        ),
        "customer_name": customer.customer_name,
        "contact_name": _contact_label(dealer),
        "product": f"{code} - {name}" if name and name != code else code,
        "quantity": str(facts.get("quantity")),
        "asked_at": asked_at_label(moment),
    }
    text_ = default_text(ctx)
    identifier = str(agent_contact.respond_io_id)
    attempted: dict = {"message": {"type": "text", "text": text_}}
    try:
        result = send_text_or_template(
            db,
            identifier=identifier,
            text=text_,
            use_case=USE_CASE,
            context_vars=ctx,
            respond_contact_id=str(agent_contact.id),
        )
    except Exception as exc:  # noqa: BLE001 - every failure is a failed log row
        resp = getattr(exc, "response", None)
        code_ = getattr(resp, "status_code", None) if resp is not None else None
        body = None
        if resp is not None:
            try:
                body = (resp.text or "")[:50000]
            except Exception:  # noqa: BLE001
                body = None
        try:
            _log(
                db,
                facts=facts,
                identifier=identifier,
                status="failed",
                request_payload=getattr(exc, "request_payload", attempted),
                status_code=code_,
                response_payload=body,
                error_message=str(exc),
            )
        except Exception:  # noqa: BLE001
            logger.warning("stock ask %s: could not write the failed send log", facts.get("turn_id"))
            db.rollback()
        logger.warning("stock ask %s: salesman send failed: %s", facts.get("turn_id"), exc)
        _record_outcome(db, facts, sent=False, reason="send_failed")
        return {"status": "failed", "error": str(exc)}

    response = result.get("response")
    _log(
        db,
        facts=facts,
        identifier=identifier,
        status="success",
        request_payload=result.get("request_payload") or attempted,
        response_payload=str(response)[:50000] if response else None,
    )
    _record_outcome(db, facts, sent=True, reason=None)
    return {"status": "sent", "sent_as": result.get("sent_as")}


# --------------------------------------------------------------------------------------- #
# S5 / S6: the asks record, read and worked by the office and by the sales agent
# --------------------------------------------------------------------------------------- #


def serialize(db: Session, rows: list[Any]) -> list[Any]:
    """Rows as `StockAskResponse`: the contact, customer and product NAMED, never their ids."""
    from app.models.access import RespondContact
    from app.models.order import Customer
    from app.models.product import Product
    from app.schemas.stock_ask import StockAskResponse

    rows = list(rows)
    contact_ids = {r.contact_id for r in rows if r.contact_id}
    customer_ids = {r.customer_id for r in rows if r.customer_id}
    product_ids = {r.product_id for r in rows if r.product_id}
    contacts = (
        {c.id: _contact_label(c) for c in db.query(RespondContact).filter(RespondContact.id.in_(contact_ids))}
        if contact_ids
        else {}
    )
    customers = (
        {
            c.id: c.customer_name
            for c in db.query(Customer.id, Customer.customer_name).filter(Customer.id.in_(customer_ids))
        }
        if customer_ids
        else {}
    )
    products = (
        {
            p.id: p.product_name
            for p in db.query(Product.id, Product.product_name).filter(Product.id.in_(product_ids))
        }
        if product_ids
        else {}
    )
    return [
        StockAskResponse(
            id=str(r.id),
            customer_name=customers.get(r.customer_id),
            contact_name=contacts.get(r.contact_id),
            product_code=r.product_code,
            product_name=products.get(r.product_id),
            quantity=r.quantity,
            branch=r.branch,
            answer_summary=r.answer_summary,
            notified_agent=bool(r.notified_agent),
            notify_skip_reason=r.notify_skip_reason,
            state=r.state,
            note=r.note,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def _page(query: Any, page: int, limit: int) -> tuple[list[Any], int]:
    from app.models.stock_ask import StockAsk

    total = query.count()
    rows = (
        query.order_by(StockAsk.created_at.desc(), StockAsk.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return rows, total


def _apply_update(db: Session, ask: Any, data: dict[str, Any]) -> Any:
    if "state" in data and data["state"] is not None:
        ask.state = data["state"]
    if "note" in data:
        note = (data["note"] or "").strip()
        ask.note = note or None
    db.commit()
    db.refresh(ask)
    return ask


def _customer_or_404(db: Session, customer_id: str) -> Any:
    from app.models.order import Customer
    from app.services.error_handler import handle_not_found

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise handle_not_found("Customer", customer_id)
    return customer


def list_for_customer(db: Session, customer_id: str, *, page: int, limit: int) -> dict[str, Any]:
    """The CRM Asks tab: one customer's asks, newest first. A customer outside the caller's
    company scope is a 404, so another company's asks never show."""
    from app.models.stock_ask import StockAsk

    _customer_or_404(db, customer_id)
    rows, total = _page(db.query(StockAsk).filter(StockAsk.customer_id == customer_id), page, limit)
    return {
        "data": serialize(db, rows),
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def update_for_customer(db: Session, customer_id: str, ask_id: str, data: dict[str, Any]) -> Any:
    from app.models.stock_ask import StockAsk
    from app.services.error_handler import handle_not_found

    _customer_or_404(db, customer_id)
    ask = (
        db.query(StockAsk)
        .filter(StockAsk.id == ask_id, StockAsk.customer_id == customer_id)
        .first()
    )
    if ask is None:
        raise handle_not_found("Stock ask", ask_id)
    return serialize(db, [_apply_update(db, ask, data)])[0]


def _agent_scope(db: Session, agent_id: str) -> Any:
    """S6 (R9): asks of customers assigned to this agent NOW (`customers.sales_agent_id`).
    An ask with no customer belongs to nobody's list."""
    from app.models.order import Customer
    from app.models.stock_ask import StockAsk

    return db.query(StockAsk).join(Customer, Customer.id == StockAsk.customer_id).filter(
        Customer.sales_agent_id == agent_id
    )


def list_for_agent(
    db: Session,
    agent_id: str,
    *,
    page: int,
    limit: int,
    q: Optional[str] = None,
    state: Optional[str] = None,
) -> dict[str, Any]:
    """The portal's Customer asks page, newest first. `q` matches the customer name or
    code, or the product code."""
    from sqlalchemy import or_

    from app.models.order import Customer
    from app.models.stock_ask import StockAsk

    query = _agent_scope(db, agent_id)
    if state:
        query = query.filter(StockAsk.state == state)
    term = (q or "").strip()
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        query = query.filter(
            or_(
                Customer.customer_name.ilike(like, escape="\\"),
                Customer.customer_code.ilike(like, escape="\\"),
                StockAsk.product_code.ilike(like, escape="\\"),
            )
        )
    rows, total = _page(query, page, limit)
    return {
        "data": serialize(db, rows),
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def update_for_agent(db: Session, agent_id: str, ask_id: str, data: dict[str, Any]) -> Any:
    from app.models.stock_ask import StockAsk
    from app.services.error_handler import handle_not_found

    ask = _agent_scope(db, agent_id).filter(StockAsk.id == ask_id).first()
    if ask is None:
        raise handle_not_found("Stock ask", ask_id)
    return serialize(db, [_apply_update(db, ask, data)])[0]
