"""SCM engine simulation harness - endpoint tests.

Reading (overview / scenarios / diff) is pure disk + registry, so these tests seed no
database rows at all - the two claims worth pinning are that it renders correctly against
the REAL committed fixtures (``scripts/scm_sim/snapshots/current.json`` +
``baselines/baseline.json``) and that it degrades gracefully when either file is absent
(a fresh checkout before anyone has ever run the harness). Running/blessing is gated on
this process being connected to the dedicated sim database, which the test suite's own
database (a prod-copy, never ``sorento_scm_sim``) naturally is not - so the 409 guard is
exercised for free, with no monkeypatching of the database itself.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.scm import simulation_service as svc
from tests.scm.conftest import requires_pg, seed_user, as_user

pytestmark = requires_pg


def _client(scm_app, role_slug: str | None):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def test_overview_reads_the_committed_fixtures(scm_app):
    app, _db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        body = c.get("/api/v1/scm/simulation/overview").json()

    # The test database is never `sorento_scm_sim` - the whole point of the guard.
    assert body["sim_db_active"] is False
    assert body["baseline_exists"] is True
    assert body["current_exists"] is True
    assert body["baseline_blessed_at"] is not None
    assert body["current_run_at"] is not None
    assert body["scenario_count"] == len(svc.SCENARIOS)
    # Not on the sim database -> no DB lookup is even attempted.
    assert body["latest_run_id"] is None


def test_overview_degrades_gracefully_with_no_json_yet(scm_app, tmp_path, monkeypatch):
    app, _db = _client(scm_app, "purchasing")
    monkeypatch.setattr(svc, "SNAPSHOT_PATH", tmp_path / "current.json")
    monkeypatch.setattr(svc, "BASELINE_PATH", tmp_path / "baseline.json")

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/simulation/overview")

    assert res.status_code == 200
    body = res.json()
    assert body["baseline_exists"] is False
    assert body["current_exists"] is False
    assert body["baseline_blessed_at"] is None
    assert body["current_run_at"] is None
    assert body["scenario_count"] == len(svc.SCENARIOS)


def test_overview_is_denied_without_the_view_permission(scm_app):
    app, _db = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/simulation/overview")
    assert res.status_code == 403


def test_scenarios_lists_every_registry_code_against_the_fixtures(scm_app):
    app, _db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        body = c.get("/api/v1/scm/simulation/scenarios").json()

    rows = body["data"]
    assert len(rows) == len(svc.SCENARIOS)
    codes = {r["code"] for r in rows}
    assert codes == {s.code for s in svc.SCENARIOS}

    # baseline.json == current.json in the committed fixtures, so nothing has changed.
    assert all(r["status"] == "SAME" for r in rows)
    assert all(r["changed_groups"] == [] for r in rows)

    sim_p001 = next(r for r in rows if r["code"] == "SIM-P001")
    assert sim_p001["current"]["rec_type"] is not None
    assert sim_p001["current"] == sim_p001["baseline"]
    # Input columns are read off the snapshot's net_position, not the ScenarioSpec - for
    # SIM-P001 (dealer, no committed/SPO/PO) they land on the same numbers either way.
    assert sim_p001["inputs"]["on_hand"] == 100
    assert sim_p001["inputs"]["committed"] == 0
    assert sim_p001["inputs"]["spo_incoming"] == 0
    assert sim_p001["inputs"]["po_open"] == 0
    assert sim_p001["inputs"]["demand_label"] == "SO"

    # SIM-P023 is a project-segment scenario with committed demand and no open PO - the
    # demand label flips to "OI" (Order Inquiry) and po_open reads 0 (no recommendation
    # inputs to carry an open PO), not null.
    sim_p023 = next(r for r in rows if r["code"] == "SIM-P023")
    assert sim_p023["inputs"]["demand_label"] == "OI"
    assert sim_p023["inputs"]["committed"] == 40
    assert sim_p023["inputs"]["po_open"] == 0

    # SIM-P025 pins the PO-is-informational-only quirk: po_open is visible (120) even
    # though it plays no part in the buy.
    sim_p025 = next(r for r in rows if r["code"] == "SIM-P025")
    assert sim_p025["inputs"]["po_open"] == 120

    # SIM-P031 has no recommendation at all (net above the reorder level) but still
    # carries net_position, so on_hand/committed/spo_incoming are real numbers, not null.
    sim_p031 = next(r for r in rows if r["code"] == "SIM-P031")
    assert sim_p031["current"] is None
    assert sim_p031["inputs"]["on_hand"] == 150
    assert sim_p031["inputs"]["po_open"] == 0


def test_scenarios_render_with_no_baseline_or_current_yet(scm_app, tmp_path, monkeypatch):
    app, _db = _client(scm_app, "purchasing")
    monkeypatch.setattr(svc, "SNAPSHOT_PATH", tmp_path / "current.json")
    monkeypatch.setattr(svc, "BASELINE_PATH", tmp_path / "baseline.json")

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/simulation/scenarios")

    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == len(svc.SCENARIOS)
    assert all(r["status"] == "NO_BASELINE" for r in rows)
    assert all(r["current"] is None for r in rows)
    assert all(r["baseline"] is None for r in rows)
    # Neither JSON file exists at all - the input columns degrade to null/0, never a
    # KeyError, and never a fabricated non-zero number.
    assert all(r["inputs"]["on_hand"] is None for r in rows)
    assert all(r["inputs"]["po_open"] == 0 for r in rows)


def test_scenarios_is_denied_without_the_view_permission(scm_app):
    app, _db = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/simulation/scenarios")
    assert res.status_code == 403


def test_scenario_diff_returns_the_full_current_blob(scm_app):
    app, _db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        body = c.get("/api/v1/scm/simulation/scenarios/SIM-P001/diff").json()

    assert body["code"] == "SIM-P001"
    assert body["status"] == "SAME"
    assert body["diffs"] == []
    assert body["current"]["title"] == "Steady high demand, low stock"
    assert body["baseline"] == body["current"]


def test_scenario_diff_for_an_unknown_code_is_404(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/simulation/scenarios/SIM-NOPE/diff")
    assert res.status_code == 404


def test_run_is_refused_with_409_when_this_process_is_not_on_the_sim_database(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/simulation/run", json={"bless_baseline": False})
    assert res.status_code == 409


def test_run_is_denied_without_the_run_permission(scm_app):
    app, _db = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/simulation/run", json={"bless_baseline": False})
    assert res.status_code == 403


def test_bless_refuses_when_there_is_no_current_run_to_bless(scm_app, tmp_path, monkeypatch):
    app, _db = _client(scm_app, "purchasing")
    monkeypatch.setattr(svc, "SNAPSHOT_PATH", tmp_path / "current.json")

    with TestClient(app) as c:
        res = c.post("/api/v1/scm/simulation/bless")

    assert res.status_code == 400


def test_bless_is_denied_without_the_run_permission(scm_app):
    app, _db = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/simulation/bless")
    assert res.status_code == 403
