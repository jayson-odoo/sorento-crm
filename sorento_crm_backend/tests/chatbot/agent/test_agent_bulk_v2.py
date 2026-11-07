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
