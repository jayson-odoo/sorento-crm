"""PREVIEW-EMAIL-PLANCHANGE: the Confirm dry run's email lines are the purchasing email's lines.

Owner rule: email = preview = attachment, all three tally (`PLAN-confirm-preview-stale-2nov.md`).
The dry run answers `email_lines` per order (`ProjectSupplyService._preview_email_lines`); the
real press sends what `_fire_pending_handover` concludes, through `handover_route_groups` and
`build_handover_email`. Each test here runs the dry run and then the real press on the same
data and asserts the two read the same, line for line.

Every test registers the post-commit listeners first, as `app/main.py` does at startup. Without
them nothing drains or discards `session.info["oi_handover_pending"]` between the fixture's own
earlier confirms and the press under test, and `record_saved_lines` folds those stale items into
the saved line: the dry run then reads `ADVANCE, ORDER 25` and drops one `CANCEL ALL` on the
`_form_three` fixture, an answer production never gives (crew-note on PR #2128, 3 Nov 2026).

Fixture chain is the real-DB one of `tests/test_planning_change_apply_on_board.py`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.order import SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services import project_order_inquiry_service as oi_service

from .test_planning_change_apply_on_board import (  # noqa: F401 - fixtures
    BASE,
    _confirm,
    _core_line,
    _core_so,
    _form_three,
    _line_payload,
    _project_line,
    _project_so,
    _uid,
    api,
    world,
)

URL = f"{BASE}/fulfilment-planning/confirm-all"

# What the email prints for a line; `so_line_id` ties a line to its order line.
_FIELDS = ("so_line_id", "item_code", "qty", "delivery_date", "remark", "was")


@pytest.fixture(autouse=True)
def _post_commit_listeners():
    """The listeners production registers at startup (`app/main.py`). Idempotent."""
    oi_service.register_order_inquiry_post_commit_dispatch()


class _SentEmails:
    """Every purchasing email the real press builds, captured at `build_handover_email` (the
    build the post-commit send makes per class group) and never dispatched."""

    def __init__(self, monkeypatch):
        self.emails = []
        self.mismatches = []
        real = oi_service.build_handover_email

        def capture(db, items, *, store_excel=True):
            built = real(db, items, store_excel=False)
            if built is not None:
                ordered = sorted(items, key=oi_service._handover_sort_key)
                lines = built[0]["handover"]["lines"]
                # Recorded, not asserted: the post-commit listener swallows an exception.
                if len(ordered) != len(lines):
                    self.mismatches.append((len(ordered), len(lines)))
                self.emails.append(
                    [
                        {"so_line_id": str(item.get("so_line_id") or ""), **line}
                        for item, line in zip(ordered, lines)
                    ]
                )
            return None

        monkeypatch.setattr(oi_service, "build_handover_email", capture)

    def lines(self):
        assert self.mismatches == [], f"items vs email lines: {self.mismatches}"
        assert len(self.emails) == 1, f"one email for one order, got {len(self.emails)}"
        return [_printed(line) for line in self.emails[0]]


def _printed(line):
    return {**{field: line.get(field) for field in _FIELDS}, "remark": line.get("remark") or ""}


def _post(client, orders, *, preview):
    body = {"orders": orders, **({"preview": True} if preview else {})}
    response = client.post(URL, json=body)
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 1 and results[0]["ok"] is True, results
    return results[0]


def _preview_then_press(client, world, orders, monkeypatch):
    sent = _SentEmails(monkeypatch)
    preview = _post(client, orders, preview=True)
    assert sent.emails == [], "a dry run sends nothing"
    _post(client, orders, preview=False)
    world.db.commit()
    return [_printed(line) for line in preview["email_lines"]], sent.lines()


# ---------------------------------------------------------------------------
# the planning-change path
# ---------------------------------------------------------------------------


def _open_pool_po_line(world, *, qty):
    db = world.db
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        issue_date=date(2026, 6, 1), status="active",
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.pool_wh.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"),
        expected_date=date(2027, 2, 20), line_status="open",
    ))
    db.commit()


def _another_orders_raised_row(fixture):
    client, world = fixture["client"], fixture["world"]
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="7")
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="7")])
    assert response.status_code == 200, response.text


def _planning_change(api):
    """`_form_three` (line 1 grows 10 to 25, lines 2 and 3 closed by the book), plus another
    order's raised awaiting row and an open pool PO line, so the placement pass places."""
    fixture = _form_three(api)
    _another_orders_raised_row(fixture)
    _open_pool_po_line(fixture["world"], qty=500)
    orders = [
        {
            "pso_id": str(fixture["order"].id),
            "batch_id": str(fixture["batch"].id),
            "lines": [_line_payload(fixture["lines"][0].id, buy_qty="25")],
        }
    ]
    return fixture, orders


def test_planning_change_preview_email_lines_equal_the_press_email(api, monkeypatch):
    fixture, orders = _planning_change(api)
    line_1, line_2, line_3 = (str(line.id) for line in fixture["lines"])

    previewed, sent = _preview_then_press(fixture["client"], fixture["world"], orders, monkeypatch)

    assert previewed == sent
    # Both closed lines are told, each once, beside the surviving line.
    assert sorted((line["so_line_id"], line["remark"]) for line in sent) == sorted(
        [(line_1, "ADVANCE, ORDER 15"), (line_2, "CANCEL ALL"), (line_3, "CANCEL ALL")]
    )


def test_planning_change_press_alone_sends_order_15_and_both_cancels(api, monkeypatch):
    """The press with no dry run before it sends the very lines the press after a dry run
    sends (the test above): a dry run leaves nothing behind (UAC A3, the two together)."""
    fixture, orders = _planning_change(api)
    sent = _SentEmails(monkeypatch)

    _post(fixture["client"], orders, preview=False)
    fixture["world"].db.commit()

    line_1, line_2, line_3 = (str(line.id) for line in fixture["lines"])
    assert sorted((line["so_line_id"], line["remark"]) for line in sent.lines()) == sorted(
        [(line_1, "ADVANCE, ORDER 15"), (line_2, "CANCEL ALL"), (line_3, "CANCEL ALL")]
    )


# ---------------------------------------------------------------------------
# the ordinary path
# ---------------------------------------------------------------------------


def _ordinary_order(api, *, quantities):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    lines = []
    for line_no, qty in enumerate(quantities, start=1):
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=str(qty))
        lines.append(_project_line(db, order, line_no=line_no, product=world.product,
                                   core_line=core))
    db.commit()
    return client, world, order, lines


def test_ordinary_first_confirm_preview_email_lines_equal_the_press_email(api, monkeypatch):
    client, world, order, lines = _ordinary_order(api, quantities=(10, 4))
    orders = [
        {
            "pso_id": str(order.id),
            "lines": [_line_payload(line.id, buy_qty=str(line.qty)) for line in lines],
        }
    ]

    previewed, sent = _preview_then_press(client, world, orders, monkeypatch)

    assert len(sent) == 2
    assert previewed == sent


def test_ordinary_reconfirm_preview_email_lines_equal_the_press_email(api, monkeypatch):
    """A re-confirm of a grown line goes through `record_saved_lines`, the step a stale queue
    item would bend."""
    client, world, order, lines = _ordinary_order(api, quantities=(10, 4))
    first = _confirm(
        client, order.id, [_line_payload(line.id, buy_qty=str(line.qty)) for line in lines]
    )
    assert first.status_code == 200, first.text
    world.db.commit()
    # The book grows line 1 from 10 to 15; the mirror carries it.
    core = world.db.get(SalesOrderLine, lines[0].core_sales_order_line_id)
    core.qty_ordered = Decimal("15")
    lines[0].qty = Decimal("15")
    world.db.commit()
    orders = [
        {
            "pso_id": str(order.id),
            "lines": [
                _line_payload(lines[0].id, buy_qty="15"),
                _line_payload(lines[1].id, buy_qty="4"),
            ],
        }
    ]

    previewed, sent = _preview_then_press(client, world, orders, monkeypatch)

    assert sent, "the grown line is told"
    assert previewed == sent
