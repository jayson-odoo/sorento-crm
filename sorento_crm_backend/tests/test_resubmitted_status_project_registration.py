"""RESUBMITTED-STATUS for portal project registrations (stage-based: resubmitted stands in for
`approval_state = pending`). Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    STAFF,
    approve,
    as_user,
    pending,
    registration,
    reject,
    submit,
    world,  # noqa: F401  (fixture)
)

LIST = STAFF


def _resubmitted(w) -> str:
    rid = pending(w)
    assert reject(w, rid, "Already registered").status_code == 200
    w.sent.clear()
    w.sent_kw.clear()
    res = submit(w, rid)
    assert res.status_code == 200, res.text
    assert registration(w, rid).approval_state == "resubmitted"
    return rid


def test_a_resubmitted_registration_can_be_approved(world):
    rid = _resubmitted(world)
    res = approve(world, rid)
    assert res.status_code == 200, res.text
    assert registration(world, rid).approval_state == "approved"


def test_a_resubmitted_registration_can_be_rejected_again(world):
    rid = _resubmitted(world)
    res = reject(world, rid, "Still a duplicate")
    assert res.status_code == 200, res.text
    assert registration(world, rid).approval_state == "rejected"


def test_resubmit_tells_the_approvers_it_was_resubmitted(world):
    rid = _resubmitted(world)
    recipients = {user for user, _type in world.sent}
    assert recipients == {world.approver}
    titles = [kw.get("title") or "" for kw in world.sent_kw]
    assert titles and all("resubmitted" in t.lower() for t in titles), titles
    assert all(str(kw.get("source_entity_id") or rid) == rid for kw in world.sent_kw)


def test_the_list_filters_on_resubmitted(world):
    plain = pending(world)
    again = _resubmitted(world)
    res = as_user(world, world.staff).get(LIST, params={"limit": 100, "approval_state": "resubmitted"})
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()["data"]}
    assert again in ids
    assert plain not in ids


def test_an_approver_may_edit_a_resubmitted_registration_like_a_pending_one(world):
    rid = _resubmitted(world)
    res = as_user(world, world.coordinator).put(
        f"{STAFF}/{rid}", json={"title": "CADANGAN BLOK BETA PHASE TWO"}
    )
    assert res.status_code == 200, res.text


def test_project_label_reads_resubmitted_where_the_code_would_be():
    from types import SimpleNamespace

    from app.services.project_service import project_label

    assert project_label(SimpleNamespace(project_code=None, approval_state="resubmitted")) == "Resubmitted"
    assert project_label(SimpleNamespace(project_code=None, approval_state="pending")) == "Awaiting approval"
