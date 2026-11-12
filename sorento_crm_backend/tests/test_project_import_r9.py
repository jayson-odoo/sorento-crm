"""Project import, fix round 9: crew's real-file pass findings (RED).

Shapes this file pins (the coder matches them):
- AC-PI-44 the upload probe lists every sheet with its PS-row count; the monthly sheets are
  ticked (`ticked`), a sheet with no PS heading is unticked; a columns save with fewer sheets
  ticks only those;
- counts: the run's `rows` and each sheet's `row_count` count EVERY PS-numbered row, the
  blank AUG placeholders included (fixture: 1398 rows, AUG 194); a preview's outcome counts
  add up to the run's rows;
- a linked customer line reads "<customer name> (<debtor code>)";
- delete: the record action `project_import_run.delete` (permission projects.import.run,
  parked through /api/v1/pending-actions like revert) removes a draft / previewed / reverted
  run, its import_job_rows and its stored source file; an imported run is refused with 422
  ("Revert it first"); park checks the permission and the company scope; commit re-checks the
  permission.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.fixtures.project_import.build_so_summary import (
    EXPECTED,
    MONTHLY_SHEETS,
    SUMMARY_SHEET,
    build_workbook,
    row_specs,
)

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    api_client,
    grant,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_company,
    seed_customer,
    world,
)
from .test_project_import_run import _simple_world

BASE = "/api/v1/projects/import"
PENDING = "/api/v1/pending-actions"
VIEW = "projects.import.view"
RUN = "projects.import.run"
BOTH = {VIEW, RUN}
DELETE = "project_import_run.delete"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _svc():
    from app.services.project_import import service

    return service


def _upload(client, content, name="SO SUMMARY 2026.xlsx"):
    response = client.post(f"{BASE}/runs", files={"file": (name, content, XLSX)})
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- AC-PI-44


def test_r9_ac_pi_44_the_probe_ticks_monthly_sheets_and_leaves_summary_unticked(world, api_client):
    client = api_client(world.db, world.admin_id, world.company_id, BOTH)

    body = _upload(client, build_workbook())

    sheets = {s["name"]: s for s in body["sheets"]}
    for spec in MONTHLY_SHEETS:
        assert sheets[spec.name]["ticked"] is True, spec.name
        assert sheets[spec.name]["has_ps_heading"] is True
    assert sheets[SUMMARY_SHEET]["ticked"] is False
    assert sheets[SUMMARY_SHEET]["has_ps_heading"] is False


def test_r9_ac_pi_44_saving_fewer_sheets_ticks_only_those(world, api_client):
    client = api_client(world.db, world.admin_id, world.company_id, BOTH)
    run_id = _upload(client, build_workbook())["id"]
    keep = [s.name for s in MONTHLY_SHEETS if s.name != "FEB'26"]

    saved = client.put(f"{BASE}/runs/{run_id}/columns", json={"sheets": keep, "columns": {}})
    assert saved.status_code in (200, 204), saved.text

    body = client.get(f"{BASE}/runs/{run_id}").json()
    ticked = [s["name"] for s in body["sheets"] if s["ticked"]]
    assert ticked == keep
    preview = client.post(f"{BASE}/runs/{run_id}/preview")
    assert preview.status_code == 200, preview.text
    feb = client.get(f"{BASE}/runs/{run_id}/rows", params={"sheet": "FEB'26", "limit": 50}).json()
    assert feb["total"] == 0, feb["total"]
    jan = client.get(f"{BASE}/runs/{run_id}/rows", params={"sheet": "JAN'26", "limit": 50}).json()
    assert jan["total"] == 170


# --------------------------------------------------------------------------- counts


def test_r9_counts_rows_and_row_count_include_every_ps_numbered_row(world, api_client):
    client = api_client(world.db, world.admin_id, world.company_id, BOTH)

    body = _upload(client, build_workbook())

    ps_per_sheet = {s.name: s.count for s in MONTHLY_SHEETS}
    sheets = {s["name"]: s for s in body["sheets"]}
    for name, count in ps_per_sheet.items():
        assert sheets[name]["row_count"] == count, name
    assert sheets["AUG'26"]["row_count"] == 194
    assert sheets[SUMMARY_SHEET]["row_count"] == 0
    detail = client.get(f"{BASE}/runs/{body['id']}").json()
    assert detail["rows"] == EXPECTED["ps_rows"] == len(row_specs()) == 1398


def test_r9_counts_preview_outcomes_add_up_to_the_run_rows(world, api_client):
    client = api_client(world.db, world.admin_id, world.company_id, BOTH)
    run_id = _upload(client, build_workbook())["id"]
    client.put(f"{BASE}/runs/{run_id}/columns",
               json={"sheets": [s.name for s in MONTHLY_SHEETS], "columns": {}})

    preview = client.post(f"{BASE}/runs/{run_id}/preview")

    assert preview.status_code == 200, preview.text
    counts = preview.json()["counts"]
    total = sum(counts.get(k, 0) for k in
                ("created", "updated", "unchanged", "skipped", "needs_review", "error"))
    detail = client.get(f"{BASE}/runs/{run_id}").json()
    assert total == detail["rows"] == 1398


# --------------------------------------------------------------------------- target label


def test_r9_a_linked_customer_line_reads_name_and_debtor_code(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))

    out = _svc().set_line(w.db, run, kind="customer", value_key="CUSTOMER 001 SDN BHD",
                          action="link", target_id=customer.id, user_id=w.admin_id)

    expected = f"{MARKER} DEALER ONE ({customer.customer_code})"
    assert out["target_label"] == expected
    line = _svc().list_lines(w.db, run, kind="customer")[0]
    assert line["target_label"] == expected


# --------------------------------------------------------------------------- delete


def test_r9_delete_is_a_registered_record_action():
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    action = get_action(DELETE)
    assert action is not None
    assert "project_import_run" in action.entity_types
    assert action.permission == RUN
    assert action.label and "_" not in action.label


def _run_in_phase(w, phase):
    run, _ = _simple_world(w, [row("PS26-0001")])
    s = _svc()
    if phase in ("previewed", "imported", "reverted"):
        s.preview(w.db, run, user_id=w.admin_id)
    if phase in ("imported", "reverted"):
        s.apply(w.db, run, user_id=w.admin_id)
    if phase == "reverted":
        s.revert(w.db, run, user_id=w.admin_id)
    w.db.commit()
    w.db.refresh(run)
    assert run.job_metadata["phase"] == phase
    return run


def _park(client, run_id):
    return client.post(PENDING, json={"action_key": DELETE, "entity_type": "project_import_run",
                                      "entity_id": str(run_id), "payload": {}})


def _commit_due(w):
    from app.models.sla import SlaFormAction
    from app.services.form_action_service import FormActionService

    for parked in w.db.query(SlaFormAction).filter(SlaFormAction.action_key == DELETE).all():
        parked.commit_at = datetime.utcnow() - timedelta(minutes=1)
    w.db.commit()
    FormActionService(w.db).commit_due()


@pytest.mark.parametrize("phase", ["draft", "previewed", "reverted"])
def test_r9_delete_removes_the_run_its_rows_and_its_file(world, api_client, phase):
    from app.models.job import ImportJob, ImportJobRow

    w = world
    run = _run_in_phase(w, phase)
    run_id, key = run.id, run.source_file_key
    assert key and key in w.storage.files
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    parked = _park(client, run_id)
    assert parked.status_code in (200, 201, 202), parked.text
    _commit_due(w)

    w.db.expire_all()
    assert w.db.get(ImportJob, run_id) is None
    assert w.db.query(ImportJobRow).filter(ImportJobRow.import_job_id == run_id).count() == 0
    assert key not in w.storage.files


def test_r9_delete_of_an_imported_run_is_refused(world, api_client):
    from app.models.job import ImportJob

    w = world
    run = _run_in_phase(w, "imported")
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = _park(client, run.id)

    assert response.status_code == 422, response.text
    assert "revert it first" in response.text.lower()
    assert w.db.get(ImportJob, run.id) is not None


def test_r9_delete_needs_the_run_permission_at_park(world, api_client):
    w = world
    run = _run_in_phase(w, "draft")
    client = api_client(w.db, w.admin_id, w.company_id, {VIEW})

    response = _park(client, run.id)

    assert response.status_code == 403, response.text


def test_r9_delete_of_another_companys_run_reads_404(world, api_client):
    from app.models.base import company_scope

    w = world
    other = seed_company(w.db, "Other")
    with company_scope(w.db, frozenset({other})):
        foreign = _svc().create_run(w.db, company_id=other, user_id=w.admin_id,
                                    filename="theirs.xlsx",
                                    content=make_book({"JAN'26": [row("PS26-0001")]}))
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = _park(client, foreign.id)

    assert response.status_code == 404, response.text


def test_r9_delete_rechecks_the_permission_at_commit(world, api_client, monkeypatch):
    from app.models.job import ImportJob
    from app.models.sla import FORM_ACTION_FAILED, SlaFormAction

    w = world
    run = _run_in_phase(w, "draft")
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    assert _park(client, run.id).status_code in (200, 201, 202)

    grant(monkeypatch, {VIEW})
    _commit_due(w)

    w.db.expire_all()
    assert w.db.get(ImportJob, run.id) is not None
    parked = w.db.query(SlaFormAction).filter(SlaFormAction.action_key == DELETE).one()
    assert parked.status == FORM_ACTION_FAILED
