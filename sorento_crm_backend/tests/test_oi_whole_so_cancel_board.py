"""OI-WHOLE-SO-CANCEL AC-WC-9, red tests: the pending `cancelled` planning-change rows a
header-cancel push / an SO delete raise must be REACHABLE by CS on Fulfilment Planning.

Browser pass finding: the rows exist but the ORDER LIST does not list the SO and the BOARD
returns no cells for it, so there is no Confirm. Backend cause: the board service filters
`SalesOrder.status IN ('open', 'closed')`, and both events leave the header `cancelled`.

Endpoints (BASE /api/v1/project-sales), all driven through `env.client`:
  list    GET  /fulfilment-planning?query=<so_number>        field `planning_change_batch_id`
  board   GET  /fulfilment-planning/board?orders=<so_number> cells[].contributions[]
                                                              .cancelled / .pending_change_batch_id
  confirm POST /sales-orders/{pso_id}/confirm  {"lines": [], "batch_id": <batch>}

Seed gaps the browser pass hit, seeded here: demand_class = 'project' on the core SO (so
`admitted_to_planning` admits it), a warehouse on the lines. (`tenant_modules` has no rows on
the blank schema, which the module guard treats as "all enabled".)

Postgres only, every test seeds its own chain. No real names, phones, emails or prices.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.inventory import Warehouse

from .test_ac_removed_lines_ingest import (  # noqa: F401 - fixtures/helpers reused
    ACK_AWAITING,
    INQUIRY_RAISED,
    _captured_dispatches,
    _push_so,
    _so_mirror_row,
    _three_rows_on_x,
    env,
)
from .test_oi_whole_so_cancel import (
    _assert_rows_cancelled_once_and_one_cancel_mail,
    _cancelled_rows,
    _delete_so,
    _header_cancel_push,
)
from .test_ac_removed_lines_ingest import _register

BASE = "/api/v1/project-sales"


# --------------------------------------------------------------------------- helpers
def _seed_planning_gaps(env, header, mirror):
    """demand_class 'project' on the core SO, a warehouse on every line."""
    wh = Warehouse(
        warehouse_code=f"ZZTWC{uuid.uuid4().hex[:6]}",
        warehouse_name="ZZT wc depot",
        company_id=env.company_a,
    )
    env.db.add(wh)
    env.db.flush()
    env.db.execute(
        text("UPDATE sales_orders SET demand_class = 'project' WHERE id = :i"),
        {"i": str(header["id"])},
    )
    env.db.execute(
        text("UPDATE sales_order_lines SET warehouse_id = :w WHERE sales_order_id = :i"),
        {"w": str(wh.id), "i": str(header["id"])},
    )
    env.db.commit()
    env.db.expire_all()


def _world(env, how):
    """Push two lines, a live OI row on x, then cancel the whole SO by `how`
    ('push' = header-cancel push, 'delete' = DELETE ingest). Returns a dict."""
    record, header, line_x, y, rows = _three_rows_on_x(env)
    mirror, _inquiry_id = _so_mirror_row.last
    _seed_planning_gaps(env, header, mirror)
    if how == "push":
        _header_cancel_push(env, record, y)
    else:
        _delete_so(env, record)
    pso_id = str(mirror.project_sales_order_id)
    return {
        "so_number": record["so_number"],
        "line_x": str(line_x["id"]),
        "rows": rows,
        "pso_id": pso_id,
    }


def _list_hits(env, w):
    res = env.client.get(f"{BASE}/fulfilment-planning", params={"query": w["so_number"]})
    assert res.status_code == 200, res.text
    return [r for r in res.json()["data"] if r.get("so_number") == w["so_number"]]


def _board(env, w):
    res = env.client.get(f"{BASE}/fulfilment-planning/board", params={"orders": w["so_number"]})
    assert res.status_code == 200, res.text
    return res.json()


def _contributions_for_line(body, line_id):
    return [c for c in body.get("contributions", []) if c.get("line_id") == line_id]


def _assert_listed_with_pending_batch(env, w):
    hits = _list_hits(env, w)
    assert len(hits) == 1, f"the cancelled SO is missing from the order list: {hits}"
    assert hits[0]["planning_change_batch_id"], hits[0]


def _assert_board_cell_cancelled_with_batch(env, w):
    body = _board(env, w)
    assert body["cells"], f"no cells on the board: {body.get('unplanned_orders')}"
    contribs = _contributions_for_line(body, w["line_x"])
    assert len(contribs) == 1, contribs
    assert contribs[0]["cancelled"] is True, contribs[0]
    batch = _cancelled_rows(env, w["line_x"])[0].batch_id
    assert contribs[0]["pending_change_batch_id"] == str(batch), contribs[0]


def _confirm_through_the_board_route(env, monkeypatch, w):
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    batch_id = str(_cancelled_rows(env, w["line_x"])[0].batch_id)
    _register(None)
    calls = _captured_dispatches(monkeypatch)
    mark_purchasing_email_trigger(env.db)
    env.db.commit()
    res = env.client.post(
        f"{BASE}/sales-orders/{w['pso_id']}/confirm", json={"lines": [], "batch_id": batch_id}
    )
    assert res.status_code == 200, res.text
    env.db.expire_all()
    return calls


# ============================================================================ AC-WC-9 (a)
def test_ac_wc_9a_the_order_list_shows_a_header_cancelled_so_with_its_pending_change(env):
    _assert_listed_with_pending_batch(env, _world(env, "push"))


def test_ac_wc_9a_the_order_list_shows_a_deleted_so_with_its_pending_change(env):
    _assert_listed_with_pending_batch(env, _world(env, "delete"))


# ============================================================================ AC-WC-9 (b)
def test_ac_wc_9b_the_board_shows_each_line_of_a_header_cancelled_so_as_cancelled(env):
    _assert_board_cell_cancelled_with_batch(env, _world(env, "push"))


def test_ac_wc_9b_the_board_shows_each_line_of_a_deleted_so_as_cancelled(env):
    _assert_board_cell_cancelled_with_batch(env, _world(env, "delete"))


# ============================================================================ AC-WC-9 (c)
def test_ac_wc_9c_the_board_confirm_retires_the_rows_after_a_header_cancel_push(
    env, monkeypatch
):
    w = _world(env, "push")
    calls = _confirm_through_the_board_route(env, monkeypatch, w)
    _assert_rows_cancelled_once_and_one_cancel_mail(env, w["rows"], calls)


def test_ac_wc_9c_the_board_confirm_retires_the_rows_after_an_so_delete(env, monkeypatch):
    w = _world(env, "delete")
    calls = _confirm_through_the_board_route(env, monkeypatch, w)
    _assert_rows_cancelled_once_and_one_cancel_mail(env, w["rows"], calls)
