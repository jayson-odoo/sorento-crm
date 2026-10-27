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


def test_resubmit_tells_the_approvers_in_app_only_like_a_first_submit(world):
    _resubmitted(world)
    assert world.sent_kw and all(kw.get("send_email") is False for kw in world.sent_kw)


def test_a_resubmitted_registration_names_its_possible_duplicates(world):
    from ._project_registration_support import SUB, as_contact, project

    existing = project(world.db, world.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-9001")
    world.semantic.append((existing.id, 0.93))
    rid = pending(world, title="CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU, JOHOR")
    assert reject(world, rid, "Check the lot").status_code == 200
    assert submit(world, rid).status_code == 200
    assert registration(world, rid).approval_state == "resubmitted"
    got = as_contact(world, world.a).get(f"{SUB}/{rid}").json()
    assert got["possible_duplicates"] == [{"project_code": existing.project_code, "title": existing.title}]


def test_the_list_tells_an_approver_they_may_edit_a_resubmitted_registration(world):
    rid = _resubmitted(world)
    res = as_user(world, world.coordinator).get(LIST, params={"limit": 100})
    assert res.status_code == 200, res.text
    row = next(r for r in res.json()["data"] if r["id"] == rid)
    assert row["can_edit"] is True
