"""Project import, fix round 6: browser pass 1 defects with a backend side (RED).

Source: crew/state/files/project-migration/browser-pass-1.md.

Shapes this file pins (the coder matches them):
- D4: every report row carries `blocking_line`: {kind, customer_value_key, value_key} of
  the line that blocks it (the same keys `/lines` uses), or null when nothing blocks;
- D7: a parked revert's history reads in plain words. No entry carries the action slug
  `project_import_run.revert`; the request reads "Revert requested" (or the action's own
  label + "requested"); the run's revert itself is ONE "Reverted" entry (no generic
  "Action applied" twin).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    api_client,
    grant,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_customer,
    seed_party,
    world,
)
from .test_project_import_run import C1, _map, _simple_world

BASE = "/api/v1/projects/import"
VIEW = "projects.import.view"
RUN = "projects.import.run"
BOTH = {VIEW, RUN}
SLUG = "project_import_run.revert"


# --------------------------------------------------------------------------- D4


def test_r6_d4_report_rows_carry_their_blocking_line(world, api_client):
    w = world
    a = seed_party(w.db, w.company_id, f"{MARKER} DEV A")
    b = seed_party(w.db, w.company_id, f"{MARKER} DEV B")
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", customer=" customer 404  sdn bhd "),
        row("PS26-0002", project_name="Unmapped  Project"),
        row("PS26-0003", project_name="TOWER X", developer="DEV A TEXT"),
        row("PS26-0004", project_name="TOWER X2", developer="DEV B TEXT"),
        row("PS26-0005", project_name=None),
    ]}))
    _map(w, run, customers={C1: customer.id},
         projects={(C1, "TOWER X"): ("create", "ZZT X"), (C1, "TOWER X2"): ("create", "ZZT X")},
         developers={"DEV A TEXT": ("link", a.id), "DEV B TEXT": ("link", b.id)})
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    assert client.post(f"{BASE}/runs/{run.id}/preview").status_code == 200

    rows = {r["ps_number"]: r for r in client.get(f"{BASE}/runs/{run.id}/rows",
                                                  params={"limit": 50}).json()["data"]}

    assert rows["PS26-0001"]["blocking_line"] == {
        "kind": "customer", "customer_value_key": "", "value_key": "CUSTOMER 404 SDN BHD"}
    assert rows["PS26-0002"]["blocking_line"] == {
        "kind": "project", "customer_value_key": C1, "value_key": "UNMAPPED PROJECT"}
    dev = rows["PS26-0003"]["blocking_line"]
    assert dev["kind"] == "developer" and dev["customer_value_key"] == ""
    assert dev["value_key"] in {"DEV A TEXT", "DEV B TEXT"}
    assert rows["PS26-0005"]["blocking_line"] is None
    # The keys are the ones /lines lists, so the screen can open that exact line.
    keys = {(l["customer_value_key"], l["value_key"])
            for l in client.get(f"{BASE}/runs/{run.id}/lines",
                                params={"kind": "project", "limit": 50}).json()["items"]}
    assert (C1, "UNMAPPED PROJECT") in keys


def test_r6_d4_the_preview_report_rows_carry_it_too(world):
    from app.services.project_import import service

    w = world
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))

    report = service.preview(w.db, run, user_id=w.admin_id)

    line = report["rows"][0]["blocking_line"]
    assert line == {"kind": "customer", "customer_value_key": "", "value_key": C1}


# --------------------------------------------------------------------------- D7


def test_r6_d7_the_revert_action_has_a_plain_label():
    import app.services.record_actions  # noqa: F401  registers every action
    from app.services.form_action_registry import get_action

    action = get_action(SLUG)
    assert action.label and "_" not in action.label and "." not in action.label
    assert re.search(r"\brevert", action.label, re.I)


def test_r6_d7_a_committed_revert_reads_in_plain_words_in_the_history(world, api_client,
                                                                      monkeypatch):
    from app.api.v1.audit import audit_logs
    from app.models.sla import FORM_ACTION_CHANNEL_UI, SlaFormAction
    from app.services.form_action_service import FormActionService
    from app.services.project_import import service

    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    service.apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    grant(monkeypatch, BOTH)
    FormActionService(w.db).dispatch(
        action_key=SLUG, entity_type="project_import_run", entity_id=str(run.id),
        payload={"entity_id": str(run.id)}, actor_id=w.admin_id,
        channel=FORM_ACTION_CHANNEL_UI, grace_seconds=10,
    )
    parked = w.db.query(SlaFormAction).filter(SlaFormAction.action_key == SLUG).one()
    parked.commit_at = datetime.utcnow() - timedelta(minutes=1)
    w.db.commit()
    FormActionService(w.db).commit_due()
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "reverted"

    monkeypatch.setattr(audit_logs, "_is_audit_admin", lambda db, uid: True)
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    entries = client.get("/api/v1/audit/logs", params={
        "entity_type": "project_import_run", "entity_id": str(run.id), "limit": 200}).json()["data"]
    texts = [" ".join(str(e.get(k) or "") for k in ("event", "description")).strip()
             for e in entries]

    assert not [t for t in texts if SLUG in t], texts
    assert not [t for t in texts if re.search(r"\bAction (requested|applied)\b", t)], texts
    assert [t for t in texts if re.search(r"\brevert\w*\b.*\brequested\b", t, re.I)], texts
    assert len([t for t in texts if re.search(r"\bReverted\b", t)]) == 1, texts
