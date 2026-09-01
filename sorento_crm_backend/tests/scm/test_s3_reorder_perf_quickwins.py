"""S3 reorder perf quick wins (PLAN-scm-reorder-oi-feedback-1sep.md, issue #464,
migration `456_reorder_perf_quickwins`).

Four independent pieces landed in commit 8def0247a with NO tests (a process violation -
Phase 2 is test-first, and this suite is the belated red/green/refactor pass). Each test
below traces to one UAC id.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql

from app.models.procurement import PurchaseOrderLine
from app.services.scm import decision_service as dsvc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, set_plan_grain
from tests.scm.test_m4_cash import (
    _client,
    _link,
    _mk_demand,
    _mk_product,
    _mk_supplier,
    _mk_warehouse,
)
from tests.scm.test_plan_row_decision import _buy_rec, _mk_stock, _run_buys

pytestmark = requires_pg

MARKER = "ZZTS3"


# ===========================================================================
# AC-3.1 - the index exists and the decision-layer's PO-line lookups use it
# ===========================================================================

class TestIndexUsage:
    """`_po_for_rec` (single) and `_pos_for_recs` (batched, AC-3.2) both resolve a
    recommendation's draft/active PO line by `(source_ref, source_system)`. Mirrors
    the exact ORM filter each one runs and EXPLAINs it against the real, already-
    migrated database - the only place the index (created by migration
    `456_reorder_perf_quickwins`, née `454`) actually exists."""

    def _plan(self, db, statement) -> list[str]:
        compiled = statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        rows = db.execute(text(f"EXPLAIN {compiled}")).scalars().all()
        return list(rows)

    def test_the_index_exists(self, db_session):
        exists = db_session.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE tablename = 'purchase_order_lines' "
                "AND indexname = 'ix_purchase_order_lines_source_ref_system'"
            )
        ).scalar()
        assert exists == 1, "AC-3.1: ix_purchase_order_lines_source_ref_system is missing"

    def test_po_for_rec_single_lookup_plans_an_index_scan(self, db_session):
        """`decision_service._po_for_rec` - one rec id, both source systems."""
        stmt = (
            db_session.query(PurchaseOrderLine)
            .filter(
                PurchaseOrderLine.source_ref == str(uuid.uuid4()),
                PurchaseOrderLine.source_system.in_(("scm_recommendation", "scm_order_summary_row")),
            )
            .order_by(PurchaseOrderLine.created_at.desc())
        ).statement
        plan = self._plan(db_session, stmt)
        text_plan = "\n".join(plan)
        assert "Seq Scan on purchase_order_lines" not in text_plan, text_plan
        assert "ix_purchase_order_lines_source_ref_system" in text_plan, text_plan

    def test_pos_for_recs_batched_lookup_plans_an_index_scan(self, db_session):
        """`decision_service._pos_for_recs` - N rec ids at once (AC-3.2's own batching)."""
        rec_ids = [str(uuid.uuid4()) for _ in range(50)]
        stmt = (
            db_session.query(PurchaseOrderLine)
            .filter(
                PurchaseOrderLine.source_ref.in_(rec_ids),
                PurchaseOrderLine.source_system.in_(("scm_recommendation", "scm_order_summary_row")),
            )
            .order_by(PurchaseOrderLine.source_ref, PurchaseOrderLine.created_at.desc())
        ).statement
        plan = self._plan(db_session, stmt)
        text_plan = "\n".join(plan)
        assert "Seq Scan on purchase_order_lines" not in text_plan, text_plan
        assert "ix_purchase_order_lines_source_ref_system" in text_plan, text_plan

    def test_refresh_run_counts_join_plans_an_index_scan(self, db_session):
        """`decision_service._refresh_run_counts` LEFT JOINs `purchase_order_lines` by the
        same pair, keyed off `scm.reorder_recommendation.id::text` - the join predicate
        the AC-3.1 index-vs-guard corner case lives on (see
        `tests/scm/test_plan_read_path_uses_indexes.py`)."""
        plan = db_session.execute(
            text(
                "EXPLAIN "
                "SELECT count(*) FROM scm.reorder_recommendation r "
                "LEFT JOIN purchase_order_lines pol "
                "  ON pol.source_ref = r.id::text "
                " AND pol.source_system IN ('scm_recommendation', 'scm_order_summary_row') "
                "WHERE r.run_id = CAST(:run_id AS uuid)"
            ),
            {"run_id": str(uuid.uuid4())},
        ).scalars().all()
        text_plan = "\n".join(plan)
        # A hash/merge join over an empty-run-id-filtered `reorder_recommendation` scan is
        # fine either way - what this pins is that `purchase_order_lines`' OWN side of the
        # join is never a sequential scan of its 70k+ rows.
        assert "Seq Scan on purchase_order_lines" not in text_plan, text_plan


@pytest.fixture()
def db_session(scm_app):
    _, db, _, _ = scm_app
    return db


# ===========================================================================
# AC-3.2 - list_plan_row_decisions runs a CONSTANT number of queries
# ===========================================================================

def _bulk_seed_decisions(db, n: int, marker: str) -> str:
    """N products, N buy recs on ONE run, N plan_row_decision rows - every decision
    carrying a real `supplier_id` so `_suppliers_by_id` / `_product_supplier_leads_batch`
    are real round trips, not short-circuited empty sets. Direct bulk INSERTs (not the
    ORM/engine) so seeding N=300 stays fast; the read path under test
    (`list_plan_row_decisions`) is unaffected by how the fixture arrived."""
    from tests.scm.conftest import ensure_reference_data

    ensure_reference_data(db)
    cat, uom = db.execute(text(
        "SELECT category_id, base_uom_id FROM products WHERE category_id IS NOT NULL LIMIT 1"
    )).fetchone()

    run_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, decision_grain, "
        "front_planning_contract_version, company_id, created_at) "
        "VALUES (CAST(:id AS uuid), 'completed', 'location', 1, CAST(:co AS uuid), now())"
    ), {"id": run_id, "co": SORENTO_COMPANY_ID})

    supplier_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active, "
        "created_at, updated_at) "
        "VALUES (CAST(:id AS uuid), :code, :name, true, now(), now())"
    ), {"id": supplier_id, "code": f"{marker}-SUP", "name": f"{marker} supplier"})

    wid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "created_at, updated_at) "
        "VALUES (CAST(:id AS uuid), :code, :name, true, now(), now())"
    ), {"id": wid, "code": f"{marker}-W", "name": f"{marker} warehouse"})

    product_rows = []
    rec_rows = []
    decision_rows = []
    ps_rows = []
    for i in range(n):
        pid = str(uuid.uuid4())
        rec_id = str(uuid.uuid4())
        product_rows.append({
            "id": pid, "code": f"{marker}-P-{i}", "name": f"{marker} product {i}",
            "cat": cat, "uom": uom,
        })
        rec_rows.append({
            "id": rec_id, "run": run_id, "p": pid, "w": wid, "s": supplier_id,
            "co": SORENTO_COMPANY_ID,
        })
        decision_rows.append({
            "id": str(uuid.uuid4()), "rec": rec_id, "s": supplier_id,
            "co": SORENTO_COMPANY_ID,
        })
        ps_rows.append({"id": str(uuid.uuid4()), "p": pid, "s": supplier_id})

    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, is_active, is_discontinued, currency, created_at, updated_at) "
        "VALUES (CAST(:id AS uuid), :code, :name, :cat, :uom, 0, true, false, 'MYR', "
        "now(), now())"
    ), product_rows)
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation (id, run_id, rec_type, product_id, "
        "warehouse_id, supplier_id, rounded_qty, recommended_qty, unit_cost, currency, "
        "company_id, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:run AS uuid), 'buy', CAST(:p AS uuid), "
        "CAST(:w AS uuid), CAST(:s AS uuid), 10, 10, 20, 'MYR', CAST(:co AS uuid), now())"
    ), rec_rows)
    db.execute(text(
        "INSERT INTO scm.plan_row_decision (id, recommendation_id, kind, buy_qty, "
        "supplier_id, company_id, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:rec AS uuid), 'buy', 10, CAST(:s AS uuid), "
        "CAST(:co AS uuid), now())"
    ), decision_rows)
    db.execute(text(
        "INSERT INTO product_suppliers (id, product_id, supplier_id, "
        "standard_lead_time_days, unit_cost, currency, is_primary_supplier, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:p AS uuid), CAST(:s AS uuid), 14, 20, 'MYR', "
        "true, now())"
    ), ps_rows)
    db.flush()
    return run_id


def _count_queries(db, fn):
    calls = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        calls["n"] += 1

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", _count)
    try:
        result = fn()
    finally:
        event.remove(connection, "before_cursor_execute", _count)
    return result, calls["n"]


def test_list_plan_row_decisions_query_count_is_constant(scm_app):
    """AC-3.2 - 50 decisions and 300 decisions cost the SAME number of SQL statements.
    Measured in the implementation's own commit message at 5 (count, quads, suppliers,
    leads, PO lines) for 50 AND for 1,500; pinned here at 50 vs 300 to keep the suite
    fast while still proving the shape, not the specific number."""
    _, db, _, _ = scm_app

    small_run = _bulk_seed_decisions(db, 50, f"{MARKER}-SMALL")
    large_run = _bulk_seed_decisions(db, 300, f"{MARKER}-LARGE")
    db.flush()

    small_result, small_queries = _count_queries(
        db, lambda: dsvc.list_plan_row_decisions(db, small_run)
    )
    large_result, large_queries = _count_queries(
        db, lambda: dsvc.list_plan_row_decisions(db, large_run)
    )

    assert small_result["decided_count"] == 50
    assert large_result["decided_count"] == 300
    assert small_queries == large_queries, (
        f"query count scaled with decision count: {small_queries} at 50, "
        f"{large_queries} at 300"
    )
    # A generous ceiling, not the exact number - the point is O(1), not this literal
    # figure. 5 is what the implementation's own docstring measures; double that catches
    # a regression without pinning brittle internals.
    assert small_queries <= 10, small_queries


# ===========================================================================
# AC-3.3 - denormalised run counts, maintained by every write path
# ===========================================================================

def _run_counts(db, run_id) -> tuple[int, int, int]:
    db.expire_all()
    row = db.execute(text(
        "SELECT planned_count, decided_count, confirmed_count "
        "FROM scm.reorder_run WHERE id = CAST(:id AS uuid)"
    ), {"id": run_id}).mappings().first()
    return (int(row["planned_count"]), int(row["decided_count"]), int(row["confirmed_count"]))


def test_run_completion_sets_planned_count(scm_app):
    _, db, _, _ = scm_app
    run_id, _rec_id, _wid = _buy_rec(db, f"{MARKER}W-PLANNED", f"{MARKER}P-PLANNED")
    assert _run_counts(db, run_id) == (1, 0, 0)


def test_record_and_clear_plan_row_decision_move_decided_count(scm_app):
    _, db, _, _ = scm_app
    run_id, rec_id, _wid = _buy_rec(db, f"{MARKER}W-RC", f"{MARKER}P-RC")
    assert _run_counts(db, run_id) == (1, 0, 0)

    dsvc.record_plan_row_decision(db, rec_id, "buy", 10, [], None, [], None, "tester")
    assert _run_counts(db, run_id) == (1, 1, 0)

    dsvc.clear_plan_row_decision(db, rec_id, "tester")
    assert _run_counts(db, run_id) == (1, 0, 0)


def test_confirm_decisions_moves_confirmed_count(scm_app):
    _, db, _, _ = scm_app
    run_id, rec_id, _wid = _buy_rec(db, f"{MARKER}W-CONF", f"{MARKER}P-CONF")
    dsvc.record_plan_row_decision(db, rec_id, "buy", 10, [], None, [], None, "tester")
    assert _run_counts(db, run_id) == (1, 1, 0)

    dsvc.confirm_decisions(db, run_id, ids=None, actor="tester")
    assert _run_counts(db, run_id) == (1, 1, 1)


def test_reset_run_decisions_moves_every_count_back(scm_app):
    _, db, _, _ = scm_app
    run_id, rec_id, _wid = _buy_rec(db, f"{MARKER}W-RESET", f"{MARKER}P-RESET")
    dsvc.record_plan_row_decision(db, rec_id, "buy", 10, [], None, [], None, "tester")
    dsvc.confirm_decisions(db, run_id, ids=None, actor="tester")
    assert _run_counts(db, run_id) == (1, 1, 1)

    dsvc.reset_run_decisions(db, run_id, actor="tester")
    assert _run_counts(db, run_id) == (1, 0, 0)


def test_plans_list_reads_the_counts_without_joining_purchase_order_lines(scm_app):
    """AC-3.3 - the plans list resolves Planned/Decided/Confirmed off the stored
    columns; it must not issue any SQL statement naming `purchase_order_lines`."""
    app, db, _, _ = scm_app
    from tests.scm.conftest import as_user, seed_user

    uid = seed_user(db, "admin")
    as_user(app, *(scm_app[2], scm_app[3]), uid)
    run_id, rec_id, _wid = _buy_rec(db, f"{MARKER}W-NOJOIN", f"{MARKER}P-NOJOIN")
    dsvc.record_plan_row_decision(db, rec_id, "buy", 10, [], None, [], None, "tester")
    db.commit()

    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", _capture)
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/scm/reorder-runs?page=1&limit=100&query={MARKER}W-NOJOIN"
            )
    finally:
        event.remove(connection, "before_cursor_execute", _capture)

    assert res.status_code == 200, res.text
    # Strip `-- ...` SQL comments first: `list_reorder_runs`' own SELECT carries a code
    # comment NAMING `purchase_order_lines` in prose (explaining what it used to join), so
    # a raw substring search over the statement text would flag its own docstring.
    import re as _re

    def _sql_only(stmt: str) -> str:
        return _re.sub(r"--[^\n]*", "", stmt)

    offenders = [s for s in statements if "purchase_order_lines" in _sql_only(s)]
    assert not offenders, (
        "the plans list joined purchase_order_lines instead of reading the "
        "denormalised counts:\n  " + "\n  ".join(offenders)
    )


# ===========================================================================
# AC-3.4 - list_recommendations drops plan_basis and reads precomputed pool columns
# ===========================================================================

def test_recommendations_payload_never_carries_plan_basis(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid_code = f"{MARKER}W-PB"
    wid = _mk_warehouse(db, wid_code)
    pid = _mk_product(db, f"{MARKER}P-PB")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} PB supplier"), cost=60)
    db.flush()
    set_plan_grain(db, "location")
    run_id, rec_id, _wid = _run_buys(db, wid_code), None, None
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{run_id}/recommendations?limit=100")
    assert res.status_code == 200, res.text
    assert "plan_basis" not in res.text, "AC-3.4: plan_basis must never reach the wire"


def test_recommendations_payload_carries_the_precomputed_pool(scm_app):
    """A LOCATION-grain row's own pool - read straight off the precomputed
    `pool_warehouse_id`/`pool_warehouse_code` columns `reorder_run_service._build_rec`
    stamps at generation time (AC-3.4), never re-derived from `inputs.plan_basis` at
    read time."""
    app, db = _client(scm_app, "purchasing")
    wid_code = f"{MARKER}W-POOL"
    wid = _mk_warehouse(db, wid_code)
    pid = _mk_product(db, f"{MARKER}P-POOL")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} pool supplier"), cost=60)
    db.flush()
    set_plan_grain(db, "location")
    run_id = _run_buys(db, wid_code)
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{run_id}/recommendations?limit=100")
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    buy = next(r for r in rows if r["type"] == "buy")
    # No pool sibling is seeded, so the location IS its own pool - the row must still
    # name it (COALESCE(pool_warehouse_id, w.id) fallback), proving the column is read
    # and not left to a LATERAL that had nothing to unnest.
    assert buy["pool_warehouse_id"] is not None
    assert buy["pool_warehouse_code"] == wid_code


def test_a_network_row_with_no_precomputed_pool_reads_null_not_a_stale_lateral(scm_app):
    """A product/network-grain row (`warehouse_id IS NULL`) whose members do not all
    share one pool got `(None, None)` at generation time
    (`reorder_run_service._group_pool_from_basis`) and must still read `(None, None)`
    here - never fall back to deriving one from `inputs.plan_basis` at request time,
    which is exactly the per-row LATERAL AC-3.4 removed."""
    _, db, _, _ = scm_app
    from tests.scm.conftest import ensure_reference_data

    ensure_reference_data(db)
    run_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, decision_grain, "
        "front_planning_contract_version, company_id, created_at) "
        "VALUES (CAST(:id AS uuid), 'completed', 'product', 1, CAST(:co AS uuid), now())"
    ), {"id": run_id, "co": SORENTO_COMPANY_ID})
    cat, uom = db.execute(text(
        "SELECT category_id, base_uom_id FROM products WHERE category_id IS NOT NULL LIMIT 1"
    )).fetchone()
    pid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, is_active, is_discontinued, currency, created_at, updated_at) "
        "VALUES (CAST(:id AS uuid), :code, :name, :cat, :uom, 0, true, false, 'MYR', "
        "now(), now())"
    ), {"id": pid, "code": f"{MARKER}P-NET", "name": f"{MARKER} net product",
        "cat": cat, "uom": uom})
    rec_id = str(uuid.uuid4())
    # No pool_warehouse_id/code set (NULL, as generation left it), no `inputs.plan_basis`
    # either - if the read path fell back to deriving one, this row would not have the
    # data to derive it FROM, which is exactly the point.
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation (id, run_id, rec_type, product_id, "
        "warehouse_id, rounded_qty, recommended_qty, unit_cost, currency, "
        "company_id, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:run AS uuid), 'buy', CAST(:p AS uuid), "
        "NULL, 10, 10, 20, 'MYR', CAST(:co AS uuid), now())"
    ), {"id": rec_id, "run": run_id, "p": pid, "co": SORENTO_COMPANY_ID})
    db.commit()

    from tests.scm.conftest import as_user, seed_user

    app = scm_app[0]
    uid = seed_user(db, "purchasing")
    as_user(app, scm_app[2], scm_app[3], uid)
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{run_id}/recommendations?limit=100")
    assert res.status_code == 200, res.text
    row = res.json()["data"][0]
    assert row["pool_warehouse_id"] is None
    assert row["pool_warehouse_code"] is None
