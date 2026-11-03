"""DEALER-AT-PROJECT-BIN (owner ruling 3 Nov 2026): a Dealer/Other order's line at a project bin
that is IN fulfilment planning is decided like any other line.

Plan: `documentation/plans/scm/PLAN-dealer-at-project-bin-3nov.md`. Card answers (crew, 3 Nov):
Q1 (a) the order inquiry routes by the sales order's class, Q2 (a) the line walks the project
bin's own ladder; owner, Q3 (b): a Dealer/Other order with a line at an active planning-ON project
bin is admitted, so such an order is on the board even with no dealer-bin line. What stays refused: a project bin that is active with planning switched OFF,
whatever the order's class.

Written test-first: on main every test of the planning-ON case fails with the
`Outside fulfilment planning` verdict, which the retail-class clause put on every project bin.
Postgres only, every test seeds its own chain.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.project_so import OrderInquiry, OrderInquiryRow
from app.services.scm.planning_predicate import (
    OUTSIDE_FULFILMENT_PLANNING,
    outside_fulfilment_planning,
)

from ..test_so_supply_confirmation import (  # noqa: F401  (`api` is a fixture)
    BASE,
    _core_line,
    _line_payload,
    _stock,
    _warehouse,
    api,
)
from .test_retail_fulfilment_planning import SOON, _adopt, _retail_order, _uid


# --------------------------------------------------------------------------- the predicate


def _bin(*, segment="project", active=True, planning=True):
    return SimpleNamespace(segment=segment, is_active=active, fulfilment_planning=planning)


@pytest.mark.parametrize("klass", ["retail", "other", "project", None])
def test_a_planning_on_project_bin_is_never_outside_planning_whatever_the_class(klass):
    assert outside_fulfilment_planning(_bin(), "sales_order", klass) is False


@pytest.mark.parametrize("klass", ["retail", "other", "project", None])
def test_a_planning_off_project_bin_stays_outside_planning_whatever_the_class(klass):
    assert outside_fulfilment_planning(_bin(planning=False), "sales_order", klass) is True


@pytest.mark.parametrize("klass", ["retail", "other", "project"])
def test_a_dealer_bin_is_never_outside_planning(klass):
    assert outside_fulfilment_planning(
        _bin(segment="dealer", planning=False), "sales_order", klass
    ) is False


def test_a_consignment_line_keeps_its_own_bin_exemption():
    assert outside_fulfilment_planning(_bin(planning=False), "consignment", "retail") is False


@pytest.mark.parametrize("klass", ["retail", "project"])
def test_an_inactive_project_bin_reads_the_same_for_every_class(klass):
    """An inactive bin was outside every read before the flag existed and never earns the flag
    verdict; a Dealer order no longer earns it through its class either."""
    assert outside_fulfilment_planning(_bin(active=False, planning=False), None, klass) is False


# --------------------------------------------------------------------------- seeds


def _sheet(client, order_id):
    response = client.get(f"{BASE}/sales-orders/{order_id}/supply")
    assert response.status_code == 200, response.text
    return response.json()["lines"]


def _two_lines(client, world, klass="retail"):
    """A Dealer order with a line at a dealer bin (BRW shape) and a second line at a project bin
    that IS in fulfilment planning (BRW-BB shape)."""
    core, _made = _retail_order(world, klass=klass, lines=(("dealer", "10"), ("project", "10")))
    order_id = _adopt(client, core)["project_sales_order_id"]
    return core, order_id, _sheet(client, order_id)


def _at(lines, warehouse):
    return next(line for line in lines if line["fulfilment_location"] == warehouse.warehouse_code)


def _oi_rows(world, order_id):
    world.db.expire_all()
    return (
        world.db.query(OrderInquiryRow)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(OrderInquiry.project_sales_order_id == order_id)
        .all()
    )


# --------------------------------------------------------------------------- planning ON


@pytest.mark.parametrize("klass", ["retail", "other"])
def test_a_dealer_line_at_a_planning_on_project_bin_is_plannable(api, klass):
    client, world = api
    _core, _order_id, lines = _two_lines(client, world, klass)

    assert [line["unplannable_reason"] for line in lines] == [None, None], lines


def test_a_dealer_line_at_a_planning_on_project_bin_confirms_a_buy(api):
    client, world = api
    _core, order_id, lines = _two_lines(client, world)

    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={
            "lines": [
                _line_payload(line["project_line_id"], buy_qty=line["open_qty"]) for line in lines
            ]
        },
    )

    assert response.status_code == 200, response.text
    rows = _oi_rows(world, order_id)
    assert sorted((row.verb, Decimal(str(row.qty))) for row in rows) == [
        ("ORDER", Decimal("10")),
        ("ORDER", Decimal("10")),
    ], response.json()


def test_a_dealer_line_at_a_planning_on_project_bin_reserves_the_bins_own_stock(api):
    """Q2 (a): the line stands on the project bin's own pile, exactly as a project line there."""
    client, world = api
    core, made = _retail_order(world, lines=(("dealer", "10"), ("project", "10")))
    _stock(world.db, world.product, world.own_wh, on_hand=10)
    world.db.commit()
    order_id = _adopt(client, core)["project_sales_order_id"]
    lines = _sheet(client, order_id)
    at_bin = _at(lines, world.own_wh)

    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={
            "lines": [
                _line_payload(
                    at_bin["project_line_id"],
                    reserve=[{"warehouse_id": str(world.own_wh.id), "qty": "10"}],
                )
            ]
        },
    )

    assert response.status_code == 200, response.text


def test_the_board_offers_a_plan_for_the_dealer_line_at_the_project_bin(api):
    client, world = api
    core, _made = _retail_order(world, lines=(("dealer", "10"), ("project", "10")))
    _adopt(client, core)

    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    )

    assert response.status_code == 200, response.text
    mine = [r for r in response.json()["contributions"] if r["so_number"] == core.so_number]
    assert len(mine) == 2, mine
    kinds = [source["kind"] for row in mine for source in row["sources"]]
    assert "unplannable" not in kinds, mine


def test_the_order_inquiry_of_a_dealer_line_at_a_project_bin_routes_as_retail(api, monkeypatch):
    """Q1 (a): routed by the sales order's class (DEALER-OI-ROUTE, 1 Nov), not by the bin."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    calls: list[dict] = []

    def _fake(self, trigger_type, *, context, source_kind, source_id):
        calls.append({"trigger_type": trigger_type, "context": context})
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _fake
    )
    register_order_inquiry_post_commit_dispatch()
    client, world = api
    core, made = _retail_order(world, lines=(("dealer", "10"), ("project", "10")))
    order_id = _adopt(client, core)["project_sales_order_id"]
    at_bin = _at(_sheet(client, order_id), world.own_wh)

    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={"lines": [_line_payload(at_bin["project_line_id"], buy_qty="10")]},
    )

    assert response.status_code == 200, response.text
    assert [(r.verb, Decimal(str(r.qty))) for r in _oi_rows(world, order_id)] == [
        ("ORDER", Decimal("10"))
    ]
    handover = [c for c in calls if c["trigger_type"] == "order_inquiry_handover"]
    assert handover, calls
    assert {c["context"]["sales_order_class"] for c in handover} == {"retail"}


# --------------------------------------------------------------------------- planning OFF


def _with_off_bin_line(client, world):
    """A Dealer order admitted on its dealer line, with a second line at a project bin that is
    active and switched OUT of fulfilment planning (BRW-SMC shape)."""
    db = world.db
    off = _warehouse(db, f"ZZT-OFF-{_uid()[:6]}", segment="project", fulfilment_planning=False)
    core, _made = _retail_order(world, lines=(("dealer", "10"),))
    _core_line(db, core, world.product, off, qty_ordered="10", required_date=SOON)
    db.commit()
    order_id = _adopt(client, core)["project_sales_order_id"]
    return core, order_id, off


def test_a_dealer_line_at_a_planning_off_project_bin_is_still_refused(api):
    client, world = api
    _core, order_id, _off = _with_off_bin_line(client, world)
    lines = _sheet(client, order_id)
    refused = [line for line in lines if line["unplannable_reason"]]

    assert [line["unplannable_reason"] for line in refused] == [OUTSIDE_FULFILMENT_PLANNING]
    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={"lines": [_line_payload(refused[0]["project_line_id"], buy_qty="10")]},
    )
    assert response.status_code in (409, 422), response.text
    assert OUTSIDE_FULFILMENT_PLANNING in response.text


def test_the_board_names_the_planning_off_bin_for_the_refused_line(api):
    client, world = api
    core, _order_id, off = _with_off_bin_line(client, world)

    board = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    ).json()

    refused = [
        row for row in board["contributions"]
        if row["so_number"] == core.so_number
        and any(source["kind"] == "unplannable" for source in row["sources"])
    ]
    assert [row["fulfilment_location"] for row in refused] == [off.warehouse_code], refused


# --------------------------------------------------------------------------- admission (Q3 (b))


def _listed(client, **params):
    response = client.get(f"{BASE}/fulfilment-planning", params=params)
    assert response.status_code == 200, response.text
    return {row["so_number"] for row in response.json()["data"]}


@pytest.mark.parametrize("klass", ["retail", "other"])
def test_a_dealer_order_with_only_a_planning_on_project_bin_line_is_admitted(api, klass):
    """The SO428978 shape: delivered from BRW-BB, no line at a dealer bin."""
    client, world = api
    core, _made = _retail_order(world, klass=klass, lines=(("project", "10"),))

    assert core.so_number in _listed(client, demand_class=["retail", "other"])
    order_id = _adopt(client, core)["project_sales_order_id"]
    assert [line["unplannable_reason"] for line in _sheet(client, order_id)] == [None]


def test_a_closed_fully_delivered_dealer_order_at_a_project_bin_is_admitted(api):
    """No date window and no status filter beyond open/closed: the owner's case was delivered."""
    client, world = api
    core, made = _retail_order(world, lines=(("project", "10"),))
    made[0].qty_delivered = Decimal("10")
    core.status = "closed"
    world.db.commit()

    assert core.so_number in _listed(client, demand_class="retail")


def test_a_dealer_order_with_only_a_planning_on_project_bin_line_opens_on_the_board(api):
    client, world = api
    core, _made = _retail_order(world, lines=(("project", "10"),))

    board = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    ).json()

    mine = [r for r in board["contributions"] if r["so_number"] == core.so_number]
    assert len(mine) == 1, board.get("unplanned_orders")
    assert "unplannable" not in [source["kind"] for source in mine[0]["sources"]]


def _only_at(world, **bin_kwargs):
    db = world.db
    where = _warehouse(db, f"ZZT-PB-{_uid()[:6]}", segment="project", **bin_kwargs)
    core, _made = _retail_order(world, lines=())
    _core_line(db, core, world.product, where, qty_ordered="10", required_date=SOON)
    db.commit()
    return core


@pytest.mark.parametrize(
    "bin_kwargs",
    [{"fulfilment_planning": False}, {"active": False, "fulfilment_planning": True}],
    ids=["planning-off", "inactive"],
)
def test_a_dealer_order_only_at_a_planning_off_or_inactive_project_bin_stays_out(api, bin_kwargs):
    from app.services.error_handler import AppException
    from app.services.project_so_adoption_service import ProjectSOAdoptionService

    client, world = api
    core = _only_at(world, **bin_kwargs)

    assert core.so_number not in _listed(client, demand_class=["retail", "other", "project"])
    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))
    assert refused.value.status_code == 409


def test_the_unadmitted_reason_names_both_ways_in():
    """The board's empty state and adoption print it: it must not say only 'dealer location'
    now that a planning-ON project bin admits too."""
    from app.services.scm.planning_predicate import why_not_admitted

    reason = why_not_admitted("SO1", "retail", "open")

    assert "dealer location" in reason
    assert "fulfilment planning" in reason
