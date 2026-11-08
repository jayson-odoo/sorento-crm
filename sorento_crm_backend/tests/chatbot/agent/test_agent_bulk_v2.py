"""AGENT-BULK-V2 (PLAN-agent-bulk-v2-8nov.md, UAC agent-bulk-v2-8nov-acceptance-criteria.md): a customer cell that
fits several accounts becomes a pick, not a dead end; every skip reason is listed; the preview is always the
code-built table; a skipped row backs the reply's not-found wording.

Red tests, written before the code. Test numbers in the names are the UAC's brackets (01..09). Seeding and turn
helpers come from the #2226 module (`test_agent_bulk_grant.py`, unchanged). Postgres only (blank schema); every test
seeds its own chain. Dealer names, codes and phones are invented (public repo).

Pinned shapes:
- `batch.propose_rows(...)` returns `(steps, skipped, waiting)`; a waiting item is
  {"row", "cells", "written", "company", "candidates": [{"code", "name"}], "more"}.
- `contact_grant.NeedsChoice` (AppException, 409) carries `.choices`; a row whose ONLY problem is customer
  ambiguity waits, any other problem skips it (with every reason joined by "; ").
- `batch.propose` data gains `needs_choice` and `rows_waiting`; `waiting_out` next to `skipped_out`.
- `batch.preview_block(steps, skipped, waiting=())`: "I will make these changes when you confirm:", then
  "Needs your choice:", then "Not changed:".
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import company_scope
from tests._ask_todo_seed import customer as seed_customer
from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    BATCH,
    GRANT,
    W,
    _listeners,
    ctx_of,
    db,
    dealer,
    fake_phone,
    local,
    make_world,
    propose_rows,
    row_,
    state,
)
from tests.chatbot.agent.test_agent_writes import action_rows, answer_, round_of, run_turn, tc

WRITTEN = "ZZT Dealer H"
SUFFIXES = ("TRADING (A/C I)", "CERAMIC (A/C II)", "IBORN (A/C III)")
NEEDS = "Needs your choice:"
NOT_CHANGED = "Not changed:"
READY = "I will make these changes when you confirm:"


def account(db, name: str, code: str, company_id: str, *, active: bool = True):
    """A customer account with a chosen code and name (the seed picks a random code)."""
    with company_scope(db, None):
        row = seed_customer(db, name, None, company_id=company_id)
        row.customer_code = code
        row.is_active = active
        db.flush()
    db.commit()
    return row


def dealer_h(db, company_id: str, count: int = 3, prefix: str = "ZH") -> list:
    """`count` active accounts of "ZZT DEALER H ..." in one company; codes are inserted out of order."""
    made = [
        account(db, f"ZZT DEALER H {SUFFIXES[i % 3]} {i}", f"{prefix}-{i:02d}", company_id)
        for i in reversed(range(1, count + 1))
    ]
    return sorted(made, key=lambda r: r.customer_code)


def candidate(row) -> dict:
    return {"code": row.customer_code, "name": row.customer_name}


def waiting_row(w, person, *, written=WRITTEN, company="MCH", **over) -> dict:
    return {**row_(person.phone_number, companies=[company], names=[written]), **over}


# ------------------------------------------------------------------ V1 (01): exact code or full name is unchanged


def test_01_an_exact_code_or_an_exact_full_name_links_as_today(db):
    w = make_world(db)
    accounts = dealer_h(db, w.mch)
    by_code, by_name = dealer(db, w, companies=(w.mch,)), dealer(db, w, companies=(w.mch,))

    out = propose_rows(db, w, [
        row_(by_code.phone_number, companies=["MCH"], codes=[accounts[1].customer_code]),
        row_(by_name.phone_number, companies=["MCH"], names=[accounts[2].customer_name.lower()]),
    ])
    steps, skipped = out[0], out[1]

    assert skipped == [] and len(steps) == 2
    assert accounts[1].customer_code in steps[0]["summary"]
    assert accounts[2].customer_code in steps[1]["summary"]


# ------------------------------------------------------------------ V2, V3 (02): a contained name is a pick


def test_02_needs_choice_is_a_409_app_exception():
    from app.services.chatbot.agent.contact_grant import NeedsChoice
    from app.services.error_handler import AppException

    assert issubclass(NeedsChoice, AppException)


def test_02_a_name_inside_several_accounts_waits_with_the_candidates_by_code_and_links_nothing(db):
    w = make_world(db)
    accounts = dealer_h(db, w.mch)
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, person, written="zzt  dealer H")])

    assert steps == [] and skipped == []
    assert len(waiting) == 1
    item = waiting[0]
    assert item["row"] == 1 and item["company"] == "MCH" and item["more"] is False
    assert item["written"].lower().replace("  ", " ") == WRITTEN.lower()
    assert item["candidates"] == [candidate(a) for a in accounts]
    assert state(db, person.phone_number)["links"] == []


def test_02_one_containing_account_still_waits_and_is_never_auto_linked(db):
    w = make_world(db)
    (only,) = dealer_h(db, w.mch, count=1)
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, person)])

    assert steps == [] and skipped == []
    assert [c["code"] for c in waiting[0]["candidates"]] == [only.customer_code]
    assert state(db, person.phone_number)["links"] == []


# ------------------------------------------------------------------ V4, V5 (03): at most 10, only eligible accounts


def test_03_more_than_ten_matches_list_ten_by_code_and_say_to_give_a_longer_name(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    accounts = dealer_h(db, w.mch, count=12)
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, person)])

    item = waiting[0]
    assert [c["code"] for c in item["candidates"]] == [a.customer_code for a in accounts[:10]]
    assert item["more"] is True
    block = batch.preview_block(steps, skipped, waiting)
    assert "more than 10 accounts match; give a longer name or the code" in block


def test_03_inactive_other_company_and_outside_company_accounts_are_never_candidates(db):
    w = make_world(db, superadmin=False)
    ok = dealer_h(db, w.mch, count=2)
    account(db, "ZZT DEALER H INACTIVE (A/C IX)", "ZH-70", w.mch, active=False)
    account(db, "ZZT DEALER H SORENTO (A/C X)", "ZH-71", w.srt)  # the user's company, but the row names MCH
    account(db, "ZZT DEALER H HIDDEN (A/C XI)", "ZH-72", w.hidden)  # a company the user does not hold
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, person)])

    assert [c["code"] for c in waiting[0]["candidates"]] == [a.customer_code for a in ok]
    assert waiting[0]["more"] is False


def test_03_the_same_name_in_both_companies_lists_only_the_rows_company(db):
    w = make_world(db)
    mocha = dealer_h(db, w.mch, count=3, prefix="ZH")
    sorento = dealer_h(db, w.srt, count=2, prefix="ZS")
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, person, company="MCH")])

    assert steps == [] and skipped == []
    assert [c["code"] for c in waiting[0]["candidates"]] == [a.customer_code for a in mocha]
    assert not {a.customer_code for a in sorento} & {c["code"] for c in waiting[0]["candidates"]}
    assert state(db, person.phone_number)["links"] == []


# ------------------------------------------------------------------ V6, V7 (04): the two dead ends say which


def test_04_a_name_only_in_the_other_company_names_that_company_and_lists_no_account(db):
    w = make_world(db)
    account(db, "ZZT DEALER K TRADING (A/C I)", "ZK-01", w.mch)
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, companies=["SRT"], names=["ZZT Dealer K"])])

    assert steps == [] and waiting == []
    reason = skipped[0]["reason"]
    assert '"ZZT Dealer K" is a Mocha customer, but the row\'s company is Sorento' in reason
    assert "ZK-01" not in reason


def test_04_a_name_nowhere_in_the_users_companies_is_no_customer_named(db):
    w = make_world(db)
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, names=["ZZT Nowhere Stores"])])

    assert steps == [] and waiting == []
    assert 'No customer named "ZZT Nowhere Stores" in your companies' in skipped[0]["reason"]


# ------------------------------------------------------------------ V8, V9 (05): every reason, hard problems win


def test_05_a_row_with_several_problems_is_skipped_once_with_every_reason_in_order(db):
    w = make_world(db)
    steps, skipped, waiting = propose_rows(db, w, [
        {**row_("12345", name="ZZT Many Faults", names=["ZZT Nowhere Stores"]),
         "role": "unknown", "access_as_written": "Manager"},
    ])

    assert steps == [] and waiting == [] and len(skipped) == 1
    reason = skipped[0]["reason"]
    phone = reason.find("is not a Malaysian mobile number")
    access = reason.find("Unknown access")
    customer = reason.find('No customer named "ZZT Nowhere Stores"')
    assert 0 <= phone < access < customer, reason
    assert reason.count("; ") >= 2


def test_05_a_hard_problem_plus_an_ambiguous_customer_is_skipped_not_waiting(db):
    w = make_world(db)
    dealer_h(db, w.mch)
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [
        waiting_row(w, person, phone="12345"),
        {**waiting_row(w, person), "role": "unknown", "access_as_written": "Manager"},
    ])

    assert steps == [] and waiting == []
    assert [s["row"] for s in skipped] == [1, 2]
    assert "is not a Malaysian mobile number" in skipped[0]["reason"]
    assert "Unknown access" in skipped[1]["reason"]
    for item in skipped:
        assert f'"{WRITTEN}" fits 3 accounts' in item["reason"]


# ------------------------------------------------------------------ V10, V12 (06): ready rows go to Confirm only


def test_06_the_preview_block_has_ready_then_needs_your_choice_then_not_changed(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    accounts = dealer_h(db, w.mch)
    ready, waits, bad = dealer(db, w), dealer(db, w, companies=(w.mch,)), dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [
        row_(ready.phone_number, codes=[w.cust_a.customer_code]),
        waiting_row(w, waits),
        row_(bad.phone_number, names=["ZZT Nowhere Stores"]),
    ])
    block = batch.preview_block(steps, skipped, waiting)

    assert len(steps) == 1 and len(waiting) == 1 and len(skipped) == 1
    assert 0 <= block.find(READY) < block.find(NEEDS) < block.find(NOT_CHANGED)
    for account_ in accounts:
        assert f"{account_.customer_code} {account_.customer_name}" in block


def test_06_a_turn_with_ready_and_waiting_rows_stores_only_the_ready_rows_and_lists_the_waiting(db):
    w = make_world(db)
    dealer_h(db, w.mch)
    ready, waits = dealer(db, w), dealer(db, w, companies=(w.mch,))
    rows = [row_(ready.phone_number, codes=[w.cust_a.customer_code]), waiting_row(w, waits)]
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_("One row is ready; one needs a choice.")]

    result, _ = run_turn(db, w, script, text_="grant access to these people")

    assert len(result.pending_action["lines"]) == 1
    stored = action_rows(db, w.respond_id)
    assert len(stored) == 1 and [s["row"] for s in stored[0].steps] == [1]
    assert NEEDS in result.reply_text
    assert "ZZT DEALER H" in result.reply_text
    assert state(db, waits.phone_number)["links"] == []


# ------------------------------------------------------------------ V11, V12 (07): no ready row, still the table


def test_07_a_turn_with_no_ready_row_stores_no_action_and_still_shows_the_table(db):
    w = make_world(db)
    dealer_h(db, w.mch)
    waits, bad = dealer(db, w, companies=(w.mch,)), dealer(db, w)
    rows = [waiting_row(w, waits), row_(bad.phone_number, names=["ZZT Nowhere Stores"])]
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_("Nothing can change yet.")]

    result, _ = run_turn(db, w, script, text_="grant access to these people")

    assert result.pending_action is None
    assert action_rows(db, w.respond_id) == []
    reply = result.reply_text
    assert 0 <= reply.find(NEEDS) < reply.find(NOT_CHANGED), reply
    assert READY not in reply
    assert 'No customer named "ZZT Nowhere Stores"' in reply


def test_07_a_turn_where_every_row_is_skipped_still_ends_with_the_not_changed_table(db):
    w = make_world(db)
    bad = dealer(db, w)
    rows = [row_(bad.phone_number, names=["ZZT Nowhere Stores"])]
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_("Nothing can change.")]

    result, _ = run_turn(db, w, script, text_="grant access to these people")

    assert result.pending_action is None and action_rows(db, w.respond_id) == []
    assert NOT_CHANGED in result.reply_text and "| # |" in result.reply_text


# ------------------------------------------------------------------ V13 (08): the result the model reads


def test_08_the_batch_result_carries_needs_choice_and_the_waiting_count(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    accounts = dealer_h(db, w.mch)
    ready, waits = dealer(db, w), dealer(db, w, companies=(w.mch,))
    steps, waiting = [], []

    out = batch.propose(
        db, ctx_of(db, w),
        {"write": GRANT, "rows": [row_(ready.phone_number, codes=[w.cust_a.customer_code]), waiting_row(w, waits)]},
        steps, seen_ids=set(), skipped_out=[], waiting_out=waiting,
    )

    assert out.status == "proposed" and len(steps) == 1
    assert out.data["needs_choice"] == [{
        "row": 2, "written": WRITTEN, "company": "MCH", "candidates": [candidate(a) for a in accounts],
    }]
    assert out.data["rows_waiting"] == 1 and out.data["rows_proposed"] == 1 and out.data["rows_total"] == 2
    assert [w_["row"] for w_ in waiting] == [2]


def test_08_with_no_ready_row_the_result_is_invalid_but_still_carries_needs_choice_and_skipped(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    dealer_h(db, w.mch)
    waits, bad = dealer(db, w, companies=(w.mch,)), dealer(db, w)

    out = batch.propose(
        db, ctx_of(db, w),
        {"write": GRANT, "rows": [waiting_row(w, waits), row_(bad.phone_number, names=["ZZT Nowhere Stores"])]},
        [], seen_ids=set(),
    )

    assert out.status == "invalid"
    assert [n["row"] for n in out.data["needs_choice"]] == [1]
    assert [s["row"] for s in out.data["skipped"]] == [2]
    assert out.data["rows_waiting"] == 1 and out.data["rows_skipped"] == 1


# ------------------------------------------------------------------ V14 (09): a batch skip backs "not found"


def test_09_a_not_found_reply_after_a_skipped_batch_row_is_accepted_without_a_repair_round(db):
    w = make_world(db)
    bad = dealer(db, w)
    rows = [row_(bad.phone_number, names=["ZZT Nowhere Stores"])]
    final = tc("answer", {
        "text": "That customer was not found, so the row is not changed.",
        "figures": [],
        "not_found": [{"what": "ZZT Nowhere Stores", "call_id": "b1"}],
        "not_checked": [],
    }, "ans-1")
    # A spare answer keeps a repair round from dying on an empty script: the assertion below is the round count.
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), round_of(final), round_of(final)]

    result, provider = run_turn(db, w, script, text_="grant access to this person")

    assert len(provider.seen) == 2, "the not-found claim needed a repair round"
    assert result.rounds == 2
    assert "I could not confirm" not in result.reply_text


# ------------------------------------------------------------------ fix round 1: guards (G1 to G3)


def test_g1_a_name_held_only_by_an_account_of_an_ungranted_company_is_no_customer_named(db):
    w = make_world(db, superadmin=False)
    account(db, "ZZT Quiet Shop", "ZHID-01", w.hidden)
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, names=["ZZT Quiet Shop"])])

    assert steps == [] and waiting == []
    reason = skipped[0]["reason"]
    assert 'No customer named "ZZT Quiet Shop" in your companies' in reason
    assert "ZZT Hidden Co" not in reason and "ZHID-01" not in reason


def test_g2_an_exact_full_name_of_a_mocha_account_on_a_sorento_row_is_refused_and_links_nothing(db):
    w = make_world(db)
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(
        db, w, [row_(person.phone_number, companies=["SRT"], names=[w.cust_b.customer_name])]
    )

    assert steps == [] and waiting == []
    assert "is a Mocha customer" in skipped[0]["reason"]
    assert state(db, person.phone_number)["links"] == []


def test_g3_one_row_with_two_ambiguous_names_is_one_waiting_row_with_two_choices(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    dealer_h(db, w.mch, count=2)
    for i in (1, 2):
        account(db, f"ZZT DEALER K BRANCH {i}", f"ZK-{i:02d}", w.mch)
    person = dealer(db, w, companies=(w.mch,))

    out = batch.propose(
        db, ctx_of(db, w),
        {"write": GRANT, "rows": [waiting_row(w, person, customer_names=[WRITTEN, "ZZT Dealer K"])]},
        [], seen_ids=set(),
    )

    assert out.data["rows_waiting"] == 1
    assert len(out.data["needs_choice"]) == 2


# ------------------------------------------------------------------ fix round 1: R4 not-found wording is exact


def _backed(what: str, reason: str) -> bool:
    from app.services.chatbot.agent import batch
    from app.services.chatbot.agent.loop import _not_found_backed

    ledger = {"b1": {"name": batch.BATCH, "status": "invalid", "args": {}, "data": {"skipped": [{"row": 1, "reason": reason}]}}}
    return _not_found_backed(what, "b1", ledger, set())


def test_r4_only_a_no_customer_part_backs_a_not_found_claim_for_exactly_that_term():
    phone_and_fit = 'Phone "12345" is not a Malaysian mobile number; "ZZT Dealer H" fits 3 accounts.'
    assert _backed("ZZT Dealer H", phone_and_fit) is False
    assert _backed("12345", phone_and_fit) is False
    assert _backed("Dealer K", '"Dealer K" is a Mocha customer, but the row\'s company is Sorento.') is False
    assert _backed("ACME", 'More than one customer has the code "ACME"; give its customer code.') is False
    assert _backed("C1", 'Phone "P1" is not a Malaysian mobile number; No customer with the code "C1" in your companies.') is True
    assert _backed("zzt  nowhere STORES", 'No customer named "ZZT Nowhere Stores" in your companies.') is True
    assert _backed("N1", 'No customer with the name "N1" in your companies.') is True
    assert _backed("Other", 'No customer named "ZZT Nowhere Stores" in your companies.') is False


# ------------------------------------------------------------------ fix round 1: R5 a repeated phone beside a waiting row


def test_r5_a_row_repeating_the_phone_of_a_waiting_row_is_skipped_as_same_as_it(db):
    w = make_world(db)
    dealer_h(db, w.mch)
    shared, other = dealer(db, w, companies=(w.mch,)), dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [
        waiting_row(w, shared),
        row_(other.phone_number, codes=[w.cust_a.customer_code]),
        row_(shared.phone_number, companies=["MCH"], codes=[w.cust_b.customer_code]),
    ])

    assert [s["row"] for s in steps] == [2] and [x["row"] for x in waiting] == [1]
    assert [s["row"] for s in skipped] == [3]
    assert "Same as row 1." in skipped[0]["reason"]


def test_r5_two_waiting_rows_with_one_phone_make_the_second_skipped(db):
    w = make_world(db)
    dealer_h(db, w.mch)
    shared = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, shared), waiting_row(w, shared)])

    assert steps == [] and [x["row"] for x in waiting] == [1]
    assert [s["row"] for s in skipped] == [2] and "Same as row 1." in skipped[0]["reason"]


# ------------------------------------------------------------------ fix round 1: R6 a not-ready table expires the old card


def test_r6_a_table_with_no_ready_row_expires_the_previous_confirm_card(db):
    w = make_world(db)
    dealer_h(db, w.mch)
    ready, waits = dealer(db, w), dealer(db, w, companies=(w.mch,))
    first = [row_(ready.phone_number, codes=[w.cust_a.customer_code])]
    run_turn(db, w, [round_of(tc(BATCH, {"write": GRANT, "rows": first}, "b1")), answer_("Ready.")], text_="grant access")
    assert [a.status for a in action_rows(db, w.respond_id)] == ["proposed"]

    second = [waiting_row(w, waits)]
    result, _ = run_turn(
        db, w, [round_of(tc(BATCH, {"write": GRANT, "rows": second}, "b2")), answer_("Pick one.")], text_="grant access"
    )

    assert result.pending_action is None
    assert [a.status for a in action_rows(db, w.respond_id)] == ["expired"]


# ------------------------------------------------------------------ fix round 1: R7 plural words and the recheck prefix


def _choice(written: str, count: int) -> list[dict]:
    return [{"written": written, "company": "MCH", "more": False,
             "candidates": [{"code": f"ZH-{i}", "name": f"ZZT DEALER H {i}"} for i in range(count)]}]


def test_r7_the_needs_choice_message_counts_the_candidates():
    from app.services.chatbot.agent.contact_grant import NeedsChoice

    assert '"X" fits 1 account' in NeedsChoice(_choice("X", 1)).message
    assert '"X" fits 1 accounts' not in NeedsChoice(_choice("X", 1)).message
    assert '"X" fits 3 accounts' in NeedsChoice(_choice("X", 3)).message


def test_r7_a_hard_problem_with_one_candidate_reads_fits_one_account(db):
    w = make_world(db)
    dealer_h(db, w.mch, count=1)
    person = dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [waiting_row(w, person, phone="12345")])

    assert waiting == []
    assert f'"{WRITTEN}" fits 1 account' in skipped[0]["reason"]
    assert "fits 1 accounts" not in skipped[0]["reason"]


def test_r7_a_recheck_that_now_needs_a_choice_gets_the_changed_since_prefix(db):
    from sqlalchemy import text

    from app.services.chatbot.agent import actions

    w = make_world(db)
    person = dealer(db, w)
    said = w.cust_a.customer_name
    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, names=[said])])
    action = actions.store_proposal(
        db, ctx_of(db, w), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=steps,
    )
    with company_scope(db, None):
        db.execute(text("UPDATE customers SET customer_name = customer_name || ' OLD' WHERE id = :i"), {"i": w.cust_a.id})
    db.commit()

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.steps[0]["status"] == "failed"
    assert outcome.steps[0]["error"].startswith("This changed since it was proposed: ")
    assert state(db, person.phone_number)["links"] == []


# ------------------------------------------------------------------ Q2 (a): the chat-reply picker (V16 to V21)


def family(db, letter: str, company_id: str, count: int, prefix: str) -> list:
    made = [
        account(db, f"ZZT DEALER {letter} {SUFFIXES[i % 3]} {i}", f"{prefix}-{i:02d}", company_id)
        for i in reversed(range(1, count + 1))
    ]
    return sorted(made, key=lambda r: r.customer_code)


def tag(row: dict, n: int) -> dict:
    return {**row, "row": n}


def say(db, w, rows, text_, final="Done."):
    """One scripted table turn: the model calls the batch tool with `rows`, then answers."""
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_(final)]
    return run_turn(db, w, script, text_=text_)[0]


def stored(db, result) -> dict:
    from app.models.chatbot_turn import ChatbotTurn

    db.expire_all()
    return db.get(ChatbotTurn, result.turn_id).response


def picker_world(db):
    w = make_world(db)
    f = family(db, "F", w.srt, 3, "ZF")
    h = family(db, "H", w.mch, 3, "ZH")
    pf, ph, pr = dealer(db, w), dealer(db, w, companies=(w.mch,)), dealer(db, w)
    first = [
        tag(row_(pf.phone_number, companies=["SRT"], names=["ZZT Dealer F"]), 1),
        tag(row_(ph.phone_number, companies=["MCH"], names=[WRITTEN]), 2),
        tag(row_(pr.phone_number, codes=[w.cust_a.customer_code]), 3),
    ]
    return w, f, h, (pf, ph, pr), first


# V16 (10)


def test_10_picking_a_code_per_row_replaces_the_card_with_one_holding_all_three_rows(db):
    from app.services.chatbot.agent import actions

    w, f, h, (pf, ph, pr), first = picker_world(db)
    r1 = say(db, w, first, "grant access to these people")
    assert len(r1.pending_action["lines"]) == 1

    second = [
        tag(row_(pf.phone_number, companies=["SRT"], codes=[f[0].customer_code]), 1),
        tag(row_(ph.phone_number, companies=["MCH"], codes=[h[1].customer_code]), 2),
        first[2],
    ]
    r2 = say(db, w, second, f"row 1: {f[0].customer_code}, row 2: {h[1].customer_code}")

    rows = action_rows(db, w.respond_id)
    assert [a.status for a in rows] == ["expired", "proposed"]
    steps = rows[1].steps
    assert [s["row"] for s in steps] == [1, 2, 3]
    assert f[0].customer_code in steps[0]["summary"] and h[1].customer_code in steps[1]["summary"]
    assert len(r2.pending_action["lines"]) == 3

    outcome = actions.confirm(db, w.respond_id, str(rows[1].id), via="console")
    assert outcome.status == "executed", outcome.steps
    assert state(db, pf.phone_number)["links"] == [str(f[0].id)]
    assert state(db, ph.phone_number)["links"] == [str(h[1].id)]
    assert state(db, pr.phone_number)["links"] == [str(w.cust_a.id)]


# V17 (10)


def test_10_row_all_links_every_listed_account_though_the_codes_were_not_typed(db):
    from app.services.chatbot.agent import actions

    w, f, h, (pf, ph, pr), first = picker_world(db)
    say(db, w, first, "grant access to these people")

    codes = [a.customer_code for a in h]
    second = [tag(row_(ph.phone_number, companies=["MCH"], codes=codes), 2)]
    say(db, w, second, "row 2 all")

    rows = action_rows(db, w.respond_id)
    step = rows[-1].steps[0]
    assert rows[-1].status == "proposed" and step["row"] == 2
    assert all(c in step["summary"] for c in codes)
    outcome = actions.confirm(db, w.respond_id, str(rows[-1].id), via="console")
    assert outcome.status == "executed", outcome.steps
    assert state(db, ph.phone_number)["links"] == sorted(str(a.id) for a in h)


# V18 (11)


def test_11_rows_keep_the_pasted_tables_numbers_in_steps_waiting_skipped_and_the_preview(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    dealer_h(db, w.mch)
    a, b, c = dealer(db, w), dealer(db, w), dealer(db, w, companies=(w.mch,))

    steps, skipped, waiting = propose_rows(db, w, [
        tag(row_(a.phone_number, codes=[w.cust_a.customer_code]), 2),
        tag(row_(b.phone_number, names=["ZZT Nowhere Stores"]), 4),
        tag(waiting_row(w, c), 5),
    ])

    assert [s["row"] for s in steps] == [2] and [s["row"] for s in skipped] == [4]
    assert [x["row"] for x in waiting] == [5]
    block = batch.preview_block(steps, skipped, waiting)
    assert "| 2 |" in block and "| 4 |" in block and "| 5 |" in block and "| 1 |" not in block


def test_11_a_skipped_first_row_leaves_the_others_numbered_two_and_three_at_turn_level(db):
    w = make_world(db)
    a, b = dealer(db, w), dealer(db, w)
    rows = [
        tag(row_(a.phone_number, codes=[w.cust_a.customer_code]), 2),
        tag(row_(b.phone_number, codes=[w.cust_a.customer_code]), 3),
    ]

    result = say(db, w, rows, "row 1 skip")

    assert [s["row"] for s in action_rows(db, w.respond_id)[0].steps] == [2, 3]
    assert len(result.pending_action["lines"]) == 2


# V19, V20 (11)


def unlisted_world(db):
    w = make_world(db)
    family(db, "F", w.srt, 3, "ZF")
    other = account(db, "ZZT UNRELATED SHOP", "ZU-01", w.srt)
    person = dealer(db, w)
    first = [tag(row_(person.phone_number, companies=["SRT"], names=["ZZT Dealer F"]), 1)]
    say(db, w, first, "grant access to this person")
    return w, other, person


def test_11_a_code_neither_listed_last_turn_nor_typed_this_turn_is_skipped_and_never_linked(db):
    w, other, person = unlisted_world(db)

    result = say(db, w, [tag(row_(person.phone_number, companies=["SRT"], codes=["ZU-01"]), 1)], "ok go ahead")

    assert result.pending_action is None
    assert '"ZU-01" was not in the list for "ZZT Dealer F" (row 1); pick from the list' in result.reply_text
    assert state(db, person.phone_number)["links"] == []


def test_11_a_code_typed_in_this_turns_message_is_accepted(db):
    w, other, person = unlisted_world(db)

    result = say(db, w, [tag(row_(person.phone_number, companies=["SRT"], codes=["ZU-01"]), 1)], "row 1:  zu-01")

    assert len(result.pending_action["lines"]) == 1
    assert "ZU-01" in action_rows(db, w.respond_id)[-1].steps[0]["summary"]


# V21 (12)


def test_12_a_table_turn_keeps_its_waiting_rows_on_the_turn_with_or_without_ready_rows(db):
    w, f, h, (pf, ph, pr), first = picker_world(db)

    mixed = stored(db, say(db, w, first, "grant access to these people"))
    only = stored(db, say(db, w, first[:2], "grant access again"))

    for response, count in ((mixed, 2), (only, 2)):
        items = response["batch_waiting"]
        assert [i["row"] for i in items] == [1, 2] and len(items) == count
        assert items[0]["written"] == "ZZT Dealer F" and items[0]["codes"] == [a.customer_code for a in f]
        assert items[1]["codes"] == [a.customer_code for a in h]
        assert pf.phone_number.lstrip("+")[2:] in items[0]["key"]


def test_12_a_table_turn_with_nothing_waiting_stores_an_empty_list_and_a_plain_turn_no_key(db):
    w = make_world(db)
    a = dealer(db, w)

    table = stored(db, say(db, w, [row_(a.phone_number, codes=[w.cust_a.customer_code])], "grant access"))
    plain, _ = run_turn(db, w, [answer_("Hello.")], text_="hello")

    assert table["batch_waiting"] == []
    assert "batch_waiting" not in stored(db, plain)


def test_12_a_plain_turn_between_two_table_turns_does_not_hide_the_earlier_waiting_rows(db):
    w, f, h, (pf, ph, pr), first = picker_world(db)
    say(db, w, first[:2], "grant access to these people")
    run_turn(db, w, [answer_("Hello.")], text_="thanks")

    codes = [a.customer_code for a in h]
    result = say(db, w, [tag(row_(ph.phone_number, companies=["MCH"], codes=codes), 2)], "row 2 all")

    assert len(result.pending_action["lines"]) == 1
    assert "was not in the list" not in result.reply_text


# ------------------------------------------------------------------ picker fix round (P1 to P3)


def test_11_a_typed_code_counts_only_as_a_whole_token_not_as_a_prefix_of_another_code(db):
    w = make_world(db)
    account(db, "ZZT DEALER C TRADING (A/C I)", "ZC10", w.srt)
    account(db, "ZZT DEALER C CERAMIC (A/C II)", "ZC11", w.srt)
    account(db, "ZZT UNRELATED SHOP", "ZC1", w.srt)  # a real account, not in the list, "zc1" starts "zc10"
    person = dealer(db, w)
    say(db, w, [tag(row_(person.phone_number, companies=["SRT"], names=["ZZT Dealer C"]), 1)], "grant access")

    result = say(db, w, [tag(row_(person.phone_number, companies=["SRT"], codes=["ZC1"]), 1)], "row 1: ZC10")

    assert result.pending_action is None
    assert '"ZC1" was not in the list for "ZZT Dealer C" (row 1); pick from the list' in result.reply_text
    assert state(db, person.phone_number)["links"] == []


def test_11_a_code_not_listed_for_row_two_is_refused_though_it_is_inside_the_users_text(db):
    w = make_world(db)
    account(db, "ZZT DEALER C TRADING (A/C I)", "ZC10", w.srt)
    account(db, "ZZT DEALER C CERAMIC (A/C II)", "ZC11", w.srt)
    account(db, "ZZT UNRELATED SHOP", "ZC1", w.srt)
    family(db, "D", w.srt, 2, "ZD")
    p1, p2 = dealer(db, w), dealer(db, w)
    say(db, w, [
        tag(row_(p1.phone_number, companies=["SRT"], names=["ZZT Dealer C"]), 1),
        tag(row_(p2.phone_number, companies=["SRT"], names=["ZZT Dealer D"]), 2),
    ], "grant access")

    result = say(db, w, [
        tag(row_(p1.phone_number, companies=["SRT"], codes=["ZC10"]), 1),
        tag(row_(p2.phone_number, companies=["SRT"], codes=["ZC1"]), 2),
    ], "row 1: ZC10, row 2 all")

    assert len(result.pending_action["lines"]) == 1
    assert '"ZC1" was not in the list for "ZZT Dealer D" (row 2); pick from the list' in result.reply_text
    assert state(db, p2.phone_number)["links"] == []


def test_11_row_numbers_repeated_in_one_call_are_all_ignored_for_the_positions(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    dealer_h(db, w.mch)
    a, b, c = dealer(db, w), dealer(db, w, companies=(w.mch,)), dealer(db, w)
    steps, waiting = [], []

    out = batch.propose(db, ctx_of(db, w), {"write": GRANT, "rows": [
        tag(row_(a.phone_number, codes=[w.cust_a.customer_code]), 2),
        tag(waiting_row(w, b), 2),
        tag(row_(c.phone_number, names=["ZZT Nowhere Stores"]), 7),
    ]}, steps, seen_ids=set(), skipped_out=[], waiting_out=waiting)

    assert [s["row"] for s in steps] == [1]
    assert [x["row"] for x in waiting] == [2]
    assert [s["row"] for s in out.data["skipped"]] == [3]
    assert out.data["rows_waiting"] == 1 and [n["row"] for n in out.data["needs_choice"]] == [2]


def test_12_the_previous_waiting_rows_are_read_without_loading_every_turn(db, monkeypatch):
    import sys

    from app.services.chatbot.agent import loop, memory

    assert hasattr(loop, "_previous_waiting")
    real = memory.conversation_turns

    def guarded(*args, **kw):
        if sys._getframe(1).f_code.co_name == "_previous_waiting":
            raise AssertionError("_previous_waiting must be one query, not every turn of the conversation")
        return real(*args, **kw)

    monkeypatch.setattr(memory, "conversation_turns", guarded)
    w, f, h, (pf, ph, pr), first = picker_world(db)
    say(db, w, first[:2], "grant access to these people")

    codes = [a.customer_code for a in h]
    result = say(db, w, [tag(row_(ph.phone_number, companies=["MCH"], codes=codes), 2)], "row 2 all")

    assert len(result.pending_action["lines"]) == 1
    assert "was not in the list" not in result.reply_text


# ------------------------------------------------------------------ live-run fix round (V22 to V26)


def mixed_world(db):
    """One ready row, one waiting row (accounts with codes the model might echo), one skipped row."""
    w = make_world(db)
    for code, i in (("300-ZZ1", 1), ("300-ZZ2", 2)):
        account(db, f"ZZT DEALER H {SUFFIXES[i]} {i}", code, w.mch)
    ready, waits, bad = dealer(db, w), dealer(db, w, companies=(w.mch,)), dealer(db, w)
    rows = [
        tag(row_(ready.phone_number, codes=[w.cust_a.customer_code]), 1),
        tag(waiting_row(w, waits), 2),
        tag(row_(bad.phone_number, names=["ZZT Nowhere Stores"]), 3),
    ]
    return w, rows


def test_13_the_summary_line_counts_distinct_rows_and_leaves_zero_parts_out(db):
    from app.services.chatbot.agent import batch

    w, rows = mixed_world(db)
    steps, skipped, waiting = propose_rows(db, w, rows)

    assert batch.summary_line(steps, skipped, waiting) == (
        "Rows from your table: 1 ready to confirm, 1 need your choice, 1 not changed."
    )
    assert batch.summary_line([], skipped, []) == "Rows from your table: 1 not changed."
    assert batch.summary_line(steps, [], waiting) == "Rows from your table: 1 ready to confirm, 1 need your choice."


def test_13_the_reply_is_the_summary_line_then_the_tables_and_never_the_models_own_text(db):
    w, rows = mixed_world(db)
    model_text = "Here you go: | 1 | MODELCOPY ROW | please pick 300-ZZ1 or 300-ZZ2 for row two."
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_(model_text)]

    result, _ = run_turn(db, w, script, text_="grant access to these people")

    reply = result.reply_text
    assert reply.startswith("Rows from your table: 1 ready to confirm, 1 need your choice, 1 not changed.\n\n")
    assert "MODELCOPY" not in reply and "please pick" not in reply
    for heading in (READY, NEEDS, NOT_CHANGED):
        assert reply.count(heading) == 1


def test_13_a_batch_turns_answer_is_not_checked_so_no_repair_round_is_spent(db):
    w, rows = mixed_world(db)
    final = tc("answer", {
        "text": "There are 98765 units and nothing exists for the other shop.",
        "figures": [], "not_checked": [],
        "not_found": [{"what": "Some Other Shop", "call_id": "b1"}],
    }, "ans-1")
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), round_of(final), round_of(final)]

    result, provider = run_turn(db, w, script, text_="grant access to these people")

    assert len(provider.seen) == 2, "the answer check spent a repair round on a batch turn"
    assert "not verified" not in result.reply_text and "98765" not in result.reply_text


def _backed_by_skip(what: str, reason: str) -> bool:
    return _backed(what, reason)


def test_14_a_quoted_or_repeated_no_customer_claim_is_backed_but_other_terms_are_not():
    reason = 'No customer named "No Such Shop" in your companies.'
    assert _backed_by_skip('Customer named "No Such Shop"', reason) is True
    assert _backed_by_skip('No customer named "No Such Shop" in your companies.', reason) is True
    assert _backed_by_skip("No Such Shop", reason) is True
    assert _backed_by_skip('"Other Shop"', reason) is False
    assert _backed_by_skip("ZZT Dealer H", '"ZZT Dealer H" fits 3 accounts.') is False


def _item(row: int) -> dict:
    return {"row": row, "cells": {"Phone": "+60190000000", "Name": "ZZT Person"}, "summary": "s"}


def _wait(row: int) -> dict:
    return {**_item(row), "written": "X", "company": "MCH", "more": False, "candidates": [{"code": "C1", "name": "N1"}]}


def _skip(row: int) -> dict:
    return {"row": row, "reason": "Unknown access: Manager.", "cells": {"Phone": "+60190000000", "Name": "ZZT Person"}}


def test_14_the_closing_line_follows_what_is_ready_waiting_or_skipped():
    from app.services.chatbot.agent import batch

    pick = "Reply with the account code(s) for each row under Needs your choice, all, or skip."
    assert batch.preview_block([], [], [_wait(1)]).endswith(f"\n\n{pick}")
    assert batch.preview_block([_item(1)], [], [_wait(2)]).endswith(
        f"\n\n{pick} Or reply yes to confirm the ready rows now."
    )
    assert batch.preview_block([_item(1)], [_skip(2)], []).endswith("\n\nReply yes to go ahead, or tell me what to change.")
    assert batch.preview_block([], [_skip(1)], []).endswith(
        "\n\nNothing can change yet; fix the rows above and send the table again."
    )


def _table_headers(block: str) -> list[list[str]]:
    out = []
    for line in block.splitlines():
        if line.startswith("| #"):
            out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def test_15_every_table_starts_with_number_phone_name_and_the_will_change_cell_is_never_cut(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    linked = [account(db, f"ZZT LONG NAME TRADING SDN BHD BRANCH NUMBER {i}", f"ZL-{i:02d}", w.srt) for i in range(10)]
    dealer_h(db, w.mch)
    ready, waits, bad = dealer(db, w), dealer(db, w, companies=(w.mch,)), dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [
        row_(ready.phone_number, codes=[a.customer_code for a in linked]),
        waiting_row(w, waits),
        row_(bad.phone_number, names=["ZZT Nowhere Stores"]),
    ])
    block = batch.preview_block(steps, skipped, waiting)

    heads = _table_headers(block)
    assert len(heads) == 3
    for head in heads:
        assert head[:3] == ["#", "Phone", "Name"], head
    for a in linked:
        assert a.customer_code in block
    assert "..." not in block
