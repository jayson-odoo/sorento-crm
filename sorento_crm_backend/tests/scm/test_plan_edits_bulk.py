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
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "revamp supplier")
    plan = run(db, legacy=legacy)
    recs = [recommendation(db, plan, prod, warehouse(db), qty=50, sup=sup)
            for _ in range(members)]
    return plan, prod, recs


def _decision_rows(db, rec_ids):
    return db.execute(text(
        "SELECT recommendation_id::text AS rec_id, kind, buy_qty "
        "FROM scm.plan_row_decision WHERE recommendation_id = ANY(CAST(:ids AS uuid[]))"
    ), {"ids": [str(r) for r in rec_ids]}).mappings().all()


def _seed_suggestion(db, product_id, *, suggested_level=24.0, reorder_qty=None):
    """A stored suggestion for the product, which is what `level` amends."""
    db.execute(text("""
        INSERT INTO scm.reorder_level
            (id, product_id, warehouse_id, suggested_level, suggested_at,
             suggestion_basis, reorder_qty, company_id, created_at)
        VALUES (gen_random_uuid(), CAST(:p AS uuid), NULL, :sl, now(),
                CAST('{}' AS jsonb), :rq, CAST(:co AS uuid), now())
    """), {"p": str(product_id), "sl": suggested_level, "rq": reorder_qty,
           "co": SORENTO_COMPANY_ID})
    db.flush()


def _level_row(db, product_id):
    return db.execute(text(
        "SELECT level, amended_level, reorder_qty FROM scm.reorder_level "
        "WHERE product_id = CAST(:p AS uuid) AND warehouse_id IS NULL"
    ), {"p": str(product_id)}).mappings().first()


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
