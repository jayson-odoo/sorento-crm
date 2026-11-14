"""PROJECT-RELATED-RECORDS fix round 1 (AC-C6, owner rule "History: who, when, old -> new"):
a record's History reads a project change as "Project: <code> <title> → <code> <title>", resolved
by the audit list's id resolver (the one that turns status ids into labels). No UUID in the line.

Postgres only (`blank_session` through the `staff` fixture); fake values (marker `zzt-prr`).
"""
from __future__ import annotations

import re

from .test_si_npa_project_link import SI, _as_editor, _inquiry, _ok, staff  # noqa: F401  (fixture)

AUDIT = "/api/v1/audit/logs/"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _label(project) -> str:
    return f"{project.project_code} {project.title}"


def _descriptions(client, row_id) -> list[str]:
    body = _ok(client.get(AUDIT, params={"entity_type": "stock_inquiry", "entity_id": str(row_id)}))
    return [r.get("description") or "" for r in body["data"]]


def test_a_project_change_reads_old_to_new_by_code_and_title(staff):
    w = staff
    row = _inquiry(w.db, status="responded", project_id=str(w.approved.id))
    with _as_editor(w) as client:
        _ok(client.patch(f"{SI}/{row.id}/project", json={"project_id": str(w.approved_2.id)}))
        lines = _descriptions(client, row.id)
    assert f"Project: {_label(w.approved)} → {_label(w.approved_2)}" in lines, lines
    assert not any(_UUID.search(line) for line in lines), lines


def test_a_first_project_reads_from_none(staff):
    w = staff
    row = _inquiry(w.db, status="responded")
    with _as_editor(w) as client:
        _ok(client.patch(f"{SI}/{row.id}/project", json={"project_id": str(w.approved_2.id)}))
        lines = _descriptions(client, row.id)
    assert f"Project: ∅ → {_label(w.approved_2)}" in lines, lines
    assert not any(_UUID.search(line) for line in lines), lines
