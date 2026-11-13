"""AGENT-BULK-W4-CONTACTS crew pass 13 Nov (PR #2256 comment 6848312354): the dealer-access side call (#2268, UAC F2)
judged "update these contacts" + a phone table to be dealer access on 5 of 7 live turns, so the turn was offered only
the grant (`dealer_schemas`) and `crm_contact_edit` was never reachable. On the W3 follow-up (P4 turn 2) the call was
shown no table at all (the earlier table was passed only for a grant), so an answer to a sales-agent table's rows
read as "answering for rows of a table" and went to the grant.

The fix stays semantic (owner rule: no word lists): the side call is told what dealer access is NOT (the other
contact and customer table writes), and it sees the immediately preceding table whatever its write, named by what
that table changes. These tests pin what the side call is shown; the verdict itself is the model's and is checked by
crew's live set. Phones, names and codes are invented (public repo).
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    BATCH,
    EDIT,
    GRANT,
    _listeners,
    db,
    fake_phone,
    local,
    make_world,
)
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc

EDIT_WRITE = "crm_contact_edit"

#: The seven turns of the crew pass (laneboard/scripts/2256.md), as their messages: the table follows the phrase.
PASS_TURNS = {
    "P1": "update these contacts\nPhone | Name | Sponsorship registered project | Workspace\n0190000561 | ZZT A Sdn Bhd",
    "P2": "tukar nama kontak ni\nTelefon | Nama\n0190000562 | ZZT Kedai Baru",
    "P4-1": "assign these sales agents\nCompany | Customer | Agent\nSRT | ZZTQ1 | NOSUCH 77",
    "P4-2": "row 2: SRT",
    "P5": "update these contacts\nPhone | Name | Sponsorship registered project | Workspace\n0190000563 | | | No Such Workspace 77",
    "P5b": "update these contacts\nPhone | Name\n0190000564 | ZZT Proper Case",
    "P7": "update these contacts\nPhone | Name\n0190000565 | ZZT Own Rule",
}


def side_prompt(provider) -> str:
    assert provider.side, "the dealer-access side call did not run"
    return provider.side[-1]["messages"][0]["content"]


def turn(db, w, text_, script=None):
    return run_turn(db, w, script or [answer_("Done.")], text_=text_)


@pytest.mark.parametrize("name", list(PASS_TURNS))
def test_every_pass_turn_tells_the_side_call_that_contact_details_are_not_dealer_access(db, name):
    w = make_world(db)
    _, provider = turn(db, w, PASS_TURNS[name])
    prompt = side_prompt(provider)
    assert PASS_TURNS[name] in prompt
    # The definition names the other contact and customer changes as not dealer access, by what they change.
    rest = prompt.split("Answer false", 1)
    assert len(rest) == 2, prompt
    not_access = rest[1].split("The user's message", 1)[0]
    for part in ("name", "sponsorship", "Respond.io workspace", "tags", "sales agents"):
        assert part in not_access, f"{part!r} is not named as something other than dealer access:\n{prompt}"


def _edit_table_turn(db, w, phone):
    rows = [{"phone": local(phone), "name": "ZZT Renamed Shop", "row": 1}]
    script = [round_of(tc(BATCH, {"write": EDIT_WRITE, "rows": rows}, "b1")), answer_("Done.")]
    result, _ = turn(db, w, "update these contacts\nPhone | Name\n" + local(phone) + " | ZZT Renamed Shop", script)
    return result


def test_a_follow_up_to_a_contact_edit_table_shows_that_table_to_the_side_call(db):
    w = make_world(db)
    first = _edit_table_turn(db, w, fake_phone())
    assert first.reply_text.startswith("Rows from your table")

    _, provider = turn(db, w, "make row 1 ZZT Renamed Shop Sdn Bhd instead")
    prompt = side_prompt(provider)
    assert first.reply_text in prompt, "the side call was not shown the contact edit table it follows"
    assert "edit contacts from a pasted table" in prompt
    assert "previous reply (a dealer access table)" not in prompt


def test_a_follow_up_to_a_sales_agent_table_shows_that_table_named_as_such(db):
    """P4 turn 2: the W3 table's follow-up was routed to the grant because the side call saw no table."""
    from tests.chatbot.agent.test_agent_bulk_w3_agents import ALL, _nosuch_table

    w = make_world(db, slugs=ALL, superadmin=True)
    _nosuch_table(db, w)

    _, provider = turn(db, w, "row 1: the first one")
    prompt = side_prompt(provider)
    assert 'No sales agent named "NOSUCH 77"' in prompt, "the side call was not shown the sales-agent table"
    assert "assign sales agents to customers" in prompt
    assert "previous reply (a dealer access table)" not in prompt


def test_a_follow_up_to_a_grant_table_still_shows_it_as_a_dealer_access_table(db):
    """#2268 UAC F2/F3 unchanged: the grant table's follow-up is still shown as a dealer access table."""
    from tests._pg_fixture import unique_code
    from tests.chatbot.agent.test_agent_bulk_grant import row_
    from tests.chatbot.agent.test_dealer_access_agent import _batch_call, add_customer

    w = make_world(db)
    stem = unique_code("ZZT Yoo Living", alpha=True)
    add_customer(db, w, f"{stem} A/C I")
    add_customer(db, w, f"{stem} A/C III")
    phone = fake_phone()
    rows = [row_(phone, role="employee", names=[stem])]
    typed = f"Sorento, {phone} {stem} employee"
    first, _ = run_turn(db, w, [_batch_call(rows), answer_("ok")], text_=typed, dealer_access=True)
    assert "Needs your choice" in first.reply_text, first.reply_text

    _, provider = turn(db, w, "row 1: all")
    prompt = side_prompt(provider)
    assert "previous reply (a dealer access table)" in prompt
    assert first.reply_text in prompt


def test_a_plain_turn_after_no_table_shows_no_table(db):
    w = make_world(db)
    turn(db, w, "hi, how is stock today?")
    _, provider = turn(db, w, PASS_TURNS["P1"])
    prompt = side_prompt(provider)
    assert "previous reply" not in prompt


def test_with_the_side_call_saying_no_the_contact_edit_is_offered_on_the_batch_tool(db):
    """The routing seam itself: a turn not judged dealer access keeps every permitted batch write."""
    w = make_world(db)
    _, provider = turn(db, w, PASS_TURNS["P1"])
    batch_tool = [t for t in provider.seen[0]["tools"] if t["function"]["name"] == BATCH]
    assert batch_tool and EDIT_WRITE in batch_tool[0]["function"]["parameters"]["properties"]["write"]["enum"]
