"""UAC A4 - the plans list is a DataGrid, so the runs endpoint behaves like one.

`GET /api/v1/scm/reorder-runs` (plan section 5.4). `/scm/reorder` is now a list of plans
rather than a card of buttons under the latest one, which means the standard listing
contract applies: `page`, `limit`, `sort`, `dir`, `query` exactly as `buildDataGridParams`
sends them, and the columns the grid shows have to come off the row.

Four of those columns had no source at all before this: the "daily" badge (`is_scheduled`),
Products (`product_count`), Decided (`decided_product_count` / `product_count`, by PRODUCT
per R14) and the Confirmed status (`confirmed_product_count`). Phase 1 shipped them
rendering an honest "not known yet" rather than a guess, and this is what fills them in.

Every field is asserted through the ROUTE, not the service: `response_model` silently drops
what a schema does not declare, and a field that never reaches the FE is the same defect as
one that was never computed.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import decision_service as dsvc
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_m4_cash import _mk_product, _mk_supplier, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTRUNL"


def _client(scm_app, role_slug="admin"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return TestClient(app), db


def _run(db, *, created_by="a-person", horizon=None, warehouse_ids=None):
    rid = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO scm.reorder_run
            (id, status, buy_scope, decision_grain, front_planning_contract_version,
             started_at, created_by, plan_horizon_date, warehouse_ids, product_ids,
             run_log, source_system, source_ref, company_id, created_at)
        VALUES (CAST(:id AS uuid), 'completed', 'warehouse', 'product', 1,
                now(), :by, CAST(:hz AS date), CAST(:wh AS jsonb), NULL,
                CAST('{"recommendation_count": 1}' AS jsonb), 'scm', :ref,
                CAST(:co AS uuid), now())
    """), {"id": rid, "by": created_by, "hz": horizon, "wh": warehouse_ids,
           "ref": f"{MARKER}-{rid[:8]}",
           "co": "00000000-0000-0000-0000-000000000001"})
    db.flush()
    return rid


def _rec(db, run_id, product_id, warehouse_id, *, qty=50, supplier_id=None):
    rec_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO scm.reorder_recommendation
            (id, run_id, rec_type, product_id, warehouse_id, supplier_id, rounded_qty,
             recommended_qty, status, unit_cost, currency, inputs, company_id, created_at)
        VALUES (CAST(:id AS uuid), CAST(:run AS uuid), 'buy', CAST(:p AS uuid),
                CAST(:w AS uuid), CAST(:s AS uuid), :q, :q, 'proposed', 10, 'MYR',
                CAST('{}' AS jsonb), CAST(:co AS uuid), now())
    """), {"id": rec_id, "run": run_id, "p": product_id, "w": warehouse_id,
           "s": supplier_id, "q": qty,
           "co": "00000000-0000-0000-0000-000000000001"})
    db.flush()
    return rec_id


def _rows_for(body, run_ids):
    wanted = set(run_ids)
    return [r for r in body["data"] if r["run_id"] in wanted]


# ===========================================================================
# the DataGrid parameters
# ===========================================================================

def test_query_matches_a_warehouse_code(scm_app):
    """Warehouse code, and deliberately nothing else (captain's ruling, 28 Aug): a plan's
    only human handles are its time and its scope, and a product-code search over
    `product_ids` would answer "which plans mention this item", which is the plan PAGE's
    question, not the list's."""
    client, db = _client(scm_app)
    wid = _mk_warehouse(db, f"{MARKER}-FINDME")
    mine = _run(db, warehouse_ids=f'["{wid}"]')
    other = _run(db, warehouse_ids=None)

    body = client.get(
        f"/api/v1/scm/reorder-runs?page=1&limit=100&query={MARKER}-FINDME"
    ).json()
    ids = {r["run_id"] for r in body["data"]}

    assert mine in ids
    assert other not in ids


def test_sort_and_dir_reorder_the_page(scm_app):
    client, db = _client(scm_app)
    early = _run(db, horizon="2026-01-31")
    late = _run(db, horizon="2026-12-31")

    asc = client.get(
        "/api/v1/scm/reorder-runs?page=1&limit=100&sort=plan_horizon_date&dir=asc"
    ).json()
    desc = client.get(
        "/api/v1/scm/reorder-runs?page=1&limit=100&sort=plan_horizon_date&dir=desc"
    ).json()

    def _order(body):
        seq = [r["run_id"] for r in body["data"] if r["run_id"] in (early, late)]
        return seq

    assert _order(asc) == [early, late]
    assert _order(desc) == [late, early]


def test_an_unknown_sort_column_is_ignored_rather_than_500(scm_app):
    client, _db = _client(scm_app)
    res = client.get("/api/v1/scm/reorder-runs?page=1&limit=5&sort=drop_table&dir=asc")
    assert res.status_code == 200


def _run_at(db, *, started_at, created_at):
    """Same shape as `_run` above, but with an EXPLICIT (not `now()`) `started_at` /
    `created_at`, so two rows can be made to tie on BOTH exactly - the shape a bulk
    historical import or several runs queued in the same transaction produce, and the
    one `now()` itself cannot reproduce (a whole transaction sees one `now()`, but
    `_run`'s own two calls still land in two DIFFERENT statements/timestamps millis
    apart in practice)."""
    rid = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO scm.reorder_run
            (id, status, buy_scope, decision_grain, front_planning_contract_version,
             started_at, created_by, plan_horizon_date, warehouse_ids, product_ids,
             run_log, source_system, source_ref, company_id, created_at)
        VALUES (CAST(:id AS uuid), 'completed', 'warehouse', 'product', 1,
                CAST(:sa AS timestamp), 'a-person', NULL, NULL, NULL,
                CAST('{"recommendation_count": 1}' AS jsonb), 'scm', :ref,
                CAST(:co AS uuid), CAST(:ca AS timestamp))
    """), {"id": rid, "sa": started_at, "ca": created_at,
           "ref": f"{MARKER}-{rid[:8]}",
           "co": "00000000-0000-0000-0000-000000000001"})
    db.flush()
    return rid


def test_started_at_ties_break_deterministically_on_id(scm_app):
    """`ORDER BY started_at ASC NULLS LAST, created_at DESC` alone still ties when
    BOTH columns match, which several runs queued in one transaction (or a bulk
    historical import) produce - Postgres gives no stability guarantee across
    LIMIT/OFFSET pages without a final, always-unique key. Same defect class the
    recommendations list was fixed for (route's own comment above `order_by`)."""
    client, db = _client(scm_app)
    same = "2020-01-01T00:00:00"
    tied = sorted([
        _run_at(db, started_at=same, created_at=same) for _ in range(3)
    ])

    page1 = client.get(
        "/api/v1/scm/reorder-runs?page=1&limit=2&sort=started_at&dir=asc"
    ).json()
    page2 = client.get(
        "/api/v1/scm/reorder-runs?page=2&limit=2&sort=started_at&dir=asc"
    ).json()

    seen = _rows_for(page1, tied) + _rows_for(page2, tied)
    seen_ids = [r["run_id"] for r in seen]

    assert sorted(seen_ids) == tied, "paging over a full tie must show each row exactly once"
    assert seen_ids == tied, "the tie breaks on id, ascending, same as any other listing"


# ===========================================================================
# the columns the plans list shows
# ===========================================================================

def test_is_scheduled_marks_the_run_nobody_started(scm_app):
    client, db = _client(scm_app)
    scheduled = _run(db, created_by=None)
    manual = _run(db, created_by="a-person")

    body = client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json()
    by_id = {r["run_id"]: r for r in _rows_for(body, [scheduled, manual])}

    assert by_id[scheduled]["is_scheduled"] is True
    assert by_id[manual]["is_scheduled"] is False


def test_product_count_is_null_when_the_plan_narrowed_to_nothing(scm_app):
    """Null is the WHOLE catalogue (the daily run's own scope), not an unknown."""
    client, db = _client(scm_app)
    rid = _run(db)

    body = client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json()
    row = _rows_for(body, [rid])[0]

    assert row["product_count"] is None


def test_the_counts_are_by_product_never_by_location(scm_app):
    client, db = _client(scm_app)
    rid = _run(db)
    sup = _mk_supplier(db, f"{MARKER} supplier")
    decided = _mk_product(db, f"{MARKER}-P-DECIDED")
    untouched = _mk_product(db, f"{MARKER}-P-UNTOUCHED")
    # THREE bins of one product, decided once - the shape R14 exists for.
    rec_ids = [
        _rec(db, rid, decided, _mk_warehouse(db, f"{MARKER}-W{i}"), supplier_id=sup)
        for i in range(3)
    ]
    _rec(db, rid, untouched, _mk_warehouse(db, f"{MARKER}-W-OTHER"), supplier_id=sup)
    for rec_id in rec_ids:
        dsvc.record_plan_row_decision(db, rec_id, "buy", 40, [], None, [], None, None)

    body = client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json()
    row = _rows_for(body, [rid])[0]

    # `product_count` is the SCOPE the plan was launched with (null here = every product);
    # `planned_product_count` is what it actually wrote rows for, which is the denominator
    # the Decided column needs - "1 / -" would be the alternative on the daily run.
    assert row["product_count"] is None
    assert row["planned_product_count"] == 2, "the plan covers two products, not four rows"
    assert row["decided_product_count"] == 1, "one product decided, not three bins"
    assert row["confirmed_product_count"] == 0


def test_confirmed_product_count_follows_the_draft_purchase_orders(scm_app):
    client, db = _client(scm_app)
    rid = _run(db)
    sup = _mk_supplier(db, f"{MARKER} supplier c")
    prod = _mk_product(db, f"{MARKER}-P-CONFIRMED")
    rec_id = _rec(db, rid, prod, _mk_warehouse(db, f"{MARKER}-W-CONF"), supplier_id=sup)
    dsvc.record_plan_row_decision(db, rec_id, "buy", 40, [], None, [], None, None)
    dsvc.confirm_decisions(db, rid, None, None)

    body = client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json()
    row = _rows_for(body, [rid])[0]

    assert row["confirmed_product_count"] == 1


def test_resetting_a_confirmed_plan_puts_the_list_back_to_planning(scm_app):
    """The Status column is derived from `confirmed_product_count`, which is read off the
    DRAFT purchase orders - so a reset that left the draft lines behind kept the plan
    reading Confirmed forever."""
    client, db = _client(scm_app)
    rid = _run(db)
    sup = _mk_supplier(db, f"{MARKER} reset supplier")
    prod = _mk_product(db, f"{MARKER}-P-RESET")
    rec_id = _rec(db, rid, prod, _mk_warehouse(db, f"{MARKER}-W-RESET"), supplier_id=sup)
    dsvc.record_plan_row_decision(db, rec_id, "buy", 40, [], None, [], None, None)
    dsvc.confirm_decisions(db, rid, None, None)

    body = client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json()
    assert _rows_for(body, [rid])[0]["confirmed_product_count"] == 1

    dsvc.reset_run_decisions(db, rid, None)

    row = _rows_for(
        client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json(), [rid])[0]
    assert row["confirmed_product_count"] == 0, "Planning again, not Confirmed"
    assert row["decided_product_count"] == 0


def test_a_run_covering_every_warehouse_says_so(scm_app):
    """A plan launched with no warehouse scope stores EVERY active warehouse id, so the
    list would read "60 warehouses" for what the buyer asked for as "all" (fix c)."""
    client, db = _client(scm_app)
    # CI's database starts empty; two seeded warehouses make "one of them" a strict subset.
    _mk_warehouse(db, f"{MARKER}-ALL-A")
    _mk_warehouse(db, f"{MARKER}-ALL-B")
    db.flush()
    every = [str(r[0]) for r in db.execute(text(
        "SELECT id FROM warehouses WHERE is_active = true")).all()]
    import json as _json
    everywhere = _run(db, warehouse_ids=_json.dumps(every))
    somewhere = _run(db, warehouse_ids=_json.dumps(every[:1]))

    body = client.get("/api/v1/scm/reorder-runs?page=1&limit=100").json()
    by_id = {r["run_id"]: r for r in _rows_for(body, [everywhere, somewhere])}

    assert by_id[everywhere]["is_all_warehouses"] is True
    assert by_id[somewhere]["is_all_warehouses"] is False


# ===========================================================================
# the plan header (plan section 5.10)
# ===========================================================================

def test_the_run_detail_carries_started_at(scm_app):
    client, db = _client(scm_app)
    rid = _run(db)

    body = client.get(f"/api/v1/scm/reorder-runs/{rid}").json()

    assert body["started_at"], "the plan header reads 'Plan dd/mm/yyyy HH:mm' off this"


def test_sorting_by_decided_orders_by_the_products_decided(scm_app):
    """The Decided column is sortable on the grid, and ORDER BY runs over the whole
    filtered set before the page is cut - so the count has to be sortable in SQL, not
    re-sorted in Python after the page came back."""
    client, db = _client(scm_app)
    sup = _mk_supplier(db, f"{MARKER} sort supplier")
    # Both plans name the same marker warehouse, so `query` narrows the page to exactly
    # these two - on the prod-copy database there are hundreds of real runs, and a page of
    # 100 sorted ascending would simply not reach them.
    scope = _mk_warehouse(db, f"{MARKER}-W-SORTQ")
    none_decided = _run(db, warehouse_ids=f'["{scope}"]')
    two_decided = _run(db, warehouse_ids=f'["{scope}"]')
    for i in range(2):
        rec = _rec(db, two_decided, _mk_product(db, f"{MARKER}-P-SORT{i}"),
                   _mk_warehouse(db, f"{MARKER}-W-SORT{i}"), supplier_id=sup)
        dsvc.record_plan_row_decision(db, rec, "buy", 5, [], None, [], None, None)
    _rec(db, none_decided, _mk_product(db, f"{MARKER}-P-SORTN"),
         _mk_warehouse(db, f"{MARKER}-W-SORTN"), supplier_id=sup)

    def _order(dir_):
        body = client.get(
            f"/api/v1/scm/reorder-runs?page=1&limit=100&sort=decided&dir={dir_}"
            f"&query={MARKER}-W-SORTQ"
        ).json()
        return [r["run_id"] for r in _rows_for(body, [none_decided, two_decided])]

    assert _order("desc") == [two_decided, none_decided]
    assert _order("asc") == [none_decided, two_decided]


def test_every_column_the_grid_can_sort_has_a_key_here(scm_app):
    """The grid sends the COLUMN ID as `sort`; an id with no entry in `_RUN_SORT` is
    silently ignored, so the header offers a sort that does nothing at all. Read off the
    component rather than restated, which is the only version of this check that cannot
    drift."""
    from app.api.v1.scm.reorder_runs import _RUN_SORT

    grid = (
        Path(__file__).resolve().parents[3]
        / "sorento_crm_frontend" / "app" / "(protected)" / "scm" / "reorder"
        / "components" / "ReorderRunsGrid.tsx"
    )
    if not grid.exists():  # backend-only checkout
        return
    source = grid.read_text()
    sortable = [
        block_id
        for block_id, block in re.findall(
            r"\{\s*\n\s*id: '([a-z_]+)',(.*?)\n      \},", source, re.S)
        if "enableSorting: true" in block
    ]

    assert sortable, "the column ids should be readable from the grid"
    missing = [c for c in sortable if c not in _RUN_SORT]
    assert missing == [], f"sortable on the grid but not in _RUN_SORT: {missing}"
