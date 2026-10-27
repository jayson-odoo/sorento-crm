"""SALES-UNIFIED: the sales ranking asks the basis with Invoiced first (owner ruling (b), 27 Oct 2026).

`documentation/plans/sales/PLAN-sales-unified-27oct.md` section 0 and contract section 7. The bot
keeps asking the basis on a ranking, never defaults it, and the question line is exactly
"Invoiced, delivered, ordered or outstanding?". The parser's `invoiced` (for "invoiced" or "1"
under that question) runs `crm_report_ask` with `basis=invoiced`. An invoiced ask by location is
said in the lane's own line; the route would refuse it (`location_needs_order_basis`).

Whole console turns, the way `test_report_ask_clarify.py` drives them: the real engine, lane and
MCP presenter; only the parser and the MCP transport are doubles.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_report_ask_clarify import _answer_keys, _sorento_wc
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    OWNER_MESSAGE,
    THIS_YEAR,
    _e,
    _rank,
    _refine,
    _say_all,
    _seed_wt,
    _t1,
    console,
)

BASIS_Q = "Invoiced, delivered, ordered or outstanding?"
LOCATION_LINE = "Sales by location are for delivered or ordered sales only."
TOOL = "crm_report_ask"


def _ran(log: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    calls = [a for n, a in log if n == TOOL]
    assert len(calls) == 1, log
    return calls[0]


# --------------------------------------------------------------------------- #
# The question
# --------------------------------------------------------------------------- #


def test_the_ranking_basis_line_offers_invoiced_first() -> None:
    from app.services.chatbot.lanes.business import ranking_ask

    assert ranking_ask.RANKING_BASIS_LINE == BASIS_Q
    assert ranking_ask.next_question(
        metric_settled=True, basis_settled=False, basis_line=ranking_ask.RANKING_BASIS_LINE
    ) == ("basis", BASIS_Q)


def test_a_ranking_with_no_basis_asks_invoiced_first_and_runs_nothing(console) -> None:
    _seed_wt(console)
    text, calls = console.say(_sorento_wc(measure="qty"), OWNER_MESSAGE)
    assert text.strip() == BASIS_Q, text
    assert calls == [], calls


def test_the_new_basis_line_is_translated() -> None:
    from app.services.chatbot.label_catalog import LABELS

    entry = LABELS[BASIS_Q]
    assert entry["ms"] and entry["zh"], entry
    assert LABELS["invoiced sales"]["ms"] and LABELS["invoiced sales"]["zh"]
    assert LABELS[LOCATION_LINE]["ms"] and LABELS[LOCATION_LINE]["zh"]


# --------------------------------------------------------------------------- #
# The answer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("reply", ["invoiced", "1"])
def test_the_invoiced_answer_runs_the_ranking_with_basis_invoiced(console, monkeypatch, reply) -> None:
    """The parser reads both replies as `basis` invoiced (template: the order the question lists them)."""
    _seed_wt(console)
    console.say(_sorento_wc(measure="qty"), OWNER_MESSAGE)
    text, log = _say_all(console, monkeypatch, _answer_keys(basis="invoiced"), reply)
    args = _ran(log)
    assert args["basis"] == "invoiced", args
    assert args["measure"] == "qty", args
    assert "crm_top_selling_report" not in [n for n, _a in log], (log, text)


def test_a_fresh_ask_naming_invoiced_runs_at_once(console) -> None:
    _text, calls = console.say(
        _rank(_e("Sorento", "brand"), basis="invoiced", **THIS_YEAR), "top 3 salesman for sorento, invoiced"
    )
    (args,) = calls
    assert args["basis"] == "invoiced", args


def test_an_analysis_verdict_with_sales_basis_invoiced_carries_it_onto_the_ranking() -> None:
    """A sales analysis by an axis only the report ask draws keeps the parser's invoiced basis."""
    from app.services.chatbot.lanes.business import report_ask

    out = report_ask.by_capability(
        {"order_status": "sales_analysis", "group_by": "sales_agent", "by_words": "by agent",
         "sales_basis": "invoiced", "rank_direction": "top", "top_n": 5}
    )
    assert out["order_status"] == report_ask.ASK_NAME, out
    assert out["basis"] == "invoiced", out


# --------------------------------------------------------------------------- #
# Location is an order basis only
# --------------------------------------------------------------------------- #


def test_an_invoiced_ranking_by_location_is_said_and_runs_nothing(console) -> None:
    text, calls = console.say(
        _rank(group_by="warehouse", basis="invoiced", **THIS_YEAR), "which location sold most this year, invoiced"
    )
    assert calls == [], calls
    assert text.strip() == LOCATION_LINE, text


def test_a_delivered_ranking_by_location_still_runs(console) -> None:
    _text, calls = console.say(
        _rank(group_by="warehouse", basis="delivered", **THIS_YEAR), "which location sold most this year, delivered"
    )
    (args,) = calls
    assert args["basis"] == "delivered" and args["group_by"] == "location", args


def test_the_location_line_reads_only_invoiced_location_args() -> None:
    from app.services.chatbot.lanes.business import report_ask

    assert report_ask.invoiced_location_line({"basis": "invoiced", "group_by": "location"}) == LOCATION_LINE
    assert report_ask.invoiced_location_line({"basis": "invoiced", "warehouse_codes": ["BB"]}) == LOCATION_LINE
    assert report_ask.invoiced_location_line({"basis": "invoiced", "group_by": "customer"}) is None
    assert report_ask.invoiced_location_line({"basis": "delivered", "group_by": "location"}) is None


# --------------------------------------------------------------------------- #
# Parser schema and template
# --------------------------------------------------------------------------- #


def test_the_parser_schema_accepts_basis_invoiced() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA

    basis = PARSE_OUTPUT_JSON_SCHEMA["properties"]["basis"]
    assert {"invoiced", "delivered", "ordered", "outstanding", "unclear", None} <= set(basis["enum"]), basis
    jsonschema.validate({"basis": "invoiced"}, {"type": "object", "properties": {"basis": basis}})


def test_the_template_teaches_the_invoiced_answer_and_words() -> None:
    from app.services.chatbot.head.parser_template import TEMPLATE, lint

    flat = " ".join(TEMPLATE.split())
    assert f'"{BASIS_Q}" -> `basis`' in flat, "the template never maps the new basis question"
    assert '"invoiced" or "1" is invoiced' in flat
    assert '"Delivered, ordered or outstanding?"' not in flat
    assert "`basis` invoiced | delivered | ordered | outstanding | unclear | null" in flat
    assert '"sales" said plainly names no basis: null, the bot asks' in flat
    assert "已开票" in flat
    assert lint(TEMPLATE) == []
