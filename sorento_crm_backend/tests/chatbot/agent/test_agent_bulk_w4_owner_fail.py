"""Owner hand test #2256 on f11eeef9 (14 Nov, 375 px, Contacts list + AI assistant): FAIL.

The owner attached a screenshot of the Contacts list (phones and first names) and typed "Please grant them mocha
access to the chatbot". The agent found the contacts, then `crm_batch_propose` came back invalid and the reply was
the tool's guidance to the model, word for word: "No row can be changed; tell the user why, row by row."

Two defects:
1. LEAK: the dealer-access reply took the batch tool's message, which is guidance for the model, not a sentence for
   the user. The user always gets a plain answer built by code.
2. A screenshot's phones are not in the typed message, so UAC F4 ("only the people this message names") left every
   row out. Rows the model read from an image attached to THIS message are named by this message.

Phones and names are invented (public repo), ZZT data only.
"""
from __future__ import annotations

from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    BATCH,
    GRANT,
    _listeners,
    db,
    dealer,
    fake_phone,
    local,
    make_world,
    row_,
)
from tests.chatbot.agent.test_agent_images import IMAGE
from tests.chatbot.agent.test_agent_writes import Provider, _no_mcp, answer_, round_of, tc

OWNER_TEXT = "Please grant them mocha access to the chatbot"
#: Guidance the batch tool gives the model; none of it may ever be the user's reply.
GUIDANCE = (
    "tell the user",
    "No row can be changed",
    "rows must be a list",
    "Arguments must be an object",
    "Propose the table on its own",
    "Call a tool now",
    "Your own text is not shown",
)


def screenshot_turn(db, w, script, text_=OWNER_TEXT, images=True):
    from app.services.chatbot.agent.loop import run_agent_turn

    provider = Provider(script, dealer_access=True)
    result = run_agent_turn(
        db, contact_respond_id=w.respond_id, text=text_, provider=provider, mcp_call=_no_mcp, catalog={},
        images=[IMAGE] if images else None,
    )
    return result, provider


def _batch(rows, cid="b1"):
    return round_of(tc(BATCH, {"write": GRANT, "rows": rows}, cid))


def assert_plain(reply: str) -> None:
    for words in GUIDANCE:
        assert words not in reply, f"model guidance reached the user: {words!r} in\n{reply}"


def test_rows_read_from_an_attached_screenshot_become_one_grant_card(db):
    w = make_world(db)
    found = [dealer(db, w, name=f"ZZT Shot {i}") for i in range(3)]
    rows = [
        {**row_(local(c.phone_number), name=c.name, role="employee", companies=("MCH",)), "row": i}
        for i, c in enumerate(found, 1)
    ]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert_plain(result.reply_text)
    assert result.pending_action is not None, result.reply_text
    assert result.reply_text.startswith("Rows from your table: 3 ready to confirm"), result.reply_text
    for c in found:
        assert c.name in result.reply_text


def test_a_screenshot_row_that_cannot_change_is_named_with_its_plain_reason(db):
    w = make_world(db)
    ok = dealer(db, w, name="ZZT Shot Ok")
    rows = [
        {**row_(local(ok.phone_number), name=ok.name, role="employee", companies=("MCH",)), "row": 1},
        {**row_("12345", name="ZZT Shot Bad", role="employee", companies=("MCH",)), "row": 2},
    ]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert_plain(result.reply_text)
    assert result.pending_action is not None, result.reply_text
    assert "1 ready to confirm, 1 not changed" in result.reply_text
    assert 'Phone "12345" is not a Malaysian mobile number.' in result.reply_text


def test_no_role_given_reads_as_a_plain_table_not_model_guidance(db):
    """The owner's exact words give no Owner/Employee: each row says so plainly; nothing is guessed."""
    w = make_world(db)
    found = [dealer(db, w, name=f"ZZT NoRole {i}") for i in range(2)]
    rows = [
        {"phone": local(c.phone_number), "name": c.name, "role": "unknown", "companies": [], "row": i}
        for i, c in enumerate(found, 1)
    ]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert_plain(result.reply_text)
    assert result.pending_action is None
    assert "Rows from your table: 2 not changed." in result.reply_text, result.reply_text
    assert "Unknown access" in result.reply_text


def test_rows_of_nobody_named_are_never_answered_with_tool_guidance(db):
    """Without an image the F4 rule still leaves out rows the message does not name; the user is told plainly."""
    w = make_world(db)
    other = dealer(db, w, name="ZZT Not Named")
    rows = [{**row_(local(other.phone_number), name=other.name, role="employee", companies=("MCH",)), "row": 1}]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], images=False)
    assert_plain(result.reply_text)
    assert result.pending_action is None
    # The left-out row is listed with its plain reason (review K2: an empty or generic reply is not enough).
    from app.services.chatbot.agent.batch import LEFT_OUT_REASON

    assert other.phone_number in result.reply_text, result.reply_text
    assert LEFT_OUT_REASON in result.reply_text


def test_a_malformed_batch_call_never_shows_its_refusal_to_the_user(db):
    w = make_world(db)
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": []}, "b1")), answer_("Done.")]
    result, _ = screenshot_turn(db, w, script)
    assert_plain(result.reply_text)
    assert result.reply_text.strip()


# ------------------------------------------------------------------ security review round (F4 kept)


def test_rows_left_out_on_one_turn_do_not_become_ready_on_the_next(db):
    """Left-out rows shown as not changed are display only: a follow-up naming nobody does not revive them."""
    w = make_world(db)
    other = dealer(db, w, name="ZZT Left Out")
    rows = [{**row_(local(other.phone_number), name=other.name, role="employee", companies=("MCH",)), "row": 1}]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="grant mocha access please", images=False)
    assert first.pending_action is None
    second, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="ok do it for Mocha", images=False)
    assert second.pending_action is None, second.reply_text
    assert "ready to confirm" not in second.reply_text


def test_an_attachment_does_not_bring_back_a_person_of_an_older_request(db):
    """A picture names the people read from it, not someone the model re-sends from an earlier table."""
    w = make_world(db)
    old = dealer(db, w, name="ZZT Old Ask")
    new = dealer(db, w, name="ZZT New Shot")
    old_row = {**row_(local(old.phone_number), name=old.name, role="unknown", companies=("MCH",)), "row": 1}
    screenshot_turn(db, w, [_batch([old_row]), answer_("Done.")], text_=f"grant {local(old.phone_number)}", images=False)
    from tests.chatbot.agent.test_agent_writes import run_turn

    between, _ = run_turn(db, w, [answer_("Hello.")], text_="hi")  # a plain turn: the old table is not the last one
    assert between.reply_text.startswith("Hello"), between.reply_text
    rows = [
        {**row_(local(new.phone_number), name=new.name, role="employee", companies=("MCH",)), "row": 1},
        {**row_(local(old.phone_number), name=old.name, role="employee", companies=("MCH",)), "row": 2},
    ]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them Mocha employee access")
    assert result.pending_action is not None, result.reply_text
    assert new.name in result.reply_text
    assert old.name not in result.reply_text, result.reply_text


def test_an_undecided_card_expired_by_a_newer_request_does_not_return_on_a_picture_turn(db):
    """Review B1: card A (undecided), card B expires it, then a picture turn re-sent A: A stays out."""
    w = make_world(db)
    a, b, c = (dealer(db, w, name=f"ZZT Card {x}") for x in "ABC")

    def r(p, n):
        return {**row_(local(p.phone_number), name=p.name, role="employee", companies=("MCH",)), "row": n}

    first, _ = screenshot_turn(db, w, [_batch([r(a, 1)]), answer_("ok")], text_=f"Mocha {local(a.phone_number)}", images=False)
    assert first.pending_action is not None
    second, _ = screenshot_turn(db, w, [_batch([r(b, 1)], "b2"), answer_("ok")], text_=f"Mocha {local(b.phone_number)}", images=False)
    assert second.pending_action is not None
    third, _ = screenshot_turn(db, w, [_batch([r(a, 1), r(c, 2)], "b3"), answer_("ok")], text_="grant them Mocha employee")
    assert third.pending_action is not None, third.reply_text
    assert c.name in third.reply_text and a.name not in third.reply_text, third.reply_text


def test_a_grant_call_with_bad_arguments_never_shows_the_argument_error(db):
    """Review S1: a GRANT schema or id refusal is guidance for the model, never the reply."""
    w = make_world(db)
    script = [round_of(tc(GRANT, {"bogus": 1}, "g1")), answer_("Done.")]
    result, _ = screenshot_turn(db, w, script, images=False)
    assert_plain(result.reply_text)
    assert "Unknown argument" not in result.reply_text and "bogus" not in result.reply_text, result.reply_text


def test_a_table_over_the_row_limit_says_so_plainly(db):
    """Review S2: too many rows gets its own plain line, not a request for details."""
    from app.services.chatbot.agent.batch import MAX_ROWS, TOO_MANY_SAY

    w = make_world(db)
    rows = [{**row_(fake_phone(), role="employee", companies=("MCH",)), "row": i} for i in range(1, MAX_ROWS + 2)]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert result.reply_text.strip() == TOO_MANY_SAY, result.reply_text


def test_a_single_grant_card_person_does_not_return_on_a_picture_turn(db):
    """Security re-review: a one-person card (no table) counts as an earlier request too."""
    w = make_world(db)
    earlier = dealer(db, w, name="ZZT Single Earlier")
    new = dealer(db, w, name="ZZT Shot New")
    single = row_(local(earlier.phone_number), name=earlier.name, role="employee", companies=("MCH",))
    first, _ = screenshot_turn(
        db, w, [round_of(tc(GRANT, single, "g1")), answer_("Done.")],
        text_=f"give {earlier.name} {local(earlier.phone_number)} Mocha access", images=False,
    )
    assert first.pending_action is not None, first.reply_text
    rows = [
        {**row_(local(new.phone_number), name=new.name, role="employee", companies=("MCH",)), "row": 1},
        {**row_(local(earlier.phone_number), name=earlier.name, role="employee", companies=("MCH",)), "row": 2},
    ]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them Mocha access")
    assert result.pending_action is not None, result.reply_text
    assert new.name in result.reply_text and earlier.name not in result.reply_text, result.reply_text
