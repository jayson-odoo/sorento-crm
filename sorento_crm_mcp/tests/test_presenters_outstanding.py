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
    _outstanding_header_lines,
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
    """R11 (owner testing round 3, 13 Sep 2026) made the DO block ONE population
    (outstanding DOs only), so `do_qty` now equals `Outstanding` and `Delivered` is
    always `0` given today's schema - the mock reflects that identity, the same way
    a real route response now would."""
    rendered = _outstanding_report(_MOCK)
    assert "*Delivery order outstanding*" in rendered, rendered
    assert "Delivery order pending" not in rendered, rendered
    assert "Delivery orders: 3" in rendered, rendered
    assert "DO qty: 640" in rendered, rendered
    assert "Delivered: 0" in rendered, rendered
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
        "DO qty: 640",
        "Delivered: 0",
        "Outstanding: 640",
        "DO date range: 03/02/2026 to 30/08/2026",
    ], lines


def test_do_breakdown_lines_carry_do_qty_with_the_outstanding_bracket():
    rendered = _outstanding_report(_MOCK)
    assert "BRW-IB: 640 (O/S: 640)" in rendered, rendered
    assert "Dealer A Sdn Bhd: 640 (O/S: 640)" in rendered, rendered


# R11 (owner testing round 3, 13 Sep 2026) RETIRES the "(O/S: 0) still prints" test
# R6 had here: "the breakdown list should tally with whatever reported at the summary
# at the top" - a name whose outstanding is 0 is no longer sent by the route AT ALL
# (option 1: breakdowns list only names with outstanding above 0), so there is no
# more real scenario for this presenter to render. The presenter itself is still a
# dumb pass-through - `test_breakdowns_print_in_the_order_given_never_resort` below
# covers what it must and must not do to whatever list it is handed.


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
# R10 (owner testing round 3, 13 Sep 2026): "be it DO outstanding or SO outstanding,
# we need to rank by highest quantity at the top." Sorting happens in the ROUTE
# service (`sorento_crm_backend/tests/test_outstanding_report.py` pins the actual
# ranking on seeded data); the presenter's own job is narrower and already true
# today - print whatever order the arrays arrive in, never re-sort. This is a
# contract lock, not a red test: the presenter has never sorted anything, so it
# already passes - it exists so a LATER change that starts re-sorting in the
# presenter (duplicating or contradicting the route's own order) fails here first.
# --------------------------------------------------------------------------


def test_breakdowns_print_in_the_order_given_never_resort():
    report = copy.deepcopy(_MOCK)
    # Deliberately ASCENDING (the opposite of ranked order), so a presenter that
    # re-sorted would print the descending order instead and this test would catch it.
    report["so_by_location"] = [
        {"code": "ZZT-LOW", "ordered_qty": 5, "outstanding_qty": 5},
        {"code": "ZZT-MID", "ordered_qty": 10, "outstanding_qty": 10},
        {"code": "ZZT-HIGH", "ordered_qty": 20, "outstanding_qty": 20},
    ]
    report["so_by_customer"] = [
        {"customer_name": "ZZT Low Corp", "ordered_qty": 5, "outstanding_qty": 5},
        {"customer_name": "ZZT High Corp", "ordered_qty": 20, "outstanding_qty": 20},
        {"customer_name": "ZZT Mid Corp", "ordered_qty": 10, "outstanding_qty": 10},
    ]
    report["do_by_location"] = [
        {"code": "ZZT-DO-LOW", "do_qty": 5, "pending_qty": 5},
        {"code": "ZZT-DO-HIGH", "do_qty": 20, "pending_qty": 20},
    ]
    report["do_by_customer"] = [
        {"customer_name": "ZZT DO Low Corp", "do_qty": 5, "pending_qty": 5},
        {"customer_name": "ZZT DO High Corp", "do_qty": 20, "pending_qty": 20},
    ]
    rendered = _outstanding_report(report)

    def _lines_between(start_marker: str, end_marker: str) -> list[str]:
        block = rendered.split(start_marker, 1)[1].split(end_marker, 1)[0]
        return [line for line in block.splitlines() if line and ":" in line]

    so_location_lines = _lines_between("*_By location_*", "*_By customer_*")
    assert [line.split(":")[0] for line in so_location_lines[:3]] == ["ZZT-LOW", "ZZT-MID", "ZZT-HIGH"], (
        f"the presenter must print so_by_location in the order it was GIVEN, not "
        f"re-sort it: {so_location_lines}"
    )
    assert "ZZT Low Corp" in rendered and "ZZT High Corp" in rendered
    low_at = rendered.index("ZZT Low Corp")
    high_at = rendered.index("ZZT High Corp")
    mid_at = rendered.index("ZZT Mid Corp")
    assert low_at < high_at < mid_at, (
        f"so_by_customer must print in the GIVEN (unsorted) order: {rendered}"
    )
    do_low_at = rendered.index("ZZT-DO-LOW")
    do_high_at = rendered.index("ZZT-DO-HIGH")
    assert do_low_at < do_high_at, "do_by_location must print in the GIVEN order too"
    do_cust_low_at = rendered.index("ZZT DO Low Corp")
    do_cust_high_at = rendered.index("ZZT DO High Corp")
    assert do_cust_low_at < do_cust_high_at, "do_by_customer must print in the GIVEN order too"


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
    # Re-pinned (hand pass 3 row 6, `83e473522`): the detail envelope carries the same
    # scope header the summary prints, prepended - `_outstanding_detail` itself still
    # renders the bare list (see the golden-byte-equal tests below, unchanged).
    assert rendered["response"] == (
        "\n".join(_outstanding_header_lines(detail)) + "\n\n" + _outstanding_detail(detail, "so")
    )


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
    (the JSON field stays `pending_qty` - presentation only). R13 (round 3, same
    sitting): the row GAINS a `Product` line - rows always carry a product now.
    The DO detail row is `DO Number`, `Customer`, `Product`, `Location`, `DO Qty`,
    `Delivered`, `Outstanding`, `DO Date`, and `Delivered` prints `0` rather than
    being omitted."""
    rendered = _outstanding_detail(_MOCK, "do")
    assert "*DO Qty:* 640" in rendered, rendered
    assert "*Delivered:* 0" in rendered, rendered
    assert "*Outstanding:* 640" in rendered, rendered
    assert "*Product:* SRTWT7445" in rendered, rendered
    assert "*Pending:*" not in rendered, rendered
    fields = [line.split(":*")[0].lstrip("*") for line in rendered.splitlines() if line.startswith("*")]
    assert fields == ["Customer", "Product", "Location", "DO Qty", "Delivered", "Outstanding", "DO Date"], (
        f"field order must be Customer, Product, Location, DO Qty, Delivered, Outstanding, DO Date: {rendered!r}"
    )


def test_detail_so_list_every_row_renders_numbered():
    report = copy.deepcopy(_MOCK)
    report["so_rows"] = report["so_rows"] + [
        {
            "so_number": "SO331900", "customer_name": "Dealer B Trading",
            "product_code": "SRTWT7445",
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
# R13 (owner ruling, 13 Sep 2026): "when we generate the outstanding summary for
# customer and for product it is different, they should be the same ... when we
# ask for customer, the by customer section becomes by product section." The
# report's subject is a product, a customer, or both, same summary shape for all
# three. Header prints `Product: all` with no product; a `*_By product_*` group
# renders wherever the body carries `so_by_product[]` / `do_by_product[]`,
# same `name: total (O/S: outstanding)` shape as `*_By customer_*`.
# --------------------------------------------------------------------------


def _customer_subject_report() -> dict:
    """A customer-subject body: no product_code, `so_by_product`/`do_by_product`
    instead of the `_customer` breakdowns - the shape the ROUTE now sends for a
    customer-only ask (`test_outstanding_report.py::
    test_customer_subject_report_has_by_product_not_by_customer` pins the route
    side; this is the presenter's own golden)."""
    report = copy.deepcopy(_MOCK)
    report["product_code"] = None
    report["customer_name"] = "Dealer A Sdn Bhd"
    del report["so_by_customer"]
    report["so_by_product"] = [
        {"product_code": "SRTWT7445", "ordered_qty": 900, "outstanding_qty": 900},
        {"product_code": "SRTWT9002", "ordered_qty": 811, "outstanding_qty": 811},
        {"product_code": "SRTWT1200", "ordered_qty": 700, "outstanding_qty": 700},
    ]
    del report["do_by_customer"]
    report["do_by_product"] = [
        {"product_code": "SRTWT7445", "do_qty": 640, "pending_qty": 640},
    ]
    return report


def test_header_prints_product_all_when_no_product_is_given():
    report = _customer_subject_report()
    rendered = _outstanding_report(report)
    assert rendered.startswith("Product: all\n"), rendered


def test_customer_subject_report_byte_equal_to_golden():
    """R13's own golden - a customer-subject report renders `*_By product_*`
    instead of `*_By customer_*`, in both blocks, same `name: total (O/S:
    outstanding)` line shape, ranked (R10)."""
    rendered = _outstanding_report(_customer_subject_report())
    assert rendered == _golden("outstanding-report-customer.txt")
    assert "*_By customer_*" not in rendered, rendered
    assert "*_By product_*" in rendered, rendered
    assert "SRTWT7445: 900 (O/S: 900)" in rendered, rendered


def test_product_subject_report_keeps_by_customer_not_by_product():
    """The mirror: the EXISTING product-subject mock must still render
    `*_By customer_*`, never `*_By product_*` - only a customer subject
    introduces the new group."""
    rendered = _outstanding_report(_MOCK)
    assert "*_By customer_*" in rendered, rendered
    assert "*_By product_*" not in rendered, rendered


# --------------------------------------------------------------------------
# R14 (owner ruling, 13 Sep 2026): on the two-option detail offer, an answer
# meaning BOTH returns both lists in one reply, SO then DO, each under its own
# heading; the offer gains `3. Both lists` whenever two scopes are on offer.
# --------------------------------------------------------------------------


def test_offer_gains_both_lists_option_when_two_scopes_are_offered():
    rendered = _outstanding_report(_MOCK)
    assert rendered.rstrip().endswith("3. Both lists"), rendered
    lines = rendered.splitlines()
    assert lines[-3:] == ["1. Sales order list", "2. Delivery order list", "3. Both lists"], lines[-3:]


def test_single_scope_offer_never_gains_both_lists():
    """R9 stands: a single-scope offer is still one sentence, never a numbered
    list, so there is nothing for `3. Both lists` to be added to."""
    so_only = copy.deepcopy(_MOCK)
    so_only["do"] = None
    rendered = _outstanding_report(so_only)
    assert "Both lists" not in rendered, rendered


def test_detail_both_renders_the_so_list_then_the_do_list_each_under_its_heading():
    """R14: `_outstanding_detail(report, "both")` (or whatever position 3 resolves
    to) must print BOTH lists in one reply, SO first, each headed so the reader
    can tell which list they are reading - this file's own choice of exact
    heading text, since no golden precedent exists yet for it."""
    rendered = _outstanding_detail(_MOCK, "both")
    assert "*SO Number:* SO331785" in rendered, rendered
    assert "*DO Number:* DO220456" in rendered, rendered
    so_at = rendered.index("*SO Number:* SO331785")
    do_at = rendered.index("*DO Number:* DO220456")
    assert so_at < do_at, "the SO list must come BEFORE the DO list: {!r}".format(rendered)


def test_envelope_dispatches_detail_both_to_the_combined_render():
    detail = copy.deepcopy(_MOCK)
    detail["detail"] = "both"
    rendered = json.loads(present_response("crm_outstanding_report", json.dumps(detail)))
    assert rendered["has_result"] is True
    # Re-pinned (hand pass 3 row 6, `83e473522`): the header is added ONCE at the
    # envelope, not inside `_outstanding_detail`'s own "both" render (which would print
    # it three times if the header lived inside the list).
    assert rendered["response"] == (
        "\n".join(_outstanding_header_lines(detail)) + "\n\n" + _outstanding_detail(detail, "both")
    )
    assert "*SO Number:*" in rendered["response"] and "*DO Number:*" in rendered["response"]


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
        "outstanding-report-customer.txt",
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
