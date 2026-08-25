"""Stock transfers (`PLAN-scm-cs-planning-uat.md` section E, UAC AC-E1 to AC-E5, AC-F1).

The captain, walking SO415472 on 25 Aug: "after Approve, stock taken from BRW - or
borrowed from anywhere else - has to physically move to the line's location. Nothing today
says so." So: a confirmation writes one `proposed` transfer per decided component drawn
from somewhere other than the line's own location, a reconfirm cancels the open ones and
writes fresh, a same-location component writes nothing, and NOTHING about demand or supply
moves as a result.

Postgres via `tests/_pg_fixture.py`, never sqlite. The seed helpers come from
`test_so_supply_confirmation` - the same chain (company, project, project SO, lines linked
to a real core SO + lines, warehouses, stock), seeded fresh per test rather than borrowed
off an existing row, because CI's database is empty.

The netting proof (AC-E4) runs on `pg_session` rather than `blank_session`: `scm.committed_v`
and `scm.on_order_v` are installed by a migration and do not exist in the scratch schema.
Same split, same reason, as `test_order_inquiry_place_on_po.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.project_so import SOSupplyDecision
from app.models.stock_transfer import StockTransfer
from app.services import project_seed_service

from ._pg_fixture import blank_session, pg_session
from .test_so_supply_confirmation import (
    _client,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _restore,
    _second_company,
    _sorento,
    _stock,
    _suffix,
    _user,
    _warehouse,
)

MARKER = "zzt-transfer"
BASE = "/api/v1/project-sales"
TRANSFERS = "/api/v1/inventory/stock-transfers"


def _uid() -> str:
    return str(uuid.uuid4())


class _World:
    def __init__(self, db, company_id, eling, project, product, own_wh, pool_wh, sibling_wh):
        self.db = db
        self.company_id = company_id
        self.eling = eling
        self.project = project
        self.product = product
        self.own_wh = own_wh
        self.pool_wh = pool_wh
        self.sibling_wh = sibling_wh


@pytest.fixture()
def api():
    """The confirmation world, plus a GROUP SIBLING at another site.

    Codes are shaped the way the real ones are - `ZZTA-BB` is the line's own location and
    `ZZTB-BB` its sibling in the same ownership group, `ZZTP` a plain site pool - because
    the kind a transfer carries is read off the group suffix whenever the component was
    frozen without a rung.
    """
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        eling = _user(db, f"{MARKER} Eling")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=eling,
            developer_party_id=None,
            title=f"{MARKER} Tuju Residences",
        )
        product = _product(db)
        stem = _suffix()
        own_wh = _warehouse(db, f"ZZT{stem}A-BB", segment="project")
        sibling_wh = _warehouse(db, f"ZZT{stem}B-BB", segment="project")
        pool_wh = _warehouse(db, f"ZZT{stem}P", segment="dealer")
        own_wh.pool_warehouse_id = pool_wh.id
        sibling_wh.pool_warehouse_id = pool_wh.id
        db.flush()
        db.commit()
        client, originals = _client(db, eling)
        world = _World(db, company_id, eling, project, product, own_wh, pool_wh, sibling_wh)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, world
        finally:
            _restore(originals)


def _one_line_order(world, *, qty="71"):
    """A published project SO with one line, at the line's OWN location."""
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()
    return order, core_so, core_line, line


def qty_of(row) -> Decimal:
    return Decimal(str(row.qty)).normalize()


def _transfers(db, order_id):
    return (
        db.query(StockTransfer)
        .filter(StockTransfer.project_sales_order_id == order_id)
        .order_by(StockTransfer.transfer_no)
        .all()
    )


# --------------------------------------------------------------------- AC-E1 the writer


def test_a_pool_reserve_on_a_bb_line_writes_one_proposed_transfer(api):
    """AC-E1: "71 from the pool" on a `-BB` line becomes pool -> own, 71, proposed,
    linked to the SO line and to the decision."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    order, _core_so, core_line, line = _one_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert response.status_code == 200, response.text

    rows = _transfers(db, order.id)
    assert len(rows) == 1
    transfer = rows[0]
    assert transfer.state == "proposed"
    assert transfer.kind == "pool"
    assert Decimal(transfer.qty) == Decimal("71")
    assert str(transfer.from_warehouse_id) == str(world.pool_wh.id)
    assert str(transfer.to_warehouse_id) == str(world.own_wh.id)
    assert str(transfer.so_line_id) == str(core_line.id)
    assert transfer.transfer_no.startswith("TR-")
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    assert str(transfer.supply_decision_id) == str(decision.id)


def test_a_group_sibling_reserve_is_an_own_group_transfer(api):
    """AC-F1's shape: `DC1-BB -> BRW-BB` is the agent's own group, not the pool."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.sibling_wh, on_hand=500)
    order, _core_so, _core_line, line = _one_line_order(world, qty="40")

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id, reserve=[{"warehouse_id": world.sibling_wh.id, "qty": "40"}]
                )
            ]
        },
    )
    assert response.status_code == 200, response.text

    rows = _transfers(db, order.id)
    assert len(rows) == 1
    assert rows[0].kind == "own_group"
    assert str(rows[0].from_warehouse_id) == str(world.sibling_wh.id)
    assert str(rows[0].to_warehouse_id) == str(world.own_wh.id)


def test_a_reserve_at_the_lines_own_location_writes_no_transfer(api):
    """Stock already where it has to be moves nowhere, so nothing is instructed."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=500)
    order, _core_so, _core_line, line = _one_line_order(world, qty="25")

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "25"}])
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert _transfers(db, order.id) == []


def test_a_whole_line_buy_writes_no_transfer(api):
    """Nothing is held anywhere yet, so there is nothing to carry."""
    client, world = api
    db = world.db
    order, _core_so, _core_line, line = _one_line_order(world, qty="30")

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="30", buy_reason="nothing free")]},
    )
    assert response.status_code == 200, response.text
    assert _transfers(db, order.id) == []


def test_numbers_run_consecutively_within_one_confirmation(api):
    """Two moves on one confirmation take two consecutive `TR-` numbers, minted off the
    flush's own connection like `OI-`."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    _stock(db, world.product, world.sibling_wh, on_hand=500)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    core_b = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line_a = _project_line(db, order, line_no=10, product=world.product, core_line=core_a)
    line_b = _project_line(db, order, line_no=20, product=world.product, core_line=core_b)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]
                ),
                _line_payload(
                    line_b.id, reserve=[{"warehouse_id": world.sibling_wh.id, "qty": "20"}]
                ),
            ]
        },
    )
    assert response.status_code == 200, response.text

    numbers = [row.transfer_no for row in _transfers(db, order.id)]
    assert len(numbers) == 2
    assert len(set(numbers)) == 2
    tails = sorted(int(n[len("TR-"):]) for n in numbers)
    assert tails[1] == tails[0] + 1


# ----------------------------------------------------------------- AC-E3 the reconfirm


def test_reconfirm_cancels_the_open_transfers_and_writes_fresh_ones(api):
    """AC-E3: superseding a revision calls off what it asked for, naming the revision that
    replaced it, and the new revision's own moves are written beside them."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    _stock(db, world.product, world.sibling_wh, on_hand=500)
    order, _core_so, _core_line, line = _one_line_order(world, qty="71")

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert first.status_code == 200, first.text
    original = _transfers(db, order.id)
    assert len(original) == 1

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id, reserve=[{"warehouse_id": world.sibling_wh.id, "qty": "71"}]
                )
            ]
        },
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    rows = _transfers(db, order.id)
    assert len(rows) == 2
    cancelled = [r for r in rows if r.state == "cancelled"]
    live = [r for r in rows if r.state == "proposed"]
    assert len(cancelled) == 1 and len(live) == 1
    assert cancelled[0].cancelled_reason == "Superseded by revision 2"
    assert str(cancelled[0].from_warehouse_id) == str(world.pool_wh.id)
    assert str(live[0].from_warehouse_id) == str(world.sibling_wh.id)
    assert live[0].kind == "own_group"


def test_a_carried_line_keeps_a_live_transfer_after_an_unrelated_reconfirm(api):
    """A line the second confirmation did not name is carried forward verbatim, so the
    movement it still implies is rewritten rather than lost with the cancelled revision."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    core_b = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line_a = _project_line(db, order, line_no=10, product=world.product, core_line=core_a)
    line_b = _project_line(db, order, line_no=20, product=world.product, core_line=core_b)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]
                )
            ]
        },
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "20"}]
                )
            ]
        },
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    live = [r for r in _transfers(db, order.id) if r.state == "proposed"]
    assert sorted(Decimal(r.qty) for r in live) == [Decimal("10"), Decimal("20")], (
        "the carried line's move must be rewritten under the new revision, not dropped"
    )


def test_a_moved_transfer_survives_a_reconfirm(api):
    """Stock that has physically moved is history: a supersede cancels the paperwork of
    what has NOT happened, never of what has."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    order, _core_so, _core_line, line = _one_line_order(world, qty="71")

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert first.status_code == 200, first.text
    transfer = _transfers(db, order.id)[0]

    assert client.post(f"{TRANSFERS}/{transfer.id}/approve").status_code == 200
    moved = client.post(
        f"{TRANSFERS}/{transfer.id}/mark-moved", json={"autocount_ref": "ZZT-TR-9001"}
    )
    assert moved.status_code == 200, moved.text

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="71", buy_reason="changed mind")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    kept = db.query(StockTransfer).filter(StockTransfer.id == transfer.id).one()
    assert kept.state == "moved"
    assert kept.cancelled_reason is None


# ---------------------------------------------- AC-E3b: stock that has already moved


def _move(client, transfer_id, ref="ZZT-TR-MOVED"):
    assert client.post(f"{TRANSFERS}/{transfer_id}/approve").status_code == 200
    moved = client.post(f"{TRANSFERS}/{transfer_id}/mark-moved", json={"autocount_ref": ref})
    assert moved.status_code == 200, moved.text


def test_a_carried_line_whose_transfer_already_moved_raises_no_second_one(api):
    """The blocker: a line carried through an unrelated reconfirm re-proposed a movement
    the warehouse had already made, so the stock would have been carried twice."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    core_b = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line_a = _project_line(db, order, line_no=10, product=world.product, core_line=core_a)
    line_b = _project_line(db, order, line_no=20, product=world.product, core_line=core_b)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]
                )
            ]
        },
    )
    assert first.status_code == 200, first.text
    _move(client, _transfers(db, order.id)[0].id)

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "20"}]
                )
            ]
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["transfers_written"] == 1, "line B's move, and line A's not again"

    db.expire_all()
    rows = _transfers(db, order.id)
    assert len(rows) == 2
    assert sorted((r.state, qty_of(r)) for r in rows) == [
        ("moved", Decimal("10")),
        ("proposed", Decimal("20")),
    ]


def test_reconfirming_the_same_composition_after_a_move_raises_nothing(api):
    """Same line, same source, same quantity, already carried: nothing left to move."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so, _core_line_row, line = _one_line_order(world, qty="71")

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert first.status_code == 200, first.text
    _move(client, _transfers(db, order.id)[0].id)

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["transfers_written"] == 0

    db.expire_all()
    rows = _transfers(db, order.id)
    assert len(rows) == 1
    assert rows[0].state == "moved"


def test_a_larger_quantity_after_a_move_raises_the_difference_only(api):
    """71 moved, then the book grows the line to 100: the warehouse is asked for the 29 it
    has not carried, never for the whole 100 again."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so, core_line, line = _one_line_order(world, qty="71")

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert first.status_code == 200, first.text
    _move(client, _transfers(db, order.id)[0].id)

    # The book comes back with the line grown, which is the case that produces a bigger
    # composition over stock that has already been carried.
    core_line.qty_ordered = Decimal("100")
    line.qty = Decimal("100")
    db.flush()
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "100"}]
                )
            ]
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["transfers_written"] == 1

    db.expire_all()
    rows = _transfers(db, order.id)
    assert sorted((r.state, qty_of(r)) for r in rows) == [
        ("moved", Decimal("71")),
        ("proposed", Decimal("29")),
    ]


def test_the_supersede_sweeps_every_open_row_on_the_order_not_only_the_last_revisions(api):
    """Item 2: keyed on the ORDER. A row left open under an older revision - which is what
    a failed best-effort write leaves behind - must not survive a later confirmation."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so, _core_line_row, line = _one_line_order(world, qty="71")

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert first.status_code == 200, first.text
    stranded = _transfers(db, order.id)[0]
    # A row from a revision two supersedes ago, as a failed write would have left it.
    stranded.supply_decision_id = None
    db.flush()
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="71", buy_reason="changed mind")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    kept = db.query(StockTransfer).filter(StockTransfer.id == stranded.id).one()
    assert kept.state == "cancelled"
    assert kept.cancelled_reason == "Superseded by revision 2"


def test_the_confirm_result_says_how_many_movements_it_raised(api):
    """Item 3: the count is on the WIRE, so a planner is told rather than a server log."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so, _core_line_row, line = _one_line_order(world, qty="71")

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transfers_written"] == 1
    assert body["transfers_failed"] == 0


def test_a_failed_transfer_write_is_reported_rather_than_swallowed(api, monkeypatch):
    """The confirmation still succeeds - the promise is already made - but the planner is
    told how many movements went unwritten."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so, _core_line_row, line = _one_line_order(world, qty="71")

    from app.services import stock_transfer_service

    def _boom(*_args, **_kwargs):
        raise RuntimeError("zzt-transfer-write-failed")

    monkeypatch.setattr(stock_transfer_service, "write_for_decision", _boom)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision_no"] == 1, "the promise itself still stands"
    assert body["transfers_written"] == 0
    assert body["transfers_failed"] == 1

    db.expire_all()
    assert _transfers(db, order.id) == []


# ---------------------------------------------------------------- the state machine


@pytest.fixture()
def one_transfer(api):
    """A world plus a single `proposed` transfer to push around the state machine."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    order, _core_so, _core_line, line = _one_line_order(world, qty="71")
    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert response.status_code == 200, response.text
    return client, world, _transfers(db, order.id)[0]


def test_approve_then_mark_moved_walks_the_states(one_transfer):
    """AC-E5: approve is deliberate, mark moved asks for the AutoCount reference, and
    nothing closes on its own."""
    client, world, transfer = one_transfer

    approved = client.post(f"{TRANSFERS}/{transfer.id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    assert approved.json()["approved_at"] is not None
    assert approved.json()["approved_by_name"] is not None

    moved = client.post(
        f"{TRANSFERS}/{transfer.id}/mark-moved", json={"autocount_ref": "ZZT-TR-1234"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["state"] == "moved"
    assert moved.json()["autocount_ref"] == "ZZT-TR-1234"
    assert moved.json()["moved_at"] is not None


def test_marking_a_proposed_transfer_moved_is_refused(one_transfer):
    """Approval is the point: skipping it would make the deliberate step optional."""
    client, _world, transfer = one_transfer
    response = client.post(
        f"{TRANSFERS}/{transfer.id}/mark-moved", json={"autocount_ref": "ZZT-TR-1"}
    )
    assert response.status_code == 422, response.text
    assert transfer.transfer_no in response.json()["message"]


def test_mark_moved_without_an_autocount_ref_is_refused(one_transfer):
    client, _world, transfer = one_transfer
    assert client.post(f"{TRANSFERS}/{transfer.id}/approve").status_code == 200
    response = client.post(f"{TRANSFERS}/{transfer.id}/mark-moved", json={"autocount_ref": "  "})
    assert response.status_code == 422, response.text


def test_cancelling_needs_a_reason_and_then_refuses_everything_after(one_transfer):
    client, _world, transfer = one_transfer

    assert client.post(f"{TRANSFERS}/{transfer.id}/cancel", json={"reason": ""}).status_code == 422

    cancelled = client.post(
        f"{TRANSFERS}/{transfer.id}/cancel", json={"reason": "Customer took it from stock"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["cancelled_reason"] == "Customer took it from stock"

    assert client.post(f"{TRANSFERS}/{transfer.id}/approve").status_code == 422


def test_a_moved_transfer_cannot_be_cancelled(one_transfer):
    client, _world, transfer = one_transfer
    assert client.post(f"{TRANSFERS}/{transfer.id}/approve").status_code == 200
    assert (
        client.post(
            f"{TRANSFERS}/{transfer.id}/mark-moved", json={"autocount_ref": "ZZT-TR-7"}
        ).status_code
        == 200
    )
    response = client.post(f"{TRANSFERS}/{transfer.id}/cancel", json={"reason": "too late"})
    assert response.status_code == 422, response.text


def test_bulk_approve_approves_what_it_can_and_names_what_it_skipped(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    lines = []
    for index, qty in enumerate(("10", "20"), start=1):
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty)
        lines.append(
            (
                _project_line(
                    db, order, line_no=index * 10, product=world.product, core_line=core
                ),
                qty,
            )
        )
    db.commit()
    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": qty}])
                for line, qty in lines
            ]
        },
    )
    assert response.status_code == 200, response.text
    rows = _transfers(db, order.id)
    assert len(rows) == 2

    cancelled = client.post(
        f"{TRANSFERS}/{rows[0].id}/cancel", json={"reason": "handled another way"}
    )
    assert cancelled.status_code == 200, cancelled.text

    bulk = client.post(
        f"{TRANSFERS}/bulk-approve", json={"ids": [str(rows[0].id), str(rows[1].id)]}
    )
    assert bulk.status_code == 200, bulk.text
    body = bulk.json()
    assert body["approved"] == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["transfer_no"] == rows[0].transfer_no
    assert "cancelled" in body["skipped"][0]["reason"].lower()


def test_bulk_approve_refuses_a_malformed_id_and_an_oversized_selection(api):
    """A bad id is a client bug worth naming, not a row that "does not exist"; a body
    longer than a page is not a selection."""
    client, _world = api

    bad = client.post(f"{TRANSFERS}/bulk-approve", json={"ids": ["not-a-uuid"]})
    assert bad.status_code == 422, bad.text

    too_many = client.post(
        f"{TRANSFERS}/bulk-approve", json={"ids": [_uid() for _ in range(201)]}
    )
    assert too_many.status_code == 422, too_many.text

    empty = client.post(f"{TRANSFERS}/bulk-approve", json={"ids": []})
    assert empty.status_code == 422, empty.text


def test_cancelling_records_who_did_it(one_transfer):
    """Item 9: History names the person, not only the reason."""
    client, _world, transfer = one_transfer

    cancelled = client.post(
        f"{TRANSFERS}/{transfer.id}/cancel", json={"reason": "Customer collected it"}
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["cancelled_by"] is not None
    assert body["cancelled_by_name"] is not None
    assert body["cancelled_at"] is not None


def test_the_route_sort_literal_matches_the_service(api):
    """The two are written twice because FastAPI cannot build a `Literal` from a runtime
    set, so a test keeps them equal - the same guard the order-inquiry worklist has."""
    from typing import get_args

    from app.api.v1.inventory.stock_transfers import TransferSort
    from app.services.stock_transfer_service import SORTABLE_FIELDS

    assert set(get_args(TransferSort)) == set(SORTABLE_FIELDS)


# ------------------------------------------------------------------- the list and filters


def test_the_list_carries_every_declared_field_on_the_wire(one_transfer):
    """`response_model` drops what the schema does not name, and a dropped column renders
    blank with no error anywhere - so the fields are asserted on the wire."""
    client, world, transfer = one_transfer
    response = client.get(TRANSFERS, params={"query": transfer.transfer_no})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 1
    row = data[0]
    for field in (
        "id",
        "transfer_no",
        "state",
        "kind",
        "qty",
        "product_id",
        "item_code",
        "product_name",
        "from_warehouse_id",
        "from_location",
        "to_warehouse_id",
        "to_location",
        "sales_order_id",
        "so_number",
        "so_line_no",
        "project_sales_order_id",
        "supply_decision_id",
        "revision_no",
        "proposed_at",
        "autocount_ref",
        "approved_by_name",
        "moved_by_name",
        "cancelled_by",
        "cancelled_by_name",
        "cancelled_at",
        "cancelled_reason",
    ):
        assert field in row, f"{field} was dropped by the response model"
    assert row["item_code"] == world.product.product_code
    assert row["from_location"] == world.pool_wh.warehouse_code
    assert row["to_location"] == world.own_wh.warehouse_code
    assert row["so_line_no"] == 10
    assert row["revision_no"] == 1
    assert row["kind"] == "pool"


def test_the_list_filters_by_state_warehouse_product_and_sales_order(one_transfer):
    client, world, transfer = one_transfer
    detail = client.get(f"{TRANSFERS}/{transfer.id}")
    assert detail.status_code == 200, detail.text
    sales_order_id = detail.json()["sales_order_id"]

    def ids(**params):
        response = client.get(TRANSFERS, params=params)
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()["data"]}

    assert str(transfer.id) in ids(state="proposed")
    assert str(transfer.id) not in ids(state="moved")
    assert str(transfer.id) in ids(from_warehouse_id=str(world.pool_wh.id))
    assert str(transfer.id) not in ids(from_warehouse_id=str(world.own_wh.id))
    assert str(transfer.id) in ids(to_warehouse_id=str(world.own_wh.id))
    assert str(transfer.id) in ids(product_id=str(world.product.id))
    assert str(transfer.id) in ids(sales_order_id=sales_order_id)
    assert str(transfer.id) in ids(kind="pool")
    assert str(transfer.id) not in ids(kind="borrow")


def test_the_search_box_matches_the_sales_order_and_the_agent(one_transfer):
    """The SO and the AGENT are reached by typing rather than by a select: the page's
    audience is the warehouse, and a select over either master would need a permission a
    warehouse role does not hold."""
    client, world, transfer = one_transfer
    db = world.db

    from app.models.order import SalesOrder, SalesOrderLine
    from app.models.sales_agent import SalesAgent

    agent = SalesAgent(
        id=_uid(), sales_agent=f"ZZTAG{_suffix()}", person_label=f"{MARKER} Cyndi"
    )
    db.add(agent)
    db.flush()
    line = (
        db.query(SalesOrderLine).filter(SalesOrderLine.id == transfer.so_line_id).one()
    )
    order = db.query(SalesOrder).filter(SalesOrder.id == line.sales_order_id).one()
    order.sales_agent_id = agent.id
    db.flush()
    db.commit()

    def ids(**params):
        response = client.get(TRANSFERS, params=params)
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()["data"]}

    assert str(transfer.id) in ids(query=order.so_number)
    assert str(transfer.id) in ids(query=agent.sales_agent)
    assert str(transfer.id) in ids(sales_agent_id=str(agent.id))


def test_a_missing_transfer_is_a_404(api):
    client, _world = api
    assert client.get(f"{TRANSFERS}/{_uid()}").status_code == 404


def test_another_companys_transfer_is_invisible(api):
    """Company scope is the session's, not the query's: a row stamped to another company
    must not appear on this one's page (AC on multi-company isolation)."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=500)
    order, _core_so, _core_line, line = _one_line_order(world, qty="71")
    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])
            ]
        },
    )
    assert response.status_code == 200, response.text
    transfer = _transfers(db, order.id)[0]

    other = _second_company(db)
    transfer.company_id = other
    db.flush()
    db.commit()

    listed = client.get(TRANSFERS, params={"query": transfer.transfer_no})
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == []
    assert client.get(f"{TRANSFERS}/{transfer.id}").status_code == 404


# ------------------------------------------------------------------------- AC-E4 netting


def test_transfers_leave_committed_and_on_order_exactly_where_they_were():
    """AC-E4: a transfer is neither demand nor supply. Totals before and after the
    confirmation that raised six of them are identical.

    On `pg_session` because `scm.committed_v` / `scm.on_order_v` are migration-installed
    views that the scratch schema does not carry.
    """
    from app.services.project_seed_service import seed_numbering_rule
    from app.services.project_service import register_project
    from app.services.project_supply_service import ProjectSupplyService

    with pg_session() as db:
        company_id = _sorento(db)
        seed_numbering_rule(db)
        actor = _user(db, f"{MARKER} Planner")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=actor,
            developer_party_id=None,
            title=f"{MARKER} Netting Residences",
        )
        product = _product(db)
        stem = _suffix()
        own_wh = _warehouse(db, f"ZZT{stem}A-BB", segment="project")
        pool_wh = _warehouse(db, f"ZZT{stem}P", segment="dealer")
        own_wh.pool_warehouse_id = pool_wh.id
        db.flush()
        _stock(db, product, pool_wh, on_hand=500)

        core_so = _core_so(db, company_id)
        core_line = _core_line(db, core_so, product, own_wh, qty_ordered="71")
        order = _project_so(db, project, so_id=core_so.id)
        line = _project_line(db, order, line_no=10, product=product, core_line=core_line)
        db.commit()

        def totals():
            committed = db.execute(
                text(
                    "SELECT COALESCE(SUM(project_confirmed_committed), 0) "
                    "FROM scm.committed_v WHERE product_id = :pid"
                ),
                {"pid": product.id},
            ).scalar()
            on_order = db.execute(
                text(
                    "SELECT COALESCE(SUM(on_order), 0) "
                    "FROM scm.on_order_v WHERE product_id = :pid"
                ),
                {"pid": product.id},
            ).scalar()
            return Decimal(str(committed)), Decimal(str(on_order))

        before = totals()

        class _Item:
            def __init__(self, warehouse_id, qty):
                self.warehouse_id = warehouse_id
                self.qty = qty

        class _Entry:
            def __init__(self, project_line_id):
                self.project_line_id = project_line_id
                self.timely_spo_qty = "0"
                self.reserve = [_Item(pool_wh.id, "71")]
                self.borrow = []
                self.buy_qty = "0"
                self.buy_reason = None
                self.amend_reason = None

        class _Payload:
            def __init__(self, lines):
                self.lines = lines
                self.as_of = None

        with company_scope(db, frozenset({company_id})):
            ProjectSupplyService(db).confirm(
                order, _Payload([_Entry(line.id)]), actor_user_id=actor
            )
        db.commit()

        db.expire_all()
        assert _transfers(db, order.id), "the confirmation must have raised a transfer"
        assert totals() == before, (
            "a stock transfer is neither demand nor supply: committed_v and on_order_v "
            "must read exactly as they did before it existed"
        )
