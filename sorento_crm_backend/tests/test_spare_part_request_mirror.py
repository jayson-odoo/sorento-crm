"""SPARE-PART-ORDER-REQUEST crew ruling: mirror Purchase Requests, red-first (Phase 2).

Contract: a new feature/approver read permission `procurement.spare_part_requests.view`
(like purchase_requests.view). Every route that accepts the create grant as an alternative
read grant also accepts it, with the same scoping (no widening).

M1 the permission registry carries the slug.
M2 an approver holding ONLY the new view slug (no projects view) reaches the list, the detail,
   the OI header, the OI history and the worklist for a pending request they can decide, and
   approves it.
M3 a holder of the new slug who sits on no stage team sees an empty list and cannot open
   another user's request (404/403), exactly as any unrelated user.

Postgres only (`blank_session`); every row is seeded here, nothing borrowed.
"""
from __future__ import annotations

from ._forms_chain_support import uid, user
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    SPR,
    WORKLIST,
    reload,
    role_grant,
    sent,
    staged,
    submitted,
    svc,
    world,
)

NEW_VIEW = "procurement.spare_part_requests.view"
PROJECTS_VIEW = "projects.projects.view"


def test_M1_the_registry_has_the_spare_part_view_permission():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert NEW_VIEW in slugs


def _team_approver(w):
    from app.models.access import AgentTeam, TeamMember

    approver = user(w.db, "spr new-view-only approver")
    role_grant(w.db, approver, NEW_VIEW)  # deliberately NOT projects.projects.view
    tier1_team = (
        w.db.query(AgentTeam)
        .filter(AgentTeam.code == w.stage1.team_set, AgentTeam.tier == 1)
        .one()
    )
    w.db.add(TeamMember(id=uid(), team_id=tier1_team.team_id, user_id=approver, sort_order=9))
    w.db.commit()
    return approver


def test_M2_a_new_view_only_approver_reads_and_decides(staged):
    w = staged
    approver = _team_approver(w)
    inquiry = submitted(w)
    assert svc().can_decide(w.db, reload(w.db, inquiry), approver) is True, "precondition"
    client = w.as_user(approver)

    res = client.get(SPR, params={"limit": 100})
    assert res.status_code == 200, f"list: {res.status_code} {res.text}"
    assert str(inquiry.id) in [i["id"] for i in res.json()["data"]]

    res = client.get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, f"detail: {res.status_code} {res.text}"

    res = client.get(f"{HEADERS}/{inquiry.id}")
    assert res.status_code == 200, f"OI header: {res.status_code} {res.text}"

    res = client.get(f"{HEADERS}/{inquiry.id}/history")
    assert res.status_code == 200, f"OI history: {res.status_code} {res.text}"

    res = client.get(WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100})
    assert res.status_code == 200, f"worklist: {res.status_code} {res.text}"

    res = client.post(f"{SPR}/{inquiry.id}/approve", json={"note": "ok"})
    assert res.status_code == 200, f"approve: {res.status_code} {res.text}"
    assert reload(w.db, inquiry).state != "pending_approval"


def test_M3_a_new_view_holder_on_no_stage_team_sees_nothing(staged):
    w = staged
    stranger = user(w.db, "spr new-view-only stranger")
    role_grant(w.db, stranger, NEW_VIEW)
    w.db.commit()
    inquiry = submitted(w)
    client = w.as_user(stranger)

    res = client.get(SPR, params={"limit": 100})
    assert res.status_code == 200, f"list: {res.status_code} {res.text}"
    assert res.json()["data"] == [], "no widening: nothing they may decide or own"

    res = client.get(f"{SPR}/{inquiry.id}")
    assert res.status_code in (403, 404), res.text
    res = client.get(f"{HEADERS}/{inquiry.id}")
    assert res.status_code in (403, 404), f"OI header must stay closed: {res.status_code}"


def test_M4_a_view_only_approver_still_opens_the_request_after_approving(staged):
    """Browser re-check on a8162c81: right after Approve the record refetched and answered 404
    ("Could not load this spare part request"), because a view-only approver is no longer the
    current stage's decider. An approver of record keeps the record and finds it in the list,
    as a Purchase Request approver does."""
    w = staged
    approver = _team_approver(w)
    inquiry = submitted(w)
    client = w.as_user(approver)
    res = client.post(f"{SPR}/{inquiry.id}/approve", json={"note": "ok"})
    assert res.status_code == 200, f"approve: {res.status_code} {res.text}"

    res = client.get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, f"detail after approving: {res.status_code} {res.text}"
    res = client.get(f"{HEADERS}/{inquiry.id}")
    assert res.status_code == 200, f"OI header after approving: {res.status_code} {res.text}"
    res = client.get(f"{HEADERS}/{inquiry.id}/history")
    assert res.status_code == 200, f"history after approving: {res.status_code} {res.text}"
    res = client.get(SPR, params={"limit": 100})
    assert res.status_code == 200, res.text
    assert str(inquiry.id) in {r["id"] for r in res.json()["data"]}, "the approved request is in their list"
