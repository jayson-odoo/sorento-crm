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


def after_answered_turn(
    db: Session,
    *,
    turn_id: str,
    contact_id: Optional[str],
    notify_salesman: bool,
    entries: Iterable[Any],
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Run once a LIVE turn's row is closed (the engine never calls this on a dry run).

    Enqueues one `notify_salesman` job per answered B1 / B2 / B4 entry when the contact's
    toggle is on, and returns the facts it enqueued. The dealer's reply has already been
    handed back by then, so nothing here can hold it up.
    """
    if not notify_salesman:
        return []
    moment = now or datetime.now(timezone.utc)
    enqueued = []
    for entry in answered_entries(entries):
        if entry["branch"] not in NOTIFIED_BRANCHES:
            continue
        facts = {
            "turn_id": turn_id,
            "contact_id": contact_id,
            "product_id": entry.get("product_id"),
            "product_code": entry.get("product_code") or entry.get("product_name") or "",
            "product_name": entry.get("product_name"),
            "quantity": entry["requested_qty"],
            "branch": entry["branch"],
            "cap_unset": bool(entry.get("cap_unset")),
            "category_name": entry.get("category_name"),
            "asked_at": moment.isoformat(),
        }
        from app.tasks.stock_ask_tasks import notify_salesman as notify_job

        enqueue_job(notify_job, facts, queue_name="respond_io", job_timeout=180)
        enqueued.append(facts)
    return enqueued


def _contact_label(contact: Any) -> str:
    return (
        getattr(contact, "name", None)
        or " ".join(filter(None, [getattr(contact, "first_name", None), getattr(contact, "last_name", None)]))
        or getattr(contact, "phone_number", None)
        or "-"
    )


def _recipient(db: Session, contact_id: Optional[str]) -> tuple[Any, Any, Any, Optional[str]]:
    """(dealer contact, customer, agent's Respond contact, skip reason)."""
    from app.models.access import RespondContact
    from app.models.order import Customer
    from app.models.sales_agent import SalesAgent
    from app.services.contact_customer_service import resolve_customer

    dealer = (
        db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if contact_id
        else None
    )
    customer_id = resolve_customer(db, contact_id) if contact_id else None
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
            business_table="chatbot_turns",
            business_id=facts["turn_id"],
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
        dealer, customer, agent_contact, reason = _recipient(db, facts.get("contact_id"))
    except Exception as exc:  # noqa: BLE001 - a broken read is a failed attempt, not a crash
        logger.warning("stock ask %s: recipient lookup failed: %s", facts.get("turn_id"), exc)
        return {"status": "failed", "error": str(exc)}
    if reason is not None:
        logger.warning(
            "stock ask %s (%s x %s): salesman not notified, %s",
            facts.get("turn_id"),
            facts.get("product_code"),
            facts.get("quantity"),
            reason,
        )
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
    return {"status": "sent", "sent_as": result.get("sent_as")}
