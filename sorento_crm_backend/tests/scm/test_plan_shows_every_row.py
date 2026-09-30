"""PLAN-lowstock-show-all.md (owner ruling 30 Sep 2026: "SHOW ALL HIDDEN ITEMS AGAIN") -
test-first, backend half. Replaces `test_plan_scope_hidden_by_default.py` and
`test_hidden_by_default_column.py`, which pinned the rule this lane retires.

The retired rule (`plan_scope.hidden_by_default`: covered + manual `reorder_level` basis +
net above level) was stamped into `scm.reorder_recommendation.hidden_by_default` at write
time and read by the recommendations serializer, the decisions total, the plans-list
counters, the order sheet export and its guard, and the low stock workbook. After this
lane NOTHING reads it, `_build_rec` no longer stamps it, and migration
`lsa_0001_show_all_counts` recounts every run's stored counters and drops the column.

AC-66/AC-67 seed bare `scm.reorder_recommendation` rows directly (the shape
`tests/scm/test_plan_row_payload_fields.py` uses for the same endpoint), one of them the
covered-above-level row the old rule hid. AC-72 seeds a `ReorderRun` +
`ReorderRecommendation`s the minimal way `test_summary_order_service.py`'s `chain` fixture
does and drives `write_rows` / `export_report` / `export_guard_stats` / `report` directly.
AC-68 runs the real engine so the write path itself is under test; AC-69 runs the
migration's recount against a run stamped the OLD, narrowed way. Postgres only,
marker-prefixed seeding, nothing borrowed with LIMIT 1 - CI's database is empty.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.scm import summary_order_service as svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session
from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user
from tests.scm.test_channel_read_model import _core_line_for_run
from tests.scm.test_m3_run import _link, _mk_demand, _mk_stock
from tests.scm.test_m4_cash import _mk_product, _mk_supplier, _mk_warehouse
from tests.scm.test_reorder_level_run import _use_level_basis
from tests.scm.test_reorder_one_formula import _product as _engine_product
from tests.scm.test_reorder_one_formula import _run as _engine_run
from tests.scm.test_reorder_one_formula import _wh
from tests.scm.test_reorder_per_product import _set_level

pytestmark = requires_pg

MARKER = "ZZTSHOWALL"

#: The manual basis every covered case below sits on, and a net far above the level 50 -
#: exactly the row the retired rule used to hide.
_MANUAL_BASIS = {"policy_type": "reorder_level", "reorder_level": 50}
_NET_FAR_ABOVE = 1447
_NET_UNDER = 40


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


# =========================================================================== #
# AC-71 - the rule, its stamp readers and the FE reveal helper are gone
# =========================================================================== #


def test_plan_scope_module_and_visible_rows_are_gone():
    """AC-71: a module nobody calls is dead code, and a dead rule is the kind of thing
    that gets re-read by accident. `plan_scope` is deleted; `summary_order_service` no
    longer carries the filter helpers `export_report` and the low stock `_split` shared;
    the ORM no longer maps the column."""
    with pytest.raises(ImportError):
        importlib.import_module("app.services.scm.plan_scope")
    assert not hasattr(svc, "visible_rows")
    assert not hasattr(svc, "_hidden_product_ids_for_run")
    assert not hasattr(ReorderRecommendation, "hidden_by_default")


_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load_migration():
    """The lsa_0001 migration module, loaded off disk the way
    `test_demand_class_backfill_migration.py` loads 425 - alembic revisions are not an
    importable package."""
    spec = importlib.util.spec_from_file_location(
        "lsa_0001_show_all_counts", _VERSIONS / "lsa_0001_show_all_counts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =========================================================================== #
# AC-66 / AC-67 - TestClient route tests, bare recommendation rows (no engine run)
# =========================================================================== #


def _client(scm_app_fixture, role_slug="admin"):
    app, db, gcu, gcuak = scm_app_fixture
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return TestClient(app), db


def _run_row(db) -> str:
    rid = _u()
    db.execute(text("""
        INSERT INTO scm.reorder_run
            (id, status, buy_scope, decision_grain, front_planning_contract_version,
             started_at, created_by, run_log, source_system, source_ref, company_id,
             created_at)
        VALUES (CAST(:id AS uuid), 'completed', 'warehouse', 'product', 1, now(),
                'tester', CAST('{}' AS jsonb), 'scm', :ref, CAST(:co AS uuid), now())
    """), {"id": rid, "ref": _code("RUN"), "co": SORENTO_COMPANY_ID})
    db.flush()
    return rid


def _rec_row(db, run_id: str, product_id: str, warehouse_id, *, rec_type: str,
             net_position, inputs: dict, supplier_id=None) -> str:
    """One bare recommendation."""
    rec_id = _u()
    db.execute(text("""
        INSERT INTO scm.reorder_recommendation
            (id, run_id, rec_type, product_id, warehouse_id, supplier_id, net_position,
             rounded_qty, recommended_qty, status, unit_cost, currency, inputs,
             company_id, created_at)
        VALUES (CAST(:id AS uuid), CAST(:run AS uuid), :rt, CAST(:p AS uuid),
                CAST(:w AS uuid), CAST(:s AS uuid), :net, 40, 40, 'proposed', 10, 'MYR',
                CAST(:inputs AS jsonb), CAST(:co AS uuid), now())
    """), {"id": rec_id, "run": run_id, "rt": rec_type, "p": product_id, "w": warehouse_id,
           "s": supplier_id, "net": net_position, "inputs": json.dumps(inputs),
           "co": SORENTO_COMPANY_ID})
    db.flush()
    return rec_id


def _three_bare_recs(db, run_id: str) -> dict[str, str]:
    """1 buy + 1 covered far above its manual level (the row the old rule hid) + 1
    covered under it. Three distinct products, one warehouse, one supplier."""
    wid = _mk_warehouse(db, _code("W")[:30])
    sid = _mk_supplier(db, f"{MARKER} supplier"[:60])
    buy = _mk_product(db, _code("SKU-BUY")[:30])
    above = _mk_product(db, _code("SKU-ABOVE")[:30])
    under = _mk_product(db, _code("SKU-UNDER")[:30])
    _rec_row(db, run_id, buy, wid, rec_type="buy", inputs=dict(_MANUAL_BASIS),
             net_position=_NET_FAR_ABOVE, supplier_id=sid)
    _rec_row(db, run_id, above, wid, rec_type="covered", inputs=dict(_MANUAL_BASIS),
             net_position=_NET_FAR_ABOVE, supplier_id=sid)
    _rec_row(db, run_id, under, wid, rec_type="covered", inputs=dict(_MANUAL_BASIS),
             net_position=_NET_UNDER, supplier_id=sid)
    return {"buy": buy, "above": above, "under": under}


def test_recommendation_rows_carry_no_hidden_by_default_key(scm_app):
    """AC-66: the serializer no longer ships the retired flag - the FE has nothing to
    hide on, so the key goes rather than riding along as a permanent `false`. All three
    rows come back, the covered-above-level one like any other."""
    client, db = _client(scm_app)
    run_id = _run_row(db)
    pids = _three_bare_recs(db, run_id)

    resp = client.get(f"/api/v1/scm/reorder-runs/{run_id}/recommendations?limit=50")
    assert resp.status_code == 200, resp.text
    rows = {r["product_id"]: r for r in resp.json()["data"]}

    assert set(pids.values()) <= set(rows), (
        f"every seeded rec must be listed, the covered-above-level one included: {sorted(rows)}"
    )
    for name, pid in pids.items():
        assert "hidden_by_default" not in rows[pid], (
            f"{name}: hidden_by_default is retired and must not be serialised: {rows[pid]}"
        )


def test_plan_row_decisions_total_counts_every_decidable_product(scm_app):
    """AC-67: `total_count` is every product with a decidable rec type - 3, the
    covered-above-level product included. The tile counts what the list shows (owner,
    10 Sep), and the list now shows everything (owner, 30 Sep)."""
    client, db = _client(scm_app)
    run_id = _run_row(db)
    _three_bare_recs(db, run_id)

    resp = client.get(f"/api/v1/scm/reorder-runs/{run_id}/plan-row-decisions")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_count"] == 3, (
        f"the covered-above-level product must count toward the tile total: {resp.json()}"
    )


# =========================================================================== #
# AC-72 - write_rows / export_report / export_guard_stats / report, direct
# =========================================================================== #


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def three_product_run(db):
    """One run, one product-grain (warehouse_id=None) recommendation per product: 1 buy
    + 1 covered far above its level (the row the old rule hid) + 1 covered under it.
    Mirrors `test_summary_order_service.py`'s own `chain` fixture (bare `ReorderRun` +
    `ReorderRecommendation`, no stock/PO/demand chain - `write_rows` tolerates an empty
    book beneath a rec)."""
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    def _product(stem: str) -> Product:
        p = Product(
            id=_u(), product_code=_code(stem), product_name=f"{MARKER} {stem}",
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        )
        db.add(p)
        db.flush()
        return p

    buy_p = _product("BUY")
    above_p = _product("ABOVE")
    under_p = _product("UNDER")

    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
        decision_grain="product", front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()

    for rec_type, product, rounded, net in (
        ("buy", buy_p, 100, -100),
        ("covered", above_p, 0, _NET_FAR_ABOVE),
        ("covered", under_p, 0, _NET_UNDER),
    ):
        db.add(ReorderRecommendation(
            id=_u(), run_id=run.id, rec_type=rec_type, product_id=product.id,
            warehouse_id=None, rounded_qty=rounded, net_position=net,
            inputs=dict(_MANUAL_BASIS),
        ))
    db.flush()
    return {"run": run, "buy": buy_p, "above": above_p, "under": under_p}


def test_export_guard_and_report_all_print_every_row(db, three_product_run):
    """AC-72: `export_report(fmt='xlsx')`, `export_guard_stats` and `report()` all say 3
    for a run whose frozen sheet holds 3 products, one of them covered above its level."""
    f = three_product_run
    written = svc.write_rows(db, f["run"].id)
    assert written == 3, f"expected the freeze to write all 3 products, wrote {written}"

    data, _content_type, _filename = svc.export_report(db, run_id=f["run"].id, fmt="xlsx")
    ws = openpyxl.load_workbook(BytesIO(data)).active
    codes = {row[0].value for row in ws.iter_rows(min_row=2)}
    assert codes == {f["buy"].product_code, f["above"].product_code, f["under"].product_code}, (
        f"the order sheet must print every planned product: {codes}"
    )

    guard = svc.export_guard_stats(db, run_id=f["run"].id)
    assert guard["row_count"] == 3, (
        f"export_guard_stats must count the same population export_report prints: {guard}"
    )

    rep = svc.report(db, run_id=f["run"].id)
    assert len(rep["rows"]) == 3, rep["rows"]


# =========================================================================== #
# AC-68 / AC-69 - the real engine: every counter counts the covered row; the migration
# recounts a run stamped the old, narrowed way
# =========================================================================== #


def _engine_folded_run(db) -> dict:
    """3 products through the real engine: 2 buys and 1 covered row with stock far above
    its level (the row the retired rule hid), folded onto ONE run row plus a 4th
    `exception` rec. Shared by the AC-68 counter test and the AC-69 recount test.

    A `covered` row is only emitted when there is committed demand to weigh against the
    stock (`_covered_rec` returns `None` otherwise), so the covered product carries a
    small committed line; its net still clears the level by a wide margin. The three
    single-product runs are folded onto one run row so one set of counters can be asked
    about all three, mirroring how the real engine writes every product of one run under
    one run_id. The `exception` is a LINE of the plan (`recommendation_count` counts it)
    but not a decidable product (`planned_count` does not) - unchanged from before this
    lane. It is stamped with the run's company like every engine-written rec, so the
    ORM's company scope sees it too.
    """
    _use_level_basis(db)

    buy_wid, buy_code = _wh(db, "BUYC")
    buy_pid, buy_pcode = _engine_product(db)
    _set_level(db, buy_pid, None, 100)
    _mk_stock(db, buy_pid, buy_wid, 10)
    _mk_demand(db, buy_pid, buy_wid, 0.0)
    _link(db, buy_pid, _mk_supplier(db, f"{MARKER} buyc"), moq=None, mult=None)

    cov_wid, cov_code = _wh(db, "COVC")
    cov_pid, cov_pcode = _engine_product(db)
    _set_level(db, cov_pid, None, 100)
    _mk_stock(db, cov_pid, cov_wid, 200)
    _mk_demand(db, cov_pid, cov_wid, 0.0)
    _link(db, cov_pid, _mk_supplier(db, f"{MARKER} covc"), moq=None, mult=None)
    _core_line_for_run(db, cov_pid, cov_wid, qty=10, demand_class="retail")

    buy2_wid, buy2_code = _wh(db, "BUY2C")
    buy2_pid, buy2_pcode = _engine_product(db)
    _set_level(db, buy2_pid, None, 50)
    _mk_stock(db, buy2_pid, buy2_wid, 5)
    _mk_demand(db, buy2_pid, buy2_wid, 0.0)
    _link(db, buy2_pid, _mk_supplier(db, f"{MARKER} buy2c"), moq=None, mult=None)
    db.flush()

    r1 = _engine_run(db, [buy_code], buy_pcode)
    r2 = _engine_run(db, [cov_code], cov_pcode)
    r3 = _engine_run(db, [buy2_code], buy2_pcode)

    def _one_rec_type(run_id):
        return db.execute(text(
            "SELECT rec_type FROM scm.reorder_recommendation WHERE run_id = :r"
        ), {"r": run_id}).scalar_one()

    assert _one_rec_type(r1) == "buy"
    assert _one_rec_type(r2) == "covered"
    assert _one_rec_type(r3) == "buy"
    # The run's own planned_count, stamped at generation: the covered product counts.
    assert db.execute(text(
        "SELECT planned_count FROM scm.reorder_run WHERE id = :r"
    ), {"r": r2}).scalar() == 1

    folded = r1
    db.execute(text(
        "UPDATE scm.reorder_recommendation SET run_id = :folded "
        "WHERE run_id IN (:r2, :r3)"
    ), {"folded": folded, "r2": r2, "r3": r3})
    exc_pid, _exc_pcode = _engine_product(db)
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, status, inputs, company_id, "
        " created_at) "
        "VALUES (gen_random_uuid(), :run, :pid, NULL, 'exception', 'proposed', "
        "        '{}'::jsonb, CAST(:co AS uuid), now())"
    ), {"run": folded, "pid": exc_pid, "co": SORENTO_COMPANY_ID})
    db.flush()
    return {"run_id": folded, "buy": buy_pid, "covered": cov_pid, "buy2": buy2_pid}


def test_migration_recounts_a_run_stamped_the_narrowed_way(scm_app):
    """AC-69 (reviewer B1): every run written 10-30 Sep stored `planned_count` and
    `run_log.recommendation_count` WITHOUT its covered-above-level rows (512's backfill
    and the write-time stamp both filtered them), and nothing recomputes those on an
    existing run except a decision. `lsa_0001_show_all_counts._recount_runs` recounts
    both for every run: 2 buys + 1 covered = 3 decidable products, + 1 exception = 4
    lines. Stamped "the old way" first (2 / 2), so the assertions are red until the
    recount runs. Idempotent: a second run lands on the same numbers."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    _, db, _, _ = scm_app
    f = _engine_folded_run(db)
    db.execute(text(
        "UPDATE scm.reorder_run "
        "SET status = 'completed', planned_count = 2, "
        "    run_log = jsonb_set(COALESCE(run_log, '{}'::jsonb), '{recommendation_count}', '2'::jsonb) "
        "WHERE id = :r"
    ), {"r": f["run_id"]})
    db.flush()

    ops = Operations(MigrationContext.configure(db.connection()))
    import alembic.op as op_module
    op_module._proxy = ops
    migration = _load_migration()
    for _attempt in ("first", "second"):
        migration._recount_runs()
        row = db.execute(text(
            "SELECT planned_count, run_log ->> 'recommendation_count' AS rec_count "
            "FROM scm.reorder_run WHERE id = :r"
        ), {"r": f["run_id"]}).mappings().one()
        assert row["planned_count"] == 3, (
            f"2 buys + 1 covered = 3 decidable products ({_attempt} recount): {row}"
        )
        assert row["rec_count"] == "4", (
            f"recommendation_count is LINES, exception included ({_attempt} recount): {row}"
        )


def test_every_counter_counts_the_covered_row(scm_app):
    """AC-68: `_summarise`'s `recommendation_count`, the run's own `planned_count`,
    `_refresh_run_counts` and `list_plan_row_decisions` all count the covered rec whose
    stock sits well above its manual level; the serializer lists it with no
    `hidden_by_default` key. Seed: `_engine_folded_run` (2 buys + 1 covered + 1
    exception on one run)."""
    app, db, gcu, gcuak = scm_app
    f = _engine_folded_run(db)
    folded = f["run_id"]

    recs = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.run_id == folded)
        .all()
    )
    assert len(recs) == 4

    from app.services.scm import reorder_run_service as rsvc
    counts = rsvc._summarise(recs)
    assert counts["recommendation_count"] == 4, (
        f"2 buys + 1 covered + 1 exception = 4 lines on the plan: {counts}"
    )

    from app.services.scm import decision_service as dsvc
    dsvc._refresh_run_counts(db, folded)
    planned = db.execute(text(
        "SELECT planned_count FROM scm.reorder_run WHERE id = :r"
    ), {"r": folded}).scalar()
    assert planned == 3, f"2 buys + 1 covered = 3 decidable products: {planned}"

    total = dsvc.list_plan_row_decisions(db, folded)["total_count"]
    assert total == 3, f"list_plan_row_decisions must count the same 3: {total}"

    uid = seed_user(db, "purchasing")
    as_user(app, gcu, gcuak, uid)
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/scm/reorder-runs/{folded}/recommendations?limit=50")
    assert resp.status_code == 200, resp.text
    by_pid = {r["product_id"]: r for r in resp.json()["data"]}
    assert {f["buy"], f["covered"], f["buy2"]} <= set(by_pid)
    assert "hidden_by_default" not in by_pid[f["covered"]]
