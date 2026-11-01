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


def _head_migration():
    """The lane's one new migration is the alembic head (CI proves there is exactly one)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(_VERSIONS.parent))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, heads
    path = Path(script.get_revision(heads[0]).path)
    source = path.read_text()
    assert "customer_service" in source and all(slug in source for slug in _GRANTED), (
        f"the head migration {path.name} does not grant the Customer Service role "
        f"{_GRANTED}"
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
