"""REPORT-OUTSTANDING-SUMMARY (29 Oct 2026): `crm_report_ask` prints the route's outstanding `summary` in the
pre-#1922 shape (`documentation/plans/reports/report-outstanding-summary-behaviour-card.md`).

The prod turn #b6e9 (26 Oct 09:28, "Srt5733 stock and outstanding") is pinned by
`test_the_prod_turn_shape_pending_delivery_for_a_product`: counts, quantities, the DO date range, By location, By
customer, then the delivery order list offer.
"""
from __future__ import annotations

from sorento_crm_mcp.presenters import _report_ask

ALL_DATES = {"date_from": None, "date_to": None}


def _body(basis: str, label: str, filters: list, summary: dict | None, total=(40, 1234.0)) -> dict:
    body = {
        "status": "ok", "message": None, "basis": basis, "basis_label": label, "measure": "qty",
        "group_by": None, "group_label": None, **ALL_DATES, "filters": filters, "rows": [], "more": 0,
        "total_count": 0, "total": {"qty": total[0], "amount": total[1]},
    }
    if summary is not None:
        body["summary"] = summary
    return body


PRODUCT = [{"key": "product", "label": "Product", "values": ["SRT5733-WH"]}]
CUSTOMER = [{"key": "customer", "label": "Customer", "values": ["Customer A"]}]


def test_the_prod_turn_shape_pending_delivery_for_a_product():
    body = _body("pending_delivery", "pending delivery", PRODUCT, {
        "documents": 3, "qty": 40, "amount": 1234.0, "date_first": "2026-10-02", "date_last": "2026-10-20",
        "groups": [
            {"axis": "location", "label": "Location", "rows": [
                {"name": "WH-A", "qty": 30, "amount": 900.0}, {"name": "WH-B", "qty": 10, "amount": 334.0}]},
            {"axis": "customer", "label": "Customer", "rows": [
                {"name": "Customer A", "qty": 25, "amount": 800.0}, {"name": "Customer B", "qty": 15, "amount": 434.0}]},
        ],
    })
    assert _report_ask(body) == "\n".join([
        "Product: SRT5733-WH",
        "Customer: all",
        "Location: all",
        "Order date: all",
        "",
        "*Delivery order outstanding*",
        "Delivery orders: 3",
        "DO qty: 40",
        "Delivered: 0",
        "Outstanding: 40 pcs, RM 1,234.00",
        "DO date range: 02/10/2026 to 20/10/2026",
        "*_By location_*",
        "WH-A: 30 (O/S: 30)",
        "WH-B: 10 (O/S: 10)",
        "*_By customer_*",
        "Customer A: 25 (O/S: 25)",
        "Customer B: 15 (O/S: 15)",
        "",
        "Reply 1 for the delivery order list.",
    ])


def test_undelivered_orders_for_a_customer_print_ordered_transferred_and_by_product():
    body = _body("outstanding", "outstanding orders", CUSTOMER, {
        "documents": 4, "ordered_qty": 300, "qty": 120, "amount": 9800.0,
        "date_first": "2026-08-05", "date_last": "2026-10-21",
        "groups": [
            {"axis": "location", "label": "Location", "rows": [{"name": "WH-A", "qty": 120, "amount": 9800.0, "ordered_qty": 300}]},
            {"axis": "product", "label": "Product", "rows": [
                {"name": "P-1", "qty": 80, "amount": 6000.0, "ordered_qty": 200},
                {"name": "P-2", "qty": 40, "amount": 3800.0, "ordered_qty": 100},
            ]},
        ],
    }, total=(120, 9800.0))
    assert _report_ask(body) == "\n".join([
        "Product: all",
        "Customer: Customer A",
        "Location: all",
        "Order date: all",
        "",
        "*Sales order outstanding*",
        "Sales orders: 4",
        "Ordered: 300",
        "Transferred to DO: 180",
        "Outstanding: 120 pcs, RM 9,800.00",
        "Order date range: 05/08/2026 to 21/10/2026",
        "*_By location_*",
        "WH-A: 300 (O/S: 120)",
        "*_By product_*",
        "P-1: 200 (O/S: 80)",
        "P-2: 100 (O/S: 40)",
        "",
        "Reply 1 for the sales order list.",
    ])


def test_both_subjects_named_print_by_location_only():
    body = _body("pending_delivery", "pending delivery", PRODUCT + CUSTOMER, {
        "documents": 1, "qty": 2, "amount": 200.0, "date_first": "2026-09-10", "date_last": "2026-09-10",
        "groups": [{"axis": "location", "label": "Location", "rows": [{"name": "WH-A", "qty": 2, "amount": 200.0}]}],
    }, total=(2, 200.0))
    text = _report_ask(body)
    assert "DO date range: 10/09/2026" in text
    assert "*_By location_*\nWH-A: 2 (O/S: 2)\n\nReply 1 for the delivery order list." in text
    assert "By customer" not in text and "By product" not in text


def test_a_location_with_no_code_reads_unassigned_and_a_long_group_is_capped():
    rows = [{"name": f"C{i:02d}", "qty": 30 - i, "amount": 1.0} for i in range(25)]
    body = _body("pending_delivery", "pending delivery", PRODUCT, {
        "documents": 25, "qty": 425, "amount": 25.0, "date_first": "2026-01-01", "date_last": "2026-02-01",
        "groups": [
            {"axis": "location", "label": "Location", "rows": [{"name": "(blank)", "qty": 425, "amount": 25.0}]},
            {"axis": "customer", "label": "Customer", "rows": rows},
        ],
    }, total=(425, 25.0))
    text = _report_ask(body)
    assert "Unassigned: 425 (O/S: 425)" in text
    assert "... and 5 more customers" in text and "C20:" not in text


def test_nothing_outstanding_says_so_with_no_offer():
    body = _body("pending_delivery", "pending delivery", PRODUCT, {
        "documents": 0, "qty": 0, "amount": 0.0, "date_first": None, "date_last": None,
        "groups": [],
    }, total=(0, 0.0))
    assert _report_ask(body) == "\n".join([
        "Product: SRT5733-WH", "Customer: all", "Location: all", "Order date: all", "",
        "*Delivery order outstanding*", "No outstanding delivery order.",
    ])


def test_no_summary_keeps_the_one_total():
    body = _body("pending_delivery", "pending delivery", PRODUCT, None)
    assert _report_ask(body) == "\n".join([
        "Product: SRT5733-WH", "Customer: all", "Location: all", "Order date: all", "", "*Delivery order outstanding*",
        "Total 40 pcs, RM 1,234.00",
    ])


def test_the_delivery_order_list_reads_plural():
    body = _body("pending_delivery", "pending delivery", PRODUCT, None)
    body.update(group_by="delivery_order", group_label="Delivery order", total_count=2, rows=[
        {"rank": 1, "name": "DO-1", "qty": 30, "amount": 900.0}, {"rank": 2, "name": "DO-2", "qty": 10, "amount": 334.0},
    ])
    assert _report_ask(body).startswith("Top 2 delivery orders by pending delivery\n"), _report_ask(body)


def test_a_named_axis_prints_as_its_own_group():
    """Owner 29 Oct: "by salesperson" replaces the default breakdowns."""
    body = _body("pending_delivery", "pending delivery", PRODUCT, {
        "documents": 2, "qty": 3, "amount": 300.0, "date_first": "2026-08-15", "date_last": "2026-09-10",
        "groups": [{"axis": "sales_agent", "label": "Sales agent", "rows": [{"name": "AG1", "qty": 3, "amount": 300.0}]}],
    }, total=(3, 300.0))
    text = _report_ask(body)
    assert "*_By sales agent_*\nAG1: 3 (O/S: 3)" in text and "By location" not in text, text


def test_the_summary_prints_when_the_ask_also_named_an_axis():
    """The route returns the ranking rows AND the summary for "<product> outstanding by salesperson": the summary wins."""
    body = _body("pending_delivery", "pending delivery", PRODUCT, {
        "documents": 2, "qty": 3, "amount": 300.0, "date_first": "2026-08-15", "date_last": "2026-09-10",
        "groups": [{"axis": "sales_agent", "label": "Sales agent", "rows": [{"name": "AG1", "qty": 3, "amount": 300.0}]}],
    }, total=(3, 300.0))
    body.update(group_by="sales_agent", group_label="Sales agent", rows=[{"rank": 1, "name": "AG1", "qty": 3, "amount": 300.0}], total_count=1)
    text = _report_ask(body)
    assert "Delivery orders: 2" in text and "*_By sales agent_*" in text, text
    assert "1. AG1" not in text and text.rstrip().endswith("Reply 1 for the delivery order list."), text


def test_the_header_names_location_brand_period_and_extra_filters_as_before_1922():
    """Item 5 (owner 29 Oct): Product / Customer / Location / Order date ("all" when unset), then Brand when one was named;
    a filter the old report had no line for (a spec, a channel) follows, and so does "Not applied"."""
    filters = PRODUCT + [
        {"key": "location", "label": "Location", "values": ["BRW-BB"]},
        {"key": "brand", "label": "Brand", "values": ["SORENTO"]},
        {"key": "channel", "label": "Channel", "values": ["Dealer"]},
    ]
    body = _body("pending_delivery", "pending delivery", filters, {
        "documents": 1, "qty": 2, "amount": 200.0, "date_first": "2026-09-10", "date_last": "2026-09-10", "groups": [],
    }, total=(2, 200.0))
    body.update(date_from="2026-09-01", date_to="2026-09-30")
    text = _report_ask(body)
    assert text.startswith("\n".join([
        "Product: SRT5733-WH", "Customer: all", "Location: BRW-BB", "Order date: 01/09/2026 to 30/09/2026",
        "Brand: SORENTO", "Channel: Dealer", "", "*Delivery order outstanding*",
    ])), text


def test_an_outstanding_total_with_no_subject_also_carries_the_header():
    body = _body("pending_delivery", "pending delivery", [], None)
    assert _report_ask(body) == "\n".join([
        "Product: all", "Customer: all", "Location: all", "Order date: all", "", "*Delivery order outstanding*",
        "Total 40 pcs, RM 1,234.00",
    ])
