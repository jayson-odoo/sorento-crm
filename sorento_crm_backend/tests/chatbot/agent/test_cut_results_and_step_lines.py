"""PR 4 fix round, F3 / F4 / F5 (red).

Plan: documentation/plans/chatbot/PLAN-agentic-unify-tools-1nov.md, "Fix round after crew's browser pass, 2 Nov".
F3: a cut read says so. F4: an ok step line is never "nothing found". F5: the ticket summary names only the change.
"""
from __future__ import annotations

import json

import pytest

from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent.loop import tool_detail
from app.services.chatbot.agent.tools import ToolResult
from app.services.chatbot.agent.writes import _ticket_summary
from tests._pg_fixture import blank_session
from tests.chatbot.agent import _ported_reads_support as support
from tests.chatbot.agent._ported_reads_support import AC1, Recorder, panel_ctx, panel_turn, slugs_for
from tests.chatbot.agent._seed import seed_user

NAME = "crm_projects_list"
SLUG = {n: s for n, s, _own in AC1}[NAME]


@pytest.fixture(scope="module")
def db():
    with blank_session() as session:
        yield session


def _run(db, rows: int) -> ToolResult:
    ctx = panel_ctx(db, seed_user(db, contact_pk=None, slugs=slugs_for(NAME, SLUG)))
    body = {"data": [{"ref": f"ZZT-{i:03d}", "note": "x" * 1500} for i in range(rows)], "total": rows}
    with panel_turn(ctx.user_id):
        return support.dispatch(db, ctx, NAME, None, rec=Recorder(body))


# ------------------------------------------------------------------ F3


def test_F3_a_cut_read_names_the_count_says_not_on_next_page_and_to_filter(db):
    out = _run(db, 15)
    assert out.status == "ok" and out.more > 0
    low = out.message.lower()
    assert str(out.more) in out.message
    assert "next page" in low
    assert "filter" in low


def test_F3_a_read_that_fits_has_no_cut_message(db):
    out = _run(db, 3)
    assert out.status == "ok" and out.more == 0
    assert "next page" not in out.message.lower()
    assert "filter" not in out.message.lower()


def test_F3_the_model_facing_body_carries_the_cut_message(db):
    out = _run(db, 15)
    body = json.loads(out.to_json("c1"))
    assert body["more"] == out.more > 0
    assert "next page" in body["message"].lower()
    assert str(out.more) in body["message"]


# ------------------------------------------------------------------ F4


def test_F4_an_ok_record_with_empty_lists_ends_done_not_nothing_found():
    out = ToolResult("ok", data={"record": {"code": "PPF2610011"}, "quotations": [], "scopes": []})
    text = tool_detail("crm_project_detail", {}, out, {})
    assert text.endswith("done"), text
    assert "nothing found" not in text


def test_F4_an_empty_result_still_ends_nothing_found():
    assert tool_detail("crm_projects_list", {}, ToolResult("empty"), {}).endswith("nothing found")


def test_F4_an_ok_list_of_three_rows_still_ends_3_rows():
    out = ToolResult("ok", data={"data": [{"a": 1}, {"a": 2}, {"a": 3}]})
    assert tool_detail("crm_projects_list", {}, out, {}).endswith("3 rows")


# ------------------------------------------------------------------ F5


def test_F5_ticket_summary_names_only_the_change():
    args = {"title": "Printer on level 2 is not printing", "priority": "high",
            "description": "The printer on level 2 is not printing."}
    text = _ticket_summary(args, {})
    low = text.lower()
    for word in ("review", "submitted", "submit"):
        assert word not in low, text
    assert "Printer on level 2 is not printing" in text
    assert "high" in text
    assert "The printer on level 2 is not printing." in text
