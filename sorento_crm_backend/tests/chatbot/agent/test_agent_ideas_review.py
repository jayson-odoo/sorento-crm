"""AGENTIC-IDEATE review round (AC-RV-1 to AC-RV-10), red tests.

Same harness as test_agent_writes_ideas.py (FakeSS at the httpx boundary, blank Postgres schema, a scripted
provider through `run_agent_turn`). Behaviour that does not exist yet is reached at call time.

Row key assumed for "each row says whether it is a test idea": a boolean `is_test` on every row of the
`crm_ideas_list` result (`out.data["ideas"]`).
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.models.chatbot_turn import ChatbotTurn
from tests.chatbot.agent.test_agent_asked_back_flag import answer_asking
from tests.chatbot.agent.test_agent_writes import answer_, make_world as ask_world, proposal_script, round_of, tc
from tests.chatbot.agent.test_agent_writes_ideas import (  # noqa: F401 - fixtures and helpers
    BOARD_VIEW, CREATE, CREATE_PATH, CRM, FIELDS, IDEA, IDEA_PATH, LIST, MANAGE, PROBLEM, SIGNING_SECRET, UPDATE,
    UUID_RE, Idea, _fresh_token_cache, _listeners, confirm, create_through, db, idea_body, leaks, list_ideas,
    make_world, operator_with, patches, posts, propose, ss, store,
)
from tests.chatbot.agent.test_agent_writes_round1 import decide_from_view, go
from jose import jwt


# ------------------------------------------------------------------ AC-RV-1 the link survives a chat confirm


def chat_confirm_reply(db, ss, model_reply):
    """Turn 1 proposes a create, turn 2 confirms through `confirm_action`; `model_reply(messages, tools)` is the
    model's final answer after the tool result. Returns (reply text, idea id)."""
    w = make_world(db)
    idea_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": idea_id, "idea_number": "IDEA-0184", "status": "captured", "title": "t"},
    )
    first, _ = go(
        db, w, [round_of(tc(CREATE, dict(FIELDS), "c1")), answer_("I have prepared the idea.")], text_="an idea"
    )
    assert first.pending_action is not None
    second, _ = go(db, w, [decide_from_view({}), model_reply], text_="yes")
    assert len(posts(ss, CREATE_PATH)) == 1
    return second.reply_text, idea_id


def last_tool_reply_text(messages):
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    body = json.loads(tool_msgs[-1]["content"])
    assert body["status"] == "ok", body
    return body["data"]["reply_text"]


def test_AC_RV_1_a_model_that_writes_its_own_text_still_gets_the_working_link_once(db, ss):
    reply, idea_id = chat_confirm_reply(db, ss, lambda messages, tools: answer_("Done, your idea is logged."))
    assert reply.count(f"{CRM}/ideas/{idea_id}") == 1, reply
    assert "/(id)" not in reply


def test_AC_RV_1_a_model_that_repeats_the_tools_text_word_for_word_leaves_no_broken_link(db, ss):
    reply, idea_id = chat_confirm_reply(
        db, ss, lambda messages, tools: answer_(last_tool_reply_text(messages))
    )
    assert reply.count(f"{CRM}/ideas/{idea_id}") == 1, reply
    assert "/(id)" not in reply


def test_AC_RV_1_a_url_with_an_id_written_by_the_model_is_dropped_whole(db, ss):
    other = str(uuid.uuid4())
    reply, idea_id = chat_confirm_reply(
        db, ss, lambda messages, tools: answer_(f"Logged, see {CRM}/ideas/{other} for it.")
    )
    assert reply.count(f"{CRM}/ideas/{idea_id}") == 1, reply
    assert other not in reply and "/(id)" not in reply


def test_AC_RV_1_a_bare_id_in_model_text_still_reads_id(db, ss):
    bare = str(uuid.uuid4())
    reply, idea_id = chat_confirm_reply(db, ss, lambda messages, tools: answer_(f"Idea {bare} is saved."))
    assert "(id)" in reply
    assert bare not in reply
    assert reply.count(f"{CRM}/ideas/{idea_id}") == 1, reply


# ------------------------------------------------------------------ AC-RV-2 no note, no added line


def test_AC_RV_2_a_chat_confirm_of_a_write_with_no_note_adds_no_line(db):
    w = ask_world(db)
    first, _ = go(db, w, proposal_script(w.asks))
    assert first.pending_action is not None
    second, _ = go(db, w, [decide_from_view({}), answer_("Done, the ask is updated.")], text_="yes go ahead")
    assert second.reply_text == "Done, the ask is updated."


# ------------------------------------------------------------------ AC-RV-3 the proposal shows full values

# The shared cleaners (`normalise_field_value`, `normalise_title`) capitalise and cut a title to 8 words, and the
# card must show what will be sent, so the fixtures start with a capital and the title has at most 8 words.
LONG = "Word " + "word " * 239  # 1200 characters, first letter a capital
LONG = LONG.strip()
TITLE_8 = "Shorter stock list on phones please now"  # 7 words


def long_args(*, with_id=False):
    args = {
        "problem": LONG + " P",
        "title": TITLE_8,
        "desired_outcome": LONG + " O",
        "current_workaround": LONG + " W",
        "use_cases": [LONG + " U1", "Short one"],
    }
    if with_id:
        args["idea_id"] = IDEA
    return args


def test_AC_RV_3_a_create_shows_every_given_value_whole(db, ss):
    w = make_world(db)
    args = long_args()
    res, step = propose(db, w, CREATE, args)
    assert res.status == "proposed", res.message
    for key in ("title", "problem", "desired_outcome", "current_workaround"):
        assert args[key] in step["summary"], key
    assert args["use_cases"][0] in step["summary"] and "Short one" in step["summary"]


def test_AC_RV_3_an_update_shows_every_new_value_whole(db, ss):
    w = make_world(db)
    Idea(ss)
    args = long_args(with_id=True)
    res, step = propose(db, w, UPDATE, args, seen=[IDEA])
    assert res.status == "proposed", res.message
    for key in ("title", "problem", "desired_outcome", "current_workaround"):
        assert args[key] in step["summary"], key
    assert args["use_cases"][0] in step["summary"]


def received_values(body):
    values = []
    for value in body.values():
        values += [v for v in value if isinstance(v, str)] if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, str) and len(v) > 3]


def test_AC_RV_3_every_value_the_fake_receives_on_a_create_is_in_the_proposal(db, ss):
    w = make_world(db)
    steps, row = store(db, w, [(CREATE, long_args())])
    confirm(db, w, row)
    (call,) = posts(ss, CREATE_PATH)
    sent = [v for k, v in call["json"].items() if k in ("problem", "title", "desired_outcome", "current_workaround")]
    sent += list(call["json"]["use_cases"])
    assert len(sent) == 6
    for value in sent:
        assert value in steps[0]["summary"], value[:40]


def test_AC_RV_3_every_value_the_fake_receives_on_an_update_is_in_the_proposal(db, ss):
    w = make_world(db)
    Idea(ss)
    steps, row = store(db, w, [(UPDATE, long_args(with_id=True))], seen=[IDEA])
    confirm(db, w, row)
    (call,) = patches(ss)
    sent = received_values(call["json"])
    assert len(sent) >= 5, call["json"]
    for value in sent:
        assert value in steps[0]["summary"], value[:40]


def test_AC_RV_3_a_twenty_word_title_shows_the_same_first_words_that_are_sent(db, ss):
    w = make_world(db)
    title = " ".join(["W01"] + [f"w{n:02d}" for n in range(2, 21)])
    steps, row = store(db, w, [(CREATE, {"problem": PROBLEM, "title": title})])
    confirm(db, w, row)
    (call,) = posts(ss, CREATE_PATH)
    sent_title = call["json"]["title"]
    assert sent_title == " ".join(title.split()[:8])
    assert sent_title in steps[0]["summary"]
    assert "w09" not in steps[0]["summary"]


# ------------------------------------------------------------------ AC-RV-4 the list is live

class LiveIdea:
    """An ss idea that GET serves live and PATCH edits, for a created test idea."""

    def __init__(self, ss, idea_id, *, problem=PROBLEM, **over):
        self.path = f"/embed/ideas/{idea_id}"
        self.state = idea_body(id=idea_id, problem=problem, **over)
        ss.routes[("GET", self.path)] = self.serve
        ss.routes[("PATCH", self.path)] = self.patch

    def serve(self, request):
        return httpx.Response(200, json=dict(self.state), request=request)

    def patch(self, request):
        body = json.loads(request.read())
        self.state.update({k: v for k, v in body.items()})
        return httpx.Response(200, json=dict(self.state), request=request)


def made_idea(db, w, ss, title="Old title zzt", number="IDEA-0184"):
    idea_id = create_through(db, w, ss, title=title, number=number, idea_id=str(uuid.uuid4()))
    return idea_id, LiveIdea(ss, idea_id, title=title, ideaNumber=number)


def edit_title(db, w, idea_id, title):
    _, row = store(db, w, [(UPDATE, {"idea_id": idea_id, "title": title})], seen=[idea_id])
    assert confirm(db, w, row).steps[0]["status"] == "done"


def rows_of(out):
    return out.data["ideas"]


def test_AC_RV_4_after_an_edit_the_list_shows_the_new_title(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss)
    edit_title(db, w, idea_id, "New title zzt")
    out, _ = list_ideas(db, w)
    body = json.dumps(out.data)
    assert "New title zzt" in body and "Old title zzt" not in body


def test_AC_RV_4_search_matches_the_live_title(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss)
    edit_title(db, w, idea_id, "Brand new heading zzt")
    out, _ = list_ideas(db, w, {"search": "brand new heading"})
    assert [r["id"] for r in rows_of(out)] == [idea_id]


def test_AC_RV_4_search_matches_a_word_only_in_the_problem(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss)
    out, _ = list_ideas(db, w, {"search": "scroll"})
    assert [r["id"] for r in rows_of(out)] == [idea_id]
    out, _ = list_ideas(db, w, {"search": "nothing matches this zzz"})
    assert rows_of(out) == []


def test_AC_RV_4_a_404_on_one_idea_skips_that_row_only(db, ss):
    w = make_world(db)
    gone, _ = made_idea(db, w, ss, title="Gone idea zzt", number="IDEA-0401")
    kept, _ = made_idea(db, w, ss, title="Kept idea zzt", number="IDEA-0402")
    ss.route("GET", f"/embed/ideas/{gone}", status=404, json_body={"error": {"code": "not_found", "message": "x"}})
    out, _ = list_ideas(db, w)
    assert out.status == "ok"
    assert [r["id"] for r in rows_of(out)] == [kept]


def test_AC_RV_4_a_row_that_is_not_mine_is_skipped(db, ss):
    w = make_world(db)
    theirs, live = made_idea(db, w, ss, title="Not mine zzt", number="IDEA-0411")
    mine, _ = made_idea(db, w, ss, title="Mine zzt", number="IDEA-0412")
    live.state["isMine"] = False
    out, _ = list_ideas(db, w)
    assert [r["id"] for r in rows_of(out)] == [mine]


def test_AC_RV_4_a_500_on_the_live_read_is_the_typed_error(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss)
    ss.route("GET", f"/embed/ideas/{idea_id}", status=500, json_body={"error": {"code": "boom", "message": "x"}})
    out, _ = list_ideas(db, w)
    assert out.status == "error"
    assert not leaks(out.message, json.dumps(out.data, default=str))


def test_AC_RV_4_test_ideas_come_first_even_when_ss_returns_a_full_list(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss)
    ss.route(
        "GET", "/embed/ideas",
        json_body=[
            {"id": str(uuid.uuid4()), "ideaNumber": f"IDEA-{n:04d}", "title": f"Board idea {n}", "isMine": True}
            for n in range(1000, 1050)
        ],
    )
    out, _ = list_ideas(db, w)
    rows = rows_of(out)
    assert rows[0]["id"] == idea_id, [r.get("id") for r in rows[:3]]


def test_AC_RV_4_each_row_says_whether_it_is_a_test_idea(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss)
    board_id = str(uuid.uuid4())
    ss.route(
        "GET", "/embed/ideas",
        json_body=[{"id": board_id, "ideaNumber": "IDEA-0900", "title": "From the board", "isMine": True}],
    )
    out, _ = list_ideas(db, w)
    flags = {r["id"]: r.get("is_test") for r in rows_of(out)}
    assert flags == {idea_id: True, board_id: False}


# ------------------------------------------------------------------ AC-RV-5 a proposing turn keeps no flag


def test_AC_RV_5_a_turn_that_proposed_never_keeps_asked_back(db, ss):
    w = make_world(db)
    result, _ = go(
        db, w, [round_of(tc(CREATE, dict(FIELDS), "c1")), answer_asking("Shall I log this idea?")], text_="an idea"
    )
    assert result.pending_action is not None
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
    assert "asked_back" not in row.response


# ------------------------------------------------------------------ AC-RV-6 intake_ref follows the flag


def test_AC_RV_6_intake_ref_differs_between_test_and_real_for_the_same_text(db, ss, monkeypatch):
    from app.services.chatbot.agent import writes

    w = make_world(db)
    _, row = store(db, w, [(CREATE, dict(FIELDS))])
    confirm(db, w, row)
    monkeypatch.setattr(writes, "IDEA_IS_TEST", False)
    _, row = store(db, w, [(CREATE, dict(FIELDS))])
    confirm(db, w, row)
    first, second = posts(ss, CREATE_PATH)
    assert first["json"]["is_test"] is True and second["json"]["is_test"] is False
    assert first["json"]["intake_ref"] != second["json"]["intake_ref"]


# ------------------------------------------------------------------ AC-RV-7 the list for an operator


def test_AC_RV_7_a_view_only_operator_is_denied_with_no_ss_call(db, ss):
    w = make_world(db)
    create_through(db, w, ss, title="Hidden zzt", number="IDEA-0501", idea_id=str(uuid.uuid4()))
    op = operator_with(db, BOARD_VIEW)
    ss.calls.clear()
    ss.session_calls.clear()
    out, _ = list_ideas(db, w, operator=op)
    assert out.status == "denied"
    assert "Hidden zzt" not in json.dumps(out.data, default=str)
    assert ss.calls == [] and ss.session_calls == []


def test_AC_RV_7_a_manage_operator_gets_the_rows_read_as_the_linked_user(db, ss):
    w = make_world(db)
    idea_id, _ = made_idea(db, w, ss, title="Visible zzt", number="IDEA-0502")
    op = operator_with(db, BOARD_VIEW, MANAGE)
    ss.session_calls.clear()
    out, _ = list_ideas(db, w, operator=op)
    assert out.status == "ok"
    assert [r["id"] for r in rows_of(out)] == [idea_id]
    subjects = [
        jwt.decode(c["assertion"], SIGNING_SECRET, algorithms=["HS256"], audience="ideation-embed")["sub"]
        for c in ss.session_calls
    ]
    assert subjects and all(sub == w.user_id for sub in subjects)


# ------------------------------------------------------------------ AC-RV-8 one valid idea id


@pytest.mark.parametrize(
    "shape",
    [
        lambda a, b: f"{a},{b}",
        lambda a, b: json.dumps([a, b]),
        lambda a, b: json.dumps([a]),
        lambda a, b: f"{a} {b}",
        lambda a, b: "not-a-uuid",
    ],
    ids=["comma_joined", "json_list_two", "json_list_one", "space_joined", "not_a_uuid"],
)
def test_AC_RV_8_idea_id_must_be_one_valid_uuid(db, ss, shape):
    w = make_world(db)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    value = shape(a, b)
    res, step = propose(db, w, UPDATE, {"idea_id": value, "title": "New"}, seen=[a, b, value])
    assert res.status in ("invalid", "denied") and step is None
    assert ss.calls == [] and ss.session_calls == []


# ------------------------------------------------------------------ AC-RV-9 use_cases limits


@pytest.mark.parametrize(
    "use_cases",
    [[f"Case {n}" for n in range(6)], ["y" * 4001]],
    ids=["six_distinct_items", "one_item_over_4000"],
)
def test_AC_RV_9_too_many_or_too_long_use_cases_are_invalid_on_a_create(db, ss, use_cases):
    w = make_world(db)
    res, step = propose(db, w, CREATE, {"problem": PROBLEM, "use_cases": use_cases})
    assert res.status == "invalid" and step is None
    assert ss.calls == []


@pytest.mark.parametrize(
    "use_cases", [[f"Case {n}" for n in range(6)], ["y" * 4001]], ids=["six_distinct_items", "one_item_over_4000"]
)
def test_AC_RV_9_too_many_or_too_long_use_cases_are_invalid_on_an_update(db, ss, use_cases):
    w = make_world(db)
    Idea(ss)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "use_cases": use_cases}, seen=[IDEA])
    assert res.status == "invalid" and step is None
    assert patches(ss) == []


def test_AC_RV_9_five_distinct_items_of_4000_characters_pass_and_all_reach_ss(db, ss):
    w = make_world(db)
    cases = [f"{n}" + "z" * 3999 for n in range(5)]  # distinct, so the shared cleaner keeps all five
    steps, row = store(db, w, [(CREATE, {"problem": PROBLEM, "use_cases": cases})])
    confirm(db, w, row)
    (call,) = posts(ss, CREATE_PATH)
    assert [c.lstrip("0123456789") for c in call["json"]["use_cases"]] == ["z" * 3999] * 5
    assert len(call["json"]["use_cases"]) == 5


# ------------------------------------------------------------------ AC-RV-10 only test ideas while the flag is on


def test_AC_RV_10_a_real_idea_is_refused_with_a_line_pointing_to_the_board_and_no_patch(db, ss):
    w = make_world(db)
    Idea(ss, isTest=False)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "title": "New title"}, seen=[IDEA])
    assert res.status in ("denied", "invalid") and step is None
    assert "board" in res.message.lower()
    assert not leaks(res.message)
    assert patches(ss) == []


def test_AC_RV_10_a_test_idea_of_the_users_still_works(db, ss):
    w = make_world(db)
    Idea(ss, isTest=True)
    _, row = store(db, w, [(UPDATE, {"idea_id": IDEA, "title": "New title"})], seen=[IDEA])
    assert confirm(db, w, row).steps[0]["status"] == "done"
    assert len(patches(ss)) == 1


def test_AC_RV_10_with_the_flag_off_a_real_idea_of_the_users_works(db, ss, monkeypatch):
    from app.services.chatbot.agent import writes

    monkeypatch.setattr(writes, "IDEA_IS_TEST", False)
    w = make_world(db)
    Idea(ss, isTest=False)
    _, row = store(db, w, [(UPDATE, {"idea_id": IDEA, "title": "New title"})], seen=[IDEA])
    assert confirm(db, w, row).steps[0]["status"] == "done"
    assert len(patches(ss)) == 1


# ================================================================== recheck round

from tests.chatbot.agent import test_agent_writes_purchase_request as prm  # noqa: E402
from tests.chatbot.agent.test_agent_writes_purchase_request import sends  # noqa: E402,F401
from tests.chatbot.agent.test_agent_writes_pr_undo import grace  # noqa: E402

NOTE_TEXT = "This is a test idea"


# ------------------------------------------------------------------ AC-RV-2 (changed) a deferred decision has no code-added line


def test_AC_RV_2_a_parked_purchase_request_decision_confirmed_in_chat_has_no_applies_in_line(db, sends, monkeypatch):
    w = prm.make_world(db)
    grace(monkeypatch, 30)
    pr = prm.make_request(db, w)
    prm.propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})
    second, _ = go(db, w, [decide_from_view({}), answer_("Approved.")], text_="yes")
    assert "applies in" not in second.reply_text.lower(), second.reply_text


def test_AC_RV_2_a_console_confirm_of_a_parked_decision_keeps_its_full_reply(db, sends, monkeypatch):
    w = prm.make_world(db)
    grace(monkeypatch, 30)
    pr = prm.make_request(db, w)
    _, action = prm.propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})
    outcome = prm.confirm(db, w, action)
    assert "applies in" in outcome.reply_text.lower(), outcome.reply_text


def test_AC_RV_2_a_console_confirm_of_an_idea_keeps_its_full_reply(db, ss):
    w = make_world(db)
    idea_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": idea_id, "idea_number": "IDEA-0184", "status": "captured", "title": "t"},
    )
    _, row = store(db, w, [(CREATE, {"problem": PROBLEM})])
    outcome = confirm(db, w, row)
    assert "IDEA-0184" in outcome.reply_text and f"{CRM}/ideas/{idea_id}" in outcome.reply_text
    assert NOTE_TEXT in outcome.reply_text


# ------------------------------------------------------------------ AC-RC-1 the model never receives the note or the link


def test_AC_RC_1_the_confirm_tool_result_carries_neither_the_note_nor_the_link(db, ss):
    seen = {}

    def model(messages, tools):
        seen["tool"] = [m["content"] for m in messages if m.get("role") == "tool"][-1]
        return answer_("Done, your idea is logged.")

    reply, idea_id = chat_confirm_reply(db, ss, model)
    assert NOTE_TEXT.lower() not in seen["tool"].lower(), seen["tool"]
    assert "/ideas/" not in seen["tool"] and idea_id not in seen["tool"]
    assert reply.count(NOTE_TEXT) == 1 and reply.count(f"{CRM}/ideas/{idea_id}") == 1


def test_AC_RC_1_a_word_for_word_relay_leaves_the_note_in_the_reply_exactly_once(db, ss):
    reply, idea_id = chat_confirm_reply(db, ss, lambda messages, tools: answer_(last_tool_reply_text(messages)))
    assert reply.count(NOTE_TEXT) == 1, reply
    assert reply.count(f"{CRM}/ideas/{idea_id}") == 1, reply


# ------------------------------------------------------------------ AC-RC-2 a model failure after the confirm


def test_AC_RC_2_a_model_failure_after_the_confirm_still_shows_the_idea(db, ss):
    w = make_world(db)
    idea_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": idea_id, "idea_number": "IDEA-0184", "status": "captured", "title": "t"},
    )
    go(db, w, [round_of(tc(CREATE, dict(FIELDS), "c1")), answer_("Prepared.")], text_="an idea")

    def boom(messages, tools):
        raise RuntimeError("provider down")

    second, _ = go(db, w, [decide_from_view({}), boom, boom, boom], text_="yes")
    assert len(posts(ss, CREATE_PATH)) == 1
    assert second.status == "failed"
    assert "IDEA-0184" in second.reply_text and f"{CRM}/ideas/{idea_id}" in second.reply_text


# ------------------------------------------------------------------ AC-RC-3 numbers glued to a URL


@pytest.mark.parametrize("glue", ["", "-", "/"], ids=["glued", "dash", "slash"])
def test_AC_RC_3_a_figure_glued_to_a_url_is_unverified(glue):
    from app.services.chatbot.agent.loop import final_reply, verify_answer

    url = f"https://x.example/{uuid.uuid4()}"
    args = {"text": f"Stock is 5000{glue}{url} units"}
    bad_numbers, bad_not_found = verify_answer(args, {}, "")
    assert "5000" in bad_numbers, bad_numbers
    reply, _ = final_reply(args, bad_numbers, bad_not_found)
    assert "5000" not in reply and "x.example" not in reply


# ------------------------------------------------------------------ AC-RC-4 only the URL goes


def _clean(text):
    from app.services.chatbot.agent.loop import final_reply

    return final_reply({"text": text}, [], [])[0]


@pytest.mark.parametrize(
    "template, expected",
    [
        ("表格在{url}，SRTWB888 还有 5 件", "表格在，SRTWB888 还有 5 件"),
        ("已记录，请看{url}。未填写：期望结果。", "已记录，请看。未填写：期望结果。"),
        ("(see {url}), thanks.", "(see ), thanks."),
        ("Open [IDEA-0184]({url}) to add photos.", "Open IDEA-0184 to add photos."),
        ("Sila lihat {url}, terima kasih.", "Sila lihat , terima kasih."),
    ],
    ids=["chinese_after", "chinese_punctuation", "paren_comma", "markdown_link", "malay"],
)
def test_AC_RC_4_only_the_url_is_removed(template, expected):
    url = f"https://crm.zzt.example/ideas/{uuid.uuid4()}"
    assert _clean(template.format(url=url)) == expected


def test_AC_RC_4_a_good_url_next_to_one_with_an_id_stays():
    good = "https://example.org/docs"
    url = f"https://crm.zzt.example/ideas/{uuid.uuid4()}"
    result = _clean(f"{good},{url}")
    assert good in result and "ideas/" not in result


def test_AC_RC_4_a_bare_id_still_reads_id():
    assert _clean(f"Idea {uuid.uuid4()} is saved.") == "Idea (id) is saved."


def test_AC_RC_4_a_hundred_thousand_characters_of_scheme_repeats_finish_in_a_second():
    import time

    text = "http://" * 14286
    started = time.monotonic()
    _clean(text)
    assert time.monotonic() - started < 1.0


# ------------------------------------------------------------------ AC-RC-5 five newest test ideas


def test_AC_RC_5_the_constant_is_five():
    from app.services.chatbot.agent import writes

    assert writes.MAX_TEST_IDEAS == 5


def test_AC_RC_5_eight_test_ideas_make_five_reads_newest_first_and_more_is_three(db, ss):
    w = make_world(db)
    ids = [
        create_through(db, w, ss, title=f"Idea {n} zzt", number=f"IDEA-{600 + n}", idea_id=str(uuid.uuid4()))
        for n in range(8)
    ]
    ss.calls.clear()
    out, _ = list_ideas(db, w)
    by_id = [c for c in ss.calls if c["method"] == "GET" and c["path"] != "/embed/ideas"]
    assert len(by_id) == 5, [c["path"] for c in by_id]
    assert [r["id"] for r in rows_of(out)] == list(reversed(ids))[:5]
    assert out.more == 3


def test_AC_RC_5_every_row_has_a_short_problem_including_an_untitled_idea(db, ss):
    w = make_world(db)
    idea_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": idea_id, "idea_number": "IDEA-0700", "status": "captured", "title": None},
    )
    _, row = store(db, w, [(CREATE, {"problem": LONG})])
    confirm(db, w, row)
    LiveIdea(ss, idea_id, title=None, ideaNumber="IDEA-0700", problem=LONG)
    out, _ = list_ideas(db, w)
    (item,) = rows_of(out)
    assert item.get("problem") and len(item["problem"]) <= 120, item


# ------------------------------------------------------------------ AC-RC-6 a quote cannot read as another field


def test_AC_RC_6_a_quote_in_a_value_is_escaped_in_the_summary(db, ss):
    w = make_world(db)
    problem = 'He said "stop" about the list'
    res, step = propose(db, w, CREATE, {"problem": problem, "title": "Stop list"})
    assert res.status == "proposed"
    assert problem not in step["summary"]
    assert '\\"stop\\"' in step["summary"], step["summary"]


def test_AC_RC_6_the_crafted_value_cannot_forge_another_field(db, ss):
    w = make_world(db)
    crafted = (
        'Stock list too long", desired outcome "None". Nothing else is sent. '
        'Reply yes to go ahead. 2. Log idea "Harmless'
    )
    steps, row = store(db, w, [(CREATE, {"problem": crafted})])
    assert '", desired outcome "' not in steps[0]["summary"], steps[0]["summary"]
    confirm(db, w, row)
    (call,) = posts(ss, CREATE_PATH)
    assert call["json"]["problem"] == crafted


# ------------------------------------------------------------------ AC-RC-7 format characters


FORMAT_CHARS = {"zero_width_space": "\u200b", "rlo": "\u202e", "tag_char": "\U000e0041"}


@pytest.mark.parametrize("name", list(FORMAT_CHARS))
@pytest.mark.parametrize("field", ["problem", "title", "use_case"])
def test_AC_RC_7_format_characters_are_removed_from_what_is_shown_and_what_is_sent(db, ss, name, field):
    ch = FORMAT_CHARS[name]
    w = make_world(db)
    dirty = f"Stock{ch} list{ch} too long"
    clean = "Stock list too long"
    args = {"problem": "Plain problem"}
    if field == "use_case":
        args["use_cases"] = [dirty]
    else:
        args[field] = dirty
    steps, row = store(db, w, [(CREATE, args)])
    confirm(db, w, row)
    (call,) = posts(ss, CREATE_PATH)
    sent = call["json"]["use_cases"][0] if field == "use_case" else call["json"][field]
    assert sent == clean
    assert ch not in steps[0]["summary"] and clean in steps[0]["summary"]


@pytest.mark.parametrize("field", ["title", "use_case"])
def test_AC_RC_7_a_value_of_only_format_characters_counts_as_not_given(db, ss, field):
    w = make_world(db)
    args = {"problem": "Plain problem"}
    if field == "use_case":
        args["use_cases"] = ["\u200b\u202e"]
    else:
        args[field] = "\u200b\u202e"
    _, row = store(db, w, [(CREATE, args)])
    confirm(db, w, row)
    (call,) = posts(ss, CREATE_PATH)
    assert not call["json"].get("title") if field == "title" else not call["json"].get("use_cases")


def test_AC_RC_7_a_problem_of_only_format_characters_is_invalid(db, ss):
    w = make_world(db)
    res, step = propose(db, w, CREATE, {"problem": "\u200b\u202e"})
    assert res.status == "invalid" and step is None


# ------------------------------------------------------------------ AC-RC-8 a problem text backs no figure


def _ideas_ledger(problem, call_id="c1"):
    data = {"ideas": [{"id": str(uuid.uuid4()), "idea_number": "IDEA-0184", "title": "Cost note", "problem": problem}]}
    return {call_id: {"name": LIST, "status": "ok", "args": {}, "data": data}}


def test_AC_RC_8_a_number_inside_an_idea_problem_does_not_back_a_figure():
    from app.services.chatbot.agent.loop import verify_answer

    bad_numbers, _ = verify_answer({"text": "Stock is 5000 units"}, _ideas_ledger("Unit cost is 5000"), "")
    assert any("5000" in b for b in bad_numbers), bad_numbers  # a flagged figure carries its unit


def test_AC_RC_8_a_figure_from_a_real_data_key_is_still_backed():
    from app.services.chatbot.agent.loop import verify_answer

    ledger = {
        "c1": {
            "name": "crm_inventory_stock_balance_list", "status": "ok", "args": {},
            "data": {"items": [{"qty": 12}], "has_result": True},
        },
        **_ideas_ledger("Unit cost is 5000", "c2"),
    }
    assert verify_answer({"text": "Stock is 12 units"}, ledger, "") == ([], [])


# ------------------------------------------------------------------ AC-RC-9 scheme case and a bounded markdown link


@pytest.mark.parametrize("scheme", ["HTTPS://", "Http://"])
def test_AC_RC_9_a_url_scheme_in_any_case_is_removed_and_the_glued_figure_is_unverified(scheme):
    from app.services.chatbot.agent.loop import final_reply, verify_answer

    ident = str(uuid.uuid4())
    args = {"text": f"Stock is 5000{scheme}x.example/{ident} units"}
    bad_numbers, bad_not_found = verify_answer(args, {}, "")
    assert "5000" in bad_numbers, bad_numbers
    reply, _ = final_reply(args, bad_numbers, bad_not_found)
    assert ident not in reply and scheme.lower() not in reply.lower() and "x.example" not in reply


def test_AC_RC_9_a_hundred_thousand_characters_of_markdown_link_openers_finish_in_a_second():
    import time

    text = "[x](http://" * 9091
    started = time.monotonic()
    _clean(text)
    assert time.monotonic() - started < 1.0


# ================================================================== console pass round

from tests.chatbot.agent.test_agent_writes_opportunity import make_world as opp_world  # noqa: E402

# ------------------------------------------------------------------ AC-RC-11 the model is told not to invent


def _description(name):
    from app.services.chatbot.agent import writes

    return writes.WRITES[name].schema["function"]["description"].lower()


@pytest.mark.parametrize("name", [CREATE, UPDATE])
def test_AC_RC_11_the_idea_tools_tell_the_model_not_to_invent(name):
    text_ = _description(name)
    assert "only" in text_ and "said" in text_ and "leave" in text_, text_


def test_AC_RC_11_the_create_tool_says_to_propose_as_soon_as_it_has_the_problem():
    text_ = _description(CREATE)
    assert "problem" in text_ and ("as soon as" in text_ or "right away" in text_ or "immediately" in text_), text_
    assert "adjust" in text_, text_


# ------------------------------------------------------------------ AC-RC-12 the model is told the proposal is shown


def _proposed_message(db, w, call):
    seen = {}

    def capture(messages, tools):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        seen["body"] = json.loads(tool_msgs[-1]["content"])
        return answer_("Prepared.")

    go(db, w, [round_of(call), capture], text_="please")
    assert seen["body"]["status"] == "proposed", seen["body"]
    return seen["body"]["message"].lower()


def test_AC_RC_12_an_idea_proposal_tells_the_model_it_is_shown_automatically(db, ss):
    w = make_world(db)
    message = _proposed_message(db, w, tc(CREATE, dict(FIELDS), "c1"))
    assert "proposed, not done" in message
    assert "automatically" in message and "repeat" in message, message


def test_AC_RC_12_an_opportunity_proposal_tells_the_model_the_same(db):
    w = opp_world(db)
    call = tc(
        "crm_opportunity_create",
        {"title": "Showroom lights", "prospect_name": "Fake Showroom Sdn Bhd", "expected_close_date": "2026-12-01"},
        "o1",
    )
    message = _proposed_message(db, w, call)
    assert "proposed, not done" in message
    assert "automatically" in message and "repeat" in message, message
