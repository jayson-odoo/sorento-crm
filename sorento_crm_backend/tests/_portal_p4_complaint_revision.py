"""PORTAL-P4-REQUESTS S2 (owner Q6 a, P4-14): complaint revision, written once for both surfaces.

Contract assumed (from the SI / PR / SF adapters in app/services/portal_revision_service.py and the
`portal_revision_configs` row the complaint type already has):

- revise on a complaint is governed ONLY by the per-type setting (enabled, allowed_statuses, cap);
- success writes a `portal_form_revisions` row (kinds: original, revision), `complaints.revision_no`
  goes 0 -> 1, status returns to the restart stage (no matching stage config here, so the type's
  submit status `submitted`), every open form-SLA tracker of the complaint is voided with
  void_reason `revised_by_contact`;
- FROZEN on revise: `contact_id` and `space_id` (the requestor identity the complaint is routed and
  owned by). A revise payload naming other values leaves them untouched;
- refusal (type disabled, status not allowed, cap reached) is HTTP 422 (409 for a stale
  expected_revision_no) and changes nothing.
"""
from __future__ import annotations

import dataclasses

from tests import _portal_p4_support as s

SPEC = dataclasses.replace(
    s.SPECS["complaint"],
    revisable=True,
    restart_status="submitted",
    frozen=("contact_id", "space_id"),
    revise_field="defect_description",
)
REVISED = "ZZT revised defect description"


def _final_complaint(sc: s.Scene, api: s.Api) -> str:
    s.seed_sla(sc, SPEC)
    sid = s._id(api.create(SPEC.kind, SPEC.body(sc)))
    s.ok(api.submit(SPEC.kind, sid))
    s.staff_to_final(sc, SPEC, sid)
    return sid


def flow_revise_ok(sc: s.Scene, api: s.Api) -> None:
    s.seed_revisions(sc, SPEC, enabled=True)
    sid = _final_complaint(sc, api)
    before = sc.row(SPEC, sid)
    frozen_before = {f: getattr(before, f) for f in SPEC.frozen}
    assert frozen_before["contact_id"] == sc.contact.id
    assert (before.revision_no or 0) == 0
    assert [r.kind for r in sc.revisions(SPEC.kind, sid)] == ["original"]
    open_trackers = [t for t in sc.trackers(SPEC.kind, sid) if t.voided_at is None]
    assert open_trackers, "the submit should have left an open SLA tracker"

    detail = s.ok(api.get(SPEC.kind, sid)).json()
    assert detail["revision"]["allowed"] is True, detail.get("revision")

    fields = {
        SPEC.revise_field: REVISED,
        "contact_id": sc.other_contact.id,
        "space_id": "sp_not_mine",
    }
    resp = s.ok(api.revise(SPEC.kind, sid, fields=fields, expected=0), 200)
    body = resp.json()
    assert body["revision_no"] == 1
    assert body["submission"]["status"] == SPEC.restart_status

    after = sc.row(SPEC, sid)
    assert after.revision_no == 1
    assert after.status == SPEC.restart_status
    assert after.defect_description == REVISED
    for f, v in frozen_before.items():
        assert getattr(after, f) == v, f"{f} changed on revise"

    revs = sc.revisions(SPEC.kind, sid)
    assert [r.kind for r in revs] == ["original", "revision"], [r.kind for r in revs]
    assert revs[-1].revision_no == 1

    old = {str(t.id) for t in open_trackers}
    for t in sc.trackers(SPEC.kind, sid):
        if str(t.id) in old:
            assert t.voided_at is not None and t.void_reason == "revised_by_contact"
            assert t.is_resolved is False

    listed = s.ok(api.revisions(SPEC.kind, sid)).json()["items"]
    assert [i["kind"] for i in listed] == ["original", "revision"], listed


def flow_revise_refused_disabled(sc: s.Scene, api: s.Api) -> None:
    s.seed_revisions(sc, SPEC, enabled=False)
    sid = _final_complaint(sc, api)
    detail = s.ok(api.get(SPEC.kind, sid)).json()
    assert detail["revision"]["allowed"] is False
    resp = api.revise(SPEC.kind, sid, fields={SPEC.revise_field: REVISED}, expected=0)
    s.not_a_missing_route(resp)
    assert resp.status_code == 422, (resp.status_code, resp.text)
    _unchanged(sc, sid)


def flow_revise_refused_status(sc: s.Scene, api: s.Api) -> None:
    s.seed_revisions(sc, SPEC, enabled=True, allowed=["rejected"])
    sid = _final_complaint(sc, api)
    assert s.ok(api.get(SPEC.kind, sid)).json()["revision"]["allowed"] is False
    resp = api.revise(SPEC.kind, sid, fields={SPEC.revise_field: REVISED}, expected=0)
    s.not_a_missing_route(resp)
    assert resp.status_code == 422, (resp.status_code, resp.text)
    _unchanged(sc, sid)


def flow_revise_refused_cap(sc: s.Scene, api: s.Api) -> None:
    s.seed_revisions(sc, SPEC, enabled=True, cap=1, allowed=[SPEC.final_status, "submitted"])
    sid = _final_complaint(sc, api)
    s.ok(api.revise(SPEC.kind, sid, fields={SPEC.revise_field: REVISED}, expected=0), 200)
    assert sc.row(SPEC, sid).revision_no == 1
    s.staff_to_final(sc, SPEC, sid)
    resp = api.revise(SPEC.kind, sid, fields={SPEC.revise_field: "ZZT again"}, expected=1)
    s.not_a_missing_route(resp)
    assert resp.status_code == 422, (resp.status_code, resp.text)
    after = sc.row(SPEC, sid)
    assert after.revision_no == 1 and after.status == SPEC.final_status
    assert after.defect_description == REVISED


def _unchanged(sc: s.Scene, sid: str) -> None:
    after = sc.row(SPEC, sid)
    assert after.status == SPEC.final_status
    assert (after.revision_no or 0) == 0
    assert [r.kind for r in sc.revisions(SPEC.kind, sid)] == ["original"]
