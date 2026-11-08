"""AGENT-BATCH-NOTCHANGED (PLAN-agent-batch-notchanged-8nov.md, UAC agent-batch-notchanged-8nov-acceptance-criteria.md):
the pick follow-up keeps the not-changed rows of the current request.

Red tests, written before the fix. Crew's live check of #2250 (grant prompt P5 run 1): a 3-row table, rows 1 and 2
waiting for an account pick and row 3 not changed (no such customer). The user picked codes; the model sent only
rows 1 and 2, so row 3 vanished from the Not changed table and the reply read "2 ready to confirm". Turn-level
through the scripted provider, with the real grant write. Postgres only; phones, names and codes are invented.
"""
from __future__ import annotations

from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    GRANT,
    _listeners,
    dealer,
    db,
    row_,
    state,
)
from tests.chatbot.agent.test_agent_bulk_v2 import WRITTEN, picker_world, say, stored, tag
from tests.chatbot.agent.test_agent_writes import action_rows

NO_SUCH = "ZZT No Such Shop Sdn Bhd"


def _first_table(db):
    """Rows 1 and 2 wait for a pick; row 3 names no customer at all, so it is not changed."""
    w, f, h, (pf, ph, pr), _ = picker_world(db)
    first = [
        tag(row_(pf.phone_number, companies=["SRT"], names=["ZZT Dealer F"]), 1),
        tag(row_(ph.phone_number, companies=["MCH"], names=[WRITTEN]), 2),
        tag(row_(pr.phone_number, names=[NO_SUCH]), 3),
    ]
    r1 = say(db, w, first, "grant access to these ppl")
    assert r1.pending_action is None
    assert "Not changed:" in r1.reply_text and NO_SUCH in r1.reply_text
    return w, f, h, (pf, ph, pr)


def test_the_pick_follow_up_keeps_the_not_changed_row_the_model_left_out(db):
    w, f, h, (pf, ph, pr) = _first_table(db)

    # The model sends only the two picked rows: exactly the live shape of P5 run 1.
    picked = [
        tag(row_(pf.phone_number, companies=["SRT"], codes=[f[0].customer_code]), 1),
        tag(row_(ph.phone_number, companies=["MCH"], codes=[a.customer_code for a in h]), 2),
    ]
    r2 = say(db, w, picked, f"row 1: {f[0].customer_code}, row 2 all")

    assert r2.reply_text.startswith("Rows from your table: 2 ready to confirm, 1 not changed.")
    not_changed = r2.reply_text.split("Not changed:", 1)[1]
    assert NO_SUCH in not_changed and pr.phone_number in not_changed
    assert "No customer named" in not_changed
    # The card holds only the two ready rows, and nothing is written before Confirm.
    lines = r2.pending_action["lines"]
    assert len(lines) == 2 and not any(pr.phone_number in line for line in lines)
    assert [s["row"] for s in action_rows(db, w.respond_id)[-1].steps] == [1, 2]
    assert state(db, pr.phone_number)["links"] == []


def test_the_follow_up_turn_keeps_the_not_changed_rows_for_the_turn_after_it(db):
    w, f, h, (pf, ph, pr) = _first_table(db)
    picked = [tag(row_(pf.phone_number, companies=["SRT"], codes=[f[0].customer_code]), 1)]
    r2 = say(db, w, picked, f"row 1: {f[0].customer_code}")

    kept = stored(db, r2).get("batch_skipped") or []
    assert [s["row"] for s in kept] == [3]


def test_a_row_the_model_does_send_again_is_rechecked_not_duplicated(db):
    w, f, h, (pf, ph, pr) = _first_table(db)
    again = [
        tag(row_(pf.phone_number, companies=["SRT"], codes=[f[0].customer_code]), 1),
        tag(row_(ph.phone_number, companies=["MCH"], codes=[h[0].customer_code]), 2),
        tag(row_(pr.phone_number, names=[NO_SUCH]), 3),
    ]
    r2 = say(db, w, again, f"row 1: {f[0].customer_code}, row 2: {h[0].customer_code}")

    assert r2.reply_text.startswith("Rows from your table: 2 ready to confirm, 1 not changed.")
    assert r2.reply_text.split("Not changed:", 1)[1].count(NO_SUCH) == 1


def test_a_new_table_with_nothing_waiting_before_it_inherits_no_rows(db):
    w, f, h, (pf, ph, pr), _ = picker_world(db)
    say(db, w, [tag(row_(pr.phone_number, names=[NO_SUCH]), 1)], "grant this one")

    other = dealer(db, w)
    r2 = say(db, w, [tag(row_(other.phone_number, codes=[w.cust_a.customer_code]), 1)], "now grant this one")

    assert r2.reply_text.startswith("Rows from your table: 1 ready to confirm.")
    assert NO_SUCH not in r2.reply_text


def test_the_tool_asks_for_every_row_of_the_current_request(db):
    from app.services.chatbot.agent import batch
    from tests.chatbot.agent.test_agent_bulk_grant import ctx_of, make_world

    w = make_world(db)
    text = batch.schema_for(db, ctx_of(db, w))["function"]["description"]
    assert "EVERY row of the current request" in text
    assert "not changed" in text
    assert "Propose only the rows still open" not in text
    assert GRANT
