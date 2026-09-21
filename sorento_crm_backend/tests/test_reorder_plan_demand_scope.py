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
    SOLineAllocation,
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
    return {
        "so_number": so_number, "so": so, "pso": pso, "inquiry": inquiry,
        "company_id": company_id, "rows": rows,
    }


def _add_form_row(db, project_so: dict, *, product_code: str, warehouse_code: str, qty,
                   delivery_date, ack_state: str = ACK_ACKNOWLEDGED,
                   inquiry_state: str = INQUIRY_RAISED) -> OrderInquiryRow:
    """A FORM-leg row (`demand.py`'s third leg, `supply_decision_id IS NULL`) on the SAME
    Order Inquiry as `project_so`'s confirmed lines - matched by `item_code`/
    `stock_location` rather than a core sales-order line, so it shares the inquiry's own
    SO number and `so_scoped` (`_SO_SCOPE_JOIN_SQL`, `demand.py:471`) sees it exactly as it
    sees a confirmed row on the same SO.
    """
    row = OrderInquiryRow(
        id=_u(), company_id=project_so["company_id"], order_inquiry_id=project_so["inquiry"].id,
        so_line_id=None, item_code=product_code, stock_location=warehouse_code, qty=qty,
        verb=IV_ORDER, state=inquiry_state, supply_decision_id=None,
        ack_state=ack_state, delivery_date=delivery_date,
    )
    db.add(row)
    db.flush()
    return row


def _add_reserve_claim(db, project_so: dict, *, product_id, warehouse_id, qty,
                        required_date=None) -> None:
    """A confirmed Project Reserve claim on `project_so`'s own PSO (`so_line_allocations`,
    `source_type='reserve'`) - the seed shape `tests/scm/test_plan_horizon_review_fixes.py`'s
    `_project_reserve` uses, adapted to hang off an EXISTING project SO (there via its own
    throwaway one) so the claim's SO number is `project_so`'s, which is what
    `_project_supply_reduction_map`'s own SO join (`reorder_run_service.py` ~1263) scopes on.
    Reuses the PSO's one ACTIVE decision (`so_supply_decisions` allows only one per PSO) via
    a second, otherwise-unrelated core line/PSO line - the join needs `d.project_sales_order_id`
    to match, not this specific line to be IN `d.line_snapshots`.
    """
    core_line = SalesOrderLine(
        id=_u(), sales_order_id=project_so["so"].id, product_id=product_id,
        warehouse_id=warehouse_id, qty_ordered=qty, qty_delivered=0, line_status="open",
        required_date=required_date, company_id=project_so["company_id"],
    )
    db.add(core_line)
    db.flush()
    pso_line = ProjectSalesOrderLine(
        id=_u(), company_id=project_so["company_id"], project_sales_order_id=project_so["pso"].id,
        line_no=999, product_id=product_id, qty=qty, core_sales_order_line_id=core_line.id,
    )
    db.add(pso_line)
    db.flush()
    alloc = SOLineAllocation(
        id=_u(), so_line_id=pso_line.id, source_type="reserve",
        warehouse_id=warehouse_id, qty=qty, company_id=project_so["company_id"],
    )
    db.add(alloc)
    db.flush()


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


def _unlocated_retail_row(db, *, product_id, qty, so_number, required_date):
    """A retail line naming NO warehouse - `_unlocated_demand_map`/`_apply_unlocated_demand`
    (`reorder_run_service.py` ~1624/1724), landed on whichever of the product's rows holds
    the most stock. Our seed has exactly one (wid), so it lands there deterministically."""
    so = SalesOrder(id=_u(), so_number=so_number, status="open", demand_class="retail")
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product_id, warehouse_id=None,
        qty_ordered=qty, qty_delivered=0, line_status="open", required_date=required_date,
    )
    db.add(line)
    db.flush()
    return so, line


def _inputs_for(db, run_id, pid) -> dict:
    row = db.execute(
        text(
            "SELECT id::text AS id, inputs FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND product_id = :p AND rec_type IN ('buy', 'covered') LIMIT 1"
        ),
        {"r": run_id, "p": pid},
    ).mappings().first()
    assert row is not None, "expected a recommendation row for the product"
    return dict(row)


def _committed_for(db, run_id, pid) -> float:
    return float((_inputs_for(db, run_id, pid)["inputs"] or {}).get("committed") or 0)


def _seed_scope_universe(db) -> dict:
    """T4-T8's shared seed (UAC seed paragraph, widened for the B1/B2 review-kill gaps):
    one retail line in range, SO A carrying an in-range acked row, an OUT-of-range acked
    row and an in-range AWAITING row, and SO B carrying one in-range acked row - all one
    product x warehouse, so a run's committed figure is a single, comparable number.

    B1 (review kill): SO A and SO B each also carry a FORM-leg row (`supply_decision_id
    IS NULL`, matched by item_code/warehouse rather than a confirmed decision) - distinct
    quantities (5 / 3) so a broken `so_scoped` join on the FORM leg specifically (as
    opposed to the confirmed leg, which T4/T5 already exercised) is caught: SO B's form
    row must never appear in a run scoped to SO A alone.

    B2 (review kill): a Reserve claim (`so_line_allocations`, `source_type='reserve'`)
    against SO A (qty 6) and one against SO B (qty 2) - distinct quantities so a broken
    `_project_supply_reduction_map` SO join is caught the same way; and one retail line
    naming no warehouse (qty 9) - `_apply_unlocated_demand` must add it for a
    retail/unscoped run and must NOT for a project-scoped one.
    """
    wcode = _code("WH")
    pcode = _code("P")
    wid = _mk_warehouse(db, wcode)
    pid = _mk_product(db, pcode)
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

    # B1 - one form-leg row per SO, in range, acked, distinct quantities.
    _add_form_row(db, so_a, product_code=pcode, warehouse_code=wcode, qty=5,
                  delivery_date=date(2026, 9, 12))
    _add_form_row(db, so_b, product_code=pcode, warehouse_code=wcode, qty=3,
                  delivery_date=date(2026, 9, 22))

    # B2 - one reserve claim per SO, in range, distinct quantities.
    _add_reserve_claim(db, so_a, product_id=pid, warehouse_id=wid, qty=6,
                       required_date=date(2026, 9, 5))
    _add_reserve_claim(db, so_b, product_id=pid, warehouse_id=wid, qty=2,
                       required_date=date(2026, 9, 25))

    # B2 - one unlocated retail line, in range.
    _unlocated_retail_row(db, product_id=pid, qty=9, so_number=_code("SOU"),
                          required_date=date(2026, 9, 18))

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
    """committed: SO A's confirmed in-range qty (11) + SO A's FORM-leg row (5) = 16 - SO
    B's form row (3) and reserve (2) must NOT leak in, which is what would happen if the
    `so_scoped` join were missing from the FORM leg specifically
    (`demand.py:807`/`_SO_SCOPE_JOIN_SQL` at `demand.py:471`) rather than only the
    confirmed leg (`demand.py:733`) - B1 (review kill).

    `project_supply_reduction`: SO A's own reserve claim (6) only - SO B's (2) must not
    leak in, which is what a missing/incorrect SO join on
    `_project_supply_reduction_map` (`reorder_run_service.py` ~1263-1268, called from
    `_apply_project_supply_reduction`'s `scoped_so_numbers` line ~1314) would let through -
    B2 (review kill).
    """
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="project", so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    inputs = _inputs_for(db, created["run_id"], u["pid"])["inputs"]
    assert float(inputs.get("committed") or 0) == 16.0
    assert float(inputs.get("project_supply_reduction") or 0) == 6.0


def test_t5_project_with_no_order_scope_counts_every_in_range_acked_so(scm_app):
    """committed: (SO A confirmed 11 + form 5) + (SO B confirmed 13 + form 3) = 32 - an
    unscoped Project run nets every project order in range, both legs, both SOs."""
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="project", so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 32.0


def test_t6_retail_counts_the_retail_line_plus_unlocated_and_ignores_so_numbers(scm_app):
    """committed: the retail located line (7) + the unlocated retail line (9) = 16 - the
    `demand_class != "project"` gate on `_apply_unlocated_demand`
    (`reorder_run_service.py:1624`, called from `_plan_per_warehouse`) must still run for a
    retail-scoped plan, or the 9 never lands.

    `so_numbers=[so_a]` is passed here even though `demand_class='retail'` (a direct
    service call bypasses the HTTP-level "so_numbers needs project" validator, T2) so this
    also proves `_apply_project_supply_reduction`'s `scoped_so_numbers = so_numbers if
    (so_numbers and demand_class == "project") else None` (`reorder_run_service.py:1314`)
    checks `demand_class`, not merely `so_numbers` truthiness: `project_supply_reduction`
    must be BOTH reserves (6 + 2 = 8), unscoped, because the claimed stock is real supply
    regardless of which demand leg this run is examining - a guard that dropped the
    `demand_class` check would instead scope it to SO A alone (6).
    """
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="retail", so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    inputs = _inputs_for(db, created["run_id"], u["pid"])["inputs"]
    assert float(inputs.get("committed") or 0) == 16.0
    assert float(inputs.get("project_supply_reduction") or 0) == 8.0


def test_t7_no_demand_class_is_unchanged_behaviour(scm_app):
    """committed: retail (7) + unlocated (9) + SO A (11+5) + SO B (13+3) = 48 - every leg,
    every SO, the unlocated gate included (demand_class None != "project")."""
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class=None, so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 48.0


def test_t8_demand_drill_matches_the_scoped_runs_frozen_committed_figure(scm_app):
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="project", so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    row = _inputs_for(db, created["run_id"], u["pid"])

    out = dbs.demand_for_recommendation(db, row["id"])

    # SO A alone, but TWO lines now (B1): the confirmed row (named by its own SO number)
    # and the form row (named by its Order Inquiry's own `inquiry_no` - it has no
    # reconciled book line to hang an SO number off, `demand_breakdown_service.py:657`).
    # SO B's form row (qty 3) must be absent - if the SO join were missing on the drill's
    # own FORM leg, `len(lines)` would be 3 and `committed_total` would be 19, not 16.
    assert len(out["lines"]) == 2
    assert sorted(line["source"] for line in out["lines"]) == [
        "order_inquiry_confirmed", "order_inquiry_form",
    ]
    confirmed = next(line for line in out["lines"] if line["source"] == "order_inquiry_confirmed")
    assert confirmed["so_number"] == u["so_a"]
    assert out["committed_total"] == float((row["inputs"] or {}).get("committed")) == 16.0


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
