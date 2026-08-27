"""The board's own read of `GET /api/v1/inventory/stock-transfers`
(`PLAN-scm-planning-inline-decisions.md` section 3.D4).

The planning board lists the OPEN transfers for the orders it is planning, above the product
matrix, and approves them there. It knows those orders by DOCUMENT NUMBER - the board is
addressed `?orders=SO404352` - so the list route grew two things and nothing else:

* `so_numbers`, comma separated, resolved through `so_line_id -> sales_order_lines ->
  sales_orders.so_number`. A number this system does not hold matches nothing rather than
  422ing: a board can legitimately name an order that has never had a transfer.
* `state` accepts a LIST, because "what has not moved yet" is two states and asking twice
  would page two answers the user has to add up.

The contract is written at the top of
`sorento_crm_frontend/app/(protected)/project-sales/_shared/services/boardTransfersService.ts`,
which is what the panel calls.

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES). The seed helpers
are `test_so_supply_confirmation`'s, the same chain the transfer writer's own tests use.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.stock_transfer import (
    TRANSFER_APPROVED,
    TRANSFER_CANCELLED,
    TRANSFER_KIND_POOL,
    TRANSFER_MOVED,
    TRANSFER_PROPOSED,
    StockTransfer,
)

from app.services import project_seed_service

from ._pg_fixture import blank_session
from .test_so_supply_confirmation import (
    _client,
    _core_line,
    _core_so,
    _product,
    _project_so,
    _restore,
    _sorento,
    _suffix,
    _user,
    _warehouse,
)

MARKER = "zzt-transfer-filter"
TRANSFERS = "/api/v1/inventory/stock-transfers"


def _uid() -> str:
    return str(uuid.uuid4())


class _World:
    """Two sales orders, each with one line, and a transfer per line."""

    def __init__(self, db, company_id, client):
        self.db = db
        self.company_id = company_id
        self.client = client
        self.numbers: dict = {}
        self.transfers: dict = {}


@pytest.fixture()
def world():
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = _user(db, f"{MARKER} Eling")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=actor,
            developer_party_id=None,
            title=f"{MARKER} Tuju Residences",
        )
        product = _product(db)
        stem = _suffix()
        own = _warehouse(db, f"ZZT{stem}A-BB", segment="project")
        pool = _warehouse(db, f"ZZT{stem}P", segment="dealer")
        db.commit()
        client, originals = _client(db, actor)
        state = _World(db, company_id, client)
        try:
            with company_scope(db, frozenset({company_id})):
                for key, transfer_state in (
                    ("a", TRANSFER_PROPOSED),
                    ("b", TRANSFER_APPROVED),
                ):
                    order = _core_so(db, company_id)
                    line = _core_line(db, order, product, own, qty_ordered="10")
                    mirror = _project_so(db, project, so_id=order.id)
                    transfer = StockTransfer(
                        id=_uid(),
                        company_id=company_id,
                        transfer_no=f"ZZT-ST-{_suffix()}",
                        so_line_id=line.id,
                        project_sales_order_id=mirror.id,
                        product_id=product.id,
                        from_warehouse_id=pool.id,
                        to_warehouse_id=own.id,
                        qty=Decimal("15"),
                        kind=TRANSFER_KIND_POOL,
                        state=transfer_state,
                    )
                    db.add(transfer)
                    db.flush()
                    state.numbers[key] = order.so_number
                    state.transfers[key] = str(transfer.id)
                # A third order whose transfer is already MOVED, so the open-state filter has
                # something to leave out.
                order = _core_so(db, company_id)
                line = _core_line(db, order, product, own, qty_ordered="10")
                mirror = _project_so(db, project, so_id=order.id)
                moved = StockTransfer(
                    id=_uid(),
                    company_id=company_id,
                    transfer_no=f"ZZT-ST-{_suffix()}",
                    so_line_id=line.id,
                    project_sales_order_id=mirror.id,
                    product_id=product.id,
                    from_warehouse_id=pool.id,
                    to_warehouse_id=own.id,
                    qty=Decimal("4"),
                    kind=TRANSFER_KIND_POOL,
                    state=TRANSFER_MOVED,
                )
                db.add(moved)
                db.flush()
                state.numbers["moved"] = order.so_number
                state.transfers["moved"] = str(moved.id)
                db.commit()
                yield state
        finally:
            _restore(originals)


def _numbers(body) -> set:
    return {row["so_number"] for row in body["data"]}


def test_so_numbers_narrows_the_list_to_the_boards_own_orders(world):
    """AC-D11: the panel asks for the orders on the board and gets those and nothing else."""
    response = world.client.get(
        TRANSFERS, params={"so_numbers": world.numbers["a"]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["data"]] == [world.transfers["a"]]
    assert body["pagination"]["total"] == 1
    assert _numbers(body) == {world.numbers["a"]}


def test_so_numbers_takes_a_list_because_a_board_plans_several_orders(world):
    response = world.client.get(
        TRANSFERS,
        params={"so_numbers": f"{world.numbers['a']},{world.numbers['b']}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _numbers(body) == {world.numbers["a"], world.numbers["b"]}
    assert body["pagination"]["total"] == 2


def test_an_unknown_document_number_matches_nothing_and_is_not_an_error(world):
    """A board may name an order that has never had a transfer, and that is not a mistake
    the planner should be shown a 422 for."""
    response = world.client.get(
        TRANSFERS, params={"so_numbers": f"{world.numbers['a']},ZZT-SO-NOBODY"}
    )

    assert response.status_code == 200, response.text
    assert _numbers(response.json()) == {world.numbers["a"]}

    only_unknown = world.client.get(TRANSFERS, params={"so_numbers": "ZZT-SO-NOBODY"})
    assert only_unknown.status_code == 200, only_unknown.text
    assert only_unknown.json()["data"] == []
    assert only_unknown.json()["empty"] is True


def test_blank_and_spaced_numbers_are_ignored_rather_than_matching_nothing(world):
    """`so_numbers=` on the URL when the board holds no orders must not silently become a
    filter that matches nothing - the panel does not call it at all in that case, and a
    trailing comma from a join must not change the answer either."""
    response = world.client.get(
        TRANSFERS, params={"so_numbers": f" {world.numbers['a']} , "}
    )

    assert response.status_code == 200, response.text
    assert _numbers(response.json()) == {world.numbers["a"]}

    unfiltered = world.client.get(TRANSFERS, params={"so_numbers": " , "})
    assert unfiltered.status_code == 200, unfiltered.text
    assert unfiltered.json()["pagination"]["total"] == 3, "an empty filter filters nothing"


def test_state_takes_a_list_so_open_means_proposed_or_approved(world):
    response = world.client.get(TRANSFERS, params={"state": "proposed,approved"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["state"] for row in body["data"]} == {
        TRANSFER_PROPOSED,
        TRANSFER_APPROVED,
    }
    assert world.transfers["moved"] not in [row["id"] for row in body["data"]]


def test_one_state_still_works_the_way_the_transfers_page_asks_for_it(world):
    response = world.client.get(TRANSFERS, params={"state": TRANSFER_PROPOSED})

    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["data"]] == [world.transfers["a"]]


def test_a_state_that_is_not_a_state_is_refused_rather_than_matching_nothing(world):
    """A filter nothing can equal reads on screen as "no work to do" when the truth is
    "that is not a state" - the closed set the route always had, kept through the widening."""
    response = world.client.get(TRANSFERS, params={"state": "proposed,banana"})

    assert response.status_code == 422, response.text


def test_the_two_filters_compose(world):
    response = world.client.get(
        TRANSFERS,
        params={
            "so_numbers": f"{world.numbers['a']},{world.numbers['b']},{world.numbers['moved']}",
            "state": "proposed,approved",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _numbers(body) == {world.numbers["a"], world.numbers["b"]}


def test_the_list_still_refuses_a_caller_without_the_view_permission(world):
    from app.services.user_service import UserPermissionService

    original = UserPermissionService.get_user_permission_slugs
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: False
    try:
        UserPermissionService.get_user_permission_slugs = lambda self, uid: []
        response = world.client.get(TRANSFERS, params={"so_numbers": world.numbers["a"]})
    finally:
        UserPermissionService.get_user_permission_slugs = original
        UserPermissionService.check_user_has_permission = (
            lambda self, uid, slug: True
        )

    assert response.status_code == 403, response.text


def test_cancelled_is_reachable_on_its_own_so_nothing_is_hidden_by_the_widening(world):
    """The Transfers page filters one state at a time and must keep working."""
    row = (
        world.db.query(StockTransfer)
        .filter(StockTransfer.id == world.transfers["moved"])
        .first()
    )
    row.state = TRANSFER_CANCELLED
    world.db.commit()

    response = world.client.get(TRANSFERS, params={"state": TRANSFER_CANCELLED})

    assert response.status_code == 200, response.text
    assert [r["id"] for r in response.json()["data"]] == [world.transfers["moved"]]
