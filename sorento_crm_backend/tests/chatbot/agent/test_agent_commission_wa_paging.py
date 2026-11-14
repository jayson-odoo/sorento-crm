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


def test_P9_the_note_never_carries_next_tier_lines_or_an_ask_for_one_line():
    """Each row carries its own `next_tier_lines` (owner 14 Nov: the model writes from them); the note keeps only
    what is about the rows as a whole, and never an "ask for one" line (owner L85)."""
    from datetime import date

    from app.services.assistant_registry import sales

    nxt = {"state": "next", "unit": "RM", "tier": 2, "threshold": 1000.0, "gap": 100.0, "payout": 20.0, "gain": 5.0}
    rows = [{
        "owner": f"Agent {i}", "owner_kind": "agent", "_zero": [], "_has_commission": True,
        "_live": [{"target_no": f"TGT-{i}", "start": date(2026, 11, 1), "end": date(2099, 11, 30), "next": nxt}],
    } for i in range(12)]
    said = sales._summary_note(rows, {"to_next_tier"}) or ""
    assert "Next tier:" not in said and "ask for one" not in said


# ------------------------------------------------------------------ L51 / L82: what the model is told to write


def test_P10_a_next_tier_result_is_never_a_card_and_carries_the_instruction():
    """L51 / L82 and owner 14 Nov: the model gets the rows and the instruction (`DISTANCE_INSTRUCTION`), and writes
    the reply; no code-rendered block stands in for it."""
    from app.services.chatbot.agent.query_tools import DISTANCE_INSTRUCTION, as_card, query_result

    data = {
        "entity": ENTITY,
        "columns": [{"key": "label", "label": "Owner"}, {"key": "to_next_tier", "label": "To the next tier"}],
        "rows": [{"id": str(i), "label": f"Agent {i}", "to_next_tier": 1000.0} for i in range(10)],
        "total": 10, "truncated": False,
    }
    for panel in (True, False):
        assert as_card(data, panel=panel) is None
        out = query_result(data, panel=panel)
        assert out.display in (None, "") and out.data["instruction"] == DISTANCE_INSTRUCTION


def test_P11_every_card_tells_the_model_how_more_works():
    from app.services.chatbot.agent.query_tools import as_card

    data = _cut(12, 40, ranked=False)
    summary = as_card(data, panel=True).data
    assert summary["next_offset"] == 12 and summary["more"] == 12
    last = as_card(_cut(12, 24, offset=12, ranked=False), panel=True).data
    assert "next_offset" not in last and last["more"] == 0


# ------------------------------------------------------------------ review on 5f651cfb: the SQL path and the last page


@pytest.fixture
def five_customers(targets):
    """Five customers of one code prefix, on the registry's SQL path (`customer`)."""
    from tests.test_dealer_targets_api import _customer

    from app.models.order import Customer

    db, _client, _t = targets

    any_customer = db.query(Customer).filter(Customer.customer_name == "ZZT DEALER W2").first()
    rows = [_customer(db, any_customer.company_id, f"ZZTPAGE {i}") for i in range(5)]
    db.flush()
    return db, sorted(r.customer_code for r in rows)


def _customers(db, **extra):
    from tests.chatbot.agent.test_ai_tools_wave2 import run as run_

    return run_(db, {
        "entity": "customer", "fields": ["code"], "sort": [{"field": "code", "dir": "asc"}],
        "filters": [{"field": "name", "op": "starts_with", "value": "ZZTPAGE"}], **extra,
    })


def test_P12_the_sql_rows_path_pages_with_the_offset(five_customers, grant):
    db, codes = five_customers
    grant("order_management.customers.view")
    page = _customers(db, limit=2, offset=2)
    assert [r["label"].split(":")[0] for r in page["rows"]] == codes[2:4], page
    assert page["total"] == 5 and page["truncated"] is True and page["offset"] == 2
    last = _customers(db, limit=2, offset=4)
    assert len(last["rows"]) == 1 and last["truncated"] is False


def test_P13_an_offset_past_the_end_still_says_the_total_on_the_sql_path(five_customers, grant):
    """Review on 5f651cfb: the window count came from the returned rows, so a page past the end read total 0, which
    every caller reads as "nothing found" (`shape_reply`'s miss, `query_as_asker`'s rerun)."""
    db, _codes = five_customers
    grant("order_management.customers.view")
    out = _customers(db, offset=50)
    assert out["rows"] == [] and out["total"] == 5 and out["truncated"] is False


def test_P14_the_sql_groups_path_pages_with_the_offset(five_customers, grant):
    db, codes = five_customers
    grant("order_management.customers.view")
    spec = {"entity": "customer", "group_by": ["code"], "aggregates": [{"fn": "count"}],
            "filters": [{"field": "name", "op": "starts_with", "value": "ZZTPAGE"}]}
    from tests.chatbot.agent.test_ai_tools_wave2 import run as run_

    page = run_(db, {**spec, "limit": 2, "offset": 2})
    assert [g["code"] for g in page["groups"]] == codes[2:4], page
    assert page["total_groups"] == 5 and page["truncated"] is True and page["offset"] == 2
    past = run_(db, {**spec, "offset": 50})
    assert past["groups"] == [] and past["total_groups"] == 5
