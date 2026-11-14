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
    EDIT,
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


def _unsaid(c, n, companies=("MCH",)):
    """A screenshot row: phone and name only; the company from the typed message, no role said."""
    return {"phone": local(c.phone_number), "name": c.name, "role": "unknown", "companies": list(companies), "row": n}


def test_owner_turn_as_typed_keeps_each_found_contacts_current_role_on_one_card(db):
    """Crew 06:42: "mocha" is the company (voice typing kept it). Each found contact already an Employee keeps that
    role (read from the record, not guessed): ONE card, company Mocha from the message."""
    w = make_world(db)
    found = [dealer(db, w, name=f"ZZT Has Role {i}", customers=[w.cust_b]) for i in range(3)]
    rows = [_unsaid(c, i) for i, c in enumerate(found, 1)]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert_plain(result.reply_text)
    assert result.pending_action is not None, result.reply_text
    assert result.reply_text.startswith("Rows from your table: 3 ready to confirm"), result.reply_text
    assert result.reply_text.count("Employee (Mocha), their current role") == 3, result.reply_text


def test_a_contact_with_no_role_yet_gets_one_question_then_one_card(db):
    """Any row still without a role: ONE plain question for those people, no card and no Not changed table; the
    answer gives ONE card for every row."""
    w = make_world(db)
    kept = [dealer(db, w, name=f"ZZT Kept {i}", customers=[w.cust_a]) for i in range(2)]
    fresh = [dealer(db, w, name=f"ZZT Fresh {i}") for i in range(2)]
    people = [*kept, *fresh]
    rows = [_unsaid(c, i) for i, c in enumerate(people, 1)]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert_plain(first.reply_text)
    assert first.pending_action is None, first.reply_text
    assert first.reply_text.strip() == f"Owner or employee for {fresh[0].name}, {fresh[1].name}?", first.reply_text

    answered = [
        {**r, "role": "employee", "access_as_written": "employee"} if r["name"].startswith("ZZT Fresh") else r
        for r in rows
    ]
    second, _ = screenshot_turn(db, w, [_batch(answered, "b2"), answer_("Done.")], text_="employee", images=False)
    assert_plain(second.reply_text)
    assert second.pending_action is not None, second.reply_text
    assert second.reply_text.startswith("Rows from your table: 4 ready to confirm"), second.reply_text
    for c in people:
        assert c.name in second.reply_text


def test_without_the_company_word_the_agent_asks_which_company(db):
    """The variant with no company word: one question for the company; never guessed, never a Not changed table."""
    w = make_world(db)
    found = [dealer(db, w, name=f"ZZT No Co {i}", customers=[w.cust_a]) for i in range(2)]
    rows = [_unsaid(c, i, companies=()) for i, c in enumerate(found, 1)]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them access to the chatbot")
    assert_plain(result.reply_text)
    assert result.pending_action is None
    assert result.reply_text.strip() == f"Sorento or Mocha for {found[0].name}, {found[1].name}?", result.reply_text


def test_neither_company_nor_role_known_asks_both_in_one_question(db):
    w = make_world(db)
    c = dealer(db, w, name="ZZT Nothing Known")
    result, _ = screenshot_turn(
        db, w, [_batch([_unsaid(c, 1, companies=())]), answer_("Done.")], text_="Please grant them access to the chatbot"
    )
    assert result.reply_text.strip() == f"Sorento or Mocha, and owner or employee, for {c.name}?", result.reply_text


def test_an_access_word_that_is_neither_role_is_still_refused_never_guessed(db):
    """Owner card Q3 kept: a written access word that is not Owner/Employee is refused even for a contact with a
    current role."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Manager Word", customers=[w.cust_a])
    row = {**_unsaid(c, 1), "access_as_written": "Manager"}
    result, _ = screenshot_turn(db, w, [_batch([row]), answer_("Done.")])
    assert result.pending_action is None
    assert "Unknown access: Manager" in result.reply_text, result.reply_text


def test_a_single_grant_with_no_role_asks_the_same_question(db):
    w = make_world(db)
    c = dealer(db, w, name="ZZT Single Ask")
    args = {k: v for k, v in _unsaid(c, 1).items() if k != "row"}
    result, _ = screenshot_turn(
        db, w, [round_of(tc(GRANT, args, "g1")), answer_("Done.")],
        text_=f"give {local(c.phone_number)} mocha access", images=False,
    )
    assert_plain(result.reply_text)
    assert result.pending_action is None
    assert result.reply_text.strip() == f"Owner or employee for {c.name}?", result.reply_text


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


# ------------------------------------------------------------------ security review of the crew decision


def _bare(c, n, companies=("MCH",), **extra):
    """A row as read from a screenshot with no name cell: nothing the user typed names the person."""
    return {"phone": local(c.phone_number), "role": "unknown", "companies": list(companies), "row": n, **extra}


def test_an_own_scope_user_never_learns_a_strangers_name_or_level_from_the_company_question(db):
    """B1: an edit_own user, another salesperson's contact, no company: the old refusal, no name, and the same reply
    whether or not the person holds dealer access anywhere."""
    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    with_level = dealer(db, o.w, name="ZZT Secret Person", customers=[o.theirs])
    without = dealer(db, o.w, name="ZZT Hidden Nobody")
    replies = []
    for c in (with_level, without):
        result, _ = screenshot_turn(db, o.w, [_batch([_bare(c, 1, companies=())]), answer_("Done.")],
                                    text_="Please grant them access to the chatbot")
        assert c.name not in result.reply_text, result.reply_text
        assert result.pending_action is None
        assert "Name the company as SRT (Sorento) or MCH (Mocha)." in result.reply_text, result.reply_text
        replies.append(result.reply_text.replace(c.phone_number, "<phone>").replace(local(c.phone_number), "<phone>"))
    assert replies[0] == replies[1], replies


def test_an_own_scope_user_never_learns_a_strangers_name_or_level_from_the_role_question(db):
    """B1: company and the user's own account named, no role, a contact linked only to someone else's account (or to
    nobody): asked by phone, never by stored name, the same for both."""
    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    with_level = dealer(db, o.w, name="ZZT Secret Level", customers=[o.theirs_m])
    without = dealer(db, o.w, name="ZZT No Level")
    replies = []
    for c in (with_level, without):
        row = _bare(c, 1, customer_codes=[o.w.cust_b.customer_code])
        result, _ = screenshot_turn(db, o.w, [_batch([row]), answer_("Done.")], text_="grant them mocha access")
        assert c.name not in result.reply_text, result.reply_text
        replies.append(result.reply_text.replace(c.phone_number, "<phone>").replace(local(c.phone_number), "<phone>"))
    assert replies[0] == replies[1], replies


def test_a_staff_number_is_refused_before_any_question(db):
    """S2: a row a later check refuses is never asked about."""
    from tests._ask_todo_seed import agent as seed_sales_agent

    w = make_world(db)
    staff = dealer(db, w, name="ZZT Staff Contact")
    seed_sales_agent(db, staff.id, "ST")  # a sales agent's own contact is staff
    db.commit()
    result, _ = screenshot_turn(db, w, [_batch([_bare(staff, 1)]), answer_("Done.")], text_="grant them mocha access")
    assert "Owner or employee" not in result.reply_text, result.reply_text
    assert "staff member" in result.reply_text, result.reply_text


def test_a_level_in_a_company_the_user_is_not_granted_is_never_used(db):
    """S1: a Mocha-only user; the contact is an Employee at Sorento only. The role is asked, not read from Sorento."""
    from app.models.company import UserCompany

    w = make_world(db, slugs=(EDIT,), superadmin=False)
    db.query(UserCompany).filter(UserCompany.user_id == w.user_id, UserCompany.company_id == w.srt).delete()
    db.commit()
    c = dealer(db, w, name="ZZT Sorento Only", customers=[w.cust_a])
    result, _ = screenshot_turn(db, w, [_batch([_unsaid(c, 1)]), answer_("Done.")])
    assert "their current role" not in result.reply_text, result.reply_text
    assert result.reply_text.strip() == f"Owner or employee for {c.name}?", result.reply_text


def test_a_level_from_the_other_company_is_named_as_such_on_the_card(db):
    """S1 wording: a Sorento Employee given Mocha: the card says the role comes from Sorento, not 'current role'."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Srt Employee", customers=[w.cust_a])
    result, _ = screenshot_turn(db, w, [_batch([_unsaid(c, 1)]), answer_("Done.")])
    assert result.pending_action is not None, result.reply_text
    assert "Employee (Mocha), as at Sorento" in result.reply_text, result.reply_text


# ------------------------------------------------------------------ code review of the crew decision


def _tag_owner(db, contact, code):
    from app.services.contact_tag_service import change_tags, owner_tag

    change_tags(db, contact, add=[owner_tag(db, code)], actor_id=None)
    db.commit()


def test_a_business_owner_elsewhere_is_never_made_owner_here_without_being_asked(db):
    """B1: Sorento Business owner, Mocha asked with no role: asked, never promoted to Mocha Business owner."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Srt Owner", customers=[w.cust_a])
    _tag_owner(db, c, "SRT")
    result, _ = screenshot_turn(db, w, [_batch([_unsaid(c, 1)]), answer_("Done.")])
    assert result.pending_action is None, result.reply_text
    assert result.reply_text.strip() == f"Owner or employee for {c.name}?", result.reply_text


def test_a_role_that_changes_before_confirm_is_refused_not_applied(db):
    """B2: the card said Employee (read from the record); the person became owner before confirm: not applied."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    c = dealer(db, w, name="ZZT Drift", customers=[w.cust_b])
    result, _ = screenshot_turn(db, w, [_batch([_unsaid(c, 1)]), answer_("Done.")])
    assert "Employee (Mocha), their current role" in result.reply_text, result.reply_text
    _tag_owner(db, c, "MCH")
    outcome = actions.confirm(db, w.respond_id, result.pending_action["id"], via="console")
    assert outcome.status != "executed", outcome
    assert "role changed" in str(outcome.steps).lower(), outcome.steps


def test_answering_a_single_grant_question_gives_the_card(db):
    """S1: 'give 01x mocha access' -> 'Owner or employee for X?' -> 'employee' -> a card for Mocha."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Single Answer")
    args = {k: v for k, v in _unsaid(c, 1).items() if k != "row"}
    first, _ = screenshot_turn(
        db, w, [round_of(tc(GRANT, args, "g1")), answer_("Done.")],
        text_=f"give {local(c.phone_number)} mocha access", images=False,
    )
    assert first.reply_text.strip() == f"Owner or employee for {c.name}?", first.reply_text
    second, _ = screenshot_turn(
        db, w, [round_of(tc(GRANT, {**args, "role": "employee", "access_as_written": "employee"}, "g2")), answer_("Done.")], text_="employee",
        images=False,
    )
    assert second.pending_action is not None, second.reply_text
    assert "add company Mocha" in str(second.pending_action["lines"]), second.pending_action


def test_the_question_beside_a_not_changed_row_has_no_contradicting_closing_line(db):
    """S3: the tables follow the question without 'Nothing can change yet'."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Ask Me")
    rows = [_unsaid(c, 1), {**_unsaid(c, 2), "phone": "12345", "name": "ZZT Bad Phone"}]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert result.reply_text.startswith(f"Owner or employee for {c.name}?"), result.reply_text
    assert 'Phone "12345" is not a Malaysian mobile number.' in result.reply_text
    assert "Nothing can change yet" not in result.reply_text, result.reply_text


def test_a_name_read_from_a_picture_cannot_become_a_link_in_the_question(db):
    """S4: the question's names are cleaned like table cells."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Plain")
    row = {**_unsaid(c, 1), "name": "ZZT [click](http://zzt.invalid)"}
    result, _ = screenshot_turn(db, w, [_batch([row]), answer_("Done.")])
    assert "[click]" not in result.reply_text and "](" not in result.reply_text, result.reply_text


# ------------------------------------------------------------------ code review round 2


def test_both_companies_asked_never_promote_an_owner_of_one_to_owner_of_the_other(db):
    """Review B1 (two companies): a Sorento Business owner given Sorento AND Mocha with no role is asked."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Two Co Owner", customers=[w.cust_a])
    _tag_owner(db, c, "SRT")
    row = _unsaid(c, 1, companies=("SRT", "MCH"))
    result, _ = screenshot_turn(db, w, [_batch([row]), answer_("Done.")],
                                text_="Please grant them sorento and mocha access to the chatbot")
    assert result.pending_action is None, result.reply_text
    assert result.reply_text.strip() == f"Owner or employee for {c.name}?", result.reply_text


def test_an_employee_of_one_company_given_both_stays_employee(db):
    w = make_world(db)
    c = dealer(db, w, name="ZZT Two Co Employee", customers=[w.cust_a])
    row = _unsaid(c, 1, companies=("SRT", "MCH"))
    result, _ = screenshot_turn(db, w, [_batch([row]), answer_("Done.")],
                                text_="Please grant them sorento and mocha access to the chatbot")
    assert result.pending_action is not None, result.reply_text
    assert "Employee (Sorento, Mocha)" in result.reply_text, result.reply_text


def test_the_question_beside_a_row_waiting_for_a_pick_keeps_the_pick_instruction(db):
    """Review S-a: only the 'Nothing can change yet' line goes; a pick's instruction stays."""
    from app.services.chatbot.agent.batch import CHOICE_TAIL

    w = make_world(db)
    twin = w.twin1.customer_name
    ask = dealer(db, w, name="ZZT Ask Beside")
    pick = dealer(db, w, name="ZZT Pick Beside")
    rows = [
        _unsaid(ask, 1, companies=("SRT",)),
        {**_unsaid(pick, 2, companies=("SRT",)), "role": "employee", "customer_names": [twin]},
    ]
    result, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_=f"sorento access, employee at {twin}")
    assert result.reply_text.startswith(f"Owner or employee for {ask.name}?"), result.reply_text
    assert "Needs your choice" in result.reply_text, result.reply_text
    assert CHOICE_TAIL in result.reply_text, result.reply_text


def test_an_own_scope_user_reads_a_level_only_where_the_contact_has_their_own_account(db):
    """Security nit: linked to the user's own Mocha account only, holding the Sorento owner tag; a Sorento row with the
    user's own Sorento account never reads the Sorento level the Dealer access screen would not show them."""
    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    c = dealer(db, o.w, name="ZZT Own Mocha Link", customers=[o.w.cust_b])
    _tag_owner(db, c, "SRT")
    row = {**_unsaid(c, 1, companies=("SRT",)), "customer_codes": [o.w.cust_a.customer_code]}
    result, _ = screenshot_turn(db, o.w, [_batch([row]), answer_("Done.")], text_="grant them sorento access")
    assert "Business owner" not in result.reply_text, result.reply_text
    # Nor is Employee carried from Mocha over an owner tag the user cannot see (review round 2 S1): asked.
    assert "as at Mocha" not in result.reply_text, result.reply_text
    assert result.reply_text.strip() == f"Owner or employee for {c.name}?", result.reply_text


# ------------------------------------------------------------------ crew pass 4 (live F14c on 4aa6eb98)


FIND = "crm_contacts_find"
UPDATE = "crm_contact_access_update"


def _no_access(db, w, name):
    """A contact with no dealer access: no access type, no company, no account, AI replies off."""
    c = dealer(db, w, name=name, types=(), companies=())
    return c


def test_ai_replies_on_for_a_contact_without_dealer_access_routes_to_the_grant_question(db):
    """Crew pass 4: the model read 'access to the chatbot' as the AI replies switch and proposed 'AI replies off ->
    on' for people with no dealer access. The switch answers the model (never the user) that such a person is given
    access through the grant, and the grant asks the company and role."""
    w = make_world(db)
    a, b = _no_access(db, w, "ZZT New One"), _no_access(db, w, "ZZT New Two")
    phones = [local(a.phone_number), local(b.phone_number)]

    def update_both(messages):
        found = [m for m in messages if m.get("role") == "tool"][-1]["content"]
        import json as _json

        ids = [r["contact_id"] for r in _json.loads(found)["data"]]
        return round_of(*[tc(UPDATE, {"contact_id": i, "chatbot_allowed": True}, f"u{n}") for n, i in enumerate(ids)])

    def grant_after_guidance(messages):
        tool_texts = " ".join(str(m.get("content")) for m in messages if m.get("role") == "tool")
        assert "crm_contact_grant" in tool_texts, "the switch did not point the model at the grant"
        rows = [_unsaid(c, n, companies=()) for n, c in enumerate((a, b), 1)]
        return _batch(rows, "b9")

    script = [round_of(tc(FIND, {"phones": phones}, "f1")), update_both, grant_after_guidance, answer_("Done.")]
    result, _ = screenshot_turn(db, w, script, text_="Please grant them access to the chatbot")
    assert_plain(result.reply_text)
    assert result.pending_action is None, result.reply_text
    assert "AI replies off -> on" not in result.reply_text, result.reply_text
    assert result.reply_text.strip() == f"Sorento or Mocha, and owner or employee, for {a.name}, {b.name}?", result.reply_text


def test_the_switch_guidance_is_never_the_users_reply(db):
    """If the model stops after the switch's answer, the user gets a plain line, never the tool guidance."""
    w = make_world(db)
    a = _no_access(db, w, "ZZT Stops Here")

    def update(messages):
        import json as _json

        found = [m for m in messages if m.get("role") == "tool"][-1]["content"]
        cid = _json.loads(found)["data"][0]["contact_id"]
        return round_of(tc(UPDATE, {"contact_id": cid, "chatbot_allowed": True}, "u1"))

    script = [round_of(tc(FIND, {"phones": [local(a.phone_number)]}, "f1")), update, answer_("Done."), answer_("Done.")]
    result, _ = screenshot_turn(db, w, script, text_="Please grant them access to the chatbot")
    assert_plain(result.reply_text)
    assert "crm_" not in result.reply_text, result.reply_text
    assert result.pending_action is None
    from app.services.chatbot.agent.loop import TELL_ME_REPLY

    assert result.reply_text.strip() == TELL_ME_REPLY, result.reply_text  # review nit: the plain line, exactly


def test_the_found_nudge_names_the_grant_as_the_way_to_give_access(db):
    """After a lookup with no change yet, the nudge offers both paths: give access (the grant) or change someone who
    has it (the switch); it no longer pushes only the switch."""
    from app.services.chatbot.agent.loop import FOUND_NUDGE

    assert "crm_contact_grant" in FOUND_NUDGE and "crm_contact_access_update" in FOUND_NUDGE


def test_the_answer_to_the_role_question_applies_only_to_the_people_it_named(db):
    """Crew pass 4 addendum: the one-word answer 'employee' was applied to every row; held rows lost their current
    role and a Mocha Business owner was offered as Employee. Held rows keep the role read from their record."""
    w = make_world(db)
    kept = dealer(db, w, name="ZZT Held Employee", customers=[w.cust_b])
    owner = dealer(db, w, name="ZZT Held Owner", customers=[w.cust_b])
    _tag_owner(db, owner, "MCH")
    fresh = dealer(db, w, name="ZZT Asked Fresh")
    rows = [_unsaid(c, n) for n, c in enumerate((kept, owner, fresh), 1)]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert first.reply_text.strip() == f"Owner or employee for {fresh.name}?", first.reply_text

    everyone_employee = [{**r, "role": "employee", "access_as_written": "employee"} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(everyone_employee, "b2"), answer_("Done.")], text_="employee", images=False)
    assert second.pending_action is not None, second.reply_text
    text = " | ".join(second.pending_action["lines"])
    assert f"{kept.name} (existing): Employee (Mocha), their current role" in text, text
    assert f"{owner.name} (existing): Business owner (Mocha), their current role" in text, text
    assert any(fresh.name in line for line in second.pending_action["lines"]), text


def test_an_existing_contact_shows_its_record_name_not_a_misread_from_the_picture(db):
    w = make_world(db)
    c = dealer(db, w, name="ZZT Real Record Name", customers=[w.cust_b])
    row = {**_unsaid(c, 1), "name": "ZZT Misread Name"}
    result, _ = screenshot_turn(db, w, [_batch([row]), answer_("Done.")])
    assert result.pending_action is not None, result.reply_text
    assert c.name in result.reply_text and "ZZT Misread Name" not in result.reply_text, result.reply_text


# ------------------------------------------------------------------ code review of crew pass 4 fixes


def test_a_role_the_user_stated_for_a_held_row_survives_the_answer(db):
    """Review B1(1): 'make X a business owner' held X while Y was asked; the answer 'employee' (the model re-sending
    employee for everyone) never turns X into Employee."""
    w = make_world(db)
    x = dealer(db, w, name="ZZT Said Owner", customers=[w.cust_b])
    y = dealer(db, w, name="ZZT Asked Y")
    rows = [{**_unsaid(x, 1), "role": "owner", "access_as_written": "business owner"}, _unsaid(y, 2)]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="make them mocha, the first a business owner")
    assert first.reply_text.strip() == f"Owner or employee for {y.name}?", first.reply_text
    again = [{**r, "role": "employee", "access_as_written": "employee"} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(again, "b2"), answer_("Done.")], text_="employee", images=False)
    assert second.pending_action is not None, second.reply_text
    text = " | ".join(second.pending_action["lines"])
    assert "Business owner (Mocha)" in next(line for line in second.pending_action["lines"] if x.name in line), text


def test_a_stated_role_of_a_new_person_is_not_asked_again(db):
    """Review B1(2): A stated employee (no role on record), B asked; the answer 'owner' gives the card, A stays
    Employee and is never asked again."""
    w = make_world(db)
    a = dealer(db, w, name="ZZT Said Employee")
    b = dealer(db, w, name="ZZT Asked B")
    rows = [{**_unsaid(a, 1), "role": "employee", "access_as_written": "employee"}, _unsaid(b, 2)]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="mocha, the first is an employee")
    assert first.reply_text.strip() == f"Owner or employee for {b.name}?", first.reply_text
    again = [{**r, "role": "owner", "access_as_written": "owner"} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(again, "b2"), answer_("Done.")], text_="owner", images=False)
    assert second.pending_action is not None, second.reply_text
    lines = second.pending_action["lines"]
    assert "Business owner" not in next(line for line in lines if a.name in line), lines  # never made owner
    assert "Business owner (Mocha)" in next(line for line in lines if b.name in line), lines


def test_a_held_person_the_answer_names_gets_the_stated_role(db):
    """Review B1(3): the answer names the held person by phone with a role: that role applies."""
    w = make_world(db)
    x = dealer(db, w, name="ZZT Named Later", customers=[w.cust_b])
    y = dealer(db, w, name="ZZT Asked Z")
    rows = [_unsaid(x, 1), _unsaid(y, 2)]
    screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    again = [{**rows[0], "role": "owner", "access_as_written": "business owner"},
             {**rows[1], "role": "employee", "access_as_written": "employee"}]
    second, _ = screenshot_turn(
        db, w, [_batch(again, "b2"), answer_("Done.")],
        text_=f"employee, and make {local(x.phone_number)} a business owner at mocha", images=False,
    )
    assert second.pending_action is not None, second.reply_text
    assert "Business owner (Mocha)" in next(line for line in second.pending_action["lines"] if x.name in line)


def test_a_misread_name_from_the_picture_never_reaches_the_answer_turns_card(db):
    """Review B2: the card comes on the answer turn (no picture); record names still win for picture rows."""
    w = make_world(db)
    kept = dealer(db, w, name="ZZT Record Kept", customers=[w.cust_b])
    fresh = dealer(db, w, name="ZZT Record Fresh")
    rows = [{**_unsaid(kept, 1), "name": "ZZT Misread Kept"}, {**_unsaid(fresh, 2), "name": "ZZT Misread Fresh"}]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")])
    assert first.reply_text.strip() == f"Owner or employee for {fresh.name}?", first.reply_text
    again = [{**r, "role": "employee", "access_as_written": "employee"} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(again, "b2"), answer_("Done.")], text_="employee", images=False)
    assert second.pending_action is not None, second.reply_text
    assert "Misread" not in second.reply_text, second.reply_text
    assert kept.name in second.reply_text and fresh.name in second.reply_text


def test_the_switch_guidance_never_shows_when_a_confirm_finds_the_person_lost_access(db):
    """Review S2: a confirm that re-plans an AI replies change after the last link went shows a plain line, never
    the model's guidance."""
    from app.models.access import RespondContactCustomer
    from app.services.chatbot.agent import actions

    w = make_world(db)
    c = dealer(db, w, name="ZZT Lost Link", types=(), companies=(), customers=[w.cust_b])

    def update(messages):
        import json as _json

        cid = _json.loads([m for m in messages if m.get("role") == "tool"][-1]["content"])["data"][0]["contact_id"]
        return round_of(tc(UPDATE, {"contact_id": cid, "chatbot_allowed": True}, "u1"))

    script = [round_of(tc(FIND, {"phones": [local(c.phone_number)]}, "f1")), update, answer_("Done.")]
    result, _ = screenshot_turn(db, w, script, text_="turn on AI replies for them", images=False)
    assert result.pending_action is not None, result.reply_text
    db.query(RespondContactCustomer).filter(RespondContactCustomer.contact_id == c.id).delete()
    db.commit()
    outcome = actions.confirm(db, w.respond_id, result.pending_action["id"], via="console")
    assert "crm_" not in (outcome.reply_text or "") and "crm_" not in str(outcome.steps), outcome


def test_an_own_scope_user_on_a_picture_turn_never_sees_a_strangers_record_name(db):
    """Security should-fix: out-of-scope contact on an attachment turn: typed name (or phone), never contact.name."""
    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    c = dealer(db, o.w, name="ZZT Stranger Record", customers=[o.theirs_m])
    row = {**_unsaid(c, 1), "name": "ZZT Typed Here", "customer_codes": [o.w.cust_b.customer_code]}
    result, _ = screenshot_turn(db, o.w, [_batch([row]), answer_("Done.")], text_="grant them mocha access")
    assert c.name not in result.reply_text, result.reply_text


def test_the_model_cannot_set_the_picture_flag(db):
    """Security should-fix: `_from_attachment` is the loop's; a model row carrying it is refused as unknown."""
    from app.services.chatbot.agent import writes

    problem = writes._args_problem(
        writes.WRITES[GRANT], {"phone": "0190000000", "role": "unknown", "companies": [], "_from_attachment": True}
    )
    assert problem and "_from_attachment" in problem


# ------------------------------------------------------------------ crew re-pass on d65ba470 (revoke)


def _find_then(update_args_for, phones):
    """A script step: read the lookup's ids, then one access update per found contact."""
    def step(messages):
        import json as _json

        found = _json.loads([m for m in messages if m.get("role") == "tool"][-1]["content"])["data"]
        return round_of(*[tc(UPDATE, update_args_for(r), f"u{n}") for n, r in enumerate(found)])

    return [round_of(tc(FIND, {"phones": phones}, "f1")), step]


def test_remove_mocha_access_unlinks_mocha_and_takes_off_the_mocha_owner_level_only(db):
    """Crew re-pass: 'Please remove their mocha access to the chatbot' gave 'AI replies on -> off' while the Mocha
    links and owner tag stayed. Removing a company's access unlinks that company's accounts and takes off its Business
    owner level; the other company's access and AI replies stay."""
    from app.services.chatbot.agent import actions
    from tests.chatbot.agent.test_agent_bulk_grant import state

    w = make_world(db)
    c = dealer(db, w, name="ZZT Both Cos", companies=(w.srt, w.mch), customers=[w.cust_a, w.cust_b])
    c.chatbot_allowed = True
    db.commit()
    _tag_owner(db, c, "MCH")
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, [local(c.phone_number)])
    result, _ = screenshot_turn(db, w, [*script, answer_("Done.")], text_="Please remove their mocha access to the chatbot")
    assert_plain(result.reply_text)
    assert result.pending_action is not None, result.reply_text
    lines = " | ".join(result.pending_action["lines"])
    assert "AI replies on -> off" not in lines, lines
    assert w.cust_b.customer_code in lines and "Employee" in lines, lines
    outcome = actions.confirm(db, w.respond_id, result.pending_action["id"], via="console")
    assert outcome.status == "executed", outcome
    after = state(db, c.phone_number)
    assert after["links"] == [str(w.cust_a.id)], after
    assert after["chatbot_allowed"] is True
    from app.services.contact_tag_service import owner_codes_by_contact

    assert "MCH" not in owner_codes_by_contact(db, [str(c.id)], ["MCH"]).get(str(c.id), set())
    assert after["companies"] == [str(w.srt)], after  # the Mocha company itself is taken off


def test_removing_the_only_companys_access_turns_ai_replies_off_with_the_last_link(db):
    w = make_world(db)
    c = dealer(db, w, name="ZZT Mocha Only", companies=(w.mch,), customers=[w.cust_b])
    c.chatbot_allowed = True  # as every dev contact linked to a Mocha account (crew re-pass fixture)
    db.commit()
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, [local(c.phone_number)])
    result, _ = screenshot_turn(db, w, [*script, answer_("Done.")], text_="remove their mocha access", images=False)
    assert result.pending_action is not None, result.reply_text
    lines = " | ".join(result.pending_action["lines"])
    assert "AI replies on -> off" in lines and w.cust_b.customer_code in lines, lines


def test_removing_a_company_the_person_does_not_have_says_so_plainly(db):
    w = make_world(db)
    c = dealer(db, w, name="ZZT Srt Only", companies=(w.srt,), customers=[w.cust_a])
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, [local(c.phone_number)])
    result, _ = screenshot_turn(db, w, [*script, answer_("Done."), answer_("Done.")], text_="remove their mocha access",
                                images=False)
    assert_plain(result.reply_text)
    assert result.pending_action is None
    assert "has no Mocha access" in result.reply_text, result.reply_text


def test_the_tools_let_the_model_name_the_company_to_remove(db):
    """The lookup says which company each account is in, and the update takes the company to remove: the model judges
    the meaning and passes structured values (no word rules)."""
    from app.services.chatbot.agent import writes

    w = make_world(db)
    c = dealer(db, w, name="ZZT Lookup Co", companies=(w.mch,), customers=[w.cust_b])
    props = writes.WRITES[UPDATE].schema["function"]["parameters"]["properties"]
    assert "remove_companies" in props
    from tests.chatbot.agent.test_agent_bulk_grant import ctx_of

    out = writes.run_user_read(db, ctx_of(db, w), FIND, {"phones": [local(c.phone_number)]}, set())
    assert out.data[0]["accounts"][0]["company"] == "MCH", out.data


def test_a_user_cannot_remove_a_company_they_are_not_granted(db):
    """Security B1: an edit_own salesperson granted Sorento only cannot take a person's Mocha access away."""
    from app.models.company import UserCompany
    from tests.chatbot.agent.test_agent_bulk_grant import state
    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    db.query(UserCompany).filter(UserCompany.user_id == o.w.user_id, UserCompany.company_id == o.w.mch).delete()
    db.commit()
    c = dealer(db, o.w, name="ZZT Keep Mocha", companies=(o.w.srt, o.w.mch), customers=[o.w.cust_a])
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, [local(c.phone_number)])
    result, _ = screenshot_turn(db, o.w, [*script, answer_("Done."), answer_("Done.")], text_="remove their mocha access",
                                images=False)
    assert result.pending_action is None, result.reply_text
    assert str(o.w.mch) in state(db, c.phone_number)["companies"]


def test_removing_a_company_is_audited(db):
    """Security S2: the removed company shows in the audit row of the change."""
    from app.models.audit import AuditLog
    from app.services.chatbot.agent import actions

    w = make_world(db)
    c = dealer(db, w, name="ZZT Audit Co", companies=(w.srt, w.mch), customers=[w.cust_a])
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, [local(c.phone_number)])
    result, _ = screenshot_turn(db, w, [*script, answer_("Done.")], text_="remove their mocha access", images=False)
    assert result.pending_action is not None, result.reply_text
    actions.confirm(db, w.respond_id, result.pending_action["id"], via="console")
    rows = db.query(AuditLog).filter(AuditLog.entity_id == str(c.id), AuditLog.event == "contact.access_agent").all()
    assert any("Companies" in (r.old_values or {}) for r in rows), [(r.old_values, r.new_values) for r in rows]


# ------------------------------------------------------------------ code review of the revoke change


def _remove_mocha(db, w, c, text_="remove their mocha access"):
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, [local(c.phone_number)])
    result, _ = screenshot_turn(db, w, [*script, answer_("Done."), answer_("Done.")], text_=text_, images=False)
    return result


def test_an_owner_of_both_companies_losing_mocha_reads_as_still_owner_of_sorento(db):
    """Review blocker 1: the card said 'Business owner (Mocha, Sorento) -> Employee' while Sorento ownership stays."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Owns Both", companies=(w.srt, w.mch), customers=[w.cust_a, w.cust_b])
    _tag_owner(db, c, "SRT")
    _tag_owner(db, c, "MCH")
    result = _remove_mocha(db, w, c)
    assert result.pending_action is not None, result.reply_text
    lines = " | ".join(result.pending_action["lines"])
    assert "-> Business owner (Sorento)" in lines and "-> Employee" not in lines, lines


def test_a_person_left_with_no_company_cannot_get_ai_replies_on_alone(db):
    """Review 2: after Mocha (their only company) is removed, AI replies on alone goes to the grant's question."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    c = dealer(db, w, name="ZZT Left Bare", companies=(w.mch,), customers=[w.cust_b])
    c.chatbot_allowed = True
    db.commit()
    result = _remove_mocha(db, w, c)
    assert actions.confirm(db, w.respond_id, result.pending_action["id"], via="console").status == "executed"
    script = _find_then(lambda r: {"contact_id": r["contact_id"], "chatbot_allowed": True}, [local(c.phone_number)])
    again, _ = screenshot_turn(db, w, [*script, answer_("Done."), answer_("Done.")], text_="turn their AI on", images=False)
    assert again.pending_action is None, again.reply_text
    assert "AI replies off -> on" not in again.reply_text


def test_removing_mocha_takes_off_legacy_mocha_owner_types_too(db):
    """Review 3: a legacy contact (owner types, no tag) loses the Mocha owner types with the company."""
    from app.services.chatbot.agent import actions
    from tests.chatbot.agent.test_agent_bulk_grant import state

    w = make_world(db)
    c = dealer(db, w, name="ZZT Legacy Owner", types=("end_user", "mocha_dealer"), companies=(w.srt, w.mch),
               customers=[w.cust_a, w.cust_b])
    result = _remove_mocha(db, w, c)
    assert result.pending_action is not None, result.reply_text
    assert actions.confirm(db, w.respond_id, result.pending_action["id"], via="console").status == "executed"
    assert "mocha_dealer" not in state(db, c.phone_number)["types"]


def test_an_own_scope_user_can_restore_a_link_their_company_removal_took(db):
    """Review 6: the unlinks of a company removal count as the user's own, so they may restore them."""
    from app.services.chatbot.agent import actions

    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    c = dealer(db, o.w, name="ZZT Restore Me", companies=(o.w.mch,), customers=[o.w.cust_b])
    result = _remove_mocha(db, o.w, c)
    assert result.pending_action is not None, result.reply_text
    assert actions.confirm(db, o.w.respond_id, result.pending_action["id"], via="console").status == "executed"
    relink = [round_of(tc(UPDATE, {"contact_id": str(c.id), "link_customer_ids": [str(o.w.cust_b.id)]}, "r1")),
              answer_("Done."), answer_("Done.")]
    from app.services.chatbot.agent.loop import run_agent_turn

    # The ids come from the page the user has open (the panel's seen ids): the contact is out of scope for a lookup now.
    again = run_agent_turn(
        db, contact_respond_id=o.w.respond_id, text=f"restore {local(c.phone_number)}",
        provider=Provider(relink, dealer_access=True), mcp_call=_no_mcp, catalog={},
        seed_ids=[str(c.id), str(o.w.cust_b.id)],
    )
    assert "only restore a link you removed" not in again.reply_text, again.reply_text
    assert again.pending_action is not None, again.reply_text


def test_an_own_scope_user_cannot_remove_a_company_another_account_reaches(db):
    """Review 7: the own-scope refusal when another account also reaches the person."""
    from tests.chatbot.agent.test_agent_bulk_grant import state
    from tests.chatbot.agent.test_dealer_access_agent import own_world

    o = own_world(db)
    c = dealer(db, o.w, name="ZZT Shared Mocha", companies=(o.w.mch,), customers=[o.w.cust_b, o.theirs_m])
    result = _remove_mocha(db, o.w, c)
    assert result.pending_action is None, result.reply_text
    assert "another account" in result.reply_text, result.reply_text
    assert str(o.w.mch) in state(db, c.phone_number)["companies"]


# ------------------------------------------------------------------ crew re-pass on b549042d (F14c regression)


def _f14c_people(db, w):
    """Group 1: hold a role (Sorento employees by account) and need only the company; group 2: new, need both."""
    g1 = [dealer(db, w, name=f"ZZT Group One {i}", customers=[w.cust_a]) for i in range(2)]
    g2 = [dealer(db, w, name=f"ZZT Group Two {i}") for i in range(2)]
    return g1, g2


def test_f14c_answering_only_the_company_leaves_the_role_question_open(db):
    """Crew re-pass b549042d: 'Mocha' answered only the company; the model filled employee for the people still
    without a role and the card defaulted them. A role counts only when the user's own words give it (the model's
    copy in access_as_written must be in the message), as the dealer name and company already must be."""
    w = make_world(db)
    g1, g2 = _f14c_people(db, w)
    people = [*g1, *g2]
    rows = [_unsaid(c, n, companies=()) for n, c in enumerate(people, 1)]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them access to the chatbot")
    assert "Sorento or Mocha, and owner or employee, for" in first.reply_text, first.reply_text
    assert first.pending_action is None

    guessed = [
        {**r, "companies": ["MCH"], **({"role": "employee", "access_as_written": "employee"} if n > 2 else {})}
        for n, r in enumerate(rows, 1)
    ]
    second, _ = screenshot_turn(db, w, [_batch(guessed, "b2"), answer_("Done.")], text_="Mocha", images=False)
    assert second.pending_action is None, second.reply_text
    assert second.reply_text.strip() == f"Owner or employee for {g2[0].name}, {g2[1].name}?", second.reply_text

    answered = [{**r, "role": "employee", "access_as_written": "employee"} if n > 2 else r for n, r in enumerate(guessed, 1)]
    third, _ = screenshot_turn(db, w, [_batch(answered, "b3"), answer_("Done.")], text_="employee", images=False)
    assert third.pending_action is not None, third.reply_text
    for c in people:
        assert c.name in third.reply_text, third.reply_text


def test_f14c_a_role_the_model_sends_without_any_words_is_not_taken(db):
    """The same answer turn with the role sent and no access word at all: still asked, never defaulted."""
    w = make_world(db)
    _, g2 = _f14c_people(db, w)
    rows = [_unsaid(c, n, companies=()) for n, c in enumerate(g2, 1)]
    screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them access to the chatbot")
    guessed = [{**r, "companies": ["MCH"], "role": "employee"} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(guessed, "b2"), answer_("Done.")], text_="Mocha", images=False)
    assert second.pending_action is None, second.reply_text
    assert second.reply_text.strip() == f"Owner or employee for {g2[0].name}, {g2[1].name}?", second.reply_text


def test_f14c_then_revoke_in_one_conversation(db):
    """Crew: the revoke fix must not break F14c. Grant through the questions, confirm, then remove Mocha access."""
    from app.services.chatbot.agent import actions
    from tests.chatbot.agent.test_agent_bulk_grant import state

    w = make_world(db)
    g1, g2 = _f14c_people(db, w)
    people = [*g1, *g2]
    rows = [_unsaid(c, n, companies=()) for n, c in enumerate(people, 1)]
    screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them access to the chatbot")
    mocha = [{**r, "companies": ["MCH"]} for r in rows]
    screenshot_turn(db, w, [_batch(mocha, "b2"), answer_("Done.")], text_="Mocha", images=False)
    answered = [{**r, "role": "employee", "access_as_written": "employee"} if n > 2 else r for n, r in enumerate(mocha, 1)]
    card, _ = screenshot_turn(db, w, [_batch(answered, "b3"), answer_("Done.")], text_="employee", images=False)
    assert card.pending_action is not None, card.reply_text
    assert actions.confirm(db, w.respond_id, card.pending_action["id"], via="console").status in ("executed", "partial")

    phones = [local(c.phone_number) for c in people]
    revoke = _find_then(lambda r: {"contact_id": r["contact_id"], "remove_companies": ["MCH"]}, phones)
    result, _ = screenshot_turn(db, w, [*revoke, answer_("Done.")], text_="Please remove their mocha access to the chatbot")
    assert result.pending_action is not None, result.reply_text
    lines = " | ".join(result.pending_action["lines"])
    assert "Mocha access removed" in lines and "AI replies on -> off\n" not in lines, lines
    assert actions.confirm(db, w.respond_id, result.pending_action["id"], via="console").status in ("executed", "partial")
    for c in people:
        assert str(w.mch) not in state(db, c.phone_number)["companies"], c.name


def test_f14c_a_business_owner_asked_only_the_company_stays_owner(db):
    """Crew re-pass b549042d: the Mocha Business owner was offered as Employee after 'Mocha'. Asked only the company,
    the record decides the role."""
    w = make_world(db)
    owner = dealer(db, w, name="ZZT Owner Asked Co", customers=[w.cust_b])
    _tag_owner(db, owner, "MCH")
    row = _unsaid(owner, 1, companies=())
    first, _ = screenshot_turn(db, w, [_batch([row]), answer_("Done.")], text_="Please grant them access to the chatbot")
    # No company named yet: Business owner is never carried, so both are asked (as crew's live turn 1 showed).
    assert first.reply_text.strip() == f"Sorento or Mocha, and owner or employee, for {owner.name}?", first.reply_text
    guessed = {**row, "companies": ["MCH"], "role": "employee", "access_as_written": "employee"}
    second, _ = screenshot_turn(db, w, [_batch([guessed], "b2"), answer_("Done.")], text_="Mocha", images=False)
    assert second.pending_action is not None, second.reply_text
    assert "Business owner (Mocha), their current role" in " | ".join(second.pending_action["lines"]), second.pending_action


def test_a_role_stated_in_the_request_survives_an_answer_that_gives_only_the_company(db):
    """Review blocker 1: 'grant them owner access' (no company) -> 'Sorento or Mocha?' -> 'Mocha': the role the user
    already gave is kept, never asked again."""
    w = make_world(db)
    people = [dealer(db, w, name=f"ZZT Said Owner {i}") for i in range(2)]
    rows = [{**_unsaid(c, n, companies=()), "role": "owner", "access_as_written": "owner"} for n, c in enumerate(people, 1)]
    first, _ = screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them owner access to the chatbot")
    assert first.reply_text.strip() == f"Sorento or Mocha for {people[0].name}, {people[1].name}?", first.reply_text
    mocha = [{**r, "companies": ["MCH"]} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(mocha, "b2"), answer_("Done.")], text_="Mocha", images=False)
    assert second.pending_action is not None, second.reply_text
    assert all("Business owner (Mocha)" in line for line in second.pending_action["lines"]), second.pending_action


def test_a_single_grant_answer_that_gives_only_the_company_never_decides_the_role(db):
    """Review blocker 2: the single-grant path of the role check."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Single Co Only")
    args = {k: v for k, v in _unsaid(c, 1, companies=()).items() if k != "row"}
    first, _ = screenshot_turn(db, w, [round_of(tc(GRANT, args, "g1")), answer_("Done.")],
                               text_=f"give {local(c.phone_number)} chatbot access", images=False)
    assert first.reply_text.strip() == f"Sorento or Mocha, and owner or employee, for {c.name}?", first.reply_text
    guessed = {**args, "companies": ["MCH"], "role": "employee", "access_as_written": "employee"}
    second, _ = screenshot_turn(db, w, [round_of(tc(GRANT, guessed, "g2")), answer_("Done.")], text_="Mocha", images=False)
    assert second.pending_action is None, second.reply_text
    assert second.reply_text.strip() == f"Owner or employee for {c.name}?", second.reply_text


def test_a_plural_answer_counts_as_the_users_word(db):
    """Review should-fix: 'Mocha, both owners' with the model copying 'owner' is the user's word."""
    w = make_world(db)
    people = [dealer(db, w, name=f"ZZT Plural {i}") for i in range(2)]
    rows = [_unsaid(c, n, companies=()) for n, c in enumerate(people, 1)]
    screenshot_turn(db, w, [_batch(rows), answer_("Done.")], text_="Please grant them access to the chatbot")
    answered = [{**r, "companies": ["MCH"], "role": "owner", "access_as_written": "owner"} for r in rows]
    second, _ = screenshot_turn(db, w, [_batch(answered, "b2"), answer_("Done.")], text_="Mocha, both owners", images=False)
    assert second.pending_action is not None, second.reply_text


def test_a_single_grant_role_stated_in_the_request_survives_the_company_answer(db):
    """Review should-fix 1: 'give <phone> owner access' -> 'Sorento or Mocha?' -> 'Mocha' gives the card."""
    w = make_world(db)
    c = dealer(db, w, name="ZZT Single Said Owner")
    args = {**{k: v for k, v in _unsaid(c, 1, companies=()).items() if k != "row"}, "role": "owner",
            "access_as_written": "owner"}
    first, _ = screenshot_turn(db, w, [round_of(tc(GRANT, args, "g1")), answer_("Done.")],
                               text_=f"give {local(c.phone_number)} owner access", images=False)
    assert first.reply_text.strip() == f"Sorento or Mocha for {c.name}?", first.reply_text
    second, _ = screenshot_turn(db, w, [round_of(tc(GRANT, {**args, "companies": ["MCH"]}, "g2")), answer_("Done.")],
                                text_="Mocha", images=False)
    assert second.pending_action is not None, second.reply_text


def test_a_very_short_copied_word_must_be_a_whole_word():
    """Review should-fix 2: a one-letter copy ('e', 'o') never matches inside another word."""
    from app.services.chatbot.agent.batch import role_in_users_words

    row = {"role": "employee", "access_as_written": "e"}
    assert role_in_users_words(row, "Mocha, everyone")["role"] == "unknown"
    assert role_in_users_words({"role": "owner", "access_as_written": "o"}, "only Mocha")["role"] == "unknown"
    assert role_in_users_words({"role": "employee", "access_as_written": "E"}, "Mocha, E")["role"] == "employee"


def test_a_stated_role_refills_when_the_model_drops_it():
    """Review nit: the request's role comes back when the answer turn's row lost it."""
    from app.services.chatbot.agent.batch import role_in_users_words

    assert role_in_users_words({"role": "unknown", "access_as_written": ""}, "Mocha", "owner")["role"] == "owner"
