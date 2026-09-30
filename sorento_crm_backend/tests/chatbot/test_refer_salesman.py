"""REFER-SALESMAN (owner ruling 30 Sep 2026, `PLAN-refer-salesman-30sep.md`): one refer
wording, and every reply that refers a dealer to their salesman is a Customer asks row.

Three parts:

* AC-RS03: a grep-shaped pin over the SOURCE (backend + MCP): the only refer sentence anywhere
  is `Please refer to your salesman.`, and the two constants that carry it are the same words.
* AC-RS10 to AC-RS15: the pure builder `refer_asks.referred_entries` (no I/O) that turns a
  refer reply into the `stock_asks` entries `stock_ask_service.after_answered_turn` writes.
* AC-RS04, AC-RS10, AC-RS11, AC-RS15, AC-RS16, AC-RS20: real turns through `engine.run_turn`
  (the `test_dealer_eta_stock_routing` harness: real engine, real incoming route, real MCP
  presenter, parser stubbed) writing real rows, and `serialize` reading them back.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.stock_ask import StockAsk
from app.services import stock_ask_service
from app.services.chatbot import refer_asks
from app.services.chatbot.turn.pending import Pending
from app.services.chatbot.turn.plan import FetchSpec, Plan, Trace
from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot.test_dealer_eta_stock_routing import (  # noqa: F401 - fixtures
    CODE,
    INCOMING,
    INCOMING_TOOL,
    SALESPERSON,
    TOLD_ETA,
    Console,
    _mcp,
    _seed,
    _v,
    stub_access,
)
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

BACKEND = Path(__file__).resolve().parents[2]
MCP = BACKEND.parent / "sorento_crm_mcp" / "sorento_crm_mcp"


# --------------------------------------------------------------------------- #
# AC-RS03: the one sentence, in the source
# --------------------------------------------------------------------------- #


def _source_files():
    for root in (BACKEND / "app", MCP):
        yield from root.rglob("*.py")


def test_ac_rs03_the_only_refer_sentence_in_the_source_is_the_constant():
    offenders = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if "refer to your salesperson" in low or "refer to your salesman to proceed" in low:
                offenders.append(f"{path.relative_to(BACKEND.parent)}:{n}: {line.strip()}")
            if re.search(r"refer to your salesman, ", low):
                offenders.append(f"{path.relative_to(BACKEND.parent)}:{n}: {line.strip()}")
    assert offenders == [], "\n".join(offenders)


def test_ac_rs03_backend_and_presenter_carry_the_same_words():
    import sys

    root = BACKEND.parent / "sorento_crm_mcp"
    if str(root) not in sys.path:
        sys.path.append(str(root))
    from sorento_crm_mcp import presenters

    assert REFER_TO_SALESMAN == "Please refer to your salesman."
    assert presenters.REFER_TO_SALESMAN == REFER_TO_SALESMAN
    assert refer_asks.REFER_TO_SALESMAN == REFER_TO_SALESMAN


# --------------------------------------------------------------------------- #
# The builder
# --------------------------------------------------------------------------- #


def _eta_item(code: str, etas: list[str]) -> dict:
    when = f"ETA: {', '.join(etas)}" if etas else "ETA: not confirmed yet"
    return {"title": f"{code}\n{when}" if code else when, "fields": [], "flags": {"dealer_view": True}}


def _envelope(domain: str, *, figures=(), miss=(), unresolved=(), entities=()) -> dict:
    return {
        "domain": domain,
        "figures": list(figures),
        "miss": list(miss),
        "unresolved": list(unresolved),
        "entities": list(entities),
        "has_result": bool(figures),
    }


def _plan(*codes: str, domain: str = "incoming", uuids: dict[str, str] | None = None) -> Plan:
    entities = [
        {"raw": c, "hint": "product", "canonical_code": c, "uuid": (uuids or {}).get(c)} for c in codes
    ]
    return Plan(
        domains=[domain],
        fetch=[FetchSpec(domain=domain, entities=entities, filters={}, date_window=None)],
        ask=None,
        denied=[],
        trace=Trace(),
    )


def _build(reply: str, envelopes=(), plan: Plan | None = None, pending=None, message="", answered=()):
    return refer_asks.referred_entries(
        reply_text=reply,
        envelopes=list(envelopes),
        plan=plan or Plan(domains=[], fetch=[], ask=None, denied=[], trace=Trace()),
        pending_before=pending,
        message_text=message,
        answered=list(answered),
    )


def test_refers_reads_the_sentence_case_insensitively_and_nothing_else():
    assert refer_asks.refers("SRT x 5: yes, we have stock. Please refer to your salesman.")
    assert refer_asks.refers("please refer to your salesman")
    assert not refer_asks.refers("How many units of SRT5674?")
    assert not refer_asks.refers("")
    assert not refer_asks.refers(None)


def test_a_reply_without_the_sentence_builds_nothing():
    env = _envelope("incoming", figures=[_eta_item("SRT1", ["2026-09-08"])], entities=["SRT1"])
    assert _build("SRT1\nETA: 2026-09-08", [env], _plan("SRT1")) == []


def test_ac_rs10_a_dealer_eta_reply_is_one_incoming_eta_entry_per_product_line():
    reply = f"SRT1\nETA: 2026-09-08\n\nSRT2\nETA: 2026-09-08, 2026-09-20\n\n{REFER_TO_SALESMAN}"
    env = _envelope(
        "incoming",
        figures=[_eta_item("SRT1", ["2026-09-08"]), _eta_item("SRT2", ["2026-09-08", "2026-09-20"])],
        entities=["SRT1", "SRT2"],
    )
    out = _build(reply, [env], _plan("SRT1", "SRT2", uuids={"SRT1": "u1"}))
    assert out == [
        {
            "product_code": "SRT1",
            "product_id": "u1",
            "requested_qty": None,
            "branch": "incoming_eta",
            "answer_summary": "ETA: 2026-09-08. Please refer to your salesman.",
        },
        {
            "product_code": "SRT2",
            "product_id": None,
            "requested_qty": None,
            "branch": "incoming_eta",
            "answer_summary": "ETA: 2026-09-08, 2026-09-20. Please refer to your salesman.",
        },
    ]


def test_ac_rs10_an_eta_line_with_no_date_says_so():
    env = _envelope("incoming", figures=[_eta_item("SRT1", [])], entities=["SRT1"])
    out = _build(f"SRT1\nETA: not confirmed yet\n\n{REFER_TO_SALESMAN}", [env], _plan("SRT1"))
    assert [e["answer_summary"] for e in out] == ["ETA: not confirmed yet. Please refer to your salesman."]


def test_ac_rs11_an_incoming_miss_is_one_referred_entry_per_missed_code():
    reply = f"Here's what you want:\n• product: SRT1\n\nBut no incoming matched these.\n\n{REFER_TO_SALESMAN}"
    env = _envelope("incoming", miss=["SRT1"], entities=["SRT1"])
    out = _build(reply, [env], _plan("SRT1", uuids={"SRT1": "u1"}))
    assert out == [
        {
            "product_code": "SRT1",
            "product_id": "u1",
            "requested_qty": None,
            "branch": "referred",
            "answer_summary": reply,
        }
    ]


def test_ac_rs12_a_stock_miss_names_the_typed_code_the_resolver_could_not_place():
    reply = f"Couldn't find ELP3753.\n\n{REFER_TO_SALESMAN}"
    env = _envelope("inventory", unresolved=["ELP3753"])
    out = _build(reply, [env], _plan(domain="inventory"))
    assert [(e["product_code"], e["branch"], e["requested_qty"]) for e in out] == [("ELP3753", "referred", None)]
    assert out[0]["answer_summary"] == reply


def test_ac_rs13_a_declined_did_you_mean_carries_the_typed_code_and_quantity():
    pending = Pending(
        kind="product_pick",
        expects="position",
        options=[{"position": 1, "label": "ELP3754", "code": "ELP3754", "uuid": "u2", "entity_type": "product"}],
        team=None,
        payload={"stock_pick": True, "did_you_mean": True, "typed": "ELP3753", "stock_qty": 10},
        asked_at_turn=3,
    )
    out = _build(REFER_TO_SALESMAN, [], _plan(domain="inventory"), pending=pending, message="no")
    assert out == [
        {
            "product_code": "ELP3753",
            "product_id": None,
            "requested_qty": 10,
            "branch": "referred",
            "answer_summary": REFER_TO_SALESMAN,
        }
    ]


def test_a_refer_reply_with_no_product_at_all_still_records_the_ask_as_typed():
    """Ambiguity raised as crew-ask on PR #1386; built as recommended: the row carries what
    the dealer typed, so the salesman still sees the ask."""
    out = _build(f"But none matched.\n\n{REFER_TO_SALESMAN}", [], message="  gunmetal water closets eta?  ")
    assert [(e["product_code"], e["branch"], e["requested_qty"]) for e in out] == [
        ("gunmetal water closets eta?", "referred", None)
    ]


def test_the_typed_text_is_capped_to_the_column():
    out = _build(REFER_TO_SALESMAN, [], message="x" * 500)
    assert len(out[0]["product_code"]) == 100


def test_ac_rs14_a_product_already_answered_with_a_stock_branch_gets_no_second_row():
    answered = [{"product_code": "SRT1", "requested_qty": 5, "branch": "in_stock"}]
    reply = f"SRT1 x 5: yes, we have stock. {REFER_TO_SALESMAN}"
    env = _envelope("inventory", entities=["SRT1"])
    assert _build(reply, [env], _plan("SRT1", domain="inventory"), answered=answered) == []


def test_ac_rs14_a_mixed_reply_adds_rows_only_for_the_products_without_one():
    answered = [{"product_code": "SRT1", "requested_qty": 5, "branch": "in_stock"}]
    reply = f"SRT1 x 5: yes, we have stock. {REFER_TO_SALESMAN}\n\nCouldn't find SRT9."
    env = _envelope("inventory", unresolved=["SRT9"], entities=["SRT1"])
    out = _build(reply, [env], _plan("SRT1", domain="inventory"), answered=answered)
    assert [e["product_code"] for e in out] == ["SRT9"]


def test_answered_entries_accept_the_two_new_branches_with_no_quantity():
    rows = stock_ask_service.answered_entries(
        [
            {"product_code": "A", "branch": "incoming_eta", "requested_qty": None},
            {"product_code": "B", "branch": "referred", "requested_qty": None},
            {"product_code": "C", "branch": "referred", "requested_qty": 10},
            {"product_code": "D", "branch": "in_stock", "requested_qty": None},  # still owes one
            {"product_code": "E", "branch": "in_stock", "requested_qty": 5},
        ]
    )
    assert [r["product_code"] for r in rows] == ["A", "B", "C", "E"]


def test_ac_rs16_the_new_branches_never_notify():
    assert "incoming_eta" not in stock_ask_service.NOTIFIED_BRANCHES
    assert "referred" not in stock_ask_service.NOTIFIED_BRANCHES


# --------------------------------------------------------------------------- #
# Real turns, real rows
# --------------------------------------------------------------------------- #


def _rows(session_factory) -> list[StockAsk]:
    db = session_factory()
    db.info["company_scope"] = None
    return db.query(StockAsk).order_by(StockAsk.created_at, StockAsk.product_code).all()


@pytest.fixture
def live(session_factory, monkeypatch, stub_access):
    from app.main import app

    try:
        yield lambda **seed: (
            _seed(session_factory, **seed),
            Console(session_factory, monkeypatch, stub_access, live=True),
        )[1]
    finally:
        app.dependency_overrides.clear()


def test_ac_rs04_ac_rs10_a_dealer_incoming_eta_turn_writes_an_incoming_eta_row(live, session_factory):
    c = live(dealer=True, salesperson=True)
    reply = c.say(f"incoming {CODE}", INCOMING)
    assert reply == f"{CODE}\nETA: {TOLD_ETA}\n\n{REFER_TO_SALESMAN}"
    assert SALESPERSON not in reply

    rows = _rows(session_factory)
    assert [(r.product_code, r.branch, r.quantity, r.state, r.source) for r in rows] == [
        (CODE, "incoming_eta", None, "open", "live")
    ]
    row = rows[0]
    assert row.answer_summary == f"ETA: {TOLD_ETA}. {REFER_TO_SALESMAN}"
    assert row.product_id is not None, "resolved by code within the ask's company"
    assert row.customer_id is not None and row.contact_id is not None
    assert row.company_id == SORENTO
    assert row.notified_agent is False and row.notify_skip_reason == "not_notified_branch"


def test_ac_rs11_a_dealer_incoming_miss_writes_a_referred_row(live, session_factory):
    c = live(dealer=True, salesperson=True, shipments=False)
    reply = c.say(f"incoming {CODE}", INCOMING)
    assert reply.endswith(REFER_TO_SALESMAN), reply
    assert "escalate" not in reply.lower() and "purchasing" not in reply.lower()

    rows = _rows(session_factory)
    assert [(r.product_code, r.branch, r.quantity) for r in rows] == [(CODE, "referred", None)]
    assert rows[0].answer_summary == reply
    assert rows[0].product_id is not None


def test_ac_rs15_a_staff_incoming_turn_writes_no_row(live, session_factory):
    c = live(dealer=False, salesperson=True)
    reply = c.say(f"incoming {CODE}", INCOMING)
    assert "salesman" not in reply
    assert _rows(session_factory) == []


def test_ac_rs15_a_dry_run_writes_no_row(session_factory, monkeypatch, stub_access):
    from app.main import app

    try:
        _seed(session_factory, dealer=True, salesperson=True)
        c = Console(session_factory, monkeypatch, stub_access)  # is_test envelope
        reply = c.say(f"incoming {CODE}", INCOMING)
        assert reply.endswith(REFER_TO_SALESMAN)
        assert _rows(session_factory) == []
    finally:
        app.dependency_overrides.clear()


def test_ac_rs16_no_salesman_job_is_enqueued_for_the_new_rows(live, session_factory, monkeypatch):
    jobs: list = []
    monkeypatch.setattr(stock_ask_service, "enqueue_job", lambda *a, **k: jobs.append(a))
    c = live(dealer=True, salesperson=True)
    c.say(f"incoming {CODE}", INCOMING)
    assert len(_rows(session_factory)) == 1
    assert jobs == []


def test_ac_rs20_serialize_reads_a_quantity_less_row(live, session_factory):
    c = live(dealer=True, salesperson=True)
    c.say(f"incoming {CODE}", INCOMING)
    db = session_factory()
    db.info["company_scope"] = None
    rows = db.query(StockAsk).all()
    out = stock_ask_service.serialize(db, rows)[0]
    assert out.quantity is None
    assert out.branch == "incoming_eta"
    assert out.product_code == CODE
    assert out.product_name == "ZZT WC"
    assert out.customer_name == "ZZT Dealer Sdn Bhd"
    assert out.model_dump()["quantity"] is None
