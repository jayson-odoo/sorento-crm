"""The buyer's own MoQ override (commit cefa08670, hardened for the B1 review finding) -
"the buyer states the MoQ the supplier is actually holding to".

Traces to `app/services/scm/reorder_run_service.py::set_moq_override` /
`effective_moq` / `recalc_rounded_qty` and `PUT /api/v1/scm/recommendations/{id}/moq`.

The contract under test:
  * `moq_override` is PERSISTED alongside a RECALCULATED `rounded_qty` / `cash_impact` -
    every existing reader of those two columns (the draft PO line at confirm, the M4
    budget allocator, the results-grid sort, the M8 explainer/market/simulation views) is
    a straight column read with no override-awareness of its own, so the override must be
    correct AT THE COLUMN, not only at read time. `inputs` (AC-M3.11's freeze) is the one
    thing that never moves - a fresh run with no override still matches it byte-for-byte.
  * Setting an override re-rounds `order_qty` through the SAME `reorder_engine.round_order_qty`
    the run itself used, off the row's FROZEN `recommended_qty` - the need never moves,
    only the rounding rung.
  * `cash_impact` follows the re-rounded qty (in BASE_CURRENCY).
  * Clearing (`moq: null`) reverts to the frozen master figure (`inputs.moq`), and PERSISTS
    the master rounding back onto the row.
  * The recommendations LIST endpoint reflects the persisted figure (still recomputed
    live as a defensive re-derive, so the two never disagree).
  * Grain guard (only a LOCATION-grain run may set/clear a MoQ) and lifecycle guard (a row
    already accepted/adjusted/dismissed refuses further changes) - both 409.
  * 404 for an unknown rec id, 422 for a negative/non-numeric/boolean moq, company
    isolation, and 403 without `scm.reorder.run`.

Two fixture styles, matching the shape of what each test needs:
  * `db` (`pg_session`) for the plain service-level tests and the company-isolation test -
    a run + rec is hand-built directly via the ORM (the same idiom
    `tests/scm/test_order_summary_routes.py` uses), which is enough surface for a function
    that only ever touches one recommendation row.
  * `scm_app` (`tests.scm.conftest`) + `TestClient` for the endpoint tests (auth, HTTP
    validation, the live list read).

Postgres only, marker-prefixed, every test seeds its own chain - nothing borrowed with
``LIMIT 1`` beyond the `scm_app` reference row `ensure_reference_data` seeds fresh in every
savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_m4_cash import _client, _mk_product, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTMOQ"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


# =============================================================================
# `db` fixture - plain pg_session, own savepoint, for the ORM-direct tests
# =============================================================================

@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _mk_run(db, **kw) -> ReorderRun:
    # LOCATION grain by default: `set_moq_override` is guarded exactly like Accept /
    # Adjust / Reject (S7), and every test in this file exercises it against a rec on
    # this run, so it must be a run those decisions may land on.
    kw.setdefault("decision_grain", "location")
    kw.setdefault("front_planning_contract_version", 1)
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        source_system="scm", source_ref=_code("RUN"), **kw,
    )
    db.add(run)
    db.flush()
    return run


def _mk_rec(db, run_id, product_id, *, warehouse_id=None, rec_type="buy",
           recommended_qty=40, master_moq=100, order_multiple=None,
           unit_cost=60, currency="MYR", rate_to_base=1.0,
           company_id=None) -> ReorderRecommendation:
    """A frozen buy row, master-rounded exactly the way the engine would have rounded
    it - `round_order_qty` is the SAME helper `recalc_rounded_qty` reuses, so the master
    figures here and the override figures under test come from one source of truth."""
    rounded = eng.round_order_qty(float(recommended_qty), master_moq, order_multiple)
    cash_impact = round(rounded * unit_cost, 2)
    rec = ReorderRecommendation(
        id=_u(), run_id=run_id, rec_type=rec_type, product_id=product_id,
        warehouse_id=warehouse_id, company_id=company_id,
        recommended_qty=recommended_qty, rounded_qty=rounded,
        unit_cost=unit_cost, currency=currency, rate_to_base=rate_to_base,
        rate_as_of=date.today(), cash_impact=cash_impact, status="proposed",
        inputs={"moq": master_moq, "order_multiple": order_multiple},
    )
    db.add(rec)
    db.flush()
    return rec


def _mk_chain(db, *, company_id=None, master_moq=100, order_multiple=None,
             recommended_qty=40, unit_cost=60, rec_type="buy"):
    """Category + uom + product + run + one recommendation, all fresh, all marker-prefixed."""
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), company_id=company_id, product_code=_code("SKU"),
        product_name="MoQ override test product", category_id=cat.id, base_uom_id=uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    run = _mk_run(db, company_id=company_id)
    rec = _mk_rec(
        db, run.id, product.id, rec_type=rec_type, recommended_qty=recommended_qty,
        master_moq=master_moq, order_multiple=order_multiple, unit_cost=unit_cost,
        company_id=company_id,
    )
    return {"run": run, "product": product, "rec": rec}


# =============================================================================
# happy path - set / clear, reround, cash follows, need never moves (AC: MoQ override)
# =============================================================================

def test_setting_an_override_re_rounds_order_qty_and_cash_follows_it(db):
    """Master MoQ 100, no order-multiple, recommended (frozen need) 40 -> master rounds
    to 100 (floored at MoQ). Overriding to 15 re-rounds to 40 (need itself, since 40 >= 15
    and there is no order-multiple to round further up), and cash follows the new qty."""
    f = _mk_chain(db, master_moq=100, order_multiple=None, recommended_qty=40, unit_cost=60)
    rec = f["rec"]
    assert float(rec.rounded_qty) == 100.0, "fixture's own master rounding is the baseline"

    result = svc.set_moq_override(db, rec.id, 15)

    assert result["moq"] == 15.0
    assert result["moq_is_override"] is True
    assert result["master_moq"] == 100.0, "the master figure is still reported alongside"
    assert result["order_qty"] == 40.0, "re-rounded off the frozen need, not off the old 100"
    assert result["recommended_qty"] == 40.0, "the frozen need itself never moves"
    assert result["cash_impact"] == pytest.approx(40.0 * 60.0), "cash follows the new qty"


def test_clearing_the_override_reverts_to_master_rounding(db):
    """`{moq: null}` (`moq=None`) clears the row back to the frozen master figure."""
    f = _mk_chain(db, master_moq=100, order_multiple=None, recommended_qty=40, unit_cost=60)
    rec = f["rec"]
    svc.set_moq_override(db, rec.id, 15)

    result = svc.set_moq_override(db, rec.id, None)

    assert result["moq"] == 100.0, "reverted to the frozen master MoQ"
    assert result["moq_is_override"] is False
    assert result["master_moq"] == 100.0
    assert result["order_qty"] == 100.0, "master rounding restored"
    assert result["cash_impact"] == pytest.approx(100.0 * 60.0)


def test_override_changes_rounding_but_never_recommended_qty_or_inputs(db):
    """The override PERSISTS the recalculated `rounded_qty` (B1 - every consumer of that
    column must see the override, not just a live re-derive), but never touches the frozen
    `recommended_qty` / `inputs` columns - AC-M3.11's freeze describes the engine's own
    arithmetic, not a derived column the buyer just corrected."""
    f = _mk_chain(db, master_moq=100, order_multiple=50, recommended_qty=40, unit_cost=60)
    rec = f["rec"]
    original_inputs = dict(rec.inputs)

    svc.set_moq_override(db, rec.id, 250)

    db.refresh(rec)
    assert float(rec.recommended_qty) == 40.0, "the frozen need column never moves"
    # floor(40, 250) = 250 -> ceil(250/50)*50 = 250, matching reorder_engine.round_order_qty
    assert float(rec.rounded_qty) == 250.0, (
        "set_moq_override must persist the recalculated rounded_qty, or every reader of "
        "that column (draft PO, budget allocator, sort) stays stale"
    )
    assert rec.inputs == original_inputs, "the frozen inputs (master moq) are never rewritten"


def test_override_with_order_multiple_re_rounds_through_the_same_engine_helper(db):
    """The override composes with order-multiple rounding exactly like the engine would:
    floor at MoQ, then round UP to the nearest multiple - proving `recalc_rounded_qty`
    is not a second copy of the arithmetic."""
    f = _mk_chain(db, master_moq=100, order_multiple=50, recommended_qty=40, unit_cost=60)
    rec = f["rec"]
    assert float(rec.rounded_qty) == 100.0  # 40 floored to 100 moq, already a multiple of 50

    result = svc.set_moq_override(db, rec.id, 30)

    # floor(40, 30) = 40 -> ceil(40/50)*50 = 50, matching reorder_engine.round_order_qty directly
    expected = eng.round_order_qty(40.0, 30.0, 50.0)
    assert result["order_qty"] == expected == 50.0


# =============================================================================
# validation - 404 unknown rec, 422 negative/non-numeric (service layer)
# =============================================================================

def test_unknown_recommendation_id_is_a_404(db):
    with pytest.raises(AppException) as caught:
        svc.set_moq_override(db, str(uuid.uuid4()), 10)
    assert caught.value.status_code == 404


def test_a_negative_moq_is_a_422(db):
    f = _mk_chain(db)
    with pytest.raises(AppException) as caught:
        svc.set_moq_override(db, f["rec"].id, -1)
    assert caught.value.status_code == 422


# =============================================================================
# S7 (review fix) - grain guard + lifecycle guard on the MoQ write
# =============================================================================

def test_a_product_grain_run_refuses_the_moq_override(db):
    """Guarded exactly like Accept/Adjust/Reject (AC-F09): a MoQ is what a LOCATION
    decision gets accepted at, so a run stamped at the OTHER grain may not take it."""
    f = _mk_chain(db)
    f["run"].decision_grain = "product"
    db.add(f["run"])
    db.flush()

    with pytest.raises(AppException) as caught:
        svc.set_moq_override(db, f["rec"].id, 10)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "decision_grain_mismatch"


def test_a_legacy_run_refuses_the_moq_override(db):
    """AC-F10: a run that predates the front-planning contract is read only."""
    f = _mk_chain(db)
    f["run"].decision_grain = None
    f["run"].front_planning_contract_version = None
    db.add(f["run"])
    db.flush()

    with pytest.raises(AppException) as caught:
        svc.set_moq_override(db, f["rec"].id, 10)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "legacy_run_read_only"


def test_an_already_decided_rec_refuses_further_moq_changes(db):
    """A rec already accepted into a draft PO must not have its MoQ moved out from
    under the PO line it may already sit in."""
    from app.services.scm import decision_service as dsvc

    f = _mk_chain(db)
    dsvc.accept_recommendation(db, f["rec"].id, actor="tester")
    db.flush()

    with pytest.raises(AppException) as caught:
        svc.set_moq_override(db, f["rec"].id, 10)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "recommendation_already_decided"


# =============================================================================
# company isolation - another company's recommendation is not reachable
# =============================================================================

@pytest.fixture()
def two_companies(db):
    """Company A and B, each with a warehouse, a product and a buy recommendation."""
    set_company_scope(db, None)
    a = Company(id=_u(), code=_code("CA")[:20], name=f"{MARKER} company A")
    b = Company(id=_u(), code=_code("CB")[:20], name=f"{MARKER} company B")
    db.add_all([a, b])
    db.flush()

    a_chain = _mk_chain(db, company_id=a.id, master_moq=100, recommended_qty=40)
    b_chain = _mk_chain(db, company_id=b.id, master_moq=100, recommended_qty=40)
    return {"a": a, "b": b, "a_chain": a_chain, "b_chain": b_chain}


def test_another_companys_recommendation_is_not_reachable(db, two_companies):
    f = two_companies
    set_company_scope(db, frozenset({str(f["a"].id)}))

    with pytest.raises(AppException) as caught:
        svc.set_moq_override(db, f["b_chain"]["rec"].id, 5)
    assert caught.value.status_code == 404, (
        "another company's recommendation must read as absent, not as a writable row"
    )


def test_this_companys_own_recommendation_is_reachable(db, two_companies):
    """The gate is not a blanket denial: company A can still override its own row."""
    f = two_companies
    set_company_scope(db, frozenset({str(f["a"].id)}))

    result = svc.set_moq_override(db, f["a_chain"]["rec"].id, 5)
    assert result["moq"] == 5.0


# =============================================================================
# HTTP endpoint - auth, validation, and the live list read
# =============================================================================

def _mk_http_chain(db, *, master_moq=100, order_multiple=None, recommended_qty=40,
                   unit_cost=60):
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("SKU"))
    run = _mk_run(db)
    rec = _mk_rec(
        db, run.id, pid, warehouse_id=wid, master_moq=master_moq,
        order_multiple=order_multiple, recommended_qty=recommended_qty, unit_cost=unit_cost,
    )
    db.flush()
    return {"run": run, "product_id": pid, "warehouse_id": wid, "rec": rec}


def test_put_moq_happy_path_endpoint(scm_app):
    app, db = _client(scm_app, "purchasing")
    f = _mk_http_chain(db, master_moq=100, order_multiple=None, recommended_qty=40)

    with TestClient(app) as c:
        res = c.put(f"/api/v1/scm/recommendations/{f['rec'].id}/moq", json={"moq": 15})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recommendation_id"] == f["rec"].id
    assert body["moq"] == 15.0
    assert body["moq_is_override"] is True
    assert body["master_moq"] == 100.0
    assert body["order_qty"] == 40.0
    assert body["cash_impact"] == pytest.approx(40.0 * 60.0)


def test_put_moq_unknown_rec_id_is_404(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.put(f"/api/v1/scm/recommendations/{uuid.uuid4()}/moq", json={"moq": 10})
    assert res.status_code == 404


def test_put_moq_negative_is_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    f = _mk_http_chain(db)
    with TestClient(app) as c:
        res = c.put(f"/api/v1/scm/recommendations/{f['rec'].id}/moq", json={"moq": -5})
    assert res.status_code == 422


def test_put_moq_non_numeric_is_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    f = _mk_http_chain(db)
    with TestClient(app) as c:
        res = c.put(f"/api/v1/scm/recommendations/{f['rec'].id}/moq", json={"moq": "abc"})
    assert res.status_code == 422


def test_put_moq_boolean_is_422(scm_app):
    """S7 (review fix): `isinstance(True, (int, float))` is `True` in Python, so a bare
    numeric-type check silently accepted a boolean as a MoQ - it must be rejected."""
    app, db = _client(scm_app, "purchasing")
    f = _mk_http_chain(db)
    with TestClient(app) as c:
        res = c.put(f"/api/v1/scm/recommendations/{f['rec'].id}/moq", json={"moq": True})
    assert res.status_code == 422


def test_put_moq_denied_without_reorder_run_permission(scm_app):
    """Auth: setting a MoQ override is a planning action -> needs `scm.reorder.run`,
    same family as Accept/Adjust/Reject and the budget apply."""
    app, db = _client(scm_app, None)
    f = _mk_http_chain(db)
    with TestClient(app) as c:
        res = c.put(f"/api/v1/scm/recommendations/{f['rec'].id}/moq", json={"moq": 10})
    assert res.status_code == 403


def test_recommendations_list_reflects_the_persisted_override(scm_app):
    """The list read reflects the override without a full engine re-run, and the
    persisted `rounded_qty` / `cash_impact` columns carry the SAME recalculated figure
    (B1) - not the master rounding - so every other reader of those columns agrees with
    what the grid shows."""
    app, db = _client(scm_app, "purchasing")
    f = _mk_http_chain(db, master_moq=100, order_multiple=None, recommended_qty=40)
    run_id = f["run"].id
    rec_id = f["rec"].id

    with TestClient(app) as c:
        put = c.put(f"/api/v1/scm/recommendations/{rec_id}/moq", json={"moq": 15})
        assert put.status_code == 200, put.text

        got = c.get(f"/api/v1/scm/reorder-runs/{run_id}/recommendations",
                    params={"type": "buy", "limit": 50})
    assert got.status_code == 200, got.text
    rows = {r["id"]: r for r in got.json()["data"]}
    row = rows[rec_id]
    assert row["order_qty"] == 40.0
    assert row["moq"] == 15.0
    assert row["moq_is_override"] is True
    assert row["master_moq"] == 100.0
    assert row["cash_impact"] == pytest.approx(40.0 * 60.0)

    # B1: the persisted rounded_qty on the row now carries the OVERRIDE figure, not the
    # frozen master rounding - every non-list reader (draft PO, budget allocator, sort)
    # is a straight column read, so this is what makes them correct too.
    from sqlalchemy import text as _text
    stored = db.execute(_text(
        "SELECT rounded_qty, cash_impact FROM scm.reorder_recommendation WHERE id = :id"
    ), {"id": rec_id}).mappings().first()
    assert float(stored["rounded_qty"]) == 40.0, (
        "set_moq_override must persist the recalculated rounded_qty"
    )
    assert float(stored["cash_impact"]) == pytest.approx(40.0 * 60.0)
