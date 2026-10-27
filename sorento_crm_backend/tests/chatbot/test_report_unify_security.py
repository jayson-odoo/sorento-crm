"""REPORT-UNIFY security review fix round: red tests (lane side). Harness: the span-pass console of
`test_report_unify_span_binding.py` (its parser config has the lookup lists, so the contact's hidden spec keys are read)."""
from __future__ import annotations

import pytest

from app.services.chatbot import engine as engine_mod
from tests.chatbot.test_report_unify_routing import P_TRAP, YEAR, _status
from tests.chatbot.test_report_unify_span_binding import (  # noqa: F401  (console / bot are fixtures)
    SpanBot,
    _only_report,
    bot,
    console,
)


def test_s2_a_hidden_spec_key_never_rides_the_lane_and_the_reply_never_names_it(bot, monkeypatch) -> None:
    """Security S2: a spec the contact may not see is dropped on every route to the report ask: no `spec` param, and
    the reply does not mention the key or its value at all."""
    monkeypatch.setattr(engine_mod.access_mod, "_hidden_spec_keys", lambda db, **_kw: frozenset({"trap_type"}))
    text, calls = bot.say(_status("sales_report", dict(P_TRAP), basis="delivered", **YEAR), "p trap sales 2026")
    for _name, args in calls:
        assert "spec" not in args, args
    low = text.lower()
    assert "trap" not in low and "spec" not in low, text


def test_s3_the_sales_agent_pick_never_lists_an_agent_of_another_company(bot) -> None:
    """Security S3: the numbered pick lists the contact's own companies' agents plus the shared ones; a company-B agent
    answering to the same word is never offered (nor its code leaked)."""
    import uuid

    from app.models.sales_agent import SalesAgent
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
    from app.models.base import company_scope
    from tests.chatbot.test_report_unify_span_binding import AGENT_CODES, PRODUCT, YEAR, _agent_spans, _ent

    db = bot.console.session_factory()
    try:
        seed_mocha(db)
        db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent="ZZT-YU-OTHERCO", aliases="yu", company_id=MOCHA_ID))
        db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent="ZZT-YU-SHARED", aliases="yu", company_id=None))
        db.commit()
    finally:
        db.close()
    text, calls = bot.say(
        _status("sales_report", _ent("yu", "sales_agent"), _ent(PRODUCT, "product"), basis="delivered", **YEAR),
        "sales agent yu sales for SRTSP231 in 2026",
        spans=_agent_spans(),
    )
    assert calls == [], calls
    assert "ZZT-YU-OTHERCO" not in text, text
    for code in (*AGENT_CODES, "ZZT-YU-SHARED"):
        assert code in text, (code, text)


def test_s3_a_turn_that_cannot_run_an_agent_filter_is_refused_not_offered_a_pick(bot) -> None:
    """Security S3: a contact the route would refuse the agent dimension (no Sales report reveal: a salesperson narrowed to
    their own book) is told so, and never shown the list of agents."""
    from app.services.chatbot.lanes.business import report_ask

    verdict = {
        "order_status": report_ask.ASK_NAME, "basis": "delivered", "group_by": None, "entities": [],
        "date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31", "capability_from": "sales_report",
        "report_ask_words": {"brand": [], "sales_agent": ["yu"], "category": []}, "report_ask_spec": [],
    }
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    db = bot.console.session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    try:
        outcome, line = report_ask.settle(db, verdict, [], dealer=False, agent_filter=False)
    finally:
        db.close()
    assert outcome is None and line == report_ask.DEALER_REFUSAL, (outcome, line)
    db = bot.console.session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    try:
        outcome, line = report_ask.settle(db, verdict, [], dealer=False)
    finally:
        db.close()
    assert outcome is not None and "Which sales agent?" in (outcome.reply or ""), (outcome, line)
