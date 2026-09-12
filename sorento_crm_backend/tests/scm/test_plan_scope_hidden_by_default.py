"""PLAN-plan-list-tile-sheet-one-scope.md - test-first, backend half (S6/S7).

The one rule (UAC): ``hidden_by_default(rec)`` is true when ALL hold: ``rec_type ==
covered``, the basis is manual (``inputs.policy_type == 'reorder_level'``), the basis
value exists (``inputs.reorder_level``, else the product's ``master_reorder_level``), the
net exists, and ``net > basis`` - where ``net`` is the rec's ``net_position`` column ALONE,
never the engine's decision net (``net_position + po_ordered``). A missing basis or net
means shown.

AC-1/AC-2 seed bare `scm.reorder_recommendation` rows directly (the shape
`tests/scm/test_plan_row_payload_fields.py` already uses for the same recommendations
endpoint) - the rule is a pure function of stored columns/inputs, so the real engine need
not run to prove the serializer/decision-count read it. AC-3/AC-4 seed a `ReorderRun` +
`ReorderRecommendation`s the same minimal way `tests/scm/test_summary_order_service.py`'s
own `chain` fixture does, then drive `write_rows`/`export_report`/`export_guard_stats`/
`report` directly (the `pg_session` idiom, not a TestClient).

Every case is red today because ``hidden_by_default`` does not exist anywhere yet: the
recommendations row carries no such key, `plan-row-decisions`' `total_count` counts every
decidable product regardless, and the export/guard count every frozen row. Postgres only,
marker-prefixed seeding, nothing borrowed with LIMIT 1 - CI's database is empty.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.scm import plan_scope
from app.services.scm import summary_order_service as svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session
from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user
from tests.scm.test_m4_cash import _mk_product, _mk_supplier, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTHID"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


# =========================================================================== #
# AC-1 / AC-2 - TestClient route tests, bare recommendation rows (no engine run)
# =========================================================================== #


def _client(scm_app_fixture, role_slug="admin"):
    app, db, gcu, gcuak = scm_app_fixture
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return TestClient(app), db


def _run_row(db) -> str:
    rid = _u()
    from sqlalchemy import text
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


def _hidden_flag(rec_type: str, inputs: dict, net_position) -> bool:
    """What `reorder_run_service._build_rec` would stamp on this row.

    Since PLAN-reorder-one-formula.md S3 the rule is evaluated ONCE, at write time, into
    `scm.reorder_recommendation.hidden_by_default`, and every reader under test here (the
    serializer, the decisions total, the export and its guard) reads that COLUMN instead
    of re-deriving the rule for itself - which is the whole point of S3, since three
    independent re-derivations is exactly what drifted (list 415, tile "0 of 950", sheet
    950). A hand-seeded row therefore has to be stamped the way the real writer stamps it,
    or it is not standing in for a real row at all.

    Computed through `plan_scope.hidden_by_default` rather than hardcoded per case, so a
    broken RULE still turns these tests red instead of the fixture agreeing with itself.
    """
    return plan_scope.hidden_by_default(
        rec_type=rec_type,
        policy_type=inputs.get("policy_type"),
        reorder_level=inputs.get("reorder_level"),
        master_reorder_level=inputs.get("master_reorder_level"),
        net_position=None if net_position is None else float(net_position),
    )


def _rec_row(db, run_id: str, product_id: str, warehouse_id, *, rec_type: str,
             net_position, inputs: dict, supplier_id=None) -> str:
    from sqlalchemy import text
    rec_id = _u()
    db.execute(text("""
        INSERT INTO scm.reorder_recommendation
            (id, run_id, rec_type, product_id, warehouse_id, supplier_id, net_position,
             rounded_qty, recommended_qty, status, unit_cost, currency, inputs,
             hidden_by_default, company_id, created_at)
        VALUES (CAST(:id AS uuid), CAST(:run AS uuid), :rt, CAST(:p AS uuid),
                CAST(:w AS uuid), CAST(:s AS uuid), :net, 40, 40, 'proposed', 10, 'MYR',
                CAST(:inputs AS jsonb), :hidden, CAST(:co AS uuid), now())
    """), {"id": rec_id, "run": run_id, "rt": rec_type, "p": product_id, "w": warehouse_id,
           "s": supplier_id, "net": net_position, "inputs": json.dumps(inputs),
           "hidden": _hidden_flag(rec_type, inputs, net_position),
           "co": SORENTO_COMPANY_ID})
    db.flush()
    return rec_id


# (case_id, rec_type, inputs, net_position, expect_hidden)
_AC1_CASES = [
    ("hidden_covered_manual_over_level", "covered",
     {"policy_type": "reorder_level", "reorder_level": 50}, 1447, True),
    ("shown_covered_manual_under_level", "covered",
     {"policy_type": "reorder_level", "reorder_level": 50}, 40, False),
    # net_position ALONE decides: an engine-net (net_position + po_ordered = 1,040) well
    # above the level must NOT flip this to hidden - only the bare net_position (40, under
    # the level) may.
    ("shown_net_position_alone_not_engine_net", "covered",
     {"policy_type": "reorder_level", "reorder_level": 50, "po_ordered": 1000}, 40, False),
    ("shown_auto_basis_reorder_point", "covered",
     {"policy_type": "reorder_point", "reorder_point": 50}, 1447, False),
    ("shown_buy_rec", "buy",
     {"policy_type": "reorder_level", "reorder_level": 50}, 1447, False),
    ("shown_covered_manual_no_level_anywhere", "covered",
     {"policy_type": "reorder_level"}, 1447, False),
]


@pytest.mark.parametrize(
    "case_id, rec_type, inputs, net_position, expect_hidden", _AC1_CASES,
    ids=[c[0] for c in _AC1_CASES],
)
def test_hidden_by_default_flag_on_recommendation_rows(
    scm_app, case_id, rec_type, inputs, net_position, expect_hidden,
):
    """AC-1: `GET /reorder-runs/{run}/recommendations` rows carry `hidden_by_default: bool`,
    read straight off `app.services.scm.plan_scope.hidden_by_default`'s inputs. Red today:
    the key is entirely absent from the row, for every case (asserted explicitly below
    rather than via `.get()`, so a missing key cannot masquerade as a correct `False`)."""
    client, db = _client(scm_app)
    run_id = _run_row(db)
    wid = _mk_warehouse(db, _code("W")[:30])
    pid = _mk_product(db, _code("SKU")[:30])
    sid = _mk_supplier(db, f"{MARKER} supplier {case_id}"[:60])
    _rec_row(db, run_id, pid, wid, rec_type=rec_type, net_position=net_position,
             inputs=inputs, supplier_id=sid)

    resp = client.get(
        f"/api/v1/scm/reorder-runs/{run_id}/recommendations?type={rec_type}&limit=50"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = next(r for r in body["data"] if r["product_id"] == pid)

    assert "hidden_by_default" in row, (
        f"{case_id}: hidden_by_default is absent from the recommendation row - "
        f"the serializer does not carry the field yet: {row}"
    )
    assert row["hidden_by_default"] is expect_hidden, (
        f"{case_id}: expected hidden_by_default={expect_hidden}, row={row}"
    )


def test_plan_row_decisions_total_excludes_hidden_rows(scm_app):
    """AC-2: `GET /reorder-runs/{run}/plan-row-decisions`' `total_count` excludes
    hidden-by-default rows. Seed: 1 Buy + 1 hidden covered + 1 shown covered (three
    distinct products) -> `total_count == 2`. Red today: `list_plan_row_decisions` counts
    every decidable product regardless (3)."""
    client, db = _client(scm_app)
    run_id = _run_row(db)

    buy_pid = _mk_product(db, _code("SKU-BUY")[:30])
    hidden_pid = _mk_product(db, _code("SKU-HID")[:30])
    shown_pid = _mk_product(db, _code("SKU-SHOWN")[:30])
    wid = _mk_warehouse(db, _code("W")[:30])
    sid = _mk_supplier(db, f"{MARKER} decisions supplier"[:60])

    _rec_row(db, run_id, buy_pid, wid, rec_type="buy",
             inputs={"policy_type": "reorder_level", "reorder_level": 50},
             net_position=1447, supplier_id=sid)
    _rec_row(db, run_id, hidden_pid, wid, rec_type="covered",
             inputs={"policy_type": "reorder_level", "reorder_level": 50},
             net_position=1447, supplier_id=sid)
    _rec_row(db, run_id, shown_pid, wid, rec_type="covered",
             inputs={"policy_type": "reorder_level", "reorder_level": 50},
             net_position=40, supplier_id=sid)

    resp = client.get(f"/api/v1/scm/reorder-runs/{run_id}/plan-row-decisions")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_count"] == 2, (
        f"the hidden covered row was still counted decidable: {body}"
    )


# =========================================================================== #
# AC-3 / AC-4 - write_rows / export_report / export_guard_stats / report, direct
# =========================================================================== #


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def three_product_run(db):
    """One run, one product-grain (warehouse_id=None) recommendation per product: 1 Buy +
    1 hidden covered (manual basis, net over level) + 1 shown covered (manual basis, net
    under level) - the exact seed AC-3/AC-4 both read. Mirrors
    `test_summary_order_service.py`'s own `chain` fixture (bare `ReorderRun` +
    `ReorderRecommendation`, no stock/PO/demand chain - `write_rows` tolerates an empty
    book beneath a rec, as `chain`'s own callers already prove)."""
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
    hidden_p = _product("HID")
    shown_p = _product("SHOWN")

    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
        decision_grain="product", front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()

    # Stamped the way `_build_rec` stamps a real row (see `_hidden_flag`): S3 moved the
    # rule to write time, so a seeded row that leaves the column at its default is not a
    # row any reader under test would ever meet.
    basis = {"policy_type": "reorder_level", "reorder_level": 50}
    for rec_type, product, rounded, net in (
        ("buy", buy_p, 100, -100),
        ("covered", hidden_p, 0, 1447),
        ("covered", shown_p, 0, 40),
    ):
        db.add(ReorderRecommendation(
            id=_u(), run_id=run.id, rec_type=rec_type, product_id=product.id,
            warehouse_id=None, rounded_qty=rounded, net_position=net, inputs=dict(basis),
            hidden_by_default=_hidden_flag(rec_type, basis, net),
        ))
    db.flush()
    return {"run": run, "buy": buy_p, "hidden": hidden_p, "shown": shown_p}


def test_export_omits_hidden_rows_and_guard_counts_the_same(db, three_product_run):
    """AC-3: `export_report(fmt='xlsx')` and `export_guard_stats` both count 2 rows (Buy +
    shown covered), not the 3 `write_rows` froze. Red today: neither function knows the
    rule, so both print/count all 3."""
    f = three_product_run
    written = svc.write_rows(db, f["run"].id)
    assert written == 3, f"expected the freeze to write all 3 products, wrote {written}"

    data, content_type, filename = svc.export_report(db, run_id=f["run"].id, fmt="xlsx")
    wb = openpyxl.load_workbook(BytesIO(data))
    ws = wb.active
    data_row_count = ws.max_row - 1  # minus the header row
    assert data_row_count == 2, (
        f"expected 2 data rows (hidden covered omitted), got {data_row_count}"
    )

    guard = svc.export_guard_stats(db, run_id=f["run"].id)
    assert guard["row_count"] == 2, (
        f"export_guard_stats must count the same population export_report prints: {guard}"
    )


def test_report_endpoint_still_lists_every_product(db, three_product_run):
    """AC-4: the frozen `order_summary_row` / `report()` endpoint is UNCHANGED - it keeps
    every product the run planned, hidden-by-default or not. Non-regression: expected
    GREEN on arrival (this pins that AC-3's filtering happens only in the export/guard
    layer, never in the frozen sheet or its report read)."""
    f = three_product_run
    svc.write_rows(db, f["run"].id)

    rep = svc.report(db, run_id=f["run"].id)
    assert len(rep["rows"]) == 3, (
        f"the report endpoint must still list every planned product: {rep['rows']}"
    )
