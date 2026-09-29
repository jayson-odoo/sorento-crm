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
