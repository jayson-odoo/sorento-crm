"""Golden-fixture coverage for the top X hot selling presenter (S1,
PLAN-chatbot-top-x-hot-selling-24sep.md / its UAC, AC-1901 to AC-1915, rewritten
for the owner's 26 Sep 2026 rulings on PR #1175).

`_top_selling` renders the WHOLE WhatsApp reply for a route body;
`_top_selling_envelope` wraps it with `result_type` / `has_result` the way
`_sales_report_envelope` does. The clarify and refusal lines are fixed
constants the lane sends before any fetch, so their goldens are `.txt` only.
No `present_response` dispatch yet: S3 adds the tool that would call it, the
same order the sales report's own S1 followed.

Fixture bytes live in TWO places for the reason `test_presenters_sales_report.py`
gives: `documentation/plans/chatbot/samples/top-selling-*` is the owner's review
copy, `tests/fixtures/top_selling/` is what the CI MCP container can see.
`test_documentation_samples_mirror_fixtures` keeps them byte-identical.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from sorento_crm_mcp.presenters import (
    TOP_SELLING_ASK_GROUP,
    TOP_SELLING_ASK_METRIC,
    TOP_SELLING_REFUSED_OTHER_CUSTOMER,
    _top_selling,
    _top_selling_envelope,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "top_selling"
_DOC_SAMPLES = Path(__file__).parent.parent.parent / "documentation" / "plans" / "chatbot" / "samples"

_BODY_GOLDENS = [
    "items-qty",
    "items-amount",
    "categories",
    "in-category",
    "customer",
    "channel",
    "agent",
    "how-many",
    "miss",
]
_FIXED_GOLDENS = {
    "clarify-metric": TOP_SELLING_ASK_METRIC,
    "clarify-group": TOP_SELLING_ASK_GROUP,
    "refused": TOP_SELLING_REFUSED_OTHER_CUSTOMER,
}
_ITEM_OFFER = "Reply with a rank number to see that item's customers and months."
_CATEGORY_OFFER = "Reply with a rank number to see that category's top items."


def _mock(name: str) -> dict:
    return json.loads((_FIXTURES / f"top-selling-{name}.json").read_text())


def _golden(name: str) -> str:
    return (_FIXTURES / f"top-selling-{name}.txt").read_text().rstrip("\n")


# --------------------------------------------------------------------------
# AC-1901 / AC-1909 / AC-1913: every golden, byte for byte
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", _BODY_GOLDENS)
def test_every_body_golden(name: str):
    assert _top_selling(_mock(name)) == _golden(name)


@pytest.mark.parametrize("name", sorted(_FIXED_GOLDENS))
def test_fixed_lines_match_goldens(name: str):
    assert _FIXED_GOLDENS[name] == _golden(name)


def test_items_by_quantity_header_order():
    """AC-1901: title, Ranked by, Basis, count, Customer, Category, Sales agent,
    Channel, Delivery date, in that order, then a blank line."""
    lines = _top_selling(_mock("items-qty")).splitlines()
    assert lines[:10] == [
        "*Top 5 selling items*",
        "Ranked by: Quantity",
        "Basis: Delivered (transferred to DO)",
        "Items with sales: 1,284",
        "Customer: all",
        "Category: all",
        "Sales agent: all",
        "Channel: all",
        "Delivery date: 01/01/2026 to 31/12/2026",
        "",
    ]


# --------------------------------------------------------------------------
# AC-1902 / AC-1914: row shapes for both grains
# --------------------------------------------------------------------------


def test_row_line_shape():
    rendered = _top_selling(_mock("items-qty"))
    assert "\n1. SRTWT7445 Kitchen Sink 2 Bowl: Qty 1,240, RM 86,400.00\n" in rendered
    # a null name prints the code alone before the colon
    assert "\n5. SRTWC5501: Qty 512, RM 143,360.00\n" in rendered


def test_rank_number_is_the_bodys_own():
    body = _mock("items-qty")
    body["rows"] = body["rows"][:1]
    body["rows"][0]["rank"] = 7
    assert "\n7. SRTWT7445 Kitchen Sink 2 Bowl:" in _top_selling(body)


def test_category_rows():
    rendered = _top_selling(_mock("categories"))
    assert rendered.startswith("*Top selling categories*\n")
    assert "Categories with sales: 6\n" in rendered
    assert "\n1. KITCHEN SINK: Qty 4,210, RM 612,300.00\n" in rendered
    # name null prints the category code; both null prints Unassigned
    assert "\n5. ACC: Qty 7,400, RM 0.00\n" in rendered
    assert "\n6. Unassigned: Qty 120, RM 3,600.00\n" in rendered


# --------------------------------------------------------------------------
# AC-1903 / AC-1904 / AC-1915: header axes and labels
# --------------------------------------------------------------------------


def test_absent_axis_prints_all():
    body = _mock("items-qty")
    for key in ("customer_name", "category_name", "sales_agent", "channel", "date_from", "date_to"):
        body.pop(key)
    rendered = _top_selling(body)
    for label in ("Customer", "Category", "Sales agent", "Channel", "Delivery date"):
        assert f"\n{label}: all\n" in rendered


def test_channel_prints_dealer_project_or_all():
    body = _mock("items-qty")
    body["channel"] = "dealer"
    assert "\nChannel: Dealer\n" in _top_selling(body)
    assert "\nChannel: Project\n" in _top_selling(_mock("channel"))
    assert "\nChannel: all\n" in _top_selling(_mock("customer"))


def test_ranked_by_and_basis_labels():
    assert "\nRanked by: Quantity\n" in _top_selling(_mock("items-qty"))
    assert "\nRanked by: Amount\n" in _top_selling(_mock("items-amount"))
    assert "\nBasis: Delivered (transferred to DO)\n" in _top_selling(_mock("items-qty"))
    assert "\nBasis: Ordered\n" in _top_selling(_mock("channel"))


def test_title_follows_named_n_or_none():
    assert _top_selling(_mock("in-category")).startswith("*Top 3 selling items*\n")
    body = _mock("items-qty")
    body["top_n"] = None
    assert _top_selling(body).startswith("*Top selling items*\n")


def test_agent_fill_note():
    rendered = _top_selling(_mock("agent"))
    assert (
        "Sales agent: SEAN I\n"
        "Note: only 87% of sales orders in this period carry a sales agent.\n"
        "Channel: all\n"
    ) in rendered
    assert "Note:" not in _top_selling(_mock("items-qty"))


# --------------------------------------------------------------------------
# AC-1905 / AC-1907: cap and input order
# --------------------------------------------------------------------------


def test_never_prints_past_one_hundred():
    body = _mock("items-qty")
    body["top_n"] = 100
    body["rows"] = [
        {"rank": i, "code": f"ZZ{i:03d}", "name": None, "qty": 1, "amount": 1}
        for i in range(1, 121)
    ]
    rendered = _top_selling(body)
    assert "\n100. ZZ100:" in rendered
    assert "ZZ101" not in rendered


def test_presenter_keeps_input_order():
    body = _mock("items-qty")
    body["rows"] = list(reversed(body["rows"]))
    rendered = _top_selling(body)
    assert rendered.index("SRTWC5501") < rendered.index("SRTWT7445")


# --------------------------------------------------------------------------
# AC-1906 / AC-1911 / AC-1912: miss, how many, detail offer
# --------------------------------------------------------------------------


def test_miss_prints_no_offer():
    rendered = _top_selling(_mock("miss"))
    assert rendered.endswith("\n\nNo sales found.")
    assert "Reply" not in rendered
    envelope = _top_selling_envelope(_mock("miss"))
    assert envelope == {"result_type": "top_selling", "response": rendered, "has_result": False}


def test_how_many_reply():
    body = _mock("how-many")
    rendered = _top_selling(body)
    assert rendered.endswith(
        "\n\nThat list is too long for one message. How many items do you want to see?"
    )
    assert "Items with sales: 1,284" in rendered
    assert "Reply" not in rendered
    envelope = _top_selling_envelope(body)
    assert envelope["result_type"] == "top_selling_how_many"
    assert envelope["has_result"] is True

    body["group"] = "category"
    assert _top_selling(body).endswith("How many categories do you want to see?")


@pytest.mark.parametrize(
    "name", ["items-qty", "items-amount", "in-category", "customer", "channel", "agent"]
)
def test_detail_offer_on_every_item_hit(name: str):
    rendered = _top_selling(_mock(name))
    assert rendered.endswith("\n\n" + _ITEM_OFFER)
    envelope = _top_selling_envelope(_mock(name))
    assert envelope["result_type"] == "top_selling"
    assert envelope["has_result"] is True


def test_detail_offer_on_category_hit():
    assert _top_selling(_mock("categories")).endswith("\n\n" + _CATEGORY_OFFER)


# --------------------------------------------------------------------------
# AC-1908 / AC-1910: formats, dash guard, no paging words
# --------------------------------------------------------------------------

_BANNED = ("\u2014", "\u2013", "\u2192", "->", "=>")
_PAGING = re.compile(r"\b(more|next|lagi|showing)\b", re.IGNORECASE)


def test_money_qty_format():
    rendered = _top_selling(_mock("customer"))
    assert "Qty 180, RM 12,600.00" in rendered
    assert "RM 0.00" in rendered
    assert "RM 52,500.50" in _top_selling(_mock("items-qty"))


@pytest.mark.parametrize("name", _BODY_GOLDENS + sorted(_FIXED_GOLDENS))
def test_dash_guard_and_no_paging_words(name: str):
    text = _golden(name)
    for banned in _BANNED:
        assert banned not in text, f"{name} carries a banned character/sequence: {banned!r}"
    assert not re.search(r"-{2,}", text)
    assert not _PAGING.search(text), f"{name} carries a paging word"


def test_hostile_body_never_crashes():
    body = copy.deepcopy(_mock("items-qty"))
    body["rows"] = [{"rank": None, "code": None, "name": None, "qty": "x", "amount": None}, "junk"]
    body["total"] = None
    assert isinstance(_top_selling(body), str)


# --------------------------------------------------------------------------
# corpus drift guard (skips when documentation/ is not mounted, e.g. the CI mcp job)
# --------------------------------------------------------------------------


def test_documentation_samples_mirror_fixtures():
    if not _DOC_SAMPLES.exists():
        pytest.skip("documentation/ not present in this environment (CI mcp test container)")
    for path in _FIXTURES.iterdir():
        mirror = _DOC_SAMPLES / path.name
        assert mirror.exists(), f"{path.name} has no documentation/ mirror"
        assert mirror.read_bytes() == path.read_bytes(), f"{path.name} has drifted from its documentation/ mirror"
