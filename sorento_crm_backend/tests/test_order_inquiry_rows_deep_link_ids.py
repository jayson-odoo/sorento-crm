"""S6 backend - OI row <-> SO line deep-link ids (`PLAN-board-oi-mechanical-22sep.md`,
`board-oi-mechanical-22sep-acceptance-criteria.md`, AC-B6-7/8/9).

TEST-FIRST: neither field exists yet.

* `OrderInquiryRowOut` (`app/schemas/project_order_inquiry.py`) and `OrderInquiryWorklistRow`
  declare `so_line_id` (the PROJECT MIRROR line id) and `so_number`, but no `core_line_id`
  (the mirror's own `core_sales_order_line_id`, the AutoCount line the SCM Lines tab
  actually addresses) and no `sales_order_id` (the CORE `sales_orders.id` the SCM sales
  order detail page is keyed by, `/scm/sales-orders/<sales_order_id>`) - `response_model`
  drops any field the service might read that the schema does not declare, so this is red
  on a missing dict key even if a coder patches only the SERVICE side.
* `SalesOrderLineInquiry` (`app/schemas/scm_orders.py`) declares only `inquiry_no`/`state`;
  `sales_order_service.py::_line_inquiries` reads only `core_sales_order_line_id`,
  `OrderInquiry.inquiry_no` and `OrderInquiryRow.state` off the join - no `OrderInquiry.id`
  or `OrderInquiryRow.id` at all, so `inquiry_id`/`row_id` are missing at both the read and
  the wire.

Both tests share ONE harness (`test_planning_change_apply_on_board`'s `world`/`api`) rather
than mixing it with a second `world`/`api` pair of a different shape: two same-named
fixtures imported into one module collide (whichever is bound last wins for every fixture
in the module that asks for "world"), so a row for AC-B6-7 is seeded here directly rather
than reusing `test_order_inquiry_handshake._raise_one_row`.

Runs on the REAL database (`_real_db_session`, imported transitively via `test_planning_
change_apply_on_board`, rolled back via a savepoint): `scm.committed_v` and the handshake
columns live only in the migrated schema. Every row is seeded here behind the ZZT marker -
CI's database has no data.
"""
from __future__ import annotations

from datetime import date

from .test_planning_change_apply_on_board import (
    BASE,
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _order_row,
    _project_line,
    _project_so,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixture; keeps linters from calling it unused

LIST = f"{BASE}/order-inquiries"


def _raise_one_row(api, *, qty="10", with_core_line=True):
    """One published order, one line, confirmed wholly as Buy: one raised inquiry row.

    `with_core_line=False` NULLS the mirror's own `core_sales_order_line_id` AFTER the
    confirm succeeds - the shape AC-B6-7's "null when the mirror has no core line" half
    needs. Confirming a line whose mirror carries no core line at all is refused
    (`test_supply_unreconciled_lines.py`'s own shape: the facts read cannot resolve a
    required date with nothing to read it off), so the id is cleared only once the row
    already exists, never before.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered=qty,
        required_date=date(2026, 8, 25),
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert (
        _confirm(client, order.id, [_line_payload(line.id, buy_qty=qty)]).status_code == 200
    )
    row = _order_row(world, line)
    if not with_core_line:
        line.core_sales_order_line_id = None
        db.commit()
    return {
        "order": order, "line": line, "core_so": core_so, "core": core, "row": row,
    }


# ---------------------------------------------------------------------------
# AC-B6-7/AC-B6-9: the OI row payload (list_rows and the worklist)
# ---------------------------------------------------------------------------


def test_oi_row_payload_carries_core_line_id_and_sales_order_id(api):
    """AC-B6-7/AC-B6-9. Both `list_rows` (`GET /projects/{id}/order-inquiry-rows`, the
    OI Lines tab's own feed) and the worklist (`GET /order-inquiries`) carry
    `core_line_id` (the mirror's `core_sales_order_line_id`) and `sales_order_id` on
    every row - null when the mirror has no core line at all."""
    client, world = api
    with_core = _raise_one_row(api, qty="10")
    without_core = _raise_one_row(api, qty="4", with_core_line=False)

    rows_resp = client.get(
        f"{BASE}/projects/{world.project.id}/order-inquiry-rows", params={"limit": 200}
    )
    assert rows_resp.status_code == 200, rows_resp.text
    by_id = {row["id"]: row for row in rows_resp.json()["data"]}
    with_core_out = by_id[str(with_core["row"].id)]
    assert "core_line_id" in with_core_out, with_core_out
    assert with_core_out["core_line_id"] == str(with_core["core"].id), with_core_out
    assert "sales_order_id" in with_core_out, with_core_out
    assert with_core_out["sales_order_id"] == str(with_core["core_so"].id), with_core_out
    without_core_out = by_id[str(without_core["row"].id)]
    assert without_core_out["core_line_id"] is None, without_core_out

    worklist_resp = client.get(LIST, params={"query": with_core["core_so"].so_number})
    assert worklist_resp.status_code == 200, worklist_resp.text
    worklist_row = next(
        row for row in worklist_resp.json()["data"]
        if row["id"] == str(with_core["row"].id)
    )
    assert worklist_row.get("core_line_id") == str(with_core["core"].id), worklist_row
    assert worklist_row.get("sales_order_id") == str(with_core["core_so"].id), worklist_row


# ---------------------------------------------------------------------------
# AC-B6-8/AC-B6-9: the SCM sales order line payload's `order_inquiry` dict
# ---------------------------------------------------------------------------


def test_scm_so_line_payload_carries_inquiry_id_and_row_id(api):
    """AC-B6-8/AC-B6-9. `sales_order_service.py:510`'s `order_inquiry` dict
    (`_line_inquiries`) gains `inquiry_id` and `row_id` beside `inquiry_no` - the
    destination `/project-sales/order-inquiries/<inquiry_id>?row=<row_id>` needs both,
    and `SalesOrderLineInquiry` declares neither today."""
    client, world = api
    fixture = _raise_one_row(api, qty="10")

    detail = client.get(f"/api/v1/scm/sales-orders/{fixture['core_so'].id}")
    assert detail.status_code == 200, detail.text
    lines = {ln["id"]: ln for ln in detail.json()["lines"]}
    line_out = lines[str(fixture["core"].id)]
    assert line_out["order_inquiry"] is not None, line_out
    assert "inquiry_id" in line_out["order_inquiry"], line_out["order_inquiry"]
    assert "row_id" in line_out["order_inquiry"], line_out["order_inquiry"]
    assert line_out["order_inquiry"]["row_id"] == str(fixture["row"].id), (
        line_out["order_inquiry"]
    )
    assert line_out["order_inquiry"]["inquiry_id"] == str(fixture["row"].order_inquiry_id), (
        line_out["order_inquiry"]
    )
