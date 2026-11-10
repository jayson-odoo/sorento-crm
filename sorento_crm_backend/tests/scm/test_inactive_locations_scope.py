"""SCM-INACTIVE-LOCATIONS (owner option (a), 10 Nov 2026): a reorder / low stock scope uses
ACTIVE locations only.

Plan: documentation/plans/scm/PLAN-scm-inactive-locations-10nov.md

1. The scope picker's payload (`GET /scm/dashboard/warehouses?active_only=true`) omits an
   inactive location; without the flag the dashboard still lists it.
2. `create_run` refuses an inactive code with 422 naming it (route and service).
3. `resolve_run_scope` reports the codes deactivated since the run, so Re-plan can drop them.
4. The daily job drops an inactive code before `create_run` and says which in its summary;
   every code inactive falls back to the nothing-ticked rule and says so.

Postgres only; every row seeded here inside a rolled-back transaction.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.scheduler.task_scheduler import _handler_scm_reorder_run
from app.services.error_handler import AppException
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import unique_code
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401 - pytest fixture import
from tests.scm.test_m3_run import _client, _mk_product, _mk_stock, _mk_warehouse

pytestmark = requires_pg


def _deactivate(db, wid):
    db.execute(text("UPDATE warehouses SET is_active = false WHERE id = :w"), {"w": wid})
    db.flush()


def _codes():
    tag = unique_code("ZZTIN", alpha=True)
    return tag, f"{tag}-A", f"{tag}-X"


# --- 1. picker payload --------------------------------------------------------------------

def test_picker_payload_offers_active_locations_only(scm_app):
    app_, db = _client(scm_app, "admin")
    tag, active_code, inactive_code = _codes()
    wa = _mk_warehouse(db, active_code)
    wx = _mk_warehouse(db, inactive_code)
    pid = _mk_product(db, f"{tag}-P")
    _mk_stock(db, pid, wa, 5)
    _mk_stock(db, pid, wx, 5)
    _deactivate(db, wx)

    with TestClient(app_) as c:
        picker = c.get("/api/v1/scm/dashboard/warehouses",
                       params={"q": tag, "active_only": "true"})
        dashboard = c.get("/api/v1/scm/dashboard/warehouses", params={"q": tag})

    assert picker.status_code == 200, picker.text
    picker_codes = {w["warehouse_code"] for w in picker.json()["data"]}
    assert active_code in picker_codes
    assert inactive_code not in picker_codes
    # The dashboard itself (and code-to-name lookups) still see every location.
    assert dashboard.status_code == 200, dashboard.text
    assert inactive_code in {w["warehouse_code"] for w in dashboard.json()["data"]}


# --- 2. create_run refuses an inactive code ----------------------------------------------

def test_create_run_refuses_an_inactive_code_naming_it(scm_app):
    _, db, _, _ = scm_app
    _, active_code, inactive_code = _codes()
    _mk_warehouse(db, active_code)
    _deactivate(db, _mk_warehouse(db, inactive_code))
    before = db.execute(text("SELECT count(*) FROM scm.reorder_run")).scalar()

    with pytest.raises(AppException) as exc:
        svc.create_run(db, [active_code, inactive_code], enqueue=False)

    assert exc.value.status_code == 422
    assert inactive_code in exc.value.message
    assert active_code not in exc.value.message
    assert db.execute(text("SELECT count(*) FROM scm.reorder_run")).scalar() == before


def test_start_plan_route_answers_422_naming_the_inactive_code(scm_app):
    app_, db = _client(scm_app, "purchasing")
    _, _, inactive_code = _codes()
    _deactivate(db, _mk_warehouse(db, inactive_code))

    with TestClient(app_) as c:
        resp = c.post("/api/v1/scm/reorder-runs", json={"warehouse_codes": [inactive_code]})

    assert resp.status_code == 422, resp.text
    assert inactive_code in resp.text


def test_create_run_with_active_codes_only_still_works(scm_app):
    _, db, _, _ = scm_app
    _, active_code, _ = _codes()
    wa = _mk_warehouse(db, active_code)

    created = svc.create_run(db, [active_code], enqueue=False)

    stored = db.execute(text("SELECT warehouse_ids FROM scm.reorder_run WHERE id = :r"),
                        {"r": created["run_id"]}).scalar()
    assert [str(w) for w in stored] == [wa]


# --- 3. Re-plan prefill: resolve_run_scope reports the deactivated codes ------------------

def test_resolve_run_scope_reports_codes_deactivated_since_the_run(scm_app):
    _, db, _, _ = scm_app
    _, active_code, inactive_code = _codes()
    wa = _mk_warehouse(db, active_code)
    wx = _mk_warehouse(db, inactive_code)
    _deactivate(db, wx)

    scope = svc.resolve_run_scope(db, [wa, wx], None, None)

    # The run's own history stays whole; the dropped subset is listed apart.
    assert sorted(scope["warehouse_codes"]) == sorted([active_code, inactive_code])
    assert scope["inactive_warehouse_codes"] == [inactive_code]


def test_resolve_run_scope_reports_none_when_all_active(scm_app):
    _, db, _, _ = scm_app
    _, active_code, _ = _codes()
    wa = _mk_warehouse(db, active_code)

    assert svc.resolve_run_scope(db, [wa], None, None)["inactive_warehouse_codes"] == []


def test_run_detail_carries_inactive_warehouse_codes(scm_app):
    app_, db = _client(scm_app, "purchasing")
    _, active_code, inactive_code = _codes()
    _mk_warehouse(db, active_code)
    wx = _mk_warehouse(db, inactive_code)
    created = svc.create_run(db, [active_code, inactive_code], enqueue=False)
    _deactivate(db, wx)

    with TestClient(app_) as c:
        resp = c.get(f"/api/v1/scm/reorder-runs/{created['run_id']}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["inactive_warehouse_codes"] == [inactive_code]


# --- 4. daily job drops inactive codes and says which -------------------------------------

class _Task:
    def __init__(self, metadata=None, timezone="UTC"):
        self.metadata_ = metadata
        self.timezone = timezone


def _stub_pipeline(monkeypatch) -> dict:
    from app.services.scm import low_stock_report_service as lsr

    captured: dict = {}

    def _create_run(db, **kwargs):
        captured["kwargs"] = kwargs
        return {"run_id": str(uuid.uuid4())}

    monkeypatch.setattr(svc, "create_run", _create_run)
    monkeypatch.setattr(svc, "run_reorder", lambda rid, db=None: None)
    monkeypatch.setattr(svc, "apply_run_budget", lambda db, rid, b, full=False: {"funded": 1})
    monkeypatch.setattr(lsr, "dispatch_ready", lambda db, rid: {"fired": 0})
    return captured


def test_daily_job_drops_an_inactive_code_and_names_it(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    _, active_code, inactive_code = _codes()
    _mk_warehouse(db, active_code)
    _deactivate(db, _mk_warehouse(db, inactive_code))
    captured = _stub_pipeline(monkeypatch)

    result = _handler_scm_reorder_run(
        db, _Task(metadata={"warehouse_codes": [active_code, inactive_code]}))

    assert captured["kwargs"]["warehouse_codes"] == [active_code]
    assert result["message"] == f"Skipped inactive location {inactive_code}"


def test_daily_job_all_inactive_falls_back_to_nothing_ticked(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    tag, _, inactive_code = _codes()
    other = f"{tag}-Y"
    _deactivate(db, _mk_warehouse(db, inactive_code))
    _deactivate(db, _mk_warehouse(db, other))
    captured = _stub_pipeline(monkeypatch)

    result = _handler_scm_reorder_run(
        db, _Task(metadata={"warehouse_codes": [inactive_code, other]}))

    assert captured["kwargs"]["warehouse_codes"] == []
    assert result["message"] == (
        f"Skipped inactive locations {', '.join(sorted([inactive_code, other]))}, "
        "planning every active location instead"
    )


def test_daily_job_with_active_codes_carries_no_message(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    _, active_code, _ = _codes()
    _mk_warehouse(db, active_code)
    captured = _stub_pipeline(monkeypatch)

    result = _handler_scm_reorder_run(db, _Task(metadata={"warehouse_codes": [active_code]}))

    assert captured["kwargs"]["warehouse_codes"] == [active_code]
    assert "message" not in result


# --- the codes path keeps active rows only, across companies ------------------------------

def test_a_code_active_in_one_company_and_inactive_in_another_plans_the_active_one(scm_app):
    """All-companies scope (the scheduler's): the same code in two companies, one row
    deactivated. Not refused (an active match exists), and the run stores ONLY the active
    warehouse, never the other company's inactive row."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.inventory import Warehouse

    _, db, _, _ = scm_app
    set_company_scope(db, None)
    tag, code, _ = _codes()
    a = Company(id=str(uuid.uuid4()), code=f"{tag}A"[:20], name=f"{tag} company A")
    b = Company(id=str(uuid.uuid4()), code=f"{tag}B"[:20], name=f"{tag} company B")
    db.add_all([a, b])
    db.flush()
    live = Warehouse(id=str(uuid.uuid4()), company_id=a.id, warehouse_code=code,
                     warehouse_name="live", is_active=True)
    dead = Warehouse(id=str(uuid.uuid4()), company_id=b.id, warehouse_code=code,
                     warehouse_name="dead", is_active=False)
    db.add_all([live, dead])
    db.flush()

    created = svc.create_run(db, [code], enqueue=False)

    stored = db.execute(text("SELECT warehouse_ids FROM scm.reorder_run WHERE id = :r"),
                        {"r": created["run_id"]}).scalar()
    assert [str(w) for w in stored] == [live.id]


def test_a_deactivated_ticked_location_does_not_make_the_scope_read_as_all(scm_app):
    """Ticked A + B, B deactivated since, C active and never ticked. Counting B would lift
    the ticked count to the active estate's size and read the run as "All", so a Re-plan
    would widen to every location (C included). Only active ticked ids count."""
    _, db, _, _ = scm_app
    tag, a_code, b_code = _codes()
    wa = _mk_warehouse(db, a_code)
    wb = _mk_warehouse(db, b_code)
    _mk_warehouse(db, f"{tag}-C")
    active_now = db.execute(text("SELECT count(*) FROM warehouses WHERE is_active")).scalar()
    _deactivate(db, wb)
    # Pad the ticked list with the estate's other active warehouses minus one, so that
    # A + B together equal the active count: the case the raw count gets wrong.
    others = [str(r[0]) for r in db.execute(text(
        "SELECT id FROM warehouses WHERE is_active AND id <> ALL(CAST(:x AS uuid[])) "
        "AND warehouse_code <> :c ORDER BY id"
    ), {"x": [wa, wb], "c": f"{tag}-C"}).all()]
    assert len(others) == active_now - 3
    ticked = [wa, wb, *others]

    scope = svc.resolve_run_scope(db, ticked, None, None)

    assert scope["is_all_warehouses"] is False
    assert scope["inactive_warehouse_codes"] == [b_code]


def test_a_ticked_scope_whose_locations_are_all_inactive_never_reads_as_all(scm_app):
    """Ticked only B, B deactivated since: still a ticked scope, so Re-plan falls back to
    nothing ticked WITH its notice (rule 3) rather than silently reading as "All"."""
    _, db, _, _ = scm_app
    _, _, b_code = _codes()
    wb = _mk_warehouse(db, b_code)
    _deactivate(db, wb)

    scope = svc.resolve_run_scope(db, [wb], None, None)

    assert scope["is_all_warehouses"] is False
    assert scope["inactive_warehouse_codes"] == [b_code]


def test_plans_list_does_not_label_a_scope_all_because_of_a_deactivated_location(scm_app):
    """The plans list reads "All" the same way the plan header does: active ticked ids only."""
    app_, db = _client(scm_app, "purchasing")
    tag, a_code, b_code = _codes()
    wa = _mk_warehouse(db, a_code)
    wb = _mk_warehouse(db, b_code)
    _mk_warehouse(db, f"{tag}-C")
    others = [r[0] for r in db.execute(text(
        "SELECT warehouse_code FROM warehouses WHERE is_active "
        "AND id <> ALL(CAST(:x AS uuid[])) AND warehouse_code <> :c"
    ), {"x": [wa, wb], "c": f"{tag}-C"}).all()]
    # A + B + every other active warehouse but C: the raw ticked count equals the active
    # estate once B is deactivated.
    created = svc.create_run(db, [a_code, b_code, *others], enqueue=False)
    _deactivate(db, wb)

    with TestClient(app_) as c:
        resp = c.get("/api/v1/scm/reorder-runs", params={"limit": 100})

    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["data"] if r["run_id"] == created["run_id"])
    assert row["is_all_warehouses"] is False
