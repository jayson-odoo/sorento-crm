"""RED tests, written before the coder's Phase 2, for
`PLAN-reorder-plan-demand-class-orders.md` / its UAC (T1-T12).

Start Plan gains a Demand scope (`project` | `retail` | unset = both, unchanged) and,
for Project, an explicit `so_numbers` order scope - stored on `scm.reorder_run`, read
back on `GET /reorder-runs/{id}`, carried through Re-plan, applied inside
`demand.horizon_committed_select_sql`, and offered as pickable candidates by a new
`GET /reorder-runs/candidate-orders` endpoint.

None of this exists yet: `CreateReorderRunRequest`/`ReplanReorderRunRequest` carry no
`demand_class`/`so_numbers` fields (pydantic drops the unknown keys silently rather than
422ing), `scm.reorder_run` has no such columns, `reorder_run_service.create_run` accepts no
such keyword, `demand.horizon_committed_select_sql` takes no arguments at all, and the
candidate-orders route does not exist (a request to it falls through to the
`/reorder-runs/{run_id}` handler with `run_id="candidate-orders"`, which cannot be cast to
a uuid). Every test below is expected to fail against that surface, for exactly one of
those reasons - never because of a broken seed or fixture.

Harness copied from `tests/scm/test_m3_run.py` (`_client`, `_mk_*`) and
`tests/scm/test_channel_read_model.py` (`_confirmed_leg`'s shape, inlined here with
`so_number`/`delivery_date` exposed - the two things this lane's tests scope on that the
shared helper does not). Postgres only, via `tests/scm/conftest.py::scm_app` - a live
TestClient over a rolled-back SAVEPOINT. CI's database starts empty: every test seeds its
own full chain, nothing borrowed off the shared local database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.user import User
from app.services.project_service import register_project
from app.services.scm import demand
from app.services.scm import demand_breakdown_service as dbs
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, scm_app  # noqa: F401 - pytest fixture
from tests.scm.test_m3_run import (
    _client,
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg

MARKER = "ZZTDCS"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _project_numbering_rule(db) -> None:
    """`register_project` draws the project code from an enabled numbering rule; CI's
    freshly-migrated database has none (copied from
    `tests.scm.test_channel_read_model._project_numbering_rule`)."""
    present = db.execute(
        text("select 1 from document_numbering_rules where doc_type = 'project' and enabled limit 1")
    ).first()
    if present is not None:
        return
    db.execute(
        text(
            "insert into document_numbering_rules "
            "(id, doc_type, enabled, prefix_template, number_digits, next_value, "
            " start_value, reset_policy) "
            "values (:id, 'project', true, :prefix, 6, 123, 1, 'none')"
        ),
        {"id": _u(), "prefix": f"{MARKER}-"},
    )
    db.flush()


def _company(db, name: str) -> str:
    """Another company, for the cross-company absence check (T11)."""
    coid = _u()
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": coid, "n": name, "c": f"ZZTDCSCO-{coid[:8]}"},
    )
    return coid


def _project_so_with_lines(db, *, lines: list[dict], company_id: str = SORENTO_COMPANY_ID) -> dict:
    """One project SO carrying N confirmed-leg ORDER rows.

    `so_supply_decisions` enforces ONE active revision per Project SO (a partial unique
    index - see the model docstring), so a multi-row SO is built as ONE decision whose
    `line_snapshots` covers every line, never as one decision per row. `lines` is a list of
    `{product_id, warehouse_id, qty, delivery_date, ack_state=, inquiry_state=}`.

    Returns `{so_number, rows: [OrderInquiryRow, ...]}` in the SAME order as `lines`.
    """
    so_number = _code("SO")
    so = SalesOrder(
        id=_u(), so_number=so_number, status="open", demand_class="project",
        company_id=company_id,
    )
    db.add(so)
    db.flush()

    owner_id = _u()
    db.add(User(id=owner_id, email=f"{owner_id}@{MARKER.lower()}.test", name=f"{MARKER} CS"))
    db.flush()
    _project_numbering_rule(db)
    project = register_project(
        db, company_id=company_id, actor_user_id=owner_id,
        developer_party_id=None, title=f"{MARKER} project {_u()[:8]}",
    )
    pso = ProjectSalesOrder(
        id=_u(), company_id=company_id, project_id=project.id,
        provisional_ref=_code("PSO"), so_id=so.id,
    )
    db.add(pso)
    db.flush()
    inquiry = OrderInquiry(id=_u(), company_id=company_id, project_sales_order_id=pso.id)
    db.add(inquiry)
    db.flush()

    built = []
    for n, spec in enumerate(lines, start=1):
        core_line = SalesOrderLine(
            id=_u(), sales_order_id=so.id, product_id=spec["product_id"],
            warehouse_id=spec["warehouse_id"], qty_ordered=spec["qty"], qty_delivered=0,
            line_status="open", company_id=company_id,
        )
        db.add(core_line)
        db.flush()
        pso_line = ProjectSalesOrderLine(
            id=_u(), company_id=company_id, project_sales_order_id=pso.id,
            line_no=n, product_id=spec["product_id"], qty=spec["qty"],
            core_sales_order_line_id=core_line.id,
        )
        db.add(pso_line)
        db.flush()
        built.append((spec, core_line, pso_line))

    decision = SOSupplyDecision(
        id=_u(), company_id=company_id, project_sales_order_id=pso.id,
        revision_no=1, state="active",
        line_snapshots=[
            {
                "line_no": n, "project_line_id": str(pso_line.id),
                "core_line_id": str(core_line.id), "buy_qty": str(spec["qty"]),
            }
            for n, (spec, core_line, pso_line) in enumerate(built, start=1)
        ],
        confirmed_at=datetime.utcnow(),
    )
    db.add(decision)
    db.flush()

    rows = []
    for spec, _core_line, pso_line in built:
        row = OrderInquiryRow(
            id=_u(), company_id=company_id, order_inquiry_id=inquiry.id,
            so_line_id=pso_line.id, qty=spec["qty"], verb=IV_ORDER,
            state=spec.get("inquiry_state", INQUIRY_RAISED),
            supply_decision_id=decision.id,
            ack_state=spec.get("ack_state", ACK_ACKNOWLEDGED),
            delivery_date=spec.get("delivery_date"),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return {"so_number": so_number, "so": so, "pso": pso, "rows": rows}


def _retail_row(db, *, product_id, warehouse_id, qty, so_number, required_date):
    so = SalesOrder(id=_u(), so_number=so_number, status="open", demand_class="retail")
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product_id, warehouse_id=warehouse_id,
        qty_ordered=qty, qty_delivered=0, line_status="open", required_date=required_date,
    )
    db.add(line)
    db.flush()
    return so, line


def _committed_for(db, run_id, pid) -> float:
    row = db.execute(
        text(
            "SELECT inputs FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND product_id = :p AND rec_type IN ('buy', 'covered') LIMIT 1"
        ),
        {"r": run_id, "p": pid},
    ).mappings().first()
    assert row is not None, "expected a recommendation row for the product"
    return float((row["inputs"] or {}).get("committed") or 0)


def _seed_scope_universe(db) -> dict:
    """T4-T7's shared seed (UAC seed paragraph): one retail line in range, SO A carrying
    an in-range acked row, an OUT-of-range acked row and an in-range AWAITING row, and SO B
    carrying one in-range acked row - all one product x warehouse, so a run's committed
    figure is a single, comparable number.
    """
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"))
    db.flush()

    so_a = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 11, "delivery_date": date(2026, 9, 1)},
        {"product_id": pid, "warehouse_id": wid, "qty": 99, "delivery_date": date(2027, 1, 4)},
        {"product_id": pid, "warehouse_id": wid, "qty": 50, "delivery_date": date(2026, 9, 10),
         "ack_state": ACK_AWAITING},
    ])
    so_b = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 13, "delivery_date": date(2026, 9, 20)},
    ])
    _retail_row(db, product_id=pid, warehouse_id=wid, qty=7, so_number=_code("SOR"),
                required_date=date(2026, 9, 15))
    db.flush()
    return {"wid": wid, "pid": pid, "so_a": so_a["so_number"], "so_b": so_b["so_number"]}


# =============================================================================
# T1-T3 - the scope is stored on the run and carried through Re-plan (route level)
# =============================================================================

def test_t1_create_run_stores_and_returns_demand_class_and_so_numbers(scm_app):
    app, db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": [],
            "demand_class": "project",
            "so_numbers": ["SO1"],
        })
        assert resp.status_code == 202, resp.text
        run_id = resp.json()["run_id"]

        # The DB row: raw SQL, so a still-missing migration fails as UndefinedColumn
        # rather than a silently-empty ORM read.
        stored = db.execute(
            text("SELECT demand_class, so_numbers FROM scm.reorder_run WHERE id = :id"),
            {"id": run_id},
        ).mappings().first()
        assert stored is not None
        assert stored["demand_class"] == "project"
        assert list(stored["so_numbers"] or []) == ["SO1"]

        status = c.get(f"/api/v1/scm/reorder-runs/{run_id}")
        assert status.status_code == 200, status.text
        body = status.json()
        assert body["demand_class"] == "project"
        assert body["so_numbers"] == ["SO1"]


def test_t2_so_numbers_without_project_demand_class_is_refused(scm_app):
    app, _db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        omitted = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": [], "so_numbers": ["SO1"],
        })
        retail = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": [], "demand_class": "retail", "so_numbers": ["SO1"],
        })

    assert omitted.status_code == 422, omitted.text
    assert retail.status_code == 422, retail.text


def test_t3_replan_carries_demand_class_and_so_numbers_onto_the_new_run(scm_app):
    app, db = _client(scm_app, "purchasing")
    old = svc.create_run(db, [], enqueue=False)
    svc.run_reorder(old["run_id"], db=db)

    with TestClient(app) as c:
        resp = c.post(f"/api/v1/scm/reorder-runs/{old['run_id']}/replan", json={
            "warehouse_codes": [],
            "demand_class": "project",
            "so_numbers": ["SO9"],
        })
        assert resp.status_code == 202, resp.text
        new_run_id = resp.json()["run_id"]

    stored = db.execute(
        text("SELECT demand_class, so_numbers FROM scm.reorder_run WHERE id = :id"),
        {"id": new_run_id},
    ).mappings().first()
    assert stored is not None
    assert stored["demand_class"] == "project"
    assert list(stored["so_numbers"] or []) == ["SO9"]


# =============================================================================
# T4-T8 - the scope is actually APPLIED (service level, synchronous run)
# =============================================================================

def test_t4_project_scoped_to_one_so_counts_only_that_sos_in_range_acked_qty(scm_app):
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="project", so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 11.0


def test_t5_project_with_no_order_scope_counts_every_in_range_acked_so(scm_app):
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="project", so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 24.0


def test_t6_retail_counts_only_the_retail_line(scm_app):
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="retail", so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 7.0


def test_t7_no_demand_class_is_unchanged_behaviour(scm_app):
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class=None, so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 31.0


def test_t8_demand_drill_matches_the_scoped_runs_frozen_committed_figure(scm_app):
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="project", so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    row = db.execute(
        text(
            "SELECT id::text AS id, inputs FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND product_id = :p AND rec_type IN ('buy', 'covered') LIMIT 1"
        ),
        {"r": created["run_id"], "p": u["pid"]},
    ).mappings().first()
    assert row is not None

    out = dbs.demand_for_recommendation(db, row["id"])

    assert [line["so_number"] for line in out["lines"]] == [u["so_a"]]
    assert out["committed_total"] == float((row["inputs"] or {}).get("committed"))


# =============================================================================
# T9-T11 - GET /reorder-runs/candidate-orders (new endpoint)
# =============================================================================

def test_t9_candidate_orders_lists_open_project_sos_with_their_row_counts(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    db.flush()

    so_a = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 5, "delivery_date": date(2026, 9, 1)},
        {"product_id": pid, "warehouse_id": wid, "qty": 3, "delivery_date": date(2026, 9, 10),
         "ack_state": ACK_AWAITING},
    ])
    so_b = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 8, "delivery_date": date(2026, 9, 20)},
    ])
    # A "closed" SO: its one row is CANCELLED, so it earns no open row at all and must be
    # absent, the same as a genuinely closed SO would be.
    so_closed = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 4, "delivery_date": date(2026, 9, 5),
         "inquiry_state": INQUIRY_CANCELLED},
    ])
    # A retail SO: not a project leg at all, must be absent.
    retail_so, _line = _retail_row(db, product_id=pid, warehouse_id=wid, qty=6,
                                    so_number=_code("SOR"), required_date=date(2026, 9, 1))

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/reorder-runs/candidate-orders",
                      params={"from": "2026-09-01", "to": "2026-10-31"})

    assert resp.status_code == 200, resp.text
    by_so = {row["so_number"]: row for row in resp.json()}

    assert so_a["so_number"] in by_so
    a = by_so[so_a["so_number"]]
    assert a["rows_total"] == 2
    assert a["rows_in_range"] == 2
    assert a["rows_awaiting"] == 1
    assert a["first_delivery"] == "2026-09-01"
    assert a["last_delivery"] == "2026-09-10"

    assert so_b["so_number"] in by_so
    b = by_so[so_b["so_number"]]
    assert b["rows_total"] == 1
    assert b["rows_in_range"] == 1
    assert b["rows_awaiting"] == 0
    assert b["first_delivery"] == b["last_delivery"] == "2026-09-20"

    assert so_closed["so_number"] not in by_so, "a closed SO (no open rows) must be absent"
    assert retail_so.so_number not in by_so, "a retail SO is not a project leg"


def test_t10_candidate_orders_with_no_bounds_every_row_counts_as_in_range(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    db.flush()

    so = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 2, "delivery_date": date(2020, 1, 1)},
        {"product_id": pid, "warehouse_id": wid, "qty": 3, "delivery_date": date(2030, 12, 31)},
    ])

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/reorder-runs/candidate-orders")

    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["so_number"] == so["so_number"])
    assert row["rows_in_range"] == row["rows_total"] == 2


def test_t11_candidate_orders_is_company_scoped_and_needs_reorder_run_permission(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    db.flush()

    own = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 5, "delivery_date": date(2026, 9, 1)},
    ])
    foreign_company_id = _company(db, f"{MARKER} Other Co")
    foreign_wid = _mk_warehouse(db, _code("FWH"))
    foreign_pid = _mk_product(db, _code("FP"))
    db.flush()
    foreign = _project_so_with_lines(
        db,
        lines=[{
            "product_id": foreign_pid, "warehouse_id": foreign_wid, "qty": 9,
            "delivery_date": date(2026, 9, 1),
        }],
        company_id=foreign_company_id,
    )

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/reorder-runs/candidate-orders",
                      params={"from": "2026-01-01", "to": "2026-12-31"})
    assert resp.status_code == 200, resp.text
    numbers = {row["so_number"] for row in resp.json()}
    assert own["so_number"] in numbers
    assert foreign["so_number"] not in numbers, "another company's SO must not surface here"

    bare_app, _bare_db = _client(scm_app, None)
    with TestClient(bare_app) as c2:
        denied = c2.get("/api/v1/scm/reorder-runs/candidate-orders")
    assert denied.status_code == 403, denied.text


# =============================================================================
# T12 - the SQL builder itself takes keyword scope args, and an unscoped call still
# renders no `:so_numbers` bind (every OTHER caller - container_request_service,
# summary_order_service, loading_plan_service - keeps compiling/binding unchanged).
# =============================================================================

def test_t12_unscoped_call_renders_sql_with_no_so_numbers_bind():
    sql = demand.horizon_committed_select_sql(demand_class=None, so_scoped=False)
    assert ":so_numbers" not in sql
