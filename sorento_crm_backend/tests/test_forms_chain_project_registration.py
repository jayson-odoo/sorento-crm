"""FORMS-REGRESSION: project registration lifecycle chain over the real routes.

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md. Uses the
PROJECT-REG-PORTAL world (tests/_project_registration_support.py), which already seeds the
contacts, sales agents, numbering rule and approvers this form needs.

One chain, end to end: draft -> save -> reopen -> submit -> reject (reason on the portal, the
applicant told in-app) -> edit -> resubmit -> approve (PPF code drawn, applicant told). A
registration has no SLA, undo or WhatsApp send: the chain also pins that nothing reaches the
Respond outbox.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._forms_chain_support import outbox
from ._project_registration_support import (
    SUB,
    approve,
    as_contact,
    create_draft,
    ppf_code,
    registration,
    reject,
    submit,
    world,  # noqa: F401  (fixture)
)


def test_draft_save_submit_reject_resubmit_approve_chain(world):
    w = world
    rid = create_draft(w)["id"]
    c = as_contact(w, w.a)
    saved = c.put(f"{SUB}/{rid}", json={"fields": {"title": "CADANGAN KILANG DI LOT 88, MUKIM TEBRAU",
                                                   "state": "Johor", "developer_name": "Example Dev"}})
    assert saved.status_code == 200, saved.text
    assert registration(w, rid).approval_state == "draft"
    assert c.get(f"{SUB}/{rid}").status_code == 200

    assert submit(w, rid).status_code == 200
    assert registration(w, rid).approval_state == "pending"
    rej = reject(w, rid, "duplicate of an existing project")
    assert rej.status_code == 200, rej.text
    seen = c.get(f"{SUB}/{rid}").json()
    assert seen["reject_reason"] == "duplicate of an existing project"
    assert registration(w, rid).approval_state == "rejected"
    assert approve(w, rid).status_code == 409  # a rejected registration must be resubmitted
    told = [kw for kw in w.sent_kw if kw.get("user_id") == w.applicant_user]
    assert told, "the applicant hears about the rejection"

    again = submit(w, rid, body={"title": "CADANGAN KILANG BARU DI LOT 88, MUKIM TEBRAU",
                                 "state": "Johor", "developer_name": "Example Dev"})
    assert again.status_code == 200, again.text
    assert registration(w, rid).approval_state == "resubmitted"

    ok = approve(w, rid)
    assert ok.status_code == 200, ok.text
    assert ok.json()["approval_state"] == "approved"
    assert ok.json()["project_code"] == ppf_code(5)
    assert len([kw for kw in w.sent_kw if kw.get("user_id") == w.applicant_user]) == len(told) + 1
    assert outbox(w.db, "projects", rid) == []
