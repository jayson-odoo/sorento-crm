"""DEALER-PLANNING PR 2, retail orders in Fulfilment Planning: admission, finding, priority,
display and access (UAC R1 to R6, R13, R14, R16).

Contract: `documentation/plans/scm/dealer-planning-1nov-acceptance-criteria.md` and the PR 2
UAC. Written test-first, so every test fails today on a missing feature (a retail order is
refused at adoption, the list has no `demand_class` filter or field, the ranking calls every
row project, no migration grants the roles) and not on an import or a fixture.

Two seams are CONTRACT NAMES that do not exist yet, taken from the brief:

* the Fulfilment Planning list takes `demand_class` (multi) and each row carries
  `demand_class`;
* R3 gives the board payload an `unplanned_orders` list of `{so_number, reason}` for an
  order the board was asked for and does not carry.

Postgres only (`blank_session`, the `api` harness of `tests/test_so_supply_confirmation.py`
and `pg_session` for the migration), every test seeds its own chain.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.services.error_handler import AppException
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.scm.planning_predicate import OUTSIDE_FULFILMENT_PLANNING

from .._pg_fixture import blank_session, pg_session
from ..test_so_supply_confirmation import (  # noqa: F401  (`api` is a fixture)
    BASE,
    _core_line,
    _line_payload,
    _product,
    _sorento,
    _stock,
    _user,
    api,
)

TODAY = date.today()
SOON = TODAY + timedelta(days=14)


# --------------------------------------------------------------------------- seeds


def _uid() -> str:
    return str(uuid.uuid4())


def _retail_order(world, *, klass="retail", lines=(("dealer", "10"),), note=None):
    """A core order of `klass` with one line per `(where, qty)`. `dealer` is the dealer
    segment pool (flagged OUT of fulfilment planning, as BRW is), `project` is a project
    segment bin that IS in planning."""
    db = world.db
    world.pool_wh.fulfilment_planning = False
    world.own_wh.fulfilment_planning = True
    where = {"dealer": world.pool_wh, "project": world.own_wh}
    core = SalesOrder(
        id=_uid(),
        company_id=world.company_id,
        so_number=f"ZZT-RTL-{_uid()[:8]}",
        status="open",
        demand_class=klass,
        internal_note=note,
    )
    db.add(core)
    db.flush()
    made = [
        _core_line(db, core, world.product, where[site], qty_ordered=qty, required_date=SOON)
        for site, qty in lines
    ]
    db.commit()
    return core, made


def _adopt(client, core):
    response = client.post(f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(core.id)})
    assert response.status_code == 200, response.text
    return response.json()


def _listed(client, **params):
    response = client.get(f"{BASE}/fulfilment-planning", params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _numbers(rows):
    return {row["so_number"] for row in rows}


# --------------------------------------------------------------------------- R1


@pytest.mark.parametrize("klass", ["retail", "other"])
def test_r1_a_retail_order_with_a_dealer_line_adopts_with_no_project(api, klass):
    """R1: 'retail' and 'other' (`demand_class.planning_class`) are both admitted."""
    client, world = api
    core, _lines = _retail_order(world, klass=klass)

    body = _adopt(client, core)

    order = (
        world.db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == body["project_sales_order_id"])
        .one()
    )
    assert order.project_id is None


def test_r1_a_retail_order_with_a_dealer_line_is_listed_for_the_retail_filter(api):
    client, world = api
    core, _lines = _retail_order(world)

    assert core.so_number in _numbers(_listed(client, demand_class="retail"))


def test_r1_an_admitted_retail_order_opens_on_the_board(api):
    client, world = api
    core, _lines = _retail_order(world)
    _adopt(client, core)

    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    )

    assert response.status_code == 200, response.text
    board = response.json()
    assert core.so_number in {row["so_number"] for row in board["contributions"]}, board.get(
        "unplanned_orders"
    )


def test_r1_an_admitted_retail_order_takes_a_line_draft(api):
    client, world = api
    core, _lines = _retail_order(world)
    _adopt(client, core)
    board = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    ).json()
    key = next(r for r in board["contributions"] if r["so_number"] == core.so_number)["key"]

    response = client.put(
        f"{BASE}/fulfilment-planning/lines/{key}/draft",
        json={"decision": {"verdict": "amended", "buy_qty": "10", "reserve": [], "borrow": []}},
    )

    assert response.status_code == 200, response.text


def test_r1_an_admitted_retail_order_confirms_and_raises_its_order_inquiry_row(api):
    client, world = api
    core, _lines = _retail_order(world)
    order_id = _adopt(client, core)["project_sales_order_id"]
    sheet = client.get(f"{BASE}/sales-orders/{order_id}/supply").json()

    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={
            "lines": [
                _line_payload(line["project_line_id"], buy_qty=line["open_qty"])
                for line in sheet["lines"]
            ]
        },
    )

    assert response.status_code == 200, response.text
    world.db.expire_all()
    rows = (
        world.db.query(OrderInquiryRow)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(OrderInquiry.project_sales_order_id == order_id)
        .all()
    )
    assert [(row.verb, Decimal(str(row.qty))) for row in rows] == [("ORDER", Decimal("10"))]


# --------------------------------------------------------------------------- R2


def test_r2_a_retail_order_with_no_line_at_a_dealer_location_stays_out(api):
    """R2: its one line is at a project-segment bin, so there is nothing at a dealer location."""
    client, world = api
    core, _lines = _retail_order(world, lines=(("project", "10"),))

    listed = _numbers(_listed(client, demand_class=["retail", "other", "project"]))
    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))

    assert core.so_number not in listed
    assert refused.value.status_code == 409


# --------------------------------------------------------------------------- R1, any status but cancelled, active location


def _closed(world, core):
    core.status = "closed"
    world.db.commit()


@pytest.mark.parametrize("klass", ["retail", "other"])
def test_r1_a_closed_retail_order_adopts_like_a_project_one(api, klass):
    """Owner ruling 1 Nov 2026: whether an order is delivered does not affect planning, so a
    closed retail or `other` order with a dealer line is admitted exactly as a project one."""
    client, world = api
    core, _lines = _retail_order(world, klass=klass)
    _closed(world, core)

    body = _adopt(client, core)

    order = (
        world.db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == body["project_sales_order_id"])
        .one()
    )
    assert order.project_id is None


def test_r1_a_closed_retail_order_opens_on_the_board(api):
    client, world = api
    core, _lines = _retail_order(world)
    _closed(world, core)

    board = _board_of(client, core)

    assert core.so_number in {row["so_number"] for row in board["contributions"]}, board.get(
        "unplanned_orders"
    )
    assert core.so_number not in {row["so_number"] for row in board.get("unplanned_orders", [])}


def _settle(world, core, lines):
    """The shape the import writes for a settled order: lines delivered and `closed`."""
    for line in lines:
        line.qty_delivered = line.qty_ordered
        line.line_status = "closed"
    _closed(world, core)


def test_r1_a_closed_fully_delivered_retail_order_plans_and_confirms(api):
    """The shape of the real case: one line at the dealer pool, ordered 1, delivered 1, line
    and header closed, stock at the pool, no other demand. Planning can come after delivery."""
    client, world = api
    core, lines = _retail_order(world, lines=(("dealer", "1"),))
    world.pool_wh.pool_warehouse_id = world.pool_wh.id
    _stock(world.db, world.product, world.pool_wh, on_hand=10)
    _settle(world, core, lines)

    order_id = _adopt(client, core)["project_sales_order_id"]
    board = _board_of(client, core)
    key = next(r for r in board["contributions"] if r["so_number"] == core.so_number)["key"]
    sheet = client.get(f"{BASE}/sales-orders/{order_id}/supply").json()
    components = [c for line in sheet["lines"] for c in line["components"]]
    totals = {k: sum(Decimal(str(c["qty"])) for c in components if c["kind"] == k) for k in {c["kind"] for c in components}}
    assert totals == {"reserve": Decimal("1")}, sheet
    assert all(c["source_location"] == world.pool_wh.warehouse_code for c in components)

    draft = client.put(
        f"{BASE}/fulfilment-planning/lines/{key}/draft",
        json={"decision": {"verdict": "amended", "buy_qty": "0", "reserve": [
            {"warehouse_id": str(world.pool_wh.id), "qty": "1"}], "borrow": []}},
    )
    assert draft.status_code == 200, draft.text
    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={"lines": [
            _line_payload(
                line["project_line_id"],
                reserve=[{"warehouse_id": str(world.pool_wh.id), "qty": "1"}],
            )
            for line in sheet["lines"]
        ]},
    )
    assert response.status_code == 200, response.text
    world.db.expire_all()
    bought = (
        world.db.query(OrderInquiryRow)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(OrderInquiry.project_sales_order_id == order_id)
        .all()
    )
    assert bought == []


def test_r1_a_closed_project_order_still_adopts_and_opens_on_the_board(api):
    """The control: the 14 Sep ruling put closed project orders on the board, and they stay."""
    client, world = api
    core, _lines = _retail_order(world, klass="project", lines=(("project", "10"),))
    _closed(world, core)

    body = _adopt(client, core)
    board = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    ).json()

    assert body["project_sales_order_id"]
    assert core.so_number in {row["so_number"] for row in board["contributions"]}


def test_r1_plannable_lines_reads_the_same_admission(api):
    """What the sales order page's Plan and the Planned pill read."""
    from app.services.scm.sales_order_service import SalesOrderService

    client, world = api
    open_retail, _a = _retail_order(world)
    closed_retail, _b = _retail_order(world)
    _closed(world, closed_retail)
    closed_project, _c = _retail_order(world, klass="project", lines=(("project", "10"),))
    _closed(world, closed_project)

    rows = SalesOrderService(world.db).with_planning_state(
        [{"id": str(core.id)} for core in (open_retail, closed_retail, closed_project)]
    )

    assert [row["plannable_lines"] for row in rows] == [1, 1, 1]


def test_r6_a_cancelled_retail_order_reads_no_plannable_lines(api):
    """A cancelled header is refused even when its line is not cancelled."""
    from app.services.scm.sales_order_service import SalesOrderService

    client, world = api
    core, _lines = _retail_order(world)
    core.status = "cancelled"
    world.db.commit()

    rows = SalesOrderService(world.db).with_planning_state([{"id": str(core.id)}])

    assert [row["plannable_lines"] for row in rows] == [0]


def test_r1_a_retail_order_at_a_retired_dealer_location_stays_out(api):
    """R1 says ACTIVE: a retired dealer bin holds stock nobody can pick."""
    client, world = api
    core, _lines = _retail_order(world)
    world.pool_wh.is_active = False
    world.db.commit()

    listed = _numbers(_listed(client, demand_class=["retail", "other", "project"]))
    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))

    assert core.so_number not in listed
    assert refused.value.status_code == 409
    assert "active" in refused.value.message.lower(), refused.value.message


# --------------------------------------------------------------------------- R1, planned then closed


def _planned_retail_order(client, world):
    """A retail order adopted and confirmed with a Buy: it has a planning record."""
    core, lines = _retail_order(world)
    order_id = _adopt(client, core)["project_sales_order_id"]
    sheet = client.get(f"{BASE}/sales-orders/{order_id}/supply").json()
    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={
            "lines": [
                _line_payload(line["project_line_id"], buy_qty=line["open_qty"])
                for line in sheet["lines"]
            ]
        },
    )
    assert response.status_code == 200, response.text
    return core, lines


def _board_of(client, core):
    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_r1_a_planned_retail_order_that_closes_keeps_its_decided_rows(api):
    """Closing does not un-plan it. A closed retail order with a planning record stays on the
    board, its decided row reads, and the list's Planned pill counts it rather than a dash."""
    from app.services.scm.sales_order_service import SalesOrderService

    client, world = api
    core, _lines = _planned_retail_order(client, world)
    _closed(world, core)

    board = _board_of(client, core)
    rows = [row for row in board["contributions"] if row["so_number"] == core.so_number]
    progress = SalesOrderService(world.db).with_planning_state([{"id": str(core.id)}])[0]

    assert len(rows) == 1, board.get("unplanned_orders")
    assert rows[0]["decision"], rows[0]
    assert core.so_number not in {row["so_number"] for row in board["unplanned_orders"]}
    assert (progress["plannable_lines"], progress["planned_lines"]) == (1, 1)


def test_r1_a_planned_retail_order_that_closes_can_still_apply_its_pending_change(api):
    """The book closed the line and the order: the pending change row is on the board, addressed
    to its batch, and applying it works. Hiding it would strand the change with no screen."""
    from app.services import planning_change_service
    from app.services.scm.outstanding_diff import CLOSED, Diff

    from ..test_planning_changes import _diff_change

    client, world = api
    core, lines = _planned_retail_order(client, world)
    line = lines[0]
    line.line_status = "closed"
    world.db.flush()
    changed = _diff_change(
        CLOSED, line, doc_number=core.so_number, item_code=world.product.product_code,
        location=world.pool_wh.warehouse_code, old_date=SOON, new_date=None,
        old_qty="10", new_qty="0",
    )
    batch = planning_change_service.build_batch(
        world.db, Diff(scope_documents=(core.so_number,), changes=[changed]),
        applied_line_ids={id(changed): str(line.id)},
        order_ids={core.so_number: str(core.id)}, actor=_user(world.db, "zzt-planner"),
        import_job_id=None, file_name="zzt-book.xlsx",
    )
    assert batch is not None
    _closed(world, core)

    board = _board_of(client, core)
    rows = [row for row in board["contributions"] if row["so_number"] == core.so_number]

    assert [row["pending_change_batch_id"] for row in rows] == [str(batch.id)], board.get(
        "unplanned_orders"
    )

    detail = planning_change_service.get_batch(world.db, str(batch.id))
    planning_change_service.set_row_decision(
        world.db, str(batch.id), detail["orders"][0]["rows"][0]["id"], "confirm"
    )
    world.db.commit()
    applied = client.post(f"{BASE}/planning-changes/{batch.id}/apply")

    assert applied.status_code == 200, applied.text
    assert applied.json()["failed_orders"] == [], applied.text
    assert applied.json()["applied_orders"] == [core.so_number], applied.text


def test_r1_a_planned_retail_order_stays_admitted_after_its_dealer_location_retires(api):
    """The planning record admits on its own. A retail order adopted while its dealer bin was
    active stays planning work once the bin retires, so its decided rows do not vanish; the
    control, an unplanned order at the same retired bin, stays out."""
    from app.services.scm.planning_predicate import admitted_to_planning

    client, world = api
    planned, _lines = _planned_retail_order(client, world)
    unplanned, _other = _retail_order(world)
    world.pool_wh.is_active = False
    world.db.commit()

    admitted = {
        row.so_number
        for row in world.db.query(SalesOrder.so_number)
        .filter(SalesOrder.id.in_((planned.id, unplanned.id)), admitted_to_planning())
        .all()
    }
    board = _board_of(client, planned)
    rows = [row for row in board["contributions"] if row["so_number"] == planned.so_number]

    assert admitted == {planned.so_number}
    assert len(rows) == 1, board.get("unplanned_orders")
    assert rows[0]["decision"], rows[0]


# --------------------------------------------------------------------------- an adopted mirror


def _mirror_of(client, world, core):
    order_id = _adopt(client, core)["project_sales_order_id"]
    line = client.get(f"{BASE}/sales-orders/{order_id}/supply").json()["lines"][0]
    return order_id, line["project_line_id"]


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("put", "/sales-orders/{order}/lines/{line}", {"qty": "99"}),
        ("put", "/sales-orders/{order}", {"area_group": "ZZT"}),
        ("post", "/sales-orders/{order}/publish", None),
    ],
    ids=["edit-a-line", "save-the-document", "publish"],
)
def test_an_adopted_mirror_cannot_be_edited_or_published(api, method, path, body):
    """An adopted order's lines are the book's. An `.edit` holder must not change quantity, price,
    product or location on the mirror, drop its lines, or publish it."""
    client, world = api
    core, _lines = _retail_order(world)
    order_id, line_id = _mirror_of(client, world, core)

    response = getattr(client, method)(
        f"{BASE}{path.format(order=order_id, line=line_id)}",
        **({"json": body} if body is not None else {}),
    )

    assert response.status_code == 409, response.text
    world.db.expire_all()
    order = world.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == order_id).one()
    assert order.status == "adopted"
    assert len(client.get(f"{BASE}/sales-orders/{order_id}/supply").json()["lines"]) == 1


# --------------------------------------------------------------------------- R3


def test_r3_an_order_with_no_class_stays_off_the_board_and_the_reason_is_true(api):
    """R3: refused at adoption with a reason that names the missing class, never the
    'cancelled, fully returned' sentence the board used to print for it."""
    client, world = api
    core, _lines = _retail_order(world, klass=None)

    listed = _numbers(_listed(client, demand_class=["retail", "other", "project"]))
    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))

    assert core.so_number not in listed
    assert refused.value.status_code == 409
    message = refused.value.message
    assert "class" in message.lower(), message
    assert "cancelled" not in message.lower(), message


def test_r3_the_board_names_why_it_left_a_classless_order_out(api):
    """R3: asked for an order it does not carry, the board says why in `unplanned_orders`."""
    client, world = api
    core, _lines = _retail_order(world, klass=None)

    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core.so_number, "granularity": "week"},
    )

    assert response.status_code == 200, response.text
    skipped = {row["so_number"]: row["reason"] for row in response.json().get("unplanned_orders", [])}
    assert core.so_number in skipped, response.json().keys()
    assert "class" in skipped[core.so_number].lower()
    assert "cancelled" not in skipped[core.so_number].lower()


# --------------------------------------------------------------------------- R4


def _adopt_two_lines(client, world):
    """A retail order admitted on its dealer line, with a second line at a project bin that is
    in fulfilment planning."""
    core, _lines = _retail_order(world, lines=(("dealer", "10"), ("project", "10")))
    order_id = _adopt(client, core)["project_sales_order_id"]
    sheet = client.get(f"{BASE}/sales-orders/{order_id}/supply").json()
    return core, order_id, sheet["lines"]


def test_r4_a_retail_line_at_a_project_location_reads_outside_fulfilment_planning(api):
    client, world = api
    _core, _order_id, lines = _adopt_two_lines(client, world)

    reasons = sorted(str(line["unplannable_reason"]) for line in lines)

    assert reasons == ["None", OUTSIDE_FULFILMENT_PLANNING], reasons


def test_r4_a_retail_line_at_a_project_location_cannot_be_decided(api):
    client, world = api
    _core, order_id, lines = _adopt_two_lines(client, world)
    refused = next(line for line in lines if line["unplannable_reason"])

    response = client.post(
        f"{BASE}/sales-orders/{order_id}/confirm",
        json={"lines": [_line_payload(refused["project_line_id"], buy_qty=refused["open_qty"])]},
    )

    assert response.status_code in (409, 422), response.text
    assert OUTSIDE_FULFILMENT_PLANNING in response.text


# --------------------------------------------------------------------------- R5


def test_r5_a_project_order_is_admitted_as_before(api):
    client, world = api
    core, _lines = _retail_order(world, klass="project", lines=(("project", "10"),))

    body = _adopt(client, core)

    assert body["project_sales_order_id"]
    assert core.so_number in _numbers(_listed(client))


def test_r5_the_migration_adoption_stays_project_only(api):
    client, world = api
    core, _lines = _retail_order(world, klass="retail")

    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt_for_migration(str(core.id))

    assert refused.value.status_code == 409


# --------------------------------------------------------------------------- R6


def test_r6_a_call_with_no_filter_returns_project_orders_only(api):
    client, world = api
    project, _a = _retail_order(world, klass="project", lines=(("project", "10"),))
    retail, _b = _retail_order(world, klass="retail")

    got = _numbers(_listed(client))

    assert project.so_number in got
    assert retail.so_number not in got


def test_r6_the_class_filter_takes_several_and_the_row_states_its_class(api):
    client, world = api
    project, _a = _retail_order(world, klass="project", lines=(("project", "10"),))
    retail, _b = _retail_order(world, klass="retail")
    other, _c = _retail_order(world, klass="other")

    only_retail = {row["so_number"]: row for row in _listed(client, demand_class="retail")}
    both = {row["so_number"]: row for row in _listed(client, demand_class=["project", "retail"])}

    assert project.so_number not in only_retail
    assert only_retail[retail.so_number]["demand_class"] == "retail"
    assert both[project.so_number]["demand_class"] == "project"
    assert retail.so_number in both
    # 'other' weighs as retail, so the retail filter carries it. The row states the class
    # stored on the order; either spelling of retail is accepted for it.
    assert other.so_number in only_retail
    assert only_retail[other.so_number]["demand_class"] in ("other", "retail")


def test_r6_an_unknown_class_is_a_422_not_an_empty_list(api):
    client, _world = api

    response = client.get(f"{BASE}/fulfilment-planning", params={"demand_class": "dealer"})

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- R13


def test_r13_a_retail_order_inquiry_row_ranks_below_a_project_one_for_a_scarce_po_line():
    """R13: the policy weights project 1.0 and retail 0.4 and ranks on the class alone, with
    the retail row EARLIER on every other tie-break (delivery date, created). Read as project
    (today) the two tie and the retail row wins on its date; read at its real weight the
    project row wins. 'other' weighs as retail."""
    from app.models.base import company_scope
    from app.models.scm import PriorityPolicy

    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db)
        db.add(
            PriorityPolicy(
                id=_uid(),
                name=f"zzt-r13-{_uid()[:6]}",
                is_active=True,
                factors={"demand_class": 1.0},
                demand_class_weights={"project": 1.0, "retail": 0.4},
            )
        )
        db.query(PriorityPolicy).filter(PriorityPolicy.name.notlike("zzt-r13-%")).update(
            {"is_active": False}, synchronize_session=False
        )
        db.flush()

        def raised(klass, delivery):
            core = SalesOrder(
                id=_uid(), company_id=company_id, so_number=f"ZZT-R13-{_uid()[:8]}",
                status="open", demand_class=klass,
            )
            db.add(core)
            db.flush()
            pso = ProjectSalesOrder(
                id=_uid(), company_id=company_id, project_id=None, so_id=core.id,
                provisional_ref=f"ZZT-R13-{_uid()[:8]}", status="published",
                published_at=datetime(2026, 1, 1),
            )
            db.add(pso)
            db.flush()
            inquiry = OrderInquiry(
                id=_uid(), company_id=company_id, project_sales_order_id=pso.id, state="raised",
            )
            db.add(inquiry)
            db.flush()
            row = OrderInquiryRow(
                id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id,
                item_code=product.product_code, qty=Decimal("10"), delivery_date=delivery,
                verb="ORDER", state="raised",
            )
            db.add(row)
            db.flush()
            return row

        retail = raised("retail", TODAY + timedelta(days=10))
        other = raised("other", TODAY + timedelta(days=11))
        project = raised("project", TODAY + timedelta(days=30))
        db.commit()

        with company_scope(db, frozenset({company_id})):
            ranked = ProjectOrderInquiryService(db)._rank_raised_rows([retail, other, project])

    assert [row.id for row in ranked][0] == project.id
    assert {ranked[1].id, ranked[2].id} == {retail.id, other.id}


# --------------------------------------------------------------------------- R14


NOTE = "Deliver to the back gate before noon"


def test_r14_a_retail_orders_internal_note_does_not_print_as_a_project_on_the_list(api):
    client, world = api
    retail, _a = _retail_order(world, klass="retail", note=NOTE)

    rows = {r["so_number"]: r for r in _listed(client, demand_class="retail")}

    assert retail.so_number in rows
    assert rows[retail.so_number]["project_label"] in (None, "")


def test_r14_a_project_orders_note_still_prints_as_its_project(api):
    """The control: the project reading is untouched."""
    client, world = api
    project, _a = _retail_order(
        world, klass="project", lines=(("project", "10"),), note="Order Inquiry project: TOWER A",
    )

    row = next(r for r in _listed(client) if r["so_number"] == project.so_number)

    assert row["project_label"] == "TOWER A"


def test_r14_a_retail_orders_internal_note_does_not_print_as_a_project_on_the_board(api):
    client, world = api
    retail, _a = _retail_order(world, klass="retail", note=NOTE)
    _adopt(client, retail)

    board = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": retail.so_number, "granularity": "week"},
    ).json()

    rows = [r for r in board["contributions"] if r["so_number"] == retail.so_number]
    assert rows, board.keys()
    assert all(not r.get("project_label") for r in rows), [r.get("project_label") for r in rows]


# --------------------------------------------------------------------------- R16

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_GRANTED = ("projects.projects.view", "projects.projects.edit", "scm.dashboard.view")


#: The grant migration, by its own revision id. It was the alembic head when it landed, but
#: any later migration on main becomes the head, so the lookup must not read "the head".
_GRANT_REVISION = "dp_0001_cs_planning_access"


def _head_migration():
    """The Customer Service grant migration (`_GRANT_REVISION`), loaded from its file."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(_VERSIONS.parent))
    script = ScriptDirectory.from_config(config)
    path = Path(script.get_revision(_GRANT_REVISION).path)
    source = path.read_text()
    assert "customer_service" in source and all(slug in source for slug in _GRANTED), (
        f"the migration {path.name} does not grant the Customer Service role {_GRANTED}"
    )
    spec = importlib.util.spec_from_file_location("zzt_r16_head", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction="upgrade"):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _head_migration()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _role(db, slug, name):
    row = db.execute(text("select id from user_roles where slug = :s"), {"s": slug}).scalar()
    if row:
        return row
    row = _uid()
    db.execute(
        text("insert into user_roles (id, slug, name, is_trashed, is_protected, is_default, created_at) "
             "values (:i, :s, :n, false, false, false, now())"),
        {"i": row, "s": slug, "n": name},
    )
    return row


def _perm(db, slug):
    row = db.execute(text("select id from user_permissions where slug = :s"), {"s": slug}).scalar()
    if row:
        return row
    row = _uid()
    db.execute(
        text("insert into user_permissions (id, slug, name, created_at) values (:i, :s, :s, now())"),
        {"i": row, "s": slug},
    )
    return row


def _granted(db, role_id):
    return {
        slug
        for (slug,) in db.execute(
            text("select p.slug from user_role_permissions rp join user_permissions p "
                 "on p.id = rp.permission_id where rp.role_id = :r"),
            {"r": role_id},
        )
    }


def _clear(db, role_id):
    db.execute(text("delete from user_role_permissions where role_id = :r"), {"r": role_id})


def test_r16_the_customer_service_role_gains_the_three_slugs_and_no_other_role_moves():
    with pg_session() as db:
        cs = _role(db, "customer_service", "Customer Service")
        bystander = _role(db, f"zzt-r16-{_uid()[:6]}", f"ZZT R16 {_uid()[:6]}")
        for slug in _GRANTED:
            _perm(db, slug)
        _clear(db, cs)
        _clear(db, bystander)
        db.flush()

        _run(db)

        assert _granted(db, cs) == set(_GRANTED)
        assert _granted(db, bystander) == set()


def test_r16_it_is_additive_and_idempotent():
    with pg_session() as db:
        cs = _role(db, "customer_service", "Customer Service")
        for slug in (*_GRANTED, "zzt.r16.keep"):
            _perm(db, slug)
        _clear(db, cs)
        db.execute(
            text("insert into user_role_permissions (id, role_id, permission_id, assigned_at) "
                 "values (:i, :r, :p, now())"),
            {"i": _uid(), "r": cs, "p": _perm(db, "zzt.r16.keep")},
        )
        db.flush()

        _run(db)
        _run(db)

        assert _granted(db, cs) == {*_GRANTED, "zzt.r16.keep"}
        count = db.execute(
            text("select count(*) from user_role_permissions where role_id = :r"), {"r": cs}
        ).scalar()
        assert count == len(_GRANTED) + 1


def test_r16_a_database_without_the_role_is_not_an_error():
    with pg_session() as db:
        db.execute(
            text("update user_roles set slug = :s where slug = 'customer_service'"),
            {"s": f"zzt-renamed-{_uid()[:6]}"},
        )
        db.flush()

        _run(db)

        assert db.execute(
            text("select count(*) from user_roles where slug = 'customer_service'")
        ).scalar() == 0


# --------------------------------------------------------------------------- R9, closed lines


def _closed_line_at_the_pool(klass):
    """Ordered 10, delivered 10, closed, 10 on hand at the dealer pool, nobody else."""
    from .test_own_pool_planning import _line, _pool, _sheet
    from .test_project_supply_service_ladder import _world

    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        order, _l, core_so, core_line = _line(db, world, pool, 10, klass=klass)
        core_line.qty_delivered = Decimal("10")
        core_line.line_status = "closed"
        core_so.status = "closed"
        db.commit()
        return _sheet(db, order)


def test_r9_a_closed_retail_line_holds_no_share_and_a_closed_project_line_does():
    retail = _closed_line_at_the_pool("retail")
    project = _closed_line_at_the_pool("project")

    assert retail == {"reserve": Decimal("10")}, retail
    assert project == {"reserve": Decimal("5"), "buy": Decimal("5")}, project


# --------------------------------------------------------------------------- R1, the true reason


def test_r1_a_closed_retail_order_with_no_dealer_line_stays_out_for_that_reason(api):
    client, world = api
    core, _lines = _retail_order(world, lines=(("project", "10"),))
    _closed(world, core)

    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))
    board = _board_of(client, core)
    skipped = {row["so_number"]: row["reason"] for row in board.get("unplanned_orders", [])}

    assert refused.value.status_code == 409
    for reason in (refused.value.message, skipped.get(core.so_number, "")):
        assert "dealer" in reason.lower() and "location" in reason.lower(), reason
        assert "closed" not in reason.lower(), reason
    assert core.so_number in skipped, board.keys()
    assert core.so_number not in {row["so_number"] for row in board["contributions"]}


def test_r3_an_open_retail_order_never_reads_as_closed(api):
    client, world = api
    core, _lines = _retail_order(world, lines=(("project", "10"),))

    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))
    board = _board_of(client, core)
    skipped = {row["so_number"]: row["reason"] for row in board.get("unplanned_orders", [])}

    assert refused.value.status_code == 409
    assert "closed" not in refused.value.message.lower(), refused.value.message
    assert core.so_number in skipped, board.keys()
    assert "closed" not in skipped[core.so_number].lower(), skipped[core.so_number]


def test_r1_a_cancelled_retail_order_stays_refused(api):
    client, world = api
    core, _lines = _retail_order(world)
    core.status = "cancelled"
    world.db.commit()

    response = client.post(f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(core.id)})
    board = _board_of(client, core)

    assert response.status_code == 409, response.text
    assert core.so_number not in {row["so_number"] for row in board["contributions"]}


def test_r1_a_closed_order_with_no_class_stays_off_with_the_true_reason(api):
    client, world = api
    core, _lines = _retail_order(world, klass=None)
    _closed(world, core)

    with pytest.raises(AppException) as refused:
        ProjectSOAdoptionService(world.db).adopt(str(core.id))
    board = _board_of(client, core)
    skipped = {row["so_number"]: row["reason"] for row in board.get("unplanned_orders", [])}

    assert refused.value.status_code == 409
    assert "class" in refused.value.message.lower(), refused.value.message
    assert core.so_number not in {row["so_number"] for row in board["contributions"]}
    assert "class" in skipped.get(core.so_number, "").lower(), skipped


def test_r6_a_closed_retail_order_does_not_flood_the_planning_worklist(api):
    """The worklist stays open orders with quantity owed; a settled one is reachable from its
    own page, not from the list."""
    client, world = api
    core, lines = _retail_order(world, lines=(("dealer", "1"),))
    _settle(world, core, lines)

    listed = _numbers(_listed(client, demand_class=["retail", "other", "project"]))

    assert core.so_number not in listed


def test_r6_an_open_retail_order_with_quantity_owed_is_still_listed(api):
    client, world = api
    core, _lines = _retail_order(world, lines=(("dealer", "1"),))

    listed = _numbers(_listed(client, demand_class=["retail", "other", "project"]))

    assert core.so_number in listed
