"""AGENT-DECIDED-CARDS (PLAN-agent-decided-cards-8nov.md, UAC agent-decided-cards-8nov-acceptance-criteria.md): a
Confirm card the user cancelled or confirmed must not come back on the next card of the same thread.

Red tests, written before the fix. The crew live check (#2247) saw: a card cancelled, then "Tag C with Mocha
Dealer" produced a 3-row card that re-included the cancelled rows for contacts A and D. The model re-sends the
whole table, and its history never said the card was decided. Turn-level through the scripted provider, with the
real grant write. Postgres only (blank schema); phones, names and codes are invented (public repo).
"""
from __future__ import annotations

from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    BATCH,
    GRANT,
    _listeners,
    db,
    dealer,
    local,
    make_world,
    row_,
    state,
    typed_companies,
    typed_phones,
)
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc

CANCELLED_REASON = "earlier cancelled table"
DONE_REASON = "earlier confirmed table"


# UAC F4: a first table turn is a paste, so its text carries the people's phones (`typed_phones`).
def _batch_turn(db, w, rows, text_):
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_("Here is the table.")]
    # UAC A18: the user's message names the rows' company, as a real one does.
    return run_turn(db, w, script, text_=typed_companies(text_, rows))


def _three(db, w):
    """Contacts A, D and C, each an existing end user of SRT with no links."""
    a = dealer(db, w, name="ZZT Ahmad")
    d = dealer(db, w, name="ZZT Devi")
    c = dealer(db, w, name="ZZT Chong")
    return a, d, c


def _rows(w, *people):
    return [row_(p.phone_number, name=p.name, codes=[w.cust_a.customer_code]) for p in people]


def _history_text(provider) -> str:
    """Everything the model was handed on its first call of the turn, as one string."""
    return "\n".join(str(m.get("content") or "") for m in provider.seen[0]["messages"])


def _lines(result) -> str:
    return "\n".join((result.pending_action or {}).get("lines") or [])


# ------------------------------------------------------------------ AC-1, AC-3: cancel, then a follow-up


def test_cancel_then_follow_up_does_not_bring_the_cancelled_rows_back(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    # The model re-sends the whole table plus the new row, exactly the crew's live shape.
    second, provider = _batch_turn(db, w, _rows(w, a, d, c), f"Tag {c.name} with that customer too")

    lines = _lines(second)
    assert c.phone_number in lines
    assert a.phone_number not in lines and d.phone_number not in lines
    assert CANCELLED_REASON in second.reply_text
    # Nothing was written for anybody: the second card waits for a yes.
    assert state(db, a.phone_number)["links"] == [] and state(db, d.phone_number)["links"] == []


def test_after_a_cancel_the_next_turn_tells_the_model_the_card_was_cancelled(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    _, provider = run_turn(db, w, [answer_("ok")], text_="thanks")

    seen = _history_text(provider)
    assert "cancelled" in seen.lower()
    assert "Card cancelled" in seen
    assert a.phone_number in seen.split("Card cancelled", 1)[1]


def test_a_cancelled_row_proposes_again_when_the_user_asks_for_it_by_phone(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    second, _ = _batch_turn(db, w, _rows(w, a, d), f"sorry, do {local(a.phone_number)} after all")

    lines = _lines(second)
    assert a.phone_number in lines
    assert d.phone_number not in lines


def test_a_cancelled_row_proposes_again_when_the_user_names_the_person(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    second, _ = _batch_turn(db, w, _rows(w, a, d), "redo zzt devi please")

    lines = _lines(second)
    assert d.phone_number in lines and a.phone_number not in lines


def test_a_row_asked_for_again_stays_open_on_the_cards_after_it(db):
    """Cancel A; ask for A again (card 2 holds A); then add C without naming A: A stays, it was asked for again."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])
    _batch_turn(db, w, _rows(w, a), f"do {a.name} again")

    third, _ = _batch_turn(db, w, _rows(w, a, c), f"and {c.name} too")

    lines = _lines(third)
    assert a.phone_number in lines and c.phone_number in lines


def test_a_new_table_with_no_decided_rows_proposes_every_row(db):
    w = make_world(db)
    a, d, c = _three(db, w)

    result, _ = _batch_turn(db, w, _rows(w, a, d, c), typed_phones("grant access to these three", _rows(w, a, d, c)))

    lines = _lines(result)
    assert all(p.phone_number in lines for p in (a, d, c))


# ------------------------------------------------------------------ AC-2, AC-4: confirm, then a follow-up


def test_confirm_then_follow_up_lists_the_done_rows_as_done_not_as_new_rows(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    outcome = actions.confirm(db, w.respond_id, first.pending_action["id"], via="console")
    assert outcome.status == "executed", outcome.steps

    second, provider = _batch_turn(db, w, _rows(w, a, d, c), f"now {c.name} as well")

    lines = _lines(second)
    assert c.phone_number in lines
    assert a.phone_number not in lines and d.phone_number not in lines
    assert DONE_REASON in second.reply_text
    seen = _history_text(provider)
    assert "Card confirmed" in seen
    assert a.phone_number in seen.split("Card confirmed", 1)[1]


# ------------------------------------------------------------------ AC-1: the history line itself


def test_history_carries_the_decision_after_the_proposing_turn(db):
    from app.services.chatbot.agent import actions, memory

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    conv = memory.latest_conversation(db, w.respond_id)
    msgs = memory.history_messages(db, conv)

    replies = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert len(replies) == 1
    assert "Card cancelled" in replies[0]
    assert a.phone_number in replies[0] and d.phone_number in replies[0]


# ------------------------------------------------------------------ review round 1


def test_a_cancelled_person_asked_for_something_else_is_a_new_row(db):
    """Cancel "A and D to customer X", then ask for the same two with another customer: both propose (B1)."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    other = [row_(p.phone_number, name=p.name, companies=["MCH"], codes=[w.cust_b.customer_code]) for p in (a, d)]
    second, _ = _batch_turn(db, w, other, "do the same two with Mocha instead")

    lines = _lines(second)
    assert a.phone_number in lines and d.phone_number in lines
    assert CANCELLED_REASON not in second.reply_text


def test_a_confirmed_person_asked_for_more_is_a_new_row(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, _, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a), typed_phones("grant access", _rows(w, a)))
    assert actions.confirm(db, w.respond_id, first.pending_action["id"], via="console").status == "executed"

    more = [row_(a.phone_number, name=a.name, companies=["MCH"], codes=[w.cust_b.customer_code])]
    second, _ = _batch_turn(db, w, more, "give them Mocha too")

    assert a.phone_number in _lines(second)
    assert DONE_REASON not in second.reply_text


def test_a_pasted_list_of_phones_asks_for_every_one_of_them_again(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    second, _ = _batch_turn(db, w, _rows(w, a, d), f"redo these:\n{local(a.phone_number)}\n{local(d.phone_number)}")

    lines = _lines(second)
    assert a.phone_number in lines and d.phone_number in lines


def test_a_row_that_failed_on_a_confirmed_card_stays_open(db):
    """A partial confirm: D's re-check fails (its companies moved), A is done. The next card keeps D, not A."""
    from app.models.company import RespondContactCompany
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    db.add(RespondContactCompany(respond_contact_id=d.id, company_id=w.mch))
    db.commit()
    outcome = actions.confirm(db, w.respond_id, first.pending_action["id"], via="console")
    assert outcome.status == "partial", outcome.steps

    second, provider = _batch_turn(db, w, _rows(w, a, d, c), f"now {c.name} as well")

    lines = _lines(second)
    assert d.phone_number in lines and c.phone_number in lines
    assert a.phone_number not in lines
    assert "(failed" in _history_text(provider)


def test_compaction_keeps_the_decision_of_a_folded_card(db):
    from datetime import datetime, timedelta, timezone

    from app.models.user import SystemSetting
    from app.services.chatbot.agent import actions, memory
    from tests.chatbot.agent._turns import seed_turn
    from tests.chatbot.agent.test_agent_loop import plain

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])
    conv = memory.latest_conversation(db, w.respond_id)
    later = datetime.now(timezone.utc) + timedelta(minutes=1)
    for i in range(8):
        turn = seed_turn(db, conv, minute=i, text=f"question {i} " + "x" * 400, reply="answer " + "y" * 400)
        turn.created_at = later + timedelta(minutes=i)
    row = db.query(SystemSetting).first() or SystemSetting()
    row.chatbot_agent_compact_tokens = 100
    db.add(row)
    db.commit()

    _, provider = run_turn(db, w, [plain("Earlier: a cancelled table."), answer_("ok")], text_="thanks")

    prompt = "\n".join(str(m.get("content") or "") for m in provider.seen[0]["messages"])
    assert "Fold the earlier conversation" in prompt
    assert "Card cancelled" in prompt and a.phone_number in prompt


def test_a_cancelled_row_re_sent_with_the_phone_and_name_written_differently_stays_closed(db):
    """Review round 2 (R1): the model rebuilds the table from memory and reformats the phone or shortens the name."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), typed_phones("grant access to these two", _rows(w, a, d)))
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    resent = [
        row_(local(a.phone_number), name="Ahmad", codes=[w.cust_a.customer_code]),
        row_(d.phone_number, name="devi", codes=[w.cust_a.customer_code]),
        *_rows(w, c),
    ]
    second, _ = _batch_turn(db, w, resent, "Tag the new one with that customer too")

    lines = _lines(second)
    assert c.phone_number in lines
    assert a.phone_number not in lines and d.phone_number not in lines
    assert CANCELLED_REASON in second.reply_text
