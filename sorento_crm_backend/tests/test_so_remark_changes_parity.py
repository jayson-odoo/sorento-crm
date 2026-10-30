"""FULFIL-SO-REMARK-CHANGES, owner ruling R5 (26 Oct 2026): "the email, popup, excel must always
match in which shows the saved lines, well of course they can split in the popup, then the email
and excel must tally to it".

Card: `documentation/plans/scm/CARD-fulfil-so-remark-changes-27oct.md` (Owner rulings, R5).

Each case presses Confirm through a real route and reads the handover email actually dispatched
and the OI Excel it attaches: the two must be the same rows. A split line is also read off the
Confirm popup (`GET .../line-splits`), whose rows for that line must carry the same quantities
and dates as the email's rows for it. Every line here is Buy: whether a stock-only line belongs in
the popup is an open owner question and is not tested.

Reuses the `sent` fixture and the row readers of `test_oi_handover_email_excel_parity.py`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.order import SalesOrderLine
from app.services.scm.outstanding_diff import QTY_CHANGED

from .test_oi_handover_email_excel_parity import (  # noqa: F401 - `sent` is a fixture
    _email_rows,
    _excel_rows,
    _sheet,
    sent,
)
from .test_oi_saved_line_email import _order, _post
from .test_planning_change_apply_on_board import (  # noqa: F401 - fixtures
    BASE,
    _build,
    _change,
    _confirm,
    api,
    world,
)
from .test_planning_changes import _line_payload

__all__ = ["api", "world", "sent"]


def _email_rows_as_printed(context):
    """`_email_rows`, with a split line's later rows printed the way the email and the Excel
    both print them (`oihr_0009`): ITEM CODE, QTY and LOCATION on the line's first row only."""
    rows = []
    for line in context["handover"]["lines"]:
        item, qty, change_to, location, remark = _email_rows(
            {"handover": {"lines": [line]}}
        )[0]
        if line.get("continued"):
            item, qty, location = "", "", ""
        rows.append((item, qty, change_to, location, remark))
    return sorted(rows)


def _same_rows(context, uploads):
    _headings, body = _sheet(context, uploads)
    assert _excel_rows(body) == _email_rows_as_printed(context), (
        _excel_rows(body), _email_rows_as_printed(context),
    )
    return body


def test_a_mixed_press_of_an_amended_line_and_a_new_line_tallies_email_and_excel(api, sent):
    _client, world = api
    contexts, uploads = sent
    order, line_a, line_b = _order(api, qty_a="10", qty_b="6")
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    contexts.clear()
    # AutoCount cut line A from 10 to 8, and line B is decided for the first time in this press.
    core_a = world.db.get(SalesOrderLine, line_a.core_sales_order_line_id)
    core_a.qty_ordered = Decimal("8")
    line_a.qty = Decimal("8")
    world.db.commit()

    _post(api, order, [
        _line_payload(line_a.id, buy_qty="8", amend_reason="Site cut."),
        _line_payload(line_b.id, buy_qty="6"),
    ])

    [context] = contexts
    body = _same_rows(context, uploads)
    assert len(body) == context["handover"]["line_count"] == 2, body


def test_a_split_line_tallies_email_excel_and_the_popups_rows(api, sent):
    client, world = api
    contexts, uploads = sent
    order, line_a, _line_b = _order(api, qty_a="10", qty_b="6")
    d_a, d_b = date(2026, 11, 2), date(2026, 11, 9)
    saved = client.put(f"{BASE}/sales-orders/{order.id}/line-splits", json={"lines": [{
        "line_id": str(line_a.id),
        "splits": [
            {"qty": 6, "delivery_date": d_a.isoformat(), "is_cancel": False,
             "sits_on_line_id": str(line_a.id), "remark": ""},
            {"qty": 4, "delivery_date": d_b.isoformat(), "is_cancel": False,
             "sits_on_line_id": str(line_a.id), "remark": ""},
        ],
    }]})
    assert saved.status_code == 200, saved.text
    world.db.commit()

    popup = client.get(f"{BASE}/sales-orders/{order.id}/line-splits")
    assert popup.status_code == 200, popup.text
    popup_line = next(x for x in popup.json()["lines"] if x["line_id"] == str(line_a.id))
    assert popup_line["split_view"], popup_line
    popup_rows = sorted(
        (Decimal(r["qty"]), r["delivery_date"]) for r in popup_line["split_view"]["rows"]
    )
    assert [q for q, _d in popup_rows] == [Decimal("4"), Decimal("6")], popup_rows
    contexts.clear()

    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])

    [context] = contexts
    _same_rows(context, uploads)
    mine = [x for x in context["handover"]["lines"] if x["item_code"] == world.product.product_code]
    email_set = sorted((Decimal(str(x["qty"])), x["delivery_date"]) for x in mine)
    popup_set = sorted(
        (q, date.fromisoformat(d).strftime("%d/%m/%Y")) for q, d in popup_rows
    )
    assert email_set == popup_set, (email_set, popup_set)


def test_an_autocount_only_press_tallies_email_and_excel(api, sent):
    _client, world = api
    contexts, uploads = sent
    order, line_a, line_b = _order(api, qty_a="10", qty_b="6")
    _post(api, order, [
        _line_payload(line_a.id, buy_qty="10"),
        _line_payload(line_b.id, buy_qty="6"),
    ])
    contexts.clear()
    core_a = world.db.get(SalesOrderLine, line_a.core_sales_order_line_id)
    core_so = core_a.sales_order
    core_a.qty_ordered = Decimal("8")
    line_a.qty = Decimal("8")
    world.db.commit()
    batch = _build(
        world,
        [_change(QTY_CHANGED, core_a, so_number=core_so.so_number, old_date=core_a.required_date,
                 new_date=core_a.required_date, old_qty="10", new_qty="8")],
        core_so, [str(core_a.id)],
    )
    assert batch is not None

    response = _confirm(
        api[0], order.id, [_line_payload(line_a.id, buy_qty="8")], batch_id=str(batch.id)
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    [context] = contexts
    _same_rows(context, uploads)


def test_the_per_order_route_with_a_so_remark_tallies_and_prints_the_remark(api, sent):
    client, world = api
    contexts, uploads = sent
    order, line_a, line_b = _order(api, qty_a="10", qty_b="6")

    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json={
        "lines": [
            _line_payload(line_a.id, buy_qty="10"),
            _line_payload(line_b.id, buy_qty="6"),
        ],
        "so_remark": "ZZT remark",
    })
    assert response.status_code == 200, response.text
    world.db.commit()

    [context] = contexts
    _same_rows(context, uploads)
    assert context["handover"]["orders"][0]["remark"] == "ZZT remark", context["handover"]["orders"]
