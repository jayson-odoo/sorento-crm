"""The agent's reply after a `crm_query` result, through the real loop with a scripted model (no live LLM).

Crew pass on f54a8859 (5 Nov): the model left out product names, dropped the cancelled-orders note in 2 of 3 runs
and wrote one period as yyyy-mm-dd. The tool output decides those (row `label`, `scope_note`, `period_display`) and
`loop.final_reply` enforces them, so the reply is right whatever the model writes.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

import app.main  # noqa: F401
from app.models.company import UserCompany
from app.models.order import Order
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._ported_reads_support import panel_turn
from tests.chatbot.agent._seed import seed_agent_contact

QUERY = "crm_query"


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def asks(name, args, cid="call-1"):
    return ChatResult(content="", prompt_tokens=10, completion_tokens=5, total_tokens=15,
                      tool_calls=[{"id": cid, "name": name, "arguments": args}])


def answer(text, cid="ans-1"):
    return ChatResult(content="", prompt_tokens=10, completion_tokens=5, total_tokens=15, tool_calls=[
        {"id": cid, "name": "answer", "arguments": {"text": text, "figures": [], "not_found": [], "not_checked": []}},
    ])


class Scripted:
    def __init__(self, script):
        self.script = list(script)

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        return self.script.pop(0)


def agent_contact(db, *slugs):
    contact = seed_agent_contact(db, slugs=slugs)
    db.add(UserCompany(user_id=contact["user_id"], company_id=DEFAULT_COMPANY_ID))
    db.flush()
    return contact


def turn(db, contact, script, text, *, panel):
    from app.services.chatbot.agent.loop import run_agent_turn

    def go():
        return run_agent_turn(db, contact_respond_id=contact["respond_id"], text=text, provider=Scripted(script),
                              mcp_call=lambda n, a: {}, catalog={})

    if panel:
        with panel_turn(contact["user_id"]):
            return go()
    return go()


def products(db, t: str) -> None:
    cat = ProductCategory(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, category_code=unique_code("ZC"), category_name="C")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, uom_code=unique_code("ZU"), uom_name="U")
    brand = Brand(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, brand_code=unique_code("ZB"), brand_name="B")
    db.add_all([cat, uom, brand])
    db.flush()
    for code, name, price in ((f"{t}-CB600", "Concealed Basin 600", "5000"), (f"{t}-BT", "Bath Tub 1108", "4000")):
        db.add(Product(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, product_code=code, product_name=name,
                       category_id=cat.id, base_uom_id=uom.id, brand_id=brand.id, list_price=Decimal(price)))
    db.flush()


@pytest.mark.parametrize("panel", [True, False], ids=["panel", "whatsapp_linked_user"])
def test_a_product_shown_by_code_alone_is_shown_by_its_label(db, panel):
    t = "ZZT" + uuid.uuid4().hex[:6].upper()
    products(db, t)
    contact = agent_contact(db, "master_data.products.view")
    spec = {"entity": "product", "fields": ["list_price"], "sort": [{"field": "list_price", "dir": "desc"}],
            "filters": [{"field": "product_code", "op": "starts_with", "value": t}], "limit": 3}
    reply = turn(db, contact, [asks(QUERY, spec), answer(f"1. {t}-CB600: RM 5,000\n2. {t}-BT: RM 4,000")],
                 "top 3 products by list price", panel=panel).reply_text
    assert f"{t}-CB600: Concealed Basin 600" in reply
    assert f"{t}-BT: Bath Tub 1108" in reply


def test_an_order_count_reply_carries_the_scope_note_and_no_iso_date(db):
    t = "ZZT" + uuid.uuid4().hex[:6].upper()
    for n, cancelled in ((1, False), (2, True)):
        db.add(Order(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, order_number=f"{t}-{n}", debtor_code=t,
                     agent="AGENT A", order_date=date(2026, 10, 5), is_cancelled=cancelled))
    db.flush()
    contact = agent_contact(db, "order_management.orders.view")
    spec = {"entity": "order", "group_by": ["agent"], "aggregates": [{"fn": "count"}], "filters": [
        {"field": "debtor_code", "op": "eq", "value": t},
        {"field": "order_date", "op": "between", "value": ["2026-10-01", "2026-10-31"]},
    ]}
    reply = turn(db, contact, [asks(QUERY, spec), answer("From 2026-10-01 to 2026-10-31: AGENT A 1 order.")],
                 "delivery orders per agent last month", panel=True).reply_text
    assert "Cancelled orders excluded." in reply
    assert "01/10/2026" in reply and "31/10/2026" in reply
    assert "2026-10-01" not in reply


def _ledger(rows, scope_note=None):
    return {"c1": {"name": QUERY, "status": "ok", "args": {}, "data": {
        "entity": "product", "rows": rows, "total": len(rows), "truncated": False, "restricted": [],
        "period_display": None, "scope_note": scope_note,
    }}}


ROWS = [{"id": "x1", "label": "CB600-NL: Concealed Basin 600", "list_price": 5000.0}]


@pytest.mark.parametrize("written", [
    "1. CB600-NL: RM 5,000",
    "1. CB600-NL (Concealed Basin 600): RM 5,000",
    "| Product | Price |\n|---|---|\n| CB600-NL | RM 5,000 |",
    "1. **CB600-NL** - RM 5,000",
    "1. cb600-nl at RM 5,000",
    "1. CB600-NL: Concealed Basin 600, RM 5,000",
], ids=["code_alone", "code_brackets_name", "table", "bold", "lower_case", "already_label"])
def test_every_way_a_model_shows_the_code_ends_as_the_label(written):
    from app.services.chatbot.agent.loop import final_reply

    reply, _ = final_reply({"text": written}, [], [], ledger=_ledger(ROWS))
    assert reply.count("CB600-NL: Concealed Basin 600") == 1, reply
    assert "(Concealed Basin 600)" not in reply


def test_the_scope_note_is_added_once_and_iso_dates_become_dd_mm_yyyy():
    from app.services.chatbot.agent.loop import final_reply

    ledger = _ledger([], scope_note="Cancelled orders excluded.")
    reply, _ = final_reply({"text": "Orders from 2026-10-01 to 2026-10-31: 12."}, [], [], ledger=ledger)
    assert reply == "Orders from 01/10/2026 to 31/10/2026: 12.\n\nCancelled orders excluded."
    said, _ = final_reply({"text": "12 orders (cancelled orders excluded)."}, [], [], ledger=ledger)
    assert said == "12 orders (cancelled orders excluded)."
    # a code that only looks like a date, and an impossible date, are left alone
    kept, _ = final_reply({"text": "SO-2026-10-01 and 2026-13-45"}, [], [], ledger={})
    assert kept == "SO-2026-10-01 and 2026-13-45"
