"""PS-REGISTER-CHECK-FIRST UAC R1: a dispute request notifies "registered as secondary lead".

Type key and the stored request kind are unchanged.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    STAFF,
    approved_project,
    as_user,
    notes,
    v2,
)

REASON = "Found this project at the site briefing last week."


def test_ac_r1_dispute_notice_reads_registered_as_secondary_lead(v2):
    row = approved_project(v2)
    res = as_user(v2, v2.sub_a).post(
        f"{STAFF}/{row.id}/takeover-requests", json={"kind": "dispute", "reason": REASON}
    )
    assert res.status_code == 201, res.text
    assert res.json()["kind"] == "dispute"
    rows = notes(v2, row.id, "project_interest_registered")
    assert rows, "the owner must be notified under the unchanged type key"
    from app.models.user import User

    name = v2.db.get(User, v2.sub_a).name
    for n in rows:
        assert n.title == f"{name} registered as secondary lead on {row.project_code}", n.title
        assert n.body == f"{name} registered as secondary lead on {row.project_code}: {row.title}", n.body
