"""PICKER-NO-CAP (owner, 2 Oct 2026): "the chatbot picker is capped at 10 options ...
remove that cap". Every option a picker stores is printed, so every option the dealer
can pick is one they can see.

The stock pickers stored up to `MAX_SLOTS` (20) options but printed only `MAX_NAMED`
(10) of them, closing with "and N others, reply with the full code." - options 11 to 20
were pickable by number yet never shown. The "others" line now only counts matches the
pick does not carry at all (`count` past the stored options).
"""
from __future__ import annotations

from app.services.chatbot.dealer_stock import did_you_mean
from app.services.chatbot.turn import task as task_mod

from tests.chatbot import _ht26_fixtures as ht


def test_family_pick_numbers_every_option_past_ten():
    codes = [f"SRTX1-{i:02d}" for i in range(15)]
    lines = task_mod.pick_question("SRTX1", codes).splitlines()
    assert lines[0] == "SRTX1 matches 15 products. Which one?"
    assert lines[1:] == task_mod.numbered(codes)
    assert not any("others" in line for line in lines)


def test_family_pick_from_the_stock_reply_lists_all_twelve():
    codes = [f"SRTX1-{i:02d}" for i in range(12)]
    reply = task_mod.after_reply(
        (), ht.envelopes(*[ht.row(c) for c in codes]), asked=[ht.asked("srtx1")]
    )
    lines = reply.text.splitlines()
    assert lines[0] == "SRTX1 matches 12 products. Which one?"
    assert lines[1:] == task_mod.numbered(codes)
    assert [o["label"] for o in reply.pick["options"]] == codes


def test_the_others_line_counts_only_matches_the_pick_does_not_carry():
    """`count` past the stored options (the stock tool matched more than `MAX_SLOTS`):
    every stored option is printed, and only the rest are counted."""
    codes = [f"SRTX1-{i:02d}" for i in range(task_mod.MAX_SLOTS)]
    lines = task_mod.pick_question("SRTX1", codes, count=27).splitlines()
    assert lines[0] == "SRTX1 matches 27 products. Which one?"
    assert lines[1:-1] == task_mod.numbered(codes)
    assert lines[-1] == "and 7 others, reply with the full code."


def test_dealer_did_you_mean_numbers_every_candidate_past_ten():
    codes = [f"ELP37{i:02d}" for i in range(14)]
    text, pending = did_you_mean(
        "elp3799",
        [{"product": c, "uuid": ht.uuid_of(c), "entity_type": "product"} for c in codes],
    )
    lines = text.splitlines()
    assert lines[0] == "Couldn't find ELP3799. Did you mean:"
    assert lines[1:] == task_mod.numbered(codes)
    assert [o["label"] for o in pending.options] == codes
