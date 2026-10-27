"""REPORT-UNIFY phase 3 fix round, R1 (lane): a contact in two companies who names neither and names no product or
customer is asked "<A> or <B>?" (SALES-COMPANY rule, `sales_company_ask.QUESTION`), on the report ask path; the answer runs
the held ask for that company; a named company rides as the route's `company`."""
from __future__ import annotations

import pytest
from sqlalchemy import text as sql

from app.models.company import Company, RespondContactCompany
from tests.chatbot.test_engine import CONTACT_ID
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    NO_DATES,
    SEP,
    YEAR,
    _customer,
    _only_report_ask,
    _reply,
    _status,
    bot,
    console,
)
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha


def _two_companies(bot) -> tuple[str, str]:
    """The harness contact holds Sorento and Mocha; returns (Sorento's name, Mocha's name)."""
    from app.services.company_scope import DEFAULT_COMPANY_ID

    db = bot.console.session_factory()
    try:
        seed_mocha(db)
        internal = db.execute(
            sql("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": str(CONTACT_ID)}
        ).scalar_one()
        held = {str(c) for (c,) in db.query(RespondContactCompany.company_id).filter(
            RespondContactCompany.respond_contact_id == str(internal)).all()}
        for cid in (DEFAULT_COMPANY_ID, MOCHA_ID):
            if cid not in held:
                db.add(RespondContactCompany(respond_contact_id=str(internal), company_id=cid))
        db.commit()
        names = {c.id: c.name for c in db.query(Company).all()}
        return names[DEFAULT_COMPANY_ID], names[MOCHA_ID]
    finally:
        db.close()


def test_g5_no_named_subject_is_still_the_company_question(bot) -> None:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    assert calls == [], calls
    assert f"{sorento} or {mocha}?" in text, text


def test_r1_the_answer_runs_the_held_ask_for_that_company(bot) -> None:
    sorento, mocha = _two_companies(bot)
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[]), mocha
    )
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID, args
    assert args["basis"] == "delivered" and args["date_from"] == "2026-01-01", args


def test_r1_a_named_subject_runs_without_the_question(bot) -> None:
    _two_companies(bot)
    text, calls = bot.say(_status("sales_report", _customer(bot), basis="delivered", **YEAR), "sales for the customer 2026")
    args = _only_report_ask(calls)
    assert "company" not in args, args


def test_r1_a_company_the_parser_named_rides_as_the_route_company(bot) -> None:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(
        _status("sales_report", basis="delivered", sales_company=mocha, **YEAR), "mocha total sales 2026"
    )
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID, args


def test_r1_a_contact_with_one_company_is_never_asked(bot) -> None:
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    args = _only_report_ask(calls)
    assert "company" not in args, args
