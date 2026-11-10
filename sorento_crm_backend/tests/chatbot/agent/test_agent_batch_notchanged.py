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
    make_world,
    row_,
    state,
)
from tests.chatbot.agent.test_agent_bulk_v2 import WRITTEN, pasted, picker_world, say, stored, tag
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
    # UAC A17: the first turn is the paste, so the dealer names are in the user's text.
    r1 = say(db, w, first, pasted("grant access to these ppl", first))
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
    say(db, w, [tag(row_(pr.phone_number, names=[NO_SUCH]), 3)], f"grant this one {pr.phone_number} {NO_SUCH}")

    other = dealer(db, w)
    r2 = say(db, w, [tag(row_(other.phone_number, codes=[w.cust_a.customer_code]), 1)], f"now grant this one {other.phone_number}")

    assert r2.reply_text.startswith("Rows from your table: 1 ready to confirm.")
    assert NO_SUCH not in r2.reply_text


def test_an_unrelated_table_after_waiting_rows_inherits_no_rows(db):
    """Rows waited, then the user sent a different list instead of a pick: none of its rows was waiting."""
    w, f, h, (pf, ph, pr) = _first_table(db)

    other = dealer(db, w)
    r2 = say(db, w, [tag(row_(other.phone_number, codes=[w.cust_a.customer_code]), 1)], f"actually just this one {other.phone_number}")

    assert r2.reply_text.startswith("Rows from your table: 1 ready to confirm.")
    assert NO_SUCH not in r2.reply_text


def test_another_write_after_waiting_rows_inherits_no_rows(db):
    from tests.chatbot.agent.test_agent_bulk_w2_tags import numbered, stem, tag_
    from tests.chatbot.agent.test_agent_bulk_w2_tags import row_ as tag_row
    from tests.chatbot.agent.test_agent_bulk_w2_tags import say as tag_say

    w, f, h, (pf, ph, pr) = _first_table(db)
    office = tag_(db, f"{stem()} Office Staff")

    # The same phone as waiting row 1, but a tags table: another request.
    r2 = tag_say(db, w, [numbered(tag_row(pf.phone_number, add=[office.name]), 1)], "tag this person")

    assert NO_SUCH not in r2.reply_text
    assert "No customer named" not in r2.reply_text


def test_a_renumbered_follow_up_still_keeps_the_not_changed_row(db):
    """Row 1 is not changed, rows 2 and 3 wait. The model sends the two picks with no row number, so they fall back
    to positions 1 and 2: the earlier row 1 is matched by its phone, not by its number, and still listed."""
    w, f, h, (pf, ph, pr), _ = picker_world(db)
    first = [
        tag(row_(pr.phone_number, names=[NO_SUCH]), 1),
        tag(row_(pf.phone_number, companies=["SRT"], names=["ZZT Dealer F"]), 2),
        tag(row_(ph.phone_number, companies=["MCH"], names=[WRITTEN]), 3),
    ]
    say(db, w, first, pasted("grant access to these ppl", first))

    picked = [
        row_(pf.phone_number, companies=["SRT"], codes=[f[0].customer_code]),
        row_(ph.phone_number, companies=["MCH"], codes=[h[0].customer_code]),
    ]
    r2 = say(db, w, picked, f"row 2: {f[0].customer_code}, row 3: {h[0].customer_code}")

    assert r2.reply_text.startswith("Rows from your table: 2 ready to confirm, 1 not changed.")
    assert NO_SUCH in r2.reply_text.split("Not changed:", 1)[1]


def test_the_result_counts_include_the_carried_row(db):
    from app.services.chatbot.agent import batch
    from tests.chatbot.agent.test_agent_bulk_grant import ctx_of

    w, f, h, (pf, ph, pr) = _first_table(db)
    previous = stored(db, say(db, w, [tag(row_(pf.phone_number, companies=["SRT"], names=["ZZT Dealer F"]), 1),
                                      tag(row_(ph.phone_number, companies=["MCH"], names=[WRITTEN]), 2),
                                      tag(row_(pr.phone_number, names=[NO_SUCH]), 3)],
                                  f"again {pf.phone_number} {ph.phone_number} {pr.phone_number}"))
    # UAC A18: the stored table also carries what each row verified as typed (`batch_typed`), its company included.
    table = {"write": previous["batch_write"], "waiting": previous["batch_waiting"], "skipped": previous["batch_skipped"],
             "typed": previous["batch_typed"]}
    rows = [tag(row_(pf.phone_number, companies=["SRT"], codes=[f[0].customer_code]), 1)]
    out = batch.propose(db, ctx_of(db, w), {"write": GRANT, "rows": rows}, [], seen_ids=set(),
                        user_text=f"row 1: {f[0].customer_code}", previous_waiting=table["waiting"], previous=table)

    assert out.data["rows_total"] == 2 and out.data["rows_skipped"] == 1 and out.data["rows_proposed"] == 1
    assert [s["row"] for s in out.data["skipped"]] == [3]


def test_the_tool_asks_for_every_row_of_the_current_request(db):
    from app.services.chatbot.agent import batch
    from tests.chatbot.agent.test_agent_bulk_grant import ctx_of

    w = make_world(db)
    text = batch.batch_tool_schema(db, ctx_of(db, w))["function"]["description"]
    assert "EVERY row of the current request" in text
    assert "not changed" in text
    assert "Propose only the rows still open" not in text
    assert GRANT


# ------------------------------------------------------------------ the tags write (#2247 S2), same guard


def test_the_tag_pick_follow_up_keeps_the_not_changed_rows_the_model_left_out(db):
    """S2 of the tags live check: 'row 3: Retail Salesperson' sent only rows 1-3, so rows 4 (Already tagged) and 5
    (No tag named Gold) vanished from Not changed in 2 of 3 runs."""
    from tests.chatbot.agent.test_agent_bulk_w2_tags import hold, numbered, stem, tag_
    from tests.chatbot.agent.test_agent_bulk_w2_tags import row_ as tag_row
    from tests.chatbot.agent.test_agent_bulk_w2_tags import say as tag_say

    w = make_world(db)
    s = stem()
    office = tag_(db, f"{s} Office Staff")
    retail = tag_(db, f"{s} Retail Salesperson")
    tag_(db, f"{s} Project Salesperson")
    a, c, d, b = dealer(db, w), dealer(db, w), dealer(db, w), dealer(db, w)
    hold(db, b, office)
    gold = f"{s} Gold"
    first = [
        numbered(tag_row(a.phone_number, add=[office.name]), 1),
        numbered(tag_row(c.phone_number, add=[office.name]), 2),
        numbered(tag_row(d.phone_number, add=["salesperson"]), 3),
        numbered(tag_row(b.phone_number, add=[office.name]), 4),
        numbered(tag_row(d.phone_number.replace("+6019", "+6017"), add=[gold]), 5),
    ]
    r1 = tag_say(db, w, first, "tag these people")
    assert "Needs your choice:" in r1.reply_text and gold in r1.reply_text

    picked = first[:2] + [numbered(tag_row(d.phone_number, add=[retail.name]), 3)]
    r2 = tag_say(db, w, picked, f"row 3: {retail.name}")

    assert r2.reply_text.startswith("Rows from your table: 3 ready to confirm, 2 not changed.")
    not_changed = r2.reply_text.split("Not changed:", 1)[1]
    assert b.phone_number in not_changed and "Already tagged" in not_changed
    assert gold in not_changed
    assert len(r2.pending_action["lines"]) == 3


# ------------------------------------------------------------------ the closing line follows the request's shape


def test_a_one_row_request_with_nothing_to_change_does_not_ask_for_the_table_again(db):
    from app.services.chatbot.agent import batch

    w, f, h, (pf, ph, pr), _ = picker_world(db)
    r = say(db, w, [row_(pr.phone_number, names=[NO_SUCH])], f"give {pr.phone_number} access to {NO_SUCH}")

    assert r.pending_action is None
    assert "send the table again" not in r.reply_text
    assert r.reply_text.endswith(batch.NOTHING_ONE_TAIL)


def test_a_table_with_nothing_to_change_still_asks_for_the_table_again():
    from app.services.chatbot.agent import batch

    skip = {"row": 1, "reason": "Unknown access: Manager.", "cells": {"Phone": "+60190000000"}}
    block = batch.preview_block([], [skip, {**skip, "row": 2}], [])
    assert block.endswith(batch.NOTHING_TAIL) and "send the table again" in batch.NOTHING_TAIL
    assert batch.preview_block([], [skip], []).endswith(batch.NOTHING_ONE_TAIL)
