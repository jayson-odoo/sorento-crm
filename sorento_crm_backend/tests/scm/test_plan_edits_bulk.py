"""UAC E1 / E2 - Save (N) is ONE request over a run's drafted edits.

`PUT /api/v1/scm/reorder-runs/{run}/plan-edits` (PLAN-scm-reorder-revamp.md section 5.1).
The revamp moves every per-row write off its own control and behind one Save: the panel's
inputs (cover mix, MOQ, AutoCount level, reorder qty, keep/discontinue) draft locally and
reach the backend together. Nothing new decides anything - each field is handed to the
service function that already owned it, so this endpoint can never disagree with the
per-row endpoints it replaces on the screen.

What the tests pin, in the order the criteria state them:

* every field lands (decision, moq, level, reorder_qty, lifecycle);
* one transaction - a failing row leaves NOTHING of the batch behind;
* a rec that is not on this run is a 404, and a legacy run is a 409;
* a grouped product row's fan-out (one entry per member rec) writes every member.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.error_handler import AppException
from app.services.scm import plan_edits_service as svc
from tests._pg_fixture import pg_session
from tests.scm._revamp_fixtures import (
    category_and_uom,
    product,
    recommendation,
    run,
    supplier,
    warehouse,
)
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg

pytestmark = requires_pg

#: The lifecycle and level tables are company-owned and their `decided_by` / `amended_by`
#: columns are id-shaped, so the fixture authenticates like a request does rather than
#: passing a word. A save with no company could not stamp `scm.reorder_level` at all.
ACTOR = str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        with company_scope(s, frozenset({SORENTO_COMPANY_ID})):
            yield s


def _plan(db, *, legacy: bool = False, members: int = 1):
    """A PRODUCT-grain plan, in the shape the engine actually writes one.

    The buy names NO warehouse (`reorder_run_service._emit_product`: "the buy names NO
    warehouse ... that also puts the level lifecycle where the rule now is - a
    `needs_level` row for a product carries no location"), which is why the level and the
    reorder quantity below land on the product-wide `scm.reorder_level` row. A
    LOCATION-grain plan is the other shape and has its own test.
    """
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "revamp supplier")
    plan = run(db, legacy=legacy)
    recs = [recommendation(db, plan, prod, None, qty=50, sup=sup)
            for _ in range(members)]
    return plan, prod, recs


def _decision_rows(db, rec_ids):
    return db.execute(text(
        "SELECT recommendation_id::text AS rec_id, kind, buy_qty "
        "FROM scm.plan_row_decision WHERE recommendation_id = ANY(CAST(:ids AS uuid[]))"
    ), {"ids": [str(r) for r in rec_ids]}).mappings().all()


def _seed_suggestion(db, product_id, *, warehouse_id=None, suggested_level=24.0,
                     reorder_qty=None):
    """A stored suggestion, on the SAME (product, warehouse) key the run stored one under.

    `level_suggestion_service._plan_pairs` keys every stored suggestion by the
    recommendation's own pair, so a product-grain buy (no warehouse) stores the
    product-wide row and a location-grain row stores its location's.
    """
    db.execute(text("""
        INSERT INTO scm.reorder_level
            (id, product_id, warehouse_id, suggested_level, suggested_at,
             suggestion_basis, reorder_qty, company_id, created_at)
        VALUES (gen_random_uuid(), CAST(:p AS uuid), CAST(:w AS uuid), :sl, now(),
                CAST('{}' AS jsonb), :rq, CAST(:co AS uuid), now())
    """), {"p": str(product_id), "w": (str(warehouse_id) if warehouse_id else None),
           "sl": suggested_level, "rq": reorder_qty, "co": SORENTO_COMPANY_ID})
    db.flush()


def _level_row(db, product_id, warehouse_id=None):
    return db.execute(text(
        "SELECT level, amended_level, reorder_qty FROM scm.reorder_level "
        " WHERE product_id = CAST(:p AS uuid) "
        "   AND COALESCE(warehouse_id::text, '') = COALESCE(CAST(:w AS text), '')"
    ), {"p": str(product_id), "w": (str(warehouse_id) if warehouse_id else None)}
    ).mappings().first()


# ===========================================================================
# every field lands (E1)
# ===========================================================================

def test_decision_lands(db):
    plan, _prod, recs = _plan(db)
    out = svc.save_plan_edits(db, plan.id, [
        {"rec_id": recs[0].id, "decision": {"kind": "buy", "buy_qty": 120}},
    ], actor=ACTOR)

    assert out["saved_rows"] == 1
    assert out["saved_products"] == 1
    rows = _decision_rows(db, [recs[0].id])
    assert len(rows) == 1
    assert rows[0]["kind"] == "buy"
    assert float(rows[0]["buy_qty"]) == 120


def test_moq_lands(db):
    plan, _prod, recs = _plan(db)
    svc.save_plan_edits(db, plan.id, [{"rec_id": recs[0].id, "moq": 25}], actor=ACTOR)

    moq = db.execute(text(
        "SELECT moq_override FROM scm.reorder_recommendation WHERE id = :id"
    ), {"id": recs[0].id}).scalar()
    assert float(moq) == 25


def test_level_lands_as_an_amendment(db):
    plan, prod, recs = _plan(db)
    _seed_suggestion(db, prod.id, suggested_level=24)

    svc.save_plan_edits(db, plan.id, [{"rec_id": recs[0].id, "level": 30}], actor=ACTOR)

    row = _level_row(db, prod.id)
    assert float(row["amended_level"]) == 30
    # The engine's own number is never overwritten by the buyer's - that is the whole
    # point of the amendment column (S14).
    assert row["level"] is None


def test_reorder_qty_lands(db):
    plan, prod, recs = _plan(db)
    _seed_suggestion(db, prod.id)

    svc.save_plan_edits(db, plan.id, [{"rec_id": recs[0].id, "reorder_qty": 18}], actor=ACTOR)

    assert float(_level_row(db, prod.id)["reorder_qty"]) == 18


def test_lifecycle_lands(db):
    plan, prod, recs = _plan(db)
    svc.save_plan_edits(db, plan.id, [
        {"rec_id": recs[0].id, "lifecycle": "discontinue"},
    ], actor=ACTOR)

    decision = db.execute(text(
        "SELECT decision FROM scm.product_lifecycle_decision WHERE product_id = CAST(:p AS uuid)"
    ), {"p": str(prod.id)}).scalar()
    assert decision == "discontinue"


def test_one_row_carries_every_field_at_once(db):
    plan, prod, recs = _plan(db)
    _seed_suggestion(db, prod.id, suggested_level=24)

    svc.save_plan_edits(db, plan.id, [{
        "rec_id": recs[0].id,
        "decision": {"kind": "buy", "buy_qty": 90},
        "moq": 10,
        "level": 33,
        "reorder_qty": 44,
        "lifecycle": "keep",
    }], actor=ACTOR)

    assert float(_decision_rows(db, [recs[0].id])[0]["buy_qty"]) == 90
    level = _level_row(db, prod.id)
    assert float(level["amended_level"]) == 33
    assert float(level["reorder_qty"]) == 44
    assert db.execute(text(
        "SELECT decision FROM scm.product_lifecycle_decision WHERE product_id = CAST(:p AS uuid)"
    ), {"p": str(prod.id)}).scalar() == "keep"


# ===========================================================================
# the LOCATION grain writes to the row the panel is reading (B1)
# ===========================================================================

def test_a_level_edit_on_a_location_grain_run_amends_that_location_s_suggestion(db):
    """The suggestion a location-grain row shows is stored under ITS OWN warehouse.

    Forcing `warehouse_id=None` here looked up the product-wide row instead, which on a
    location run holds no suggestion at all - so every Level edit came back 422 ("There is
    no suggestion to amend for this item") and the whole batch rolled back with it.
    """
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "location grain level supplier")
    plan = run(db, grain="location")
    wh = warehouse(db)
    rec = recommendation(db, plan, prod, wh, qty=50, sup=sup)
    _seed_suggestion(db, prod.id, warehouse_id=wh.id, suggested_level=24)

    out = svc.save_plan_edits(db, plan.id, [
        {"rec_id": rec.id, "level": 30, "reorder_qty": 18},
    ], actor=ACTOR)

    assert out["saved_rows"] == 1
    row = _level_row(db, prod.id, wh.id)
    assert float(row["amended_level"]) == 30
    assert float(row["reorder_qty"]) == 18


# ===========================================================================
# B1 guard: a Level edit against a row with no suggestion has nothing to amend
# ===========================================================================

def test_a_level_edit_with_no_suggestion_422s_and_rolls_the_batch_back(db):
    """`_plan` seeds no `scm.reorder_level` row at all, so the product-grain rec below
    carries no suggestion to amend. Section 11's blocker fix keyed the amendment off the
    RIGHT (product, warehouse) pair - it never made a missing suggestion succeed, and it
    still must not: `level_suggestion_service.amend_suggestion` refuses it with a 422,
    and that refusal has to take the rest of the batch down with it, the same as any
    other row failure (`test_a_failing_row_rolls_the_whole_batch_back` above)."""
    plan, _prod, recs = _plan(db, members=2)

    with pytest.raises(AppException) as err:
        svc.save_plan_edits(db, plan.id, [
            {"rec_id": recs[0].id, "moq": 25},
            {"rec_id": recs[1].id, "level": 30},
        ], actor=ACTOR)

    assert err.value.status_code == 422
    db.rollback()
    moq = db.execute(text(
        "SELECT moq_override FROM scm.reorder_recommendation WHERE id = :id"
    ), {"id": recs[0].id}).scalar()
    assert moq is None, "the whole batch rolls back, including the row before the failure"


def test_the_422_names_which_row_had_no_suggestion(db):
    plan, prod, recs = _plan(db, members=1)

    with pytest.raises(AppException) as err:
        svc.save_plan_edits(db, plan.id, [
            {"rec_id": recs[0].id, "level": 30},
        ], actor=ACTOR)

    message = str(err.value.detail.get("message") or "")
    assert str(recs[0].id) in message or prod.product_code in message


# ===========================================================================
# one transaction (E1)
# ===========================================================================

def test_a_failing_row_rolls_the_whole_batch_back(db):
    """The second row's decision is invalid, so the FIRST row's must not survive either.

    Save is one button over several rows; a partial save would leave the buyer looking at
    a screen whose pills say Saved for edits that never reached the database.
    """
    plan, _prod, recs = _plan(db, members=2)

    with pytest.raises(AppException):
        svc.save_plan_edits(db, plan.id, [
            {"rec_id": recs[0].id, "decision": {"kind": "buy", "buy_qty": 120}},
            # `skip` may not carry a quantity - `_validate_plan_row_decision` refuses it.
            {"rec_id": recs[1].id, "decision": {"kind": "skip", "buy_qty": 5}},
        ], actor=ACTOR)

    db.rollback()
    assert _decision_rows(db, [recs[0].id, recs[1].id]) == []


# ===========================================================================
# scope guards (E1)
# ===========================================================================

def test_a_rec_outside_the_run_is_a_404(db):
    plan, _prod, _recs = _plan(db)
    other_plan, _p2, other_recs = _plan(db)

    with pytest.raises(AppException) as err:
        svc.save_plan_edits(db, plan.id, [
            {"rec_id": other_recs[0].id, "moq": 5},
        ], actor=ACTOR)
    assert err.value.status_code == 404


def test_an_unknown_run_is_a_404(db):
    _p, _prod, recs = _plan(db)
    with pytest.raises(AppException) as err:
        svc.save_plan_edits(
            db, "00000000-0000-0000-0000-0000000000ff",
            [{"rec_id": recs[0].id, "moq": 5}], actor=ACTOR)
    assert err.value.status_code == 404


def test_a_legacy_run_is_a_409(db):
    plan, _prod, recs = _plan(db, legacy=True)
    with pytest.raises(AppException) as err:
        svc.save_plan_edits(db, plan.id, [
            {"rec_id": recs[0].id, "decision": {"kind": "buy", "buy_qty": 10}},
        ], actor=ACTOR)
    assert err.value.status_code == 409


# ===========================================================================
# grouped product row fan-out (E2)
# ===========================================================================

def test_a_grouped_product_row_writes_every_member(db):
    """The screen sends one entry per MEMBER rec, exactly as the per-row endpoints are
    called today; the counts come back per row and per PRODUCT (R14)."""
    plan, _prod, recs = _plan(db, members=3)

    out = svc.save_plan_edits(db, plan.id, [
        {"rec_id": rec.id, "decision": {"kind": "buy", "buy_qty": 60}} for rec in recs
    ], actor=ACTOR)

    assert out["saved_rows"] == 3
    assert out["saved_products"] == 1, "three bins of one product are one product"
    rows = _decision_rows(db, [r.id for r in recs])
    assert len(rows) == 3
    assert {float(r["buy_qty"]) for r in rows} == {60.0}


def test_an_empty_batch_saves_nothing(db):
    plan, _prod, _recs = _plan(db)
    assert svc.save_plan_edits(db, plan.id, [], actor=ACTOR) == {
        "saved_rows": 0, "saved_products": 0,
    }


# ===========================================================================
# route-level: auth denial, scope guard and rollback through the actual endpoint
# (Phase 3 tester additions) - `svc.save_plan_edits` above pins the SERVICE; these pin
# the route wrapping it (`PUT /reorder-runs/{run}/plan-edits`), which owns the
# permission check and the request/response schema the service tests never exercise.
# ===========================================================================

from fastapi.testclient import TestClient  # noqa: E402

from tests.scm.conftest import as_user, seed_user  # noqa: E402


def _route_client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _route_plan(db, *, members: int = 1):
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "revamp route supplier")
    plan = run(db)
    recs = [recommendation(db, plan, prod, warehouse(db), qty=50, sup=sup)
            for _ in range(members)]
    return plan, prod, recs


def test_route_is_denied_without_the_decision_permission(scm_app):
    app, db = _route_client(scm_app, None)  # a user with no role at all
    plan, _prod, recs = _route_plan(db)

    with TestClient(app) as c:
        res = c.put(
            f"/api/v1/scm/reorder-runs/{plan.id}/plan-edits",
            json={"rows": [{"rec_id": str(recs[0].id), "moq": 25}]},
        )

    assert res.status_code == 403
    assert _decision_rows(db, [recs[0].id]) == []


def test_route_404s_a_rec_that_belongs_to_another_run(scm_app):
    app, db = _route_client(scm_app, "purchasing")
    plan, _prod, _recs = _route_plan(db)
    _other_plan, _p2, other_recs = _route_plan(db)

    with TestClient(app) as c:
        res = c.put(
            f"/api/v1/scm/reorder-runs/{plan.id}/plan-edits",
            json={"rows": [{"rec_id": str(other_recs[0].id), "moq": 5}]},
        )

    assert res.status_code == 404
    assert _decision_rows(db, [other_recs[0].id]) == []


def test_route_rolls_back_the_earlier_row_when_a_later_one_in_the_same_batch_fails(scm_app):
    """The FIRST row's decision is well-formed; the SECOND's is not (`skip` carrying a
    quantity). Through the actual route - request parsing, permission check, commit -
    the first row's write must still not survive."""
    app, db = _route_client(scm_app, "purchasing")
    plan, _prod, recs = _route_plan(db, members=2)

    with TestClient(app) as c:
        res = c.put(
            f"/api/v1/scm/reorder-runs/{plan.id}/plan-edits",
            json={"rows": [
                {"rec_id": str(recs[0].id), "decision": {"kind": "buy", "buy_qty": 120}},
                {"rec_id": str(recs[1].id), "decision": {"kind": "skip", "buy_qty": 5}},
            ]},
        )

    assert res.status_code == 422, res.text
    # The failed request never reached `db.commit()`, but the first row's write is still
    # FLUSHED and pending on the shared test session, which (same as the service-level
    # `test_a_failing_row_rolls_the_whole_batch_back` above) reads its own uncommitted
    # write back. A real request gets this for free when `get_db()`'s `finally: db.close()`
    # rolls the transaction back at teardown; the test fixture reuses one session across
    # "requests", so it has to ask for that explicitly to see what the next request would.
    db.rollback()
    assert _decision_rows(db, [recs[0].id, recs[1].id]) == []
