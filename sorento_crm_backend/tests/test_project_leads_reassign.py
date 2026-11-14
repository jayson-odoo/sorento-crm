"""PROJECT-LEADS-REASSIGN UAC A1-A6: one reassign path, reassign back, the primary lead.

UAC: documentation/plans/project-sales/project-leads-reassign-14nov-acceptance-criteria.md.

Contract names the coder matches (captain's brief, 14 Nov):
- `projects.projects.primary_owner_user_id` (nullable), echoed on the project payload as
  `primary_owner_user_id` + `primary_owner_name`.
- `project_service.reassign_project_owner(db, *, project, to_user_id, actor_user_id)`, called by
  BOTH the dispute approve and the `update_project` owner branch.
- `project_service.backfill_primary_owner(db)` (UAC A6): (1) earliest owner_reassigned
  from_user_id, else (2) the linked lead's owner_user_id, else (3) the current owner; never
  created_by; fills NULLs only; idempotent.

Notifications are asserted as real `notifications` rows (the v2 world runs the real service).
Every user, project and activity row is seeded here.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import MARKER
from ._project_register_v2_support import (  # noqa: F401
    LIST,
    MANAGE,
    STAFF,
    approved_project,
    as_user,
    developer,
    notes,
    project,
    register_body,
    save_draft,
    title,
    uid,
    v2,
)

REASON = "Found this project at the site briefing last week."
TEMPLATE = "owner_reassigned"
NOTIF = "project_reassigned"


def _name(w, key: str) -> str:
    return f"{MARKER} {w.names[key]}"


def _interest(w, user: str, project_id: str):
    res = as_user(w, user).post(
        f"{STAFF}/{project_id}/takeover-requests", json={"kind": "dispute", "reason": REASON}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _approve(w, project_id: str, request_id: str):
    res = as_user(w, w.manager).post(
        f"{STAFF}/{project_id}/takeover-requests/{request_id}/decide", json={"approve": True}
    )
    assert res.status_code == 200, res.text
    return res


def _put_owner(w, actor: str, project_id: str, owner: str):
    return as_user(w, actor).put(f"{STAFF}/{project_id}", json={"owner_user_id": owner})


def _registered(w, owner: str, actor: str | None = None) -> str:
    """A staff registration through the real route, so every creation-time column (the primary
    lead included) is set the way production sets it. `actor` defaults to the manager, who may
    register for someone else."""
    dev = developer(w.db, w.company_id, f"CONTOH Dev {uid()[:6]}")
    body = register_body(w, user=owner, developer_party_id=dev.id, owner_user_id=owner)
    res = as_user(w, actor or w.manager).post(LIST, json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _project_row(w, project_id: str):
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, project_id)


def _primary(w, project_id: str):
    return _project_row(w, project_id).primary_owner_user_id


def _reassign_rows(w, project_id: str) -> list:
    from app.models.activities import ActivityEvent

    w.db.expire_all()
    return (
        w.db.query(ActivityEvent)
        .filter(
            ActivityEvent.entity_type == "project",
            ActivityEvent.entity_id == str(project_id),
            ActivityEvent.system_template == TEMPLATE,
        )
        .order_by(ActivityEvent.created_at, ActivityEvent.id)
        .all()
    )


def _collaborators(w, project_id: str) -> set:
    from app.models.projects import ProjectCollaborator

    w.db.expire_all()
    return {
        r.user_id
        for r in w.db.query(ProjectCollaborator).filter(ProjectCollaborator.project_id == project_id)
    }


def _pairs(rows) -> list:
    return [((r.system_payload or {}).get("from_user_id"), (r.system_payload or {}).get("to_user_id")) for r in rows]


# ------------------------------------------------------------------ A1: owner change via PUT


def test_a1_manager_owner_change_writes_one_activity_naming_both_and_keeps_old_owner(v2):
    row = approved_project(v2)
    res = _put_owner(v2, v2.manager, row.id, v2.sales_b)
    assert res.status_code == 200, res.text

    assert _project_row(v2, row.id).owner_user_id == v2.sales_b
    rows = _reassign_rows(v2, row.id)
    assert len(rows) == 1, _pairs(rows)
    event = rows[0]
    payload = event.system_payload or {}
    assert payload.get("from_user_id") == v2.owner
    assert payload.get("to_user_id") == v2.sales_b
    assert payload.get("from_name") == _name(v2, "owner")
    assert payload.get("to_name") == _name(v2, "sales_b")
    assert event.body_text == f"Reassigned from {_name(v2, 'owner')} to {_name(v2, 'sales_b')}"
    assert event.actor_id == v2.manager
    assert v2.owner in _collaborators(v2, row.id)


def test_a1_manager_owner_change_notifies_the_new_and_the_previous_owner(v2):
    row = approved_project(v2)
    assert _put_owner(v2, v2.manager, row.id, v2.sales_b).status_code == 200
    recipients = {n.user_id for n in notes(v2, row.id, NOTIF)}
    assert {v2.sales_b, v2.owner} <= recipients, recipients


def test_a1_both_paths_run_the_one_shared_reassign_function(v2, monkeypatch):
    from app.services import project_service

    calls: list = []
    original = project_service.reassign_project_owner

    def spy(db, *, project, to_user_id, actor_user_id):
        calls.append((str(project.id), to_user_id, actor_user_id))
        return original(db, project=project, to_user_id=to_user_id, actor_user_id=actor_user_id)

    monkeypatch.setattr(project_service, "reassign_project_owner", spy)

    row = approved_project(v2)
    _approve(v2, row.id, _interest(v2, v2.sales_b, row.id))
    assert _put_owner(v2, v2.manager, row.id, v2.owner).status_code == 200

    assert calls == [
        (row.id, v2.sales_b, v2.manager),
        (row.id, v2.owner, v2.manager),
    ]


# ------------------------------------------------------------------ A2: reassign back


def test_a2_dispute_then_owner_change_back_gives_two_rows_and_restores_the_primary(v2):
    pid = _registered(v2, v2.owner)
    assert _primary(v2, pid) == v2.owner

    _approve(v2, pid, _interest(v2, v2.sales_b, pid))
    assert _project_row(v2, pid).owner_user_id == v2.sales_b
    assert v2.owner in _collaborators(v2, pid)

    res = _put_owner(v2, v2.manager, pid, v2.owner)
    assert res.status_code == 200, res.text

    rows = _reassign_rows(v2, pid)
    # One transaction in the test, so created_at ties: assert both directions, one row each.
    assert sorted(_pairs(rows)) == sorted([(v2.owner, v2.sales_b), (v2.sales_b, v2.owner)]), _pairs(rows)
    back = [r for r in rows if (r.system_payload or {}).get("to_user_id") == v2.owner]
    assert back[0].body_text == f"Reassigned from {_name(v2, 'sales_b')} to {_name(v2, 'owner')}"

    assert _project_row(v2, pid).owner_user_id == v2.owner
    assert v2.sales_b in _collaborators(v2, pid)
    assert _primary(v2, pid) == v2.owner


def test_a2_the_reassign_back_notifies_both_people_again(v2):
    row = approved_project(v2)
    _approve(v2, row.id, _interest(v2, v2.sales_b, row.id))
    first = notes(v2, row.id, NOTIF)
    assert {n.user_id for n in first} >= {v2.owner, v2.sales_b}

    seen = {n.id for n in first}
    assert _put_owner(v2, v2.manager, row.id, v2.owner).status_code == 200
    fresh = [n for n in notes(v2, row.id, NOTIF) if n.id not in seen]
    assert {n.user_id for n in fresh} >= {v2.owner, v2.sales_b}, [n.user_id for n in fresh]


def test_a2_a_third_reassign_to_the_same_person_is_not_swallowed_by_dedup(v2):
    row = approved_project(v2)
    assert _put_owner(v2, v2.manager, row.id, v2.sales_b).status_code == 200
    assert _put_owner(v2, v2.manager, row.id, v2.owner).status_code == 200
    assert _put_owner(v2, v2.manager, row.id, v2.sales_b).status_code == 200

    per_user: dict = {}
    for n in notes(v2, row.id, NOTIF):
        per_user[n.user_id] = per_user.get(n.user_id, 0) + 1
    assert per_user.get(v2.sales_b) == 3, per_user
    assert per_user.get(v2.owner) == 3, per_user
    assert len(_reassign_rows(v2, row.id)) == 3


# ------------------------------------------------------------------ A3: manager only


def test_a3_a_non_manager_owner_change_is_403_and_changes_nothing(v2):
    """Guard: the rule is unchanged (UAC A3), so this may already be green."""
    row = approved_project(v2)
    # Committed (onto the fixture's savepoint) so the route's rollback on 403 keeps the seed.
    v2.db.commit()
    # The owner (edit rights, no manage) trying to hand their own project away.
    res = _put_owner(v2, v2.owner, row.id, v2.sales_c)
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "project_owner_reassign_forbidden"
    assert _project_row(v2, row.id).owner_user_id == v2.owner
    assert _reassign_rows(v2, row.id) == []
    assert _collaborators(v2, row.id) == set()
    assert notes(v2, row.id, NOTIF) == []


def test_a3_service_level_non_manager_owner_change_raises_403(v2):
    from app.services import project_service
    from app.services.error_handler import AppException

    row = approved_project(v2)
    with pytest.raises(AppException) as err:
        project_service.update_project(
            v2.db,
            row,
            {"owner_user_id": v2.sales_c},
            actor_user_id=v2.owner,
            permissions={"projects.projects.view", "projects.projects.edit"},
        )
    assert err.value.status_code == 403
    assert _project_row(v2, row.id).owner_user_id == v2.owner
    assert _reassign_rows(v2, row.id) == []


# ------------------------------------------------------------------ A4: same owner = no-op


def test_a4_shared_function_same_owner_is_a_no_op(v2):
    from app.services import project_service

    row = approved_project(v2)
    project_service.reassign_project_owner(
        v2.db, project=row, to_user_id=v2.owner, actor_user_id=v2.manager
    )
    v2.db.flush()
    assert _project_row(v2, row.id).owner_user_id == v2.owner
    assert _reassign_rows(v2, row.id) == []
    assert _collaborators(v2, row.id) == set()
    assert notes(v2, row.id, NOTIF) == []


def test_a4_shared_function_moves_owner_once_and_keeps_collaborator_idempotent(v2):
    from app.services import project_service

    row = approved_project(v2)
    project_service.reassign_project_owner(
        v2.db, project=row, to_user_id=v2.sales_b, actor_user_id=v2.manager
    )
    project_service.reassign_project_owner(
        v2.db, project=row, to_user_id=v2.owner, actor_user_id=v2.manager
    )
    project_service.reassign_project_owner(
        v2.db, project=row, to_user_id=v2.sales_b, actor_user_id=v2.manager
    )
    v2.db.flush()
    assert _project_row(v2, row.id).owner_user_id == v2.sales_b
    # Sales A was demoted twice: still one collaborator row, no IntegrityError.
    assert _collaborators(v2, row.id) == {v2.owner}
    assert len(_reassign_rows(v2, row.id)) == 3


def test_a4_manager_put_with_the_same_owner_is_a_no_op(v2):
    """Guard through the route: today's PUT is silent, so this may already be green."""
    row = approved_project(v2)
    res = _put_owner(v2, v2.manager, row.id, v2.owner)
    assert res.status_code == 200, res.text
    assert _reassign_rows(v2, row.id) == []
    assert _collaborators(v2, row.id) == set()
    assert notes(v2, row.id, NOTIF) == []


# ------------------------------------------------------------------ A5: primary at registration


def test_a5_staff_registration_for_someone_else_sets_primary_to_the_owner(v2):
    pid = _registered(v2, v2.sales_b, actor=v2.manager)
    row = _project_row(v2, pid)
    assert row.owner_user_id == v2.sales_b
    assert row.created_by == v2.manager
    assert row.primary_owner_user_id == v2.sales_b


def test_a5_staff_registration_for_self_sets_primary(v2):
    pid = _registered(v2, v2.owner, actor=v2.owner)
    assert _primary(v2, pid) == v2.owner


def test_a5_salesperson_draft_registration_sets_primary(v2):
    res = save_draft(v2, v2.sub_b)
    assert res.status_code in (200, 201), res.text
    assert _primary(v2, res.json()["id"]) == v2.sub_b


def test_a5_primary_never_changes_on_reassign(v2):
    pid = _registered(v2, v2.owner)
    assert _put_owner(v2, v2.manager, pid, v2.sales_b).status_code == 200
    _approve(v2, pid, _interest(v2, v2.sales_c, pid))
    assert _project_row(v2, pid).owner_user_id == v2.sales_c
    assert _primary(v2, pid) == v2.owner


def test_a5_detail_get_returns_the_primary_id_and_name(v2):
    pid = _registered(v2, v2.sales_b)
    assert _put_owner(v2, v2.manager, pid, v2.sales_c).status_code == 200

    res = as_user(v2, v2.manager).get(f"{STAFF}/{pid}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["owner_user_id"] == v2.sales_c
    assert body["primary_owner_user_id"] == v2.sales_b
    assert body["primary_owner_name"] == _name(v2, "sales_b")


# ------------------------------------------------------------------ A6: backfill


def _seed_reassign_row(w, project_id: str, frm: str, to: str, at: datetime):
    from app.models.activities import ActivityEvent

    w.db.add(
        ActivityEvent(
            entity_type="project",
            entity_id=str(project_id),
            kind="system",
            system_template=TEMPLATE,
            system_payload={"from_user_id": frm, "to_user_id": to},
            body_text="Reassigned",
            actor_id=w.manager,
            created_at=at,
        )
    )
    w.db.flush()


def _backfilled(w, *project_ids: str) -> list:
    """Run the backfill twice (idempotent) and return each project's primary."""
    from app.services import project_service

    project_service.backfill_primary_owner(w.db)
    w.db.flush()
    first = [_primary(w, pid) for pid in project_ids]
    project_service.backfill_primary_owner(w.db)
    w.db.flush()
    assert [_primary(w, pid) for pid in project_ids] == first, "second run changed a value"
    return first


T0 = datetime(2026, 9, 1, 9, 0, 0)


def test_a6_rule1_earliest_owner_reassigned_row_wins(v2):
    from ._project_register_v2_support import seed_lead

    # Two reassignments, the LATER one inserted first: earliest by time wins, not by insert.
    # A lead whose owner differs is linked too: rule 1 outranks rule 2.
    lead = seed_lead(v2, v2.approver)
    moved = project(v2.db, v2.company_id, title("Moved"), owner=v2.sales_c)
    moved.created_by = v2.manager
    moved.lead_id = lead.id
    _seed_reassign_row(v2, moved.id, v2.sales_b, v2.sales_c, T0 + timedelta(days=3))
    _seed_reassign_row(v2, moved.id, v2.owner, v2.sales_b, T0)
    # Another entity's owner_reassigned row, older still, must not leak in.
    _seed_reassign_row(v2, uid(), v2.approver, v2.sales_b, T0 - timedelta(days=30))
    v2.db.flush()

    assert _backfilled(v2, moved.id) == [v2.owner]


def test_a6_rule2_no_reassign_row_but_a_lead_takes_the_lead_owner(v2):
    from ._project_register_v2_support import seed_lead

    lead = seed_lead(v2, v2.sales_b)
    from_lead = project(v2.db, v2.company_id, title("FromLead"), owner=v2.sales_c)
    from_lead.created_by = v2.manager
    from_lead.lead_id = lead.id
    v2.db.flush()

    assert _backfilled(v2, from_lead.id) == [v2.sales_b]


def test_a6_rule3_no_reassign_row_no_lead_takes_the_current_owner_never_created_by(v2):
    # Bulk-imported shape: created_by is the importer, not the salesperson.
    imported = project(v2.db, v2.company_id, title("Imported"), owner=v2.sales_b)
    imported.created_by = v2.manager
    # Dev shape: creator Salesperson B, owner Salesperson A, no lead.
    handed = project(v2.db, v2.company_id, title("Handed"), owner=v2.owner)
    handed.created_by = v2.sales_b
    v2.db.flush()

    assert _backfilled(v2, imported.id, handed.id) == [v2.sales_b, v2.owner]


def test_a6_an_already_set_primary_is_untouched(v2):
    from ._project_register_v2_support import seed_lead

    kept = project(v2.db, v2.company_id, title("Kept"), owner=v2.sales_b)
    kept.lead_id = seed_lead(v2, v2.approver).id
    kept.primary_owner_user_id = v2.sales_c
    _seed_reassign_row(v2, kept.id, v2.owner, v2.sales_b, T0)
    v2.db.flush()

    assert _backfilled(v2, kept.id) == [v2.sales_c]
