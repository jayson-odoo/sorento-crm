"""CHATBOT-PICK-CARRY (owner, 1 Nov 2026, Chatbot Console, prompt v70; PLAN-chatbot-pick-carry-1nov.md): the customer a
person picks is the customer the report runs on, across the sales basis question that follows the pick.

Owner's turns: "Dealer <customer> oct total sales" -> "Which one do you mean? 1. <dealer A> (SRT, MCH) 2. <dealer B>";
"1" -> "Invoiced, delivered, ordered or outstanding?"; "invoiced" -> a report on one project ledger of dealer A and on a
different customer in the other company, Total RM 0.00. Neither was offered or picked.

An account code is per company, and the two rows of the owner's reply are the two rows of one code. A roster option for
several ledgers carries one code, every picked row reads that code, and a turn-2 parse that echoes the option beside the
pick has the resolver look it up. `turn_runtime._entities_for` then kept the resolver's rows by code and dropped the
plan's own: the slot held them and turn 3 ran them.

Engine harness: `test_new_ask_drops_sales_channel.chat` (real `engine.run_turn` and gate, Postgres; parser, access,
resolver and MCP faked). Fake customers only (public repo).
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import ResolveGateServices
from app.services.chatbot.turn.plan import FetchSpec
from app.services.chatbot.turn_runtime import _entities_for
from tests.chatbot._sales_pick_helpers import _pick
from tests.chatbot.conftest import validating_resolve_entity
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_new_ask_drops_sales_channel import _report_calls, _reply, chat  # noqa: F401  (fixture)

OCT_2026 = {"date_mode": "month", "date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}
BASIS_QUESTION = "Invoiced, delivered, ordered or outstanding?"

DEALER_A = "ZZ DEMO SANITARY SDN BHD"
DEALER_B = "ZZ DEMO BATH SDN BHD (PROJECT)"
STRANGER = "ZZ STRANGER HARDWARE SDN BHD - [A/C I]"
#: The account code option 1 carries: the first picked ledger's, and in the other company a different customer's.
SHARED_CODE = "300-ZZ10"
#: Option 1 as the roster prints it: the group's name and its companies.
OPTION_LABEL = f"{DEALER_A} (SRT, MCH)"

PICKED = ("project", "ac1", "iborn")


def _seed(session_factory) -> dict[str, str]:
    """Dealer A: three ledgers in its customer group of each company. Dealer B: one ledger. The stranger: the other
    company's row of dealer A's project ledger code, in no group, nothing to do with dealer A."""
    from sqlalchemy import text as sql_text

    from app.models.order import CustomerGroup
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import MOCHA_ID, customer, seed_mocha
    from tests.chatbot.test_engine import CONTACT_ID

    db = session_factory()
    seed_mocha(db)
    db.execute(
        sql_text("INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
                 "SELECT gen_random_uuid(), id, :company FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": str(CONTACT_ID), "company": MOCHA_ID},
    )
    groups = {company: CustomerGroup(name=DEALER_A, company_id=company) for company in (DEFAULT_COMPANY_ID, MOCHA_ID)}
    db.add_all(groups.values())
    db.flush()
    rows = {
        "project": customer(db, company_id=DEFAULT_COMPANY_ID, name=f"{DEALER_A} (PROJECT)"),
        "ac1": customer(db, company_id=DEFAULT_COMPANY_ID, name=f"{DEALER_A} [A/C I]"),
        "iborn": customer(db, company_id=MOCHA_ID, name=f"{DEALER_A} - [IBORN]"),
        "dealer_b": customer(db, company_id=DEFAULT_COMPANY_ID, name=DEALER_B),
        "stranger": customer(db, company_id=MOCHA_ID, name=STRANGER),
    }
    for key in PICKED:
        rows[key].customer_group_id = groups[rows[key].company_id].id
    ids = {key: row.id for key, row in rows.items()}
    db.commit()
    db.close()
    return ids


def _services(ids: dict[str, str]) -> ResolveGateServices:
    """The word finds both customers. The shared code finds its row in each company, as the live resolver does for a code."""

    def hit(key: str, code: str, name: str, company: str = "SRT") -> dict[str, Any]:
        return {"entity_type": "customer", "canonical_code": code, "uuid": ids[key], "company_code": company,
                "display": {"customer_name": name}}

    project = hit("project", SHARED_CODE, f"{DEALER_A} (PROJECT)")
    ac1 = hit("ac1", "300-ZZ04", f"{DEALER_A} [A/C I]")
    iborn = hit("iborn", "300-ZZ33", f"{DEALER_A} - [IBORN]", "MCH")

    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        tokens = body.get("tokens") or []
        found = {
            SHARED_CODE.casefold(): [project, hit("stranger", SHARED_CODE, STRANGER, "MCH")],
            OPTION_LABEL.casefold(): [project, ac1, iborn],
        }
        everyone = [project, ac1, iborn, hit("dealer_b", "300-ZZ59", DEALER_B)]
        return {
            "tokens": tokens,
            "resolutions": [{"token": t, "matches": found.get(str(t).casefold(), everyone)} for t in tokens],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve),
        probe=lambda **_: {"items": [], "has_result": False},
    )


def _t1() -> dict[str, Any]:
    """"Dealer <customer> oct total sales": no basis named, so the basis is asked after the customer."""
    return _parser_output(
        message_type="business_query", domain_hint="sales", intent_hint="check_order", order_status="sales_report",
        sales_channel="dealer", domain_in_message=True, entity_op="replace_combine", basis=None,
        entities=[{"raw": "zz demo", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
        **OCT_2026,
    )


def _echo(raw: str, *, current: bool, code: str | None = None) -> dict[str, Any]:
    return {"raw": raw, "hint": "customer", "canonical_code": code, "current_message": current, "confident": True}


def _t2(*entities: dict[str, Any]) -> dict[str, Any]:
    """"1": the pick, with whatever the parser echoes beside it."""
    return _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="sales_report",
        group_by=None, sales_channel=None, entities=list(entities), entity_op="reuse", domain_in_message=False,
        open_question_answer=_pick(1), **OCT_2026,
    )


def _t3(basis: str = "invoiced", position: int = 1) -> dict[str, Any]:
    """The owner's turn 3 parse, field for field: no entity, `reuse`, the position of the basis option."""
    return _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="sales_report",
        basis=basis, sales_basis=basis, sales_channel="dealer", sales_company=None, entities=[], entity_op="reuse",
        domain_in_message=False, continuation=True, by_words=None, open_question_answer=_pick(position), **OCT_2026,
    )


def _three_turns(chat, session_factory, tag: str, t2: dict[str, Any], t3: dict[str, Any] | None = None, text3: str = "invoiced"):
    ids = _seed(session_factory)
    services = _services(ids)
    first, captured = chat(_t1(), "Dealer zz demo oct total sales", f"ZZT-pc-{tag}-1", resolve_services=services)
    assert _report_calls(captured) == [], captured
    assert (chat.session().get("open_question") or {}).get("kind") == "customer_pick", _reply(first)
    second, captured = chat(t2, "1", f"ZZT-pc-{tag}-2", resolve_services=services)
    assert _reply(second).strip() == BASIS_QUESTION, f"the sales basis is still asked: {_reply(second)!r}"
    assert _report_calls(captured) == [], f"no figure before the basis is answered: {captured}"
    third, captured = chat(t3 or _t3(), text3, f"ZZT-pc-{tag}-3", resolve_services=services)
    calls = _report_calls(captured)
    assert len(calls) == 1, (_reply(third), captured)
    return ids, calls[0]


def _assert_the_pick(ids: dict[str, str], args: dict[str, Any], basis: str = "invoiced") -> None:
    names = {uuid: key for key, uuid in ids.items()}
    got = sorted(names.get(uuid, uuid) for uuid in args.get("customer_ids") or [])
    assert got == sorted(PICKED), f"exactly the ledgers of the option picked, got {got}"
    assert args.get("basis") == basis, args
    assert args.get("channel") == "dealer", args
    assert args.get("date_from") == "2026-10-01" and args.get("date_to") == "2026-10-31", args


# ------------------------------------------------------------------ the owner's turns


@pytest.mark.parametrize("current", [True, False], ids=["said-current", "said-carried"])
def test_p1_a_code_echoed_beside_the_pick_never_brings_in_the_other_company_s_row(chat, session_factory, current):
    """The owner's reply: the picked option's code echoed at turn 2 ran the report on that code's two rows."""
    t2 = _t2(_echo(SHARED_CODE, current=current, code=SHARED_CODE))
    ids, args = _three_turns(chat, session_factory, f"p1-{current}", t2)
    assert ids["stranger"] not in (args.get("customer_ids") or []), "a different customer sharing the code, never picked"
    _assert_the_pick(ids, args)


@pytest.mark.parametrize("current", [True, False], ids=["said-current", "said-carried"])
def test_p2_the_option_s_label_echoed_beside_the_pick_never_cuts_the_pick_to_one_ledger(chat, session_factory, current):
    ids, args = _three_turns(chat, session_factory, f"p2-{current}", _t2(_echo(OPTION_LABEL, current=current)))
    _assert_the_pick(ids, args)


def test_g1_guard_a_bare_pick_keeps_every_ledger(chat, session_factory):
    ids, args = _three_turns(chat, session_factory, "g1", _t2())
    _assert_the_pick(ids, args)


def test_g2_guard_2_at_turn_3_is_the_basis_option_never_option_2_of_the_customer_list(chat, session_factory):
    """The customer list is still on the session at turn 3; the open question is the basis, and it takes the answer."""
    ids, args = _three_turns(chat, session_factory, "g2", _t2(), t3=_t3("delivered", 2), text3="2")
    assert ids["dealer_b"] not in (args.get("customer_ids") or []), args
    _assert_the_pick(ids, args, basis="delivered")


# ------------------------------------------------------------------ the merge itself, every kind


def _row(kind: str, code: str, uuid: str, **extra: Any) -> dict[str, Any]:
    return {"entity_type": kind, "code": code, "canonical_code": code, "uuid": uuid, **extra}


def _plan(kind: str, *rows: tuple[str, str | None]) -> FetchSpec:
    entities = [{"raw": code, "hint": kind, "canonical_code": code, **({"uuid": uuid} if uuid else {})} for code, uuid in rows]
    return FetchSpec(domain="order", entities=entities, filters={}, date_window=None)


U1, U2, U3 = ("aaaaaaaa-0000-4000-8000-00000000000" + d for d in "123")


def _uuids(rows: list[dict[str, Any]]) -> list[str]:
    return [r.get("uuid") for r in rows]


@pytest.mark.parametrize("kind", ["customer", "product"])
def test_u1_a_settled_row_is_not_replaced_by_the_same_code_in_another_company(kind):
    out = _entities_for(_plan(kind, ("c1", U1)), [_row(kind, "c1", U2)])
    assert _uuids(out) == [U1], out


def test_u2_every_settled_ledger_of_one_code_stays_when_the_resolver_returns_one_of_them():
    out = _entities_for(_plan("customer", ("c1", U1), ("c1", U2), ("c1", U3)), [_row("customer", "c1", U1)])
    assert sorted(_uuids(out)) == sorted([U1, U2, U3]), out


def test_u3_guard_the_resolver_s_own_row_of_a_settled_uuid_is_kept_once_with_what_it_knows():
    out = _entities_for(_plan("product", ("c1", U1)), [_row("product", "c1", U1, set_code="S1")])
    assert _uuids(out) == [U1] and out[0].get("set_code") == "S1", out


def test_u4_guard_a_word_typed_this_turn_takes_every_row_the_resolver_found_for_it():
    out = _entities_for(_plan("customer", ("c1", None)), [_row("customer", "c1", U1), _row("customer", "c1", U2)])
    assert sorted(_uuids(out)) == sorted([U1, U2]), out


def test_u5_a_settled_row_beside_a_word_typed_this_turn():
    out = _entities_for(_plan("product", ("c1", U1), ("c2", None)), [_row("product", "c2", U2), _row("product", "c1", U3)])
    assert sorted(_uuids(out)) == sorted([U1, U2]), out


def test_u6_guard_a_settled_row_of_another_code_stays_dropped_when_the_resolver_answers_the_kind():
    """Today's narrowing: the resolver answered for this kind and said nothing about that code."""
    out = _entities_for(_plan("product", ("c1", U1), ("c2", U2)), [_row("product", "c1", U1)])
    assert _uuids(out) == [U1], out


def test_u7_guard_a_kind_the_resolver_did_not_answer_falls_back_to_the_plan():
    out = _entities_for(_plan("customer", ("c1", U1)), [_row("product", "p1", U2)])
    assert sorted(_uuids(out)) == sorted([U1, U2]), out
