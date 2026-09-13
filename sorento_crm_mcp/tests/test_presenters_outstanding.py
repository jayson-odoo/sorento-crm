"""Golden-fixture coverage for the outstanding-report presenter (S1,
PLAN-chatbot-outstanding-report.md / chatbot-outstanding-report-acceptance-criteria.md,
AC-1101 to AC-1108).

`_outstanding_report` / `_outstanding_detail` render the WHOLE WhatsApp reply
directly as a string - no envelope, no `view=render` dispatch through
`present_response` - because the report's shape (two named blocks, each with its
own By location / By customer subgroup, D6) does not fit the generic item/field
envelope every other tool in this module builds.

**Fixture bytes live in TWO places on purpose.** The canonical, human-reviewed
copy the plan names is `documentation/plans/chatbot/samples/outstanding-*` (the
captain's Phase 1 sign-off page). This file reads its OWN copy under
`tests/fixtures/outstanding/` instead, because the MCP suite's CI job
(`.github/workflows/deploy.yml` "Run MCP test suite") mounts ONLY
`sorento_crm_mcp/tests` into the test container - `documentation/` does not
exist there, the same class of gotcha `chatbot/samples/README.md`'s "growth r1
phrase corpus" note flags for the backend image, just one repo layer up. Both
copies are generated from the same presenter run and must stay byte-identical;
`test_documentation_samples_mirror_fixtures` enforces that whenever `documentation/`
IS present (a normal local `pytest` run), and skips harmlessly when it is not
(the CI container).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from sorento_crm_mcp.presenters import (
    _outstanding_detail,
    _outstanding_report,
    present_response,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "outstanding"
_DOC_SAMPLES = Path(__file__).parent.parent.parent / "documentation" / "plans" / "chatbot" / "samples"

_MOCK = json.loads((_FIXTURES / "outstanding-report-mock.json").read_text())


def _golden(name: str) -> str:
    """A golden fixture's text, trailing newline stripped - the presenter itself
    never appends one, the file on disk carries the usual one."""
    return (_FIXTURES / name).read_text().rstrip("\n")


def _miss_report() -> dict:
    """Both scopes asked, both empty (AC-1107 / journey step 6): no product, no
    customer, no location, no date, every count zero."""
    return {
        "product_code": "SRTWT9999",
        "customer_name": None,
        "location_token": None,
        "warehouse_codes": [],
        "order_date_from": None,
        "order_date_to": None,
        "so": {
            "ordered_qty": 0, "transferred_qty": 0, "outstanding_qty": 0,
            "so_count": 0, "order_date_min": None, "order_date_max": None,
        },
        "do": {
            "do_qty": 0, "delivered_qty": 0, "pending_qty": 0,
            "do_count": 0, "do_date_min": None, "do_date_max": None,
        },
        "so_by_location": [], "so_by_customer": [],
        "do_by_location": [], "do_by_customer": [],
        "so_rows": [], "do_rows": [],
    }


# --------------------------------------------------------------------------
# AC-1101 / AC-1102: golden fixtures, byte-equal
# --------------------------------------------------------------------------

def test_report_both_scopes_byte_equal_to_golden():
    assert _outstanding_report(_MOCK) == _golden("outstanding-report-both.txt")


def test_report_so_scope_only_omits_do_block_and_uses_single_line_offer():
    """R9 (owner testing round 3, 13 Sep 2026): with only ONE scope on offer the
    reply ends with a single sentence, not a numbered list - `1. Sales order list`
    becomes `Reply 1 for the sales order list.`; the numbered form stays for TWO
    scopes (`test_report_both_scopes_byte_equal_to_golden`)."""
    so_only = copy.deepcopy(_MOCK)
    so_only["do"] = None
    rendered = _outstanding_report(so_only)
    assert rendered == _golden("outstanding-report-so.txt")
    assert "Delivery order outstanding" not in rendered
    assert "Delivery order pending" not in rendered
    assert "2. Delivery order list" not in rendered
    assert "1. Sales order list" not in rendered
    assert rendered.rstrip().endswith("Reply 1 for the sales order list.")


def test_report_do_scope_only_omits_so_block_and_uses_single_line_offer():
    """R9: the DO-only mirror of the above."""
    do_only = copy.deepcopy(_MOCK)
    do_only["so"] = None
    rendered = _outstanding_report(do_only)
    assert rendered == _golden("outstanding-report-do.txt")
    assert "Sales order outstanding" not in rendered
    assert "1. Delivery order list" not in rendered
    assert rendered.rstrip().endswith("Reply 1 for the delivery order list.")


# --------------------------------------------------------------------------
# R6 (owner testing round 3, 13 Sep 2026): "need to show the delivered also, so
# the by location and by customer needs to be the DO qty (O/S: {pending}) so DO
# qty minus pending should be those quantity delivered." `DO qty:` / `Delivered:`
# are BACK on the block, and both breakdowns regain the `(O/S: ...)` bracket
# (`name: do_qty (O/S: pending)`), over EVERY DO in scope - pending and
# delivered - which is what R1 (13 Sep, round 1) had dropped. R7 (round 3, same
# day) renames the block title to `Delivery order outstanding` and the `Pending:`
# line to `Outstanding:`, and reorders the four totals to
# `Delivery orders` / `DO qty` / `Delivered` / `Outstanding` / `DO date range`.
# --------------------------------------------------------------------------


def test_do_block_prints_do_qty_delivered_and_outstanding_lines():
    rendered = _outstanding_report(_MOCK)
    assert "*Delivery order outstanding*" in rendered, rendered
    assert "Delivery order pending" not in rendered, rendered
    assert "Delivery orders: 3" in rendered, rendered
    assert "DO qty: 700" in rendered, rendered
    assert "Delivered: 60" in rendered, rendered
    assert "Outstanding: 640" in rendered, rendered
    assert "Pending:" not in rendered, rendered


def test_do_block_lines_print_in_the_r7_order():
    """`Delivery orders`, `DO qty`, `Delivered`, `Outstanding`, `DO date range` -
    in that order, immediately after the block title."""
    rendered = _outstanding_report(_MOCK)
    block = rendered.split("*Delivery order outstanding*\n", 1)[1]
    lines = block.splitlines()[:5]
    assert lines == [
        "Delivery orders: 3",
        "DO qty: 700",
        "Delivered: 60",
        "Outstanding: 640",
        "DO date range: 03/02/2026 to 30/08/2026",
    ], lines


def test_do_breakdown_lines_carry_do_qty_with_the_outstanding_bracket():
    rendered = _outstanding_report(_MOCK)
    assert "BRW-IB: 700 (O/S: 640)" in rendered, rendered
    assert "Dealer A Sdn Bhd: 700 (O/S: 640)" in rendered, rendered


def test_do_breakdown_line_pending_zero_still_prints_the_bracket():
    """R6: "a name whose pending is 0 is still printed as `(O/S: 0)`" - a
    location/customer that is only ever delivered must not be elided."""
    report = copy.deepcopy(_MOCK)
    report["do_by_location"] = report["do_by_location"] + [
        {"code": "MWH-IB", "do_qty": 20, "pending_qty": 0},
    ]
    report["do_by_customer"] = report["do_by_customer"] + [
        {"customer_name": "Dealer Delivered Only", "do_qty": 50, "pending_qty": 0},
    ]
    rendered = _outstanding_report(report)
    assert "MWH-IB: 20 (O/S: 0)" in rendered, rendered
    assert "Dealer Delivered Only: 50 (O/S: 0)" in rendered, rendered


def test_do_breakdowns_sum_to_both_do_qty_and_outstanding_block_totals():
    """AC-1116: the breakdown sums must equal the block on BOTH figures now that
    `do_qty` is back alongside `pending_qty`."""
    rendered = _outstanding_report(_MOCK)
    assert rendered  # sanity - the real arithmetic check lives in the backend suite
    location_do_qty = sum(row["do_qty"] for row in _MOCK["do_by_location"])
    location_pending = sum(row["pending_qty"] for row in _MOCK["do_by_location"])
    customer_do_qty = sum(row["do_qty"] for row in _MOCK["do_by_customer"])
    customer_pending = sum(row["pending_qty"] for row in _MOCK["do_by_customer"])
    assert location_do_qty == _MOCK["do"]["do_qty"] == customer_do_qty
    assert location_pending == _MOCK["do"]["pending_qty"] == customer_pending


# --------------------------------------------------------------------------
# AC-1103: every breakdown line renders, thousands separators, Unassigned, no elision
# --------------------------------------------------------------------------

def test_fourteen_customers_render_without_elision():
    report = copy.deepcopy(_MOCK)
    report["do"] = None
    report["so"]["so_count"] = 14
    report["so"]["ordered_qty"] = 14_000
    report["so"]["outstanding_qty"] = 14_000
    report["so_by_customer"] = [
        {"customer_name": f"Dealer {i:02d}", "ordered_qty": 1000, "outstanding_qty": 1000}
        for i in range(14)
    ]
    report["so_by_location"] = [{"code": None, "ordered_qty": 14_000, "outstanding_qty": 14_000}]
    rendered = _outstanding_report(report)
    customer_lines = [
        line for line in rendered.splitlines()
        if line.startswith("Dealer ") and "(O/S:" in line
    ]
    assert len(customer_lines) == 14
    assert "+" not in rendered.split("Reply with a number")[0]
    assert "more" not in rendered
    # NULL warehouse (code=None) prints Unassigned, and the thousands separator is a comma.
    assert "Unassigned: 14,000 (O/S: 14,000)" in rendered


def test_null_customer_prints_unassigned_in_both_blocks():
    """Owner smoke test, 13 Sep 2026: `SRTWT7443 outstanding both` printed
    `None: 178 (O/S: 178)` under *_By customer_* - a sales order with no customer
    rendered Python's `None` at the reader. A missing customer prints `Unassigned`,
    the SAME word a NULL warehouse already uses, in both blocks."""
    report = copy.deepcopy(_MOCK)
    report["so_by_customer"] = [
        {"customer_name": None, "ordered_qty": 178, "outstanding_qty": 178},
    ]
    report["do_by_customer"] = [{"customer_name": None, "do_qty": 640, "pending_qty": 640}]
    rendered = _outstanding_report(report)
    assert "Unassigned: 178 (O/S: 178)" in rendered, rendered
    assert "Unassigned: 640 (O/S: 640)" in rendered, rendered
    assert "None" not in rendered, rendered


@pytest.mark.parametrize("scope", ["so", "do"])
def test_null_customer_prints_unassigned_in_the_detail_rows(scope: str):
    """The same word in the detail list's Customer field, for both scopes - the row
    is one SO / one pending DO, and `None` is not a customer."""
    report = copy.deepcopy(_MOCK)
    report["so_rows"] = [{**report["so_rows"][0], "customer_name": None}]
    report["do_rows"] = [{**report["do_rows"][0], "customer_name": None}]
    rendered = _outstanding_detail(report, scope)
    assert "*Customer:* Unassigned" in rendered, rendered
    assert "None" not in rendered, rendered


def test_null_warehouse_prints_unassigned():
    report = copy.deepcopy(_MOCK)
    report["do"] = None
    report["so_by_location"] = [{"code": None, "ordered_qty": 5, "outstanding_qty": 5}]
    rendered = _outstanding_report(report)
    assert "Unassigned: 5 (O/S: 5)" in rendered


# --------------------------------------------------------------------------
# AC-1104: date forms
# --------------------------------------------------------------------------

def test_no_date_window_prints_all():
    report = copy.deepcopy(_MOCK)
    report["do"] = None
    report["order_date_from"] = None
    report["order_date_to"] = None
    rendered = _outstanding_report(report)
    assert "Order date: all" in rendered
    assert "oldest" not in rendered
    assert "newest" not in rendered
    assert "since" not in rendered


def test_date_range_prints_dd_mm_yyyy_to_dd_mm_yyyy():
    rendered = _outstanding_report(_MOCK)
    assert "Order date: 01/01/2026 to 31/12/2026" in rendered
    assert "Order date range: 05/01/2026 to 28/08/2026" in rendered


def test_single_day_window_prints_once():
    report = copy.deepcopy(_MOCK)
    report["do"] = None
    report["order_date_from"] = "2026-03-01"
    report["order_date_to"] = "2026-03-01"
    rendered = _outstanding_report(report)
    assert "Order date: 01/03/2026" in rendered
    assert "01/03/2026 to 01/03/2026" not in rendered


# --------------------------------------------------------------------------
# AC-1105: Location header forms
# --------------------------------------------------------------------------

def test_location_header_suffix_resolution_shows_token_and_codes():
    rendered = _outstanding_report(_MOCK)
    assert "Location: IB (BRW-IB, MWH-IB)" in rendered


def test_location_header_exact_code_prints_alone():
    report = copy.deepcopy(_MOCK)
    report["do"] = None
    report["location_token"] = "BRW-IB"
    report["warehouse_codes"] = ["BRW-IB"]
    rendered = _outstanding_report(report)
    assert "Location: BRW-IB" in rendered
    assert "Location: BRW-IB (BRW-IB)" not in rendered


def test_location_header_no_token_prints_all():
    report = copy.deepcopy(_MOCK)
    report["do"] = None
    report["location_token"] = None
    report["warehouse_codes"] = []
    rendered = _outstanding_report(report)
    assert "Location: all" in rendered


def test_location_header_is_rendered_from_a_real_route_body():
    """AC-1105 through the WIRE, not a hand-made key (review round, 13 Sep 2026): the
    header's two inputs are the route's own `warehouse_codes` echo and the `location_token`
    the caller sent, so the two must travel on the response body - `location_codes` only
    ever existed in the mock, which is why a live turn printed `Location: all`."""
    body = {
        "product_code": "SRTWT7445",
        "customer_name": None,
        "warehouse_codes": ["BRW-IB", "MWH-IB"],
        "location_token": "IB",
        "order_date_from": None,
        "order_date_to": None,
        "so": {
            "ordered_qty": 10, "transferred_qty": 3, "outstanding_qty": 7, "so_count": 1,
            "order_date_min": "2026-01-01", "order_date_max": "2026-01-01",
        },
        "so_by_location": [], "so_by_customer": [],
        "do_by_location": [], "do_by_customer": [],
        "so_rows": [], "do_rows": [],
    }
    rendered = json.loads(present_response("crm_outstanding_report", json.dumps(body)))["response"]
    assert "Location: IB (BRW-IB, MWH-IB)" in rendered, rendered

    body["location_token"] = None
    assert "Location: all" in json.loads(
        present_response("crm_outstanding_report", json.dumps(body))
    )["response"]


def test_so_refused_line_sits_between_the_header_and_the_do_block():
    """AC-1141 / S4 point 11: the refusal is a note about the withheld half, so it goes
    AFTER the four header lines and BEFORE the DO block. The lane used to prepend it to
    the whole reply, which reads as a refusal of the question itself."""
    body = copy.deepcopy(_MOCK)
    body.pop("so", None)
    body["so_by_location"] = []
    body["so_by_customer"] = []
    body["so_rows"] = []
    body["so_refused"] = True
    rendered = json.loads(present_response("crm_outstanding_report", json.dumps(body)))["response"]
    lines = rendered.splitlines()
    assert "Sales order figures are not enabled for your account." in lines, rendered
    refusal_at = lines.index("Sales order figures are not enabled for your account.")
    header_at = next(i for i, line in enumerate(lines) if line.startswith("Order date:"))
    block_at = lines.index("*Delivery order outstanding*")
    assert header_at < refusal_at < block_at, rendered


def test_the_envelope_carries_has_result_so_a_miss_can_escalate():
    """AC-1107: the rendered header is ALWAYS non-empty, so the text alone can never tell
    a hit from a miss. `present_response` therefore returns an envelope carrying
    `has_result` (any block with rows), which is what the chatbot lane reads to send a
    total miss down the escalate path."""
    hit = json.loads(present_response("crm_outstanding_report", json.dumps(_MOCK)))
    assert hit["has_result"] is True
    assert hit["response"] == _outstanding_report(_MOCK)

    miss = json.loads(present_response("crm_outstanding_report", json.dumps(_miss_report())))
    assert miss["has_result"] is False
    assert miss["response"] == _outstanding_report(_miss_report())

    detail = copy.deepcopy(_MOCK)
    detail["detail"] = "so"
    rendered = json.loads(present_response("crm_outstanding_report", json.dumps(detail)))
    assert rendered["has_result"] is True
    assert rendered["response"] == _outstanding_detail(detail, "so")


# --------------------------------------------------------------------------
# AC-1106: detail lists
# --------------------------------------------------------------------------

def test_detail_so_list_byte_equal_to_golden():
    assert _outstanding_detail(_MOCK, "so") == _golden("outstanding-detail-so.txt")


def test_detail_do_list_byte_equal_to_golden():
    assert _outstanding_detail(_MOCK, "do") == _golden("outstanding-detail-do.txt")


def test_detail_do_list_shows_delivered_even_when_zero():
    """R3 (owner testing round 2, 13 Sep 2026): "need to show delivered also,
    doesn't mean if it is 0 then we don't show, if it is 0 then we show 0, don't
    hide." R7 (round 3), RENAMED: the row label `Pending` becomes `Outstanding`
    (the JSON field stays `pending_qty` - presentation only). The DO detail row
    is `DO Number`, `Customer`, `Location`, `DO Qty`, `Delivered`, `Outstanding`,
    `DO Date`, and `Delivered` prints `0` rather than being omitted."""
    rendered = _outstanding_detail(_MOCK, "do")
    assert "*DO Qty:* 640" in rendered, rendered
    assert "*Delivered:* 0" in rendered, rendered
    assert "*Outstanding:* 640" in rendered, rendered
    assert "*Pending:*" not in rendered, rendered
    fields = [line.split(":*")[0].lstrip("*") for line in rendered.splitlines() if line.startswith("*")]
    assert fields == ["Customer", "Location", "DO Qty", "Delivered", "Outstanding", "DO Date"], (
        f"field order must be Customer, Location, DO Qty, Delivered, Outstanding, DO Date: {rendered!r}"
    )


def test_detail_so_list_every_row_renders_numbered():
    report = copy.deepcopy(_MOCK)
    report["so_rows"] = report["so_rows"] + [
        {
            "so_number": "SO331900", "customer_name": "Dealer B Trading",
            "location": "BRW-IB, MWH-IB", "ordered_qty": 811, "transferred_qty": 0,
            "outstanding_qty": 811, "order_date": "2026-01-05",
        },
    ]
    rendered = _outstanding_detail(report, "so")
    assert rendered.count("*SO Number:*") == 2
    assert rendered.startswith("1. *SO Number:* SO331785")
    assert "2. *SO Number:* SO331900" in rendered
    assert "more" not in rendered


# --------------------------------------------------------------------------
# AC-1107: miss lines, header unchanged, no offer, escalate offer left to the lane
# --------------------------------------------------------------------------

def test_miss_prints_block_titles_and_one_line_per_scope_under_the_same_header():
    rendered = _outstanding_report(_miss_report())
    assert rendered == _golden("outstanding-report-miss.txt")
    assert "*Sales order outstanding*\nNo open sales order." in rendered
    assert "*Delivery order outstanding*\nNo outstanding delivery order." in rendered
    assert "No pending delivery order." not in rendered
    # the presenter stops there - the escalate offer is the lane's job, not this function's
    assert "Reply with a number for detail" not in rendered
    assert "escalat" not in rendered.lower()


def test_partial_miss_keeps_the_hit_scopes_offer():
    """One scope empty, the other not: the empty block prints its OWN title plus the
    one miss line (never the omitted-block treatment AC-1102 uses for a scope that
    was never asked), the hit block prints in full, and only the hit scope is offered -
    as the R9 single-line sentence, since only one scope survives to be offered."""
    report = copy.deepcopy(_MOCK)
    report["do"]["do_count"] = 0
    rendered = _outstanding_report(report)
    assert "*Delivery order outstanding*\nNo outstanding delivery order." in rendered
    assert "Sales order outstanding" in rendered
    assert "Reply 1 for the sales order list." in rendered
    assert "1. Sales order list" not in rendered
    assert "Delivery order list" not in rendered
    # the empty scope keeps its title but not its breakdown body
    assert "DO qty:" not in rendered
    assert "Delivered:" not in rendered


# --------------------------------------------------------------------------
# AC-1108: dash guard over every golden file
# --------------------------------------------------------------------------

# Escaped, never a literal em/en-dash/arrow in this SOURCE file: the repo-wide
# dash-guard pre-push hook scans every ADDED line for the raw bytes, string-literal
# catalogue or not.
_BANNED = ("\u2014", "\u2013", "\u2192", "->", "=>")


@pytest.mark.parametrize(
    "name",
    [
        "outstanding-report-both.txt",
        "outstanding-report-so.txt",
        "outstanding-report-do.txt",
        "outstanding-report-miss.txt",
        "outstanding-detail-so.txt",
        "outstanding-detail-do.txt",
    ],
)
def test_dash_guard_over_every_golden_file(name: str):
    text = _golden(name)
    for banned in _BANNED:
        assert banned not in text, f"{name} carries a banned character/sequence: {banned!r}"
    # No em/en-dash disguised as a hyphen-minus run either (a triple hyphen used as a rule).
    assert not re.search(r"-{2,}", text)


def test_dash_guard_over_every_presenter_output():
    """Same guard, run over the LIVE presenter output (both/so/do/miss/both details),
    not just the files on disk - a golden file can go stale, the function cannot."""
    so_only = copy.deepcopy(_MOCK)
    so_only["do"] = None
    do_only = copy.deepcopy(_MOCK)
    do_only["so"] = None
    outputs = [
        _outstanding_report(_MOCK),
        _outstanding_report(so_only),
        _outstanding_report(do_only),
        _outstanding_report(_miss_report()),
        _outstanding_detail(_MOCK, "so"),
        _outstanding_detail(_MOCK, "do"),
    ]
    for text in outputs:
        for banned in _BANNED:
            assert banned not in text


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
