"""Shared seeding for the sales-asks-todo suites (not collected by pytest).

Every test seeds its OWN chain: agents (each with a linked respond contact), customers
assigned to them, asks with explicit `created_at`. Nothing is borrowed from an existing row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.models.stock_ask import StockAsk

SORENTO = "00000000-0000-0000-0000-000000000001"
#: 11:00 Malaysia; today_start = 2026-09-28T16:00:00Z.
NOW = datetime(2026, 9, 29, 3, 0, 0)
TODAY_START = datetime(2026, 9, 28, 16, 0, 0)


def uid() -> str:
    return str(uuid.uuid4())


def contact(db, name: str) -> str:
    cid = uid()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, name, session_vars) "
            "VALUES (:id, :rid, :phone, :name, CAST('{}' AS jsonb))"
        ),
        {"id": cid, "rid": f"ZZT-{uid()[:8]}", "phone": f"+6006{uuid.uuid4().int % 10**7:07d}", "name": name},
    )
    return cid


def agent(db, contact_id, code: str) -> SalesAgent:
    row = SalesAgent(id=uid(), sales_agent=f"ZZT{code}{uid()[:4]}", contact_id=contact_id, company_id=SORENTO)
    db.add(row)
    db.flush()
    return row


def customer(db, name: str, sales_agent, company_id: str = SORENTO) -> Customer:
    row = Customer(
        id=uid(),
        customer_code=f"ZZT-C-{uid()[:6]}",
        customer_name=name,
        company_id=company_id,
        sales_agent_id=sales_agent.id if sales_agent else None,
    )
    db.add(row)
    db.flush()
    return row


def ask(db, cust, contact_id, code="SRT1", *, created_at=None, branch="in_stock", state="open", **over) -> StockAsk:
    row = StockAsk(
        id=over.pop("id", uid()),
        company_id=SORENTO,
        customer_id=cust.id if cust else None,
        contact_id=contact_id,
        product_code=code,
        quantity=10,
        branch=branch,
        answer_summary=f"{code} x 10: answer.",
        notified_agent=True,
        state=state,
        created_at=created_at or NOW - timedelta(hours=1),
        **over,
    )
    db.add(row)
    db.flush()
    return row


def world(db) -> dict:
    """Agents A (contact CA) and B (contact CB); X and Y are A's customers, Z is B's."""
    dealer = contact(db, "Ah Seng")
    ca = contact(db, "Agent Alpha")
    cb = contact(db, "Agent Beta")
    a = agent(db, ca, "A")
    b = agent(db, cb, "B")
    return {
        "dealer": dealer,
        "ca": ca,
        "cb": cb,
        "a": a,
        "b": b,
        "x": customer(db, "Customer X", a),
        "y": customer(db, "Customer Y", a),
        "z": customer(db, "Customer Z", b),
    }


# ---- conversation seeding (S3, AC-ST309 to 311) -------------------------------------------
#: `chat_histories.contact_id` carries `respond_contacts.respond_io_id`, NOT `respond_contacts.id`
#: (conversation_thread_service.py: `ChatHistory.contact_id == contact.respond_io_id`).
ASK_AT = datetime(2026, 9, 29, 3, 0, 0)  # 11:00 Malaysia; the Malaysia day is 09-28T16:00Z .. 09-29T16:00Z


def respond_io_id(db, contact_id: str) -> str:
    return db.execute(text("SELECT respond_io_id FROM respond_contacts WHERE id = :i"), {"i": contact_id}).scalar_one()


def chat(db, respond_io_id_value: str, at: datetime, kind: str, message: str):
    """One `chat_histories` row; `kind` is 'incoming' or 'outgoing'. Returns the row (id is a bigint)."""
    from app.models.chat_history import ChatHistory

    row = ChatHistory(
        channel="whatsapp",
        contact_id=respond_io_id_value,
        phone_number="+60123456789",
        message=message,
        sent_at=at,
        type=kind,
    )
    db.add(row)
    db.flush()
    return row


def conversation_world(db) -> dict:
    """`world` plus X's ask at ASK_AT with a rich chat around it, and a second contact's chat row in
    the window. Rows (minutes relative to ASK_AT): in -10 (the question), out +1 (unrelated), out +2
    (contains the answer_summary), out +20; outside the window: -31 and +31; another contact: 0."""
    w = world(db)
    rid = respond_io_id(db, w["dealer"])
    row = ask(db, w["x"], w["dealer"], "SRT-CONV", created_at=ASK_AT)
    other = contact(db, "Other Dealer")
    m = timedelta(minutes=1)
    w.update(
        rid=rid,
        ask=row,
        q_in=chat(db, rid, ASK_AT - 10 * m, "incoming", "Got SRT-CONV? 10 pcs"),
        out_other=chat(db, rid, ASK_AT + 1 * m, "outgoing", "One moment please"),
        out_answer=chat(db, rid, ASK_AT + 2 * m, "outgoing", f"Hi!\n{row.answer_summary}\nAnything else?"),
        out_late=chat(db, rid, ASK_AT + 20 * m, "outgoing", "Following up"),
        too_early=chat(db, rid, ASK_AT - 31 * m, "incoming", "way before"),
        too_late=chat(db, rid, ASK_AT + 31 * m, "incoming", "way after"),
        other_contact_row=chat(db, respond_io_id(db, other), ASK_AT, "incoming", "someone else's chat"),
        uuid_keyed_row=chat(db, w["dealer"], ASK_AT, "incoming", "keyed by the respond_contacts.id"),
    )
    return w
