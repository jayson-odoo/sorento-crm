"""AGENT-COMMISSION-WA, crew pass 6882082161 on 7d133d52 (NOT READY, two owner standing-rule lines):

- L85, a capped list ends with the standard 'Reply "more" to see the next N.' line (`composers.sets.more_line`) and
  "more" pages on. The 50-row next-tier ranking ended "And 40 more targets: ask for one agent, team or dealer." and a
  "more" answered about the screen behind the panel. Now `crm_query` takes `offset`: the model, which reads its last
  call in the history (`memory.digest_line`), repeats that call with the offset when the user asks for more, in any
  words or language (owner rule: understanding is the model's, never a word list). A next-tier ranking pages by
  NEXT_LINES rows, each with its own sentence.
- L51 / L82, on a typo and a Malay question the model wrote its own paragraph after the next-tier table, repeating
  the figures with an en-dash range and raw `*`. The reply stays the model's (owner 14 Nov: no system-appended or
  system-stripped text); the tool output says what to write: the table is the answer, nothing in it repeated, no
  markdown, a range as dd/mm/yyyy - dd/mm/yyyy.
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import grant, refused, run, targets  # noqa: F401  (fixtures)
from tests.test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"


# ------------------------------------------------------------------ L85: the "more" line and the offset


def test_P1_crm_query_takes_an_offset_and_says_what_more_means():
    from app.services.chatbot.agent.query_tools import QUERY_SCHEMA

    prop = QUERY_SCHEMA["function"]["parameters"]["properties"]["offset"]
    assert prop["type"] == "integer"
    said = prop["description"].lower()
    # The model is told: the next page of the list it last showed, the same call again, offset = rows already shown.
    assert "more" in said and "same" in said and "already shown" in said


def test_P2_an_offset_returns_the_next_rows_of_the_same_ranking(targets):
    db, _c, _t = targets
    spec = {"entity": ENTITY, "period": "2026"}
    whole = run(db, spec)
    assert whole["total"] >= 2, whole
    first = run(db, {**spec, "limit": 1})
    second = run(db, {**spec, "limit": 1, "offset": 1})
    assert [r["id"] for r in first["rows"]] == [whole["rows"][0]["id"]]
    assert [r["id"] for r in second["rows"]] == [whole["rows"][1]["id"]]
    assert second["offset"] == 1 and second["total"] == whole["total"]
    assert second["truncated"] == (whole["total"] > 2)
    # Totals are over every matching row, whatever page is shown.
    assert second.get("totals") == whole.get("totals")


def test_P3_an_offset_past_the_end_finds_no_rows_and_is_not_cut(targets):
    db, _c, _t = targets
    out = run(db, {"entity": ENTITY, "period": "2026", "offset": 500})
    assert out["rows"] == [] and out["truncated"] is False


def test_P4_offset_pages_groups_too(targets):
    db, _c, _t = targets
    spec = {"entity": ENTITY, "period": "2026", "group_by": ["owner_kind"], "aggregates": [{"fn": "count"}]}
    whole = run(db, spec)
    if whole["total_groups"] < 2:
        pytest.skip("the fixture has one kind")
    second = run(db, {**spec, "limit": 1, "offset": 1})
    assert second["groups"] == whole["groups"][1:2] and second["offset"] == 1


@pytest.mark.parametrize("bad", [-1, "1", True, 1.5])
def test_P5_offset_is_a_whole_number_from_0(targets, bad):
    db, _c, _t = targets
    assert "offset" in refused(db, {"entity": ENTITY, "period": "2026", "offset": bad}).message


def _cut(shown: int, total: int, offset: int = 0, ranked: bool = True) -> dict:
    data = {
        "entity": ENTITY,
        "columns": [{"key": "label", "label": "Owner"}, {"key": "payout", "label": "Payout"}],
        "rows": [{"id": str(i), "label": f"Agent {i}", "payout": 1.0} for i in range(offset, offset + shown)],
        "total": total, "truncated": offset + shown < total, "offset": offset,
    }
    if ranked:
        data["ranked_by"] = "Payout"
    return data


def test_P6_a_cut_list_ends_with_the_standard_more_line():
    from app.services.chatbot.agent.query_tools import render_card
    from app.services.chatbot.composers.sets import more_line

    for panel in (True, False):
        text = render_card(_cut(10, 25), title="Payout", panel=panel)
        assert text.rstrip().endswith(more_line(10)), text
        assert "Top 10 of 25 by payout." in text
        later = render_card(_cut(10, 25, offset=10), title="Payout", panel=panel)
        assert "21 to 30" not in later and "11 to 20 of 25" in later and later.rstrip().endswith(more_line(5))


def test_P7_the_last_page_has_no_more_line_and_says_which_rows_it_shows():
    from app.services.chatbot.agent.query_tools import render_card

    text = render_card(_cut(5, 25, offset=20), title="Payout", panel=True)
    assert "21 to 25 of 25" in text and '"more"' not in text


def test_P8_a_next_tier_ranking_pages_by_its_sentences():
    from app.services.assistant_registry.sales import NEXT_LINES, _next_tier_spec

    for asked in (None, 5, 50):
        spec = {"entity": ENTITY, "next_tier": "closest", "subjects": "agent", "offset": 10}
        if asked is not None:
            spec["limit"] = asked
        out = _next_tier_spec(spec)
        assert out["limit"] == min(asked or NEXT_LINES, NEXT_LINES) and out["offset"] == 10


def test_P9_no_ask_for_one_line_every_row_shown_has_its_sentence():
    import inspect

    from app.services.assistant_registry import sales

    source = inspect.getsource(sales._summary_note)
    assert "ask for one agent, team or dealer" not in source
    assert "[:NEXT_LINES]" not in source


# ------------------------------------------------------------------ L51 / L82: what the model is told to write


def test_P10_the_next_tier_tool_output_says_the_table_is_the_answer():
    from app.services.chatbot.agent.query_tools import as_card

    data = {
        "entity": ENTITY,
        "columns": [{"key": "label", "label": "Owner"}, {"key": "to_next_tier", "label": "To the next tier"}],
        "rows": [{"id": "1", "label": "Agent A", "to_next_tier": 1000.0}],
        "total": 1, "truncated": False,
        "scope_note": "Next tier: TGT-1 (Agent A, 01/10/2026 - 31/10/2026): tier 2 at RM 5,000.00.",
    }
    for panel in (True, False):
        said = as_card(data, panel=panel).data["instruction"]
        for must in ("do not repeat", "dd/mm/yyyy - dd/mm/yyyy", "no markdown"):
            assert must in said.lower(), (must, said)


def test_P11_every_card_tells_the_model_how_more_works():
    from app.services.chatbot.agent.query_tools import as_card

    data = _cut(12, 40, ranked=False)
    summary = as_card(data, panel=True).data
    assert summary["next_offset"] == 12 and summary["more"] == 12
    last = as_card(_cut(12, 24, offset=12, ranked=False), panel=True).data
    assert "next_offset" not in last and last["more"] == 0
