"""FULFIL-CONFIRM-SCOPE round 2 (Preview): `POST .../fulfilment-planning/confirm-all` with
`preview: true`.

Plan `documentation/plans/scm/PLAN-fulfil-confirm-scope-30sep.md` "Design v2" P3, UAC
`fulfil-confirm-scope-30sep-acceptance-criteria.md` AC-P1..AC-P3.

Contract: a preview runs the same per-order write as a real press and ROLLS BACK every
order instead of committing. Per order it answers `ok`, `preview: true`, `lines_confirmed`,
`lines_carried`, `lines_held_back`, `lines_fulfilled_skipped`, `decision_revision` (the
number the press WOULD write), `inquiry_rows` and `transfers`. A refused order answers
`ok: false` exactly as a real press. Asserted on the HTTP body, never the service dict,
because `response_model` silently drops an undeclared field.

RED today for the right reason: the body has no `preview` key and the route commits, so the
"writes nothing" tests find rows and the echo tests find no `inquiry_rows` / `transfers`.

Postgres via `tests/_pg_fixture.py`, fixture chain reused from
`tests/test_so_supply_confirmation.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.project_so import (
    OrderInquiryRow,
    SOSupplyDecision,
    SOSupplyDecisionDraft,
)
from app.models.stock_transfer import StockTransfer

from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _stock,
    _suffix,
    _warehouse,
    api,
)

URL = f"{BASE}/fulfilment-planning/confirm-all"


def _reserve(world, line, qty):
    return _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": str(qty)}])


def _two_line_order(world, *, pool=1000, qty_each="50"):
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=pool)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    lines = []
    for line_no in (10, 20):
        core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty_each)
        lines.append(
            _project_line(
                db, order, line_no=line_no, product=world.product, core_line=core_line
            )
        )
    db.commit()
    return order, core_so, lines


def _seed_draft(world, core_so, line):
    """A saved-but-unconfirmed draft on line 10: a real press deletes it, a preview must not."""
    db = world.db
    core_line_id = line.core_sales_order_line_id
    db.add(
        SOSupplyDecisionDraft(
            id=str(uuid.uuid4()),
            company_id=world.company_id,
            sales_order_id=str(core_so.id),
            core_line_id=core_line_id,
            line_no=line.line_no,
            item_code=world.product.product_code,
            bucket_key="2026-09-03",
            decision={"verdict": "approved"},
            saved_by=world.eling,
            saved_at=datetime(2026, 9, 3, 9, 0, 0),
        )
    )
    db.commit()


def _counts(world, order, core_so=None):
    """Row counts read through a SECOND session on the same connection, so nothing the
    request left pending in the API's own session can hide."""
    with Session(bind=world.db.get_bind(), join_transaction_mode="create_savepoint") as fresh:
        return {
            "decisions": fresh.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == order.id)
            .count(),
            "active": fresh.query(SOSupplyDecision)
            .filter(
                SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == "active",
            )
            .count(),
            "inquiry_rows": fresh.query(OrderInquiryRow).count(),
            "transfers": fresh.query(StockTransfer)
            .filter(StockTransfer.project_sales_order_id == order.id)
            .count(),
            "drafts": (
                fresh.query(SOSupplyDecisionDraft)
                .filter(SOSupplyDecisionDraft.sales_order_id == str(core_so.id))
                .count()
                if core_so is not None
                else 0
            ),
        }


def _post(client, order, lines, *, preview=None):
    body = {"orders": [{"pso_id": order.id, "lines": lines}]}
    if preview is not None:
        body["preview"] = preview
    return client.post(URL, json=body)


# --------------------------------------------------------------------------- AC-P1


def test_a_preview_writes_nothing_and_names_the_lines_it_would_confirm(api):
    """AC-P1: decisions, OI rows, transfers and drafts are all unchanged after a preview."""
    client, world = api
    order, core_so, (line_a, line_b) = _two_line_order(world)
    _seed_draft(world, core_so, line_a)
    before = _counts(world, order, core_so)
    assert before["drafts"] == 1 and before["decisions"] == 0

    response = _post(
        client,
        order,
        [_line_payload(line_a.id, buy_qty="50"), _line_payload(line_b.id, buy_qty="50")],
        preview=True,
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True, result
    assert result["preview"] is True
    assert result["decision_revision"] == 1
    assert [row["line_no"] for row in result["lines_confirmed"]] == [10, 20]
    assert _counts(world, order, core_so) == before
    assert _counts(world, order, core_so)["active"] == 0


# --------------------------------------------------------------------------- AC-P2


def test_a_buy_line_previews_an_order_inquiry_row(api):
    client, world = api
    order, _core_so_row, (line_a, line_b) = _two_line_order(world)

    response = _post(
        client,
        order,
        [_line_payload(line_a.id, buy_qty="50"), _line_payload(line_b.id, buy_qty="50")],
        preview=True,
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    rows = result["inquiry_rows"]
    assert {row["line_no"] for row in rows} == {10, 20}
    for row in rows:
        assert row["verb"] == "ORDER"
        assert row["item_code"] == world.product.product_code
        assert float(row["qty"]) == 50.0
        assert row["stock_location"] == world.own_wh.warehouse_code
        assert {"delivery_date", "note"} <= set(row)
    assert result["transfers"] == []


def test_a_borrow_line_previews_a_borrow_transfer(api):
    """AC-P2: a borrow from another location previews one `transfers` entry with the
    from and to warehouse codes, qty and kind, and nothing is written."""
    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-DNR-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()
    before = _counts(world, order)

    payload = [
        _line_payload(
            line.id,
            borrow=[
                {
                    "source": "other_location",
                    "warehouse_id": donor_wh.id,
                    "qty": "20",
                    "reason": "Their hand-over is in December.",
                }
            ],
        )
    ]
    response = _post(client, order, payload, preview=True)

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True, result
    assert len(result["transfers"]) == 1, result
    move = result["transfers"][0]
    assert move["kind"] == "borrow"
    assert float(move["qty"]) == 20.0
    assert move["line_no"] == 10
    assert move["from_location"] == donor_wh.warehouse_code
    assert move["to_location"] == world.own_wh.warehouse_code
    assert _counts(world, order) == before


# --------------------------------------------------------------------------- AC-P3


def test_the_real_press_writes_exactly_what_the_preview_said(api):
    client, world = api
    order, _core_so_row, (line_a, line_b) = _two_line_order(world)
    lines = [_reserve(world, line_a, 50), _line_payload(line_b.id, buy_qty="50")]

    preview = _post(client, order, lines, preview=True)
    assert preview.status_code == 200, preview.text
    previewed = preview.json()["results"][0]
    assert previewed["ok"] is True, previewed
    assert previewed["preview"] is True

    press = _post(client, order, lines, preview=False)
    assert press.status_code == 200, press.text
    pressed = press.json()["results"][0]
    assert pressed["ok"] is True, pressed
    assert pressed.get("preview") is not True

    assert pressed["lines_confirmed"] == previewed["lines_confirmed"]
    assert pressed["decision_revision"] == previewed["decision_revision"]
    assert pressed["inquiry_rows_created"] == len(previewed["inquiry_rows"])
    assert pressed["transfers_written"] == len(previewed["transfers"])
    assert pressed["transfers_written"] == 1


# --------------------------------------------------------------------------- hold-back parity


def test_a_preview_reports_the_held_back_line_the_press_would_drop_and_writes_nothing(api):
    """Pool holds 50, two lines of 50 each reserve all 50: the second is held back."""
    client, world = api
    order, _core_so_row, (line_a, line_b) = _two_line_order(world, pool=50, qty_each="50")
    before = _counts(world, order)

    response = _post(
        client, order, [_reserve(world, line_a, 50), _reserve(world, line_b, 50)], preview=True
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True, result
    assert result["preview"] is True
    assert [row["line_no"] for row in result["lines_confirmed"]] == [10]
    assert [row["line_no"] for row in result["lines_held_back"]] == [20]
    assert _counts(world, order) == before


# --------------------------------------------------------------------------- refusal + schema


def test_a_refused_order_answers_ok_false_in_preview_as_a_real_press_does(api):
    client, world = api
    order, _core_so_row, (line_a, line_b) = _two_line_order(world)
    other = _project_so(world.db, world.project)
    world.db.commit()

    # `line_a` belongs to `order`, not `other`: "not on this sales order".
    response = client.post(
        URL,
        json={
            "orders": [{"pso_id": other.id, "lines": [_line_payload(line_a.id, buy_qty="50")]}],
            "preview": True,
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is False, result
    assert result["preview"] is True
    assert result.get("error")
    assert any(
        "not on this sales order" in (row.get("reason") or "")
        for row in (result.get("failing_lines") or [])
    ), result


def test_preview_false_behaves_exactly_as_a_plain_press(api):
    """Schema: `preview: false` is today's press, and commits."""
    client, world = api
    order, _core_so_row, (line_a, _line_b) = _two_line_order(world)

    response = _post(client, order, [_reserve(world, line_a, 50)], preview=False)

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True, result
    assert result["decision_revision"] == 1
    assert result["lines_decided"] == 1
    assert result["transfers_written"] == 1
    assert result.get("preview") in (None, False)
    assert _counts(world, order)["active"] == 1
