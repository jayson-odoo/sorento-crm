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
)
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc

CANCELLED_REASON = "earlier cancelled table"
DONE_REASON = "earlier confirmed table"


def _batch_turn(db, w, rows, text_):
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_("Here is the table.")]
    return run_turn(db, w, script, text_=text_)


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
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
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
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
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
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    second, _ = _batch_turn(db, w, _rows(w, a, d), f"sorry, do {local(a.phone_number)} after all")

    lines = _lines(second)
    assert a.phone_number in lines
    assert d.phone_number not in lines


def test_a_cancelled_row_proposes_again_when_the_user_names_the_person(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, _ = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    second, _ = _batch_turn(db, w, _rows(w, a, d), "redo zzt devi please")

    lines = _lines(second)
    assert d.phone_number in lines and a.phone_number not in lines


def test_a_row_asked_for_again_stays_open_on_the_cards_after_it(db):
    """Cancel A; ask for A again (card 2 holds A); then add C without naming A: A stays, it was asked for again."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
    actions.cancel(db, w.respond_id, first.pending_action["id"])
    _batch_turn(db, w, _rows(w, a), f"do {a.name} again")

    third, _ = _batch_turn(db, w, _rows(w, a, c), f"and {c.name} too")

    lines = _lines(third)
    assert a.phone_number in lines and c.phone_number in lines


def test_a_new_table_with_no_decided_rows_proposes_every_row(db):
    w = make_world(db)
    a, d, c = _three(db, w)

    result, _ = _batch_turn(db, w, _rows(w, a, d, c), "grant access to these three")

    lines = _lines(result)
    assert all(p.phone_number in lines for p in (a, d, c))


# ------------------------------------------------------------------ AC-2, AC-4: confirm, then a follow-up


def test_confirm_then_follow_up_lists_the_done_rows_as_done_not_as_new_rows(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    a, d, c = _three(db, w)
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
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
    first, _ = _batch_turn(db, w, _rows(w, a, d), "grant access to these two")
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    conv = memory.latest_conversation(db, w.respond_id)
    msgs = memory.history_messages(db, conv)

    replies = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert len(replies) == 1
    assert "Card cancelled" in replies[0]
    assert a.phone_number in replies[0] and d.phone_number in replies[0]
