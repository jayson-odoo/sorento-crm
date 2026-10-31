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

LONG = "word " * 240  # 1200 characters
TITLE_200 = ("title " * 33).strip()  # the title limit is 200 characters, so a long title is as long as allowed


def test_AC_RV_3_a_create_shows_every_given_value_whole(db, ss):
    w = make_world(db)
    args = {
        "problem": LONG.strip() + " P",
        "title": TITLE_200,
        "desired_outcome": LONG.strip() + " O",
        "current_workaround": LONG.strip() + " W",
        "use_cases": [LONG.strip() + " U1", "short one"],
    }
    res, step = propose(db, w, CREATE, args)
    assert res.status == "proposed", res.message
    for key in ("title", "problem", "desired_outcome", "current_workaround"):
        assert args[key] in step["summary"], key
    assert args["use_cases"][0] in step["summary"] and "short one" in step["summary"]


def test_AC_RV_3_an_update_shows_every_new_value_whole(db, ss):
    w = make_world(db)
    Idea(ss)
    args = {
        "idea_id": IDEA,
        "title": TITLE_200,
        "problem": LONG.strip() + " P",
        "desired_outcome": LONG.strip() + " O",
        "current_workaround": LONG.strip() + " W",
        "use_cases": [LONG.strip() + " U1"],
    }
    res, step = propose(db, w, UPDATE, args, seen=[IDEA])
    assert res.status == "proposed", res.message
    for key in ("title", "problem", "desired_outcome", "current_workaround"):
        assert args[key] in step["summary"], key
    assert args["use_cases"][0] in step["summary"]


# ------------------------------------------------------------------ AC-RV-4 the list is live

class LiveIdea:
    """An ss idea that GET serves live and PATCH edits, for a created test idea."""

    def __init__(self, ss, idea_id, **over):
        self.path = f"/embed/ideas/{idea_id}"
        self.state = idea_body(id=idea_id, problem=PROBLEM, **over)
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
    [["x"] * 11, ["y" * 4001]],
    ids=["eleven_items", "one_item_over_4000"],
)
def test_AC_RV_9_too_many_or_too_long_use_cases_are_invalid_on_a_create(db, ss, use_cases):
    w = make_world(db)
    res, step = propose(db, w, CREATE, {"problem": PROBLEM, "use_cases": use_cases})
    assert res.status == "invalid" and step is None
    assert ss.calls == []


@pytest.mark.parametrize("use_cases", [["x"] * 11, ["y" * 4001]], ids=["eleven_items", "one_item_over_4000"])
def test_AC_RV_9_too_many_or_too_long_use_cases_are_invalid_on_an_update(db, ss, use_cases):
    w = make_world(db)
    Idea(ss)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "use_cases": use_cases}, seen=[IDEA])
    assert res.status == "invalid" and step is None
    assert patches(ss) == []


def test_AC_RV_9_ten_items_of_4000_characters_are_accepted(db, ss):
    w = make_world(db)
    res, step = propose(db, w, CREATE, {"problem": PROBLEM, "use_cases": ["z" * 4000] * 10})
    assert res.status == "proposed" and step is not None


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
