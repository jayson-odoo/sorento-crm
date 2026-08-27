"""UAC F2 / F3 and plan sections 5.9 / 5.11 - two fields the lightboxes name things with.

`project_title` (5.9): the Project and Retail dialogs both carry a Project column, and a
demand row carried the customer, the agent, the price and the quantity but never the job
the units are for - which is the thing a buyer recognises a project order by.

`pool_warehouse_code` (5.11): the SPO and PO dialogs say "to BRW", and a grouped product
row holds the pool's ID but no CODE. A run only writes rows for locations with demand, so
on live data (32MM TAIL PIECE COUPLING) no member sits at the pool to read one off, and
naming the first member instead printed a project bin beside a count that excludes it.

`response_model` drops what a schema does not declare, so both are asserted where the FE
reads them.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_m4_cash import _mk_product, _mk_supplier, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTRPAY"
SORENTO = "00000000-0000-0000-0000-000000000001"


def _client(scm_app, role_slug="admin"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return TestClient(app), db


def _run(db):
    rid = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO scm.reorder_run
            (id, status, buy_scope, decision_grain, front_planning_contract_version,
             started_at, created_by, run_log, source_system, source_ref, company_id,
             created_at)
        VALUES (CAST(:id AS uuid), 'completed', 'warehouse', 'product', 1, now(),
                'tester', CAST('{}' AS jsonb), 'scm', :ref, CAST(:co AS uuid), now())
    """), {"id": rid, "ref": f"{MARKER}-{rid[:8]}", "co": SORENTO})
    db.flush()
    return rid


def _rec(db, run_id, product_id, warehouse_id, *, supplier_id=None):
    rec_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO scm.reorder_recommendation
            (id, run_id, rec_type, product_id, warehouse_id, supplier_id, rounded_qty,
             recommended_qty, status, unit_cost, currency, inputs, company_id, created_at)
        VALUES (CAST(:id AS uuid), CAST(:run AS uuid), 'buy', CAST(:p AS uuid),
                CAST(:w AS uuid), CAST(:s AS uuid), 40, 40, 'proposed', 10, 'MYR',
                CAST('{}' AS jsonb), CAST(:co AS uuid), now())
    """), {"id": rec_id, "run": run_id, "p": product_id, "w": warehouse_id,
           "s": supplier_id, "co": SORENTO})
    db.flush()
    return rec_id


# ===========================================================================
# 5.11 - the pool's CODE beside its id
# ===========================================================================

def test_a_recommendation_row_names_its_pool(scm_app):
    client, db = _client(scm_app)
    pool_code = f"{MARKER}-POOL"
    pool = _mk_warehouse(db, pool_code)
    bin_id = _mk_warehouse(db, f"{MARKER}-POOL-BB")
    db.execute(text(
        "UPDATE warehouses SET pool_warehouse_id = CAST(:p AS uuid), segment = 'project' "
        "WHERE id = CAST(:w AS uuid)"
    ), {"p": pool, "w": bin_id})
    db.flush()

    run_id = _run(db)
    prod = _mk_product(db, f"{MARKER}-SKU")
    _rec(db, run_id, prod, bin_id, supplier_id=_mk_supplier(db, f"{MARKER} supplier"))

    body = client.get(
        f"/api/v1/scm/reorder-runs/{run_id}/recommendations?page=1&limit=50"
    ).json()
    row = next(r for r in body["data"] if r["product_id"] == prod)

    assert row["pool_warehouse_id"] == pool
    # The CODE, so a grouped row can say "to BRW" without reading it off a member that
    # may not exist.
    assert row["pool_warehouse_code"] == pool_code


def test_a_location_with_no_pool_is_its_own(scm_app):
    client, db = _client(scm_app)
    code = f"{MARKER}-SOLO"
    wid = _mk_warehouse(db, code)
    run_id = _run(db)
    prod = _mk_product(db, f"{MARKER}-SKU-SOLO")
    _rec(db, run_id, prod, wid, supplier_id=_mk_supplier(db, f"{MARKER} supplier solo"))

    body = client.get(
        f"/api/v1/scm/reorder-runs/{run_id}/recommendations?page=1&limit=50"
    ).json()
    row = next(r for r in body["data"] if r["product_id"] == prod)

    assert row["pool_warehouse_code"] == code


# ===========================================================================
# 5.9 - the job a demand line is for
# ===========================================================================

def test_a_demand_row_names_the_project_it_is_for(scm_app):
    """The core sales-order line carries no project; the project sales-order line that
    mirrors it does, and that is the join the dialog's Project column needs.

    Read on the CONFIRMED leg, which is what `channel=project` actually returns: project
    demand is the Order Inquiry alone since P3, so the book query excludes project class
    outright and the Project dialog reads this leg.
    """
    from app.services.scm.demand import ACTIVE_DECISION_STATE, BUY_VERB

    client, db = _client(scm_app)
    wid = _mk_warehouse(db, f"{MARKER}-W-DEMAND")
    prod = _mk_product(db, f"{MARKER}-SKU-DEMAND")
    run_id = _run(db)
    rec_id = _rec(db, run_id, prod, wid,
                  supplier_id=_mk_supplier(db, f"{MARKER} supplier demand"))

    title = f"{MARKER} Riverside Tower"
    project_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO projects.projects
            (id, company_id, project_code, title, normalised_title, created_at)
        VALUES (CAST(:id AS uuid), CAST(:co AS uuid), :code, :title, lower(:title), now())
    """), {"id": project_id, "co": SORENTO, "code": f"{MARKER}-{project_id[:8]}",
           "title": title})

    so_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO sales_orders
            (id, so_number, status, order_date, demand_class, company_id,
             created_at, updated_at)
        VALUES (CAST(:id AS uuid), :num, 'open', now(), 'project', CAST(:co AS uuid),
                now(), now())
    """), {"id": so_id, "num": f"{MARKER}-SO-{so_id[:8]}", "co": SORENTO})
    line_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO sales_order_lines
            (id, sales_order_id, product_id, warehouse_id, qty_ordered, qty_delivered,
             unit_price, line_status, purchasing_status, company_id, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:so AS uuid), CAST(:p AS uuid), CAST(:w AS uuid),
                12, 0, 5.5, 'open', 'pending', CAST(:co AS uuid), now(), now())
    """), {"id": line_id, "so": so_id, "p": prod, "w": wid, "co": SORENTO})

    pso_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO projects.sales_orders
            (id, project_id, provisional_ref, status, company_id, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:pj AS uuid), :ref, 'published',
                CAST(:co AS uuid), now(), now())
    """), {"id": pso_id, "pj": project_id, "ref": f"{MARKER}-PSO-{pso_id[:8]}",
           "co": SORENTO})
    psl_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO projects.sales_order_lines
            (id, project_sales_order_id, line_no, core_sales_order_line_id, product_id,
             qty, unit_price, amount, company_id, created_at)
        VALUES (CAST(:id AS uuid), CAST(:so AS uuid), 1, CAST(:core AS uuid),
                CAST(:p AS uuid), 12, 5.5, 66, CAST(:co AS uuid), now())
    """), {"id": psl_id, "so": pso_id, "core": line_id, "p": prod, "co": SORENTO})

    decision_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO projects.so_supply_decisions
            (id, project_sales_order_id, revision_no, state, line_snapshots, company_id)
        VALUES (CAST(:id AS uuid), CAST(:so AS uuid), 1, :state, CAST('{}' AS jsonb),
                CAST(:co AS uuid))
    """), {"id": decision_id, "so": pso_id, "state": ACTIVE_DECISION_STATE,
           "co": SORENTO})
    inquiry_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO projects.order_inquiries
            (id, project_sales_order_id, state, raised_at, company_id, inquiry_no)
        VALUES (CAST(:id AS uuid), CAST(:so AS uuid), 'open', now(), CAST(:co AS uuid),
                :no)
    """), {"id": inquiry_id, "so": pso_id, "co": SORENTO,
           "no": f"{MARKER}-OI-{inquiry_id[:8]}"})
    db.execute(text("""
        INSERT INTO projects.order_inquiry_rows
            (id, order_inquiry_id, so_line_id, supply_decision_id, item_code, qty,
             verb, state, company_id, created_at)
        VALUES (CAST(:id AS uuid), CAST(:oi AS uuid), CAST(:line AS uuid),
                CAST(:d AS uuid), :code, 12, :verb, 'raised', CAST(:co AS uuid), now())
    """), {"id": str(uuid.uuid4()), "oi": inquiry_id, "line": psl_id, "d": decision_id,
           "code": f"{MARKER}-SKU-DEMAND", "verb": BUY_VERB, "co": SORENTO})
    db.flush()

    body = client.get(
        f"/api/v1/scm/reorder-runs/{run_id}/recommendations/{rec_id}/demand"
        "?channel=project"
    ).json()
    line = next(ln for ln in body["lines"] if ln["so_number"].startswith(MARKER))

    assert line["project_title"] == title


def test_a_retail_line_carries_the_key_with_no_project_behind_it(scm_app):
    """Absent is a fact, not a gap - a retail order is for nobody's job, and the column
    has to render a dash rather than crash on a missing key."""
    client, db = _client(scm_app)
    wid = _mk_warehouse(db, f"{MARKER}-W-RETAIL")
    prod = _mk_product(db, f"{MARKER}-SKU-RETAIL")
    run_id = _run(db)
    rec_id = _rec(db, run_id, prod, wid,
                  supplier_id=_mk_supplier(db, f"{MARKER} supplier retail"))

    so_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO sales_orders
            (id, so_number, status, order_date, demand_class, company_id,
             created_at, updated_at)
        VALUES (CAST(:id AS uuid), :num, 'open', now(), 'dealer', CAST(:co AS uuid),
                now(), now())
    """), {"id": so_id, "num": f"{MARKER}-SOR-{so_id[:8]}", "co": SORENTO})
    db.execute(text("""
        INSERT INTO sales_order_lines
            (id, sales_order_id, product_id, warehouse_id, qty_ordered, qty_delivered,
             unit_price, line_status, purchasing_status, company_id, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:so AS uuid), CAST(:p AS uuid), CAST(:w AS uuid),
                7, 0, 3.25, 'open', 'pending', CAST(:co AS uuid), now(), now())
    """), {"id": str(uuid.uuid4()), "so": so_id, "p": prod, "w": wid, "co": SORENTO})
    db.flush()

    body = client.get(
        f"/api/v1/scm/reorder-runs/{run_id}/recommendations/{rec_id}/demand"
    ).json()
    line = next(ln for ln in body["lines"] if ln["so_number"].startswith(MARKER))

    assert "project_title" in line
    assert line["project_title"] is None
