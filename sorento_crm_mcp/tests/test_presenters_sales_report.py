"""Golden-fixture coverage for the sales-report presenter (S1,
PLAN-chatbot-sales-report.md / chatbot-sales-report-acceptance-criteria.md,
AC-1601 to AC-1609).

`_sales_report` / `_sales_report_detail` render the WHOLE WhatsApp reply
directly as a string - no envelope, no `view=render` dispatch through
`present_response` yet (S1 wires only a directly callable function; S2/S3 add
the route and the tool that would call it, the same order the outstanding
report's own S1 followed).

**Fixture bytes live in TWO places on purpose**, the same reason
`test_presenters_outstanding.py` gives: the canonical, human-reviewed copy the
plan names is `documentation/plans/chatbot/samples/sales-report-*` (the
captain's Phase 1 sign-off page). This file reads its OWN copy under
`tests/fixtures/sales_report/` instead, because the MCP suite's CI job
(`.github/workflows/deploy.yml` "Run MCP test suite") mounts ONLY
`sorento_crm_mcp/tests` into the test container - `documentation/` does not
exist there. Both copies are generated from the same presenter run and must
stay byte-identical; `test_documentation_samples_mirror_fixtures` enforces
that whenever `documentation/` IS present (a normal local `pytest` run), and
skips harmlessly when it is not (the CI container).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from sorento_crm_mcp.presenters import _sales_report, _sales_report_detail

_FIXTURES = Path(__file__).parent / "fixtures" / "sales_report"
_DOC_SAMPLES = Path(__file__).parent.parent.parent / "documentation" / "plans" / "chatbot" / "samples"


def _mock(name: str) -> dict:
    return json.loads((_FIXTURES / f"sales-report-{name}.json").read_text())


def _golden(name: str) -> str:
    """A golden fixture's text, trailing newline stripped - the presenter itself
    never appends one, the file on disk carries the usual one."""
    return (_FIXTURES / f"sales-report-{name}.txt").read_text().rstrip("\n")


# --------------------------------------------------------------------------
# AC-1601 / AC-1602: golden fixtures, byte-equal, month block line order
# --------------------------------------------------------------------------


def test_customer_subject_golden():
    """AC-1601: a customer-subject body with two months renders byte-equal to
    the golden - five header lines in the order Customer / Product / Channel /
    Location / Delivery date, a blank line, then month blocks in the order
    given."""
    assert _sales_report(_mock("customer")) == _golden("customer")


def test_month_block_line_order():
    """AC-1602: each month block prints, in order, the month title, Sales
    orders, Ordered, Confirmed (DO), Outstanding, the breakdown sub-heading,
    then the breakdown lines."""
    rendered = _sales_report(_mock("customer"))
    block = rendered.split("*_Sep 2026_*\n", 1)[1].split("\n\n", 1)[0]
    lines = block.splitlines()
    assert lines[0] == "Sales orders: 31"
    assert lines[1] == "Ordered: RM 182,450.00 (Qty: 3,120)"
    assert lines[2] == "Confirmed (DO): RM 96,300.50 (Qty: 1,540)"
    assert lines[3] == "Outstanding: RM 86,149.50 (Qty: 1,580)"
    assert lines[4] == "*_By product_*"
    assert lines[5] == "SRTWT7445: RM 50,000.00 (Qty: 900) (Confirmed: RM 40,000.00, Qty: 720)"
    assert lines[6] == "SRTKT39SS: RM 31,200.00 (Qty: 400) (Confirmed: RM 0.00, Qty: 0)"


# --------------------------------------------------------------------------
# AC-1603: absent header axis prints "all"
# --------------------------------------------------------------------------


def test_absent_axis_prints_all():
    rendered = _sales_report(_mock("customer"))
    assert rendered.startswith(
        "Customer: HANLIM TRADING SDN BHD, HANLIM TRADING SDN BHD [A/C I]\n"
        "Product: all\n"
        "Channel: Dealer\n"
        "Location: all\n"
        "Delivery date: all\n"
    )
    both_absent = _sales_report(_mock("miss"))
    assert both_absent.startswith(
        "Customer: all\n"
        "Product: SRTWT9999\n"
        "Channel: all\n"
        "Location: all\n"
        "Delivery date: all\n"
    )


def test_channel_prints_dealer_project_or_all():
    assert "Channel: Dealer" in _sales_report(_mock("customer"))
    assert "Channel: Project" in _sales_report(_mock("both"))
    assert "Channel: all" in _sales_report(_mock("product"))


def test_location_header_matches_the_outstanding_header():
    """S9 (captain ruling 19 Sep 2026): `Location:` prints exactly as
    `_outstanding_location_header` does - reused directly, not copied. A typed
    token that resolved to more than one code brackets the codes; a token that
    IS the single resolved code (the "codes alone" case AC-1603 names) prints
    just that code, no brackets."""
    report = copy.deepcopy(_mock("product"))
    report["location_token"] = "IB"
    report["warehouse_codes"] = ["BRW-IB", "MWH-IB"]
    assert "Location: IB (BRW-IB, MWH-IB)" in _sales_report(report)

    report["location_token"] = "BRW-IB"
    report["warehouse_codes"] = ["BRW-IB"]
    rendered = _sales_report(report)
    assert "Location: BRW-IB" in rendered
    assert "Location: BRW-IB (BRW-IB)" not in rendered

    # No token at all (this lane's own five mocks): "all", even with resolved
    # codes present - the same rule the outstanding header applies.
    assert "Location: all" in _sales_report(_mock("product"))


# --------------------------------------------------------------------------
# AC-1604: breakdown heading follows the subject
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected_heading",
    [
        # customer subject -> By product; product subject -> By customer;
        # both named -> no breakdown heading at all (AC-1604's third case).
        ("customer", "*_By product_*"),
        ("product", "*_By customer_*"),
        ("both", None),
    ],
)
def test_breakdown_heading_follows_subject(name, expected_heading):
    rendered = _sales_report(_mock(name))
    for heading in ("*_By product_*", "*_By customer_*"):
        if heading == expected_heading:
            assert heading in rendered, rendered
        else:
            assert heading not in rendered, rendered


# --------------------------------------------------------------------------
# AC-1605: a hit ends with the offer sentence and nothing after it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["customer", "product", "both"])
def test_hit_ends_with_offer_sentence(name):
    rendered = _sales_report(_mock(name))
    assert rendered.endswith("Reply 1 for the sales order list.")
    assert rendered.count("Reply 1 for the sales order list.") == 1


# --------------------------------------------------------------------------
# AC-1606: detail golden, field order
# --------------------------------------------------------------------------


def test_detail_golden():
    assert _sales_report_detail(_mock("detail")) == _golden("detail")


def test_detail_field_order():
    rendered = _sales_report_detail(_mock("detail"))
    first_item = rendered.split("\n\n", 1)[0]
    labels = []
    for line in first_item.splitlines():
        line = re.sub(r"^\d+\.\s+", "", line)  # strip the leading "1. " on the first line
        labels.append(line.split(":*", 1)[0].lstrip("*"))
    assert labels == [
        "SO Number", "Customer", "Location", "Order Date",
        "Ordered", "Confirmed (DO)", "Outstanding",
    ], labels
    assert rendered.startswith("1. *SO Number:* SO421287")
    assert "2. *SO Number:* SO420911" in rendered


# --------------------------------------------------------------------------
# AC-1607: a miss prints the header then "No sales found." and no offer
# --------------------------------------------------------------------------


def test_miss_prints_no_offer():
    rendered = _sales_report(_mock("miss"))
    assert rendered == _golden("miss")
    assert rendered.endswith("No sales found.")
    assert "Reply" not in rendered
    assert "escalat" not in rendered.lower()


# --------------------------------------------------------------------------
# AC-1608: months and breakdown rows print in the order given, never re-sorted
# --------------------------------------------------------------------------


def test_presenter_keeps_input_order():
    report = {
        "customer_name": "ZZT Test Sdn Bhd",
        "product_code": None,
        "channel": None,
        "warehouse_codes": [],
        "date_from": None,
        "date_to": None,
        "months": [
            {
                "month": "2026-01",
                "so_count": 1,
                "ordered_value": 10,
                "ordered_qty": 1,
                "confirmed_value": 10,
                "confirmed_qty": 1,
                "outstanding_value": 0,
                "outstanding_qty": 0,
                "by_product": [
                    {"product_code": "ZZT-LOW", "ordered_value": 5, "ordered_qty": 1,
                     "confirmed_value": 5, "confirmed_qty": 1, "outstanding_value": 0, "outstanding_qty": 0},
                    {"product_code": "ZZT-HIGH", "ordered_value": 20, "ordered_qty": 4,
                     "confirmed_value": 20, "confirmed_qty": 4, "outstanding_value": 0, "outstanding_qty": 0},
                    {"product_code": "ZZT-MID", "ordered_value": 10, "ordered_qty": 2,
                     "confirmed_value": 10, "confirmed_qty": 2, "outstanding_value": 0, "outstanding_qty": 0},
                ],
            },
            {
                "month": "2025-12",
                "so_count": 1,
                "ordered_value": 5,
                "ordered_qty": 1,
                "confirmed_value": 5,
                "confirmed_qty": 1,
                "outstanding_value": 0,
                "outstanding_qty": 0,
                "by_product": [],
            },
        ],
        "so_rows": [],
    }
    rendered = _sales_report(report)
    # An unsorted body (Jan then Dec, deliberately the opposite of "latest first")
    # comes out in the order it was given - the presenter never re-sorts months.
    jan_at = rendered.index("*_Jan 2026_*")
    dec_at = rendered.index("*_Dec 2025_*")
    assert jan_at < dec_at

    # A deliberately unranked breakdown (low, high, mid) prints in that given
    # order too, never re-sorted by value.
    low_at = rendered.index("ZZT-LOW")
    high_at = rendered.index("ZZT-HIGH")
    mid_at = rendered.index("ZZT-MID")
    assert low_at < high_at < mid_at


# --------------------------------------------------------------------------
# AC-1609: money format, zero, and the dash guard
# --------------------------------------------------------------------------


def test_money_format_and_no_dashes():
    rendered = _sales_report(_mock("customer"))
    assert "RM 182,450.00" in rendered
    assert "RM 0.00" in rendered
    for banned in _BANNED:
        assert banned not in rendered, f"banned character/sequence found: {banned!r}"
    assert not re.search(r"-{2,}", rendered)


# --------------------------------------------------------------------------
# dash guard over every golden file
# --------------------------------------------------------------------------

_BANNED = ("\u2014", "\u2013", "\u2192", "->", "=>")


@pytest.mark.parametrize(
    "name",
    ["customer", "product", "both", "miss", "detail"],
)
def test_dash_guard_over_every_golden_file(name: str):
    text = _golden(name)
    for banned in _BANNED:
        assert banned not in text, f"{name} carries a banned character/sequence: {banned!r}"
    assert not re.search(r"-{2,}", text)


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
