"""PORTAL-P4-REQUESTS S7 red tests: a salesperson's Price Tag Request written from the CRM through
/api/v1/my-requests, by the portal's own code (`public/portal_price_tag.py`, route bodies moved to one service).

Paths and bodies are the portal router's. Revise goes through the generic revise route; the PTAG adapter exists.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_pt_support import (  # noqa: F401
    KIND,
    LOOK,
    PT_CREATE,
    PT_VIEW,
    PT_VIEW_OWN,
    SPEC,
    SUB,
    create,
    integration_logs,
    pt_row,
    scene,
    submitted,
    to_proof,
    world,
)


def _mounted(w):
    s.ok(w.rep.me.call("GET", SUB))


def _lines(body):
    return [(l["product_id"], l["quantity"]) for l in body["lines"]]


def test_p4_pt_parity_create_and_list_equal_the_portal(world):
    w = world
    mine, theirs = create(w.rep.me, w), create(w.rep.portal, w)
    assert set(mine) == set(theirs)
    assert (mine["status"], bool(mine["portal_draft_at"])) == (theirs["status"], bool(theirs["portal_draft_at"])) == ("new", True)
    assert s.shape(mine["doc_number"]) == s.shape(theirs["doc_number"]) and mine["doc_number"].startswith("PT-")
    row = pt_row(w, mine["id"])
    assert row.contact_id == w.rep.contact.id and str(row.company_id) == w.company_id
    assert _lines(mine) == _lines(theirs)
    got_me = s.ok(w.rep.me.call("GET", SUB)).json()
    got_portal = s.ok(w.rep.portal.call("GET", SUB)).json()
    assert {r["id"] for r in got_me["items"]} == {r["id"] for r in got_portal["items"]} == {mine["id"], theirs["id"]}
    assert set(got_me["items"][0]) == set(got_portal["items"][0]) and set(got_me) == set(got_portal)


def _walk(api, w) -> list:
    """create -> save -> detail -> submit -> save refused -> resubmit refused -> delete refused."""
    out = []
    d = create(api, w, debtor_name=None, debtor_code=None, print_by=None)
    out.append(("create", d["status"]))
    r = api.call("POST", f"{SUB}/{d['id']}/submit")
    out.append(("submit_incomplete", r.status_code, r.json().get("code"), r.json().get("detail")))
    r = api.call("PUT", f"{SUB}/{d['id']}", json={"debtor_name": "ZZT Dealer", "debtor_code": "ZZT-D1"})
    out.append(("save_debtor", r.status_code, r.json().get("debtor_name")))
    r = api.call("POST", f"{SUB}/{d['id']}/submit")
    out.append(("submit_no_print_by", r.status_code, r.json().get("code")))
    r = api.call("PUT", f"{SUB}/{d['id']}", json={"print_by": "self", "notes": "ZZT changed"})
    out.append(("save_print_by", r.status_code, r.json().get("print_by"), r.json().get("notes")))
    r = api.call("POST", f"{SUB}/{d['id']}/submit")
    out.append(("submit", r.status_code, r.json().get("status"), r.json().get("portal_draft_at")))
    r = api.call("PUT", f"{SUB}/{d['id']}", json={"notes": "ZZT late"})
    out.append(("save_after_submit", r.status_code, r.json().get("code")))
    r = api.call("POST", f"{SUB}/{d['id']}/submit")
    out.append(("resubmit", r.status_code, r.json().get("code")))
    r = api.call("DELETE", f"{SUB}/{d['id']}")
    out.append(("delete_submitted", r.status_code, r.json().get("code")))
    return out


def test_p4_pt_draft_save_submit_rules_match_the_portal(world):
    w = world
    mine, theirs = _walk(w.rep.me, w), _walk(w.rep.portal, w)
    assert mine == theirs
    assert ("submit_incomplete", 422, "PRINT_BY_REQUIRED", "print_by") in mine
    assert ("submit_no_print_by", 422, "PRINT_BY_REQUIRED") in mine
    assert ("save_after_submit", 409, "NOT_DRAFT") in mine and ("resubmit", 409, "ALREADY_SUBMITTED") in mine
    assert [step for step in mine if step[0] == "submit"][0][1:3] == (200, "new")
    assert ("delete_submitted", 409, "NOT_DRAFT") in mine


def test_p4_pt_save_replaces_lines_and_delete_draft_hard_deletes(world):
    w = world
    d = create(w.rep.me, w)
    from tests import _ptag_r9_seed

    second = _ptag_r9_seed.seed_product(w.sc.db)
    w.sc.db.commit()
    saved = s.ok(w.rep.me.call("PUT", f"{SUB}/{d['id']}", json={"lines": [
        {"line_type": "product", "product_id": second.id, "quantity": 5}]})).json()
    assert _lines(saved) == [(second.id, 5)]
    assert s.ok(w.rep.me.call("GET", f"{SUB}/{d['id']}")).json()["lines"][0]["code"]
    s.ok(w.rep.me.call("DELETE", f"{SUB}/{d['id']}"), 204)
    assert w.rep.me.call("GET", f"{SUB}/{d['id']}").status_code == 404
    from app.models.price_tag import PriceTagRequest

    assert w.sc.db.query(PriceTagRequest).filter(PriceTagRequest.id == d["id"]).count() == 0


def test_p4_pt_submit_runs_the_portals_sla_tracker_auto_assign_and_notification(world):
    w = world
    s.seed_sla(w.sc, SPEC)
    ids = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = submitted(api, w)
        ids[name] = rid
    me_t, po_t = w.sc.trackers(KIND, ids["me"]), w.sc.trackers(KIND, ids["portal"])
    assert len(me_t) == len(po_t) >= 1, "the form SLA must open a tracker on submit"
    mine, theirs = pt_row(w, ids["me"]), pt_row(w, ids["portal"])
    assert (mine.status, bool(mine.assigned_to_id)) == (theirs.status, bool(theirs.assigned_to_id)) == ("designing", True)
    assert mine.portal_draft_at is None
    assert len(integration_logs(w, ids["me"])) == len(integration_logs(w, ids["portal"])) >= 1, "the submitted message is logged"


def test_p4_pt_approve_proof_matches_the_portal_and_stays_theirs(world):
    w = world
    out = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = submitted(api, w)
        to_proof(w, rid)
        r = api.call("POST", f"{SUB}/{rid}/approve")
        out[name] = (r.status_code, r.json().get("status"), pt_row(w, rid).status)
    assert out["me"] == out["portal"] == (200, "approved", "approved")


def test_p4_pt_approve_before_the_proof_is_refused_like_the_portal(world):
    w = world
    mine, theirs = submitted(w.rep.me, w), submitted(w.rep.portal, w)
    a, b = w.rep.me.call("POST", f"{SUB}/{mine}/approve"), w.rep.portal.call("POST", f"{SUB}/{theirs}/approve")
    s.not_a_missing_route(a)
    assert a.status_code == b.status_code and a.status_code >= 400
    assert a.json() == b.json()


def test_p4_pt_request_changes_stores_the_round_and_the_comments(world):
    w = world
    out = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = submitted(api, w)
        to_proof(w, rid)
        r = api.call("POST", f"{SUB}/{rid}/request-changes", json={"note": "ZZT make the price bigger"})
        comments = api.call("GET", f"{SUB}/{rid}/review-comments")
        out[name] = (
            r.status_code, r.json().get("status"), r.json().get("round"), len(r.json().get("comments", [])),
            comments.status_code, len(comments.json()), pt_row(w, rid).status,
        )
    assert out["me"] == out["portal"]
    assert out["me"][:2] == (200, "changes_requested") and out["me"][5] >= 1 and out["me"][6] == "changes_requested"


def test_p4_pt_request_changes_needs_the_proof_ready_status(world):
    w = world
    mine, theirs = submitted(w.rep.me, w), submitted(w.rep.portal, w)
    a = w.rep.me.call("POST", f"{SUB}/{mine}/request-changes", json={"note": "ZZT early"})
    b = w.rep.portal.call("POST", f"{SUB}/{theirs}/request-changes", json={"note": "ZZT early"})
    s.not_a_missing_route(a)
    assert (a.status_code, a.json().get("code")) == (b.status_code, b.json().get("code")) == (409, "INVALID_TRANSITION")


def test_p4_pt_collect_records_the_contact_and_closes_the_request(world):
    w = world
    out = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = submitted(api, w)
        to_proof(w, rid)
        s.ok(api.call("POST", f"{SUB}/{rid}/approve"))
        s.ok(w.sc.staff_call("POST", f"/api/v1/dealer-kit/price-tag-requests/{rid}/transition", json={"status": "ready_for_collection"}))
        r = api.call("POST", f"{SUB}/{rid}/collect")
        row = pt_row(w, rid)
        out[name] = (r.status_code, r.json().get("status"), row.status, row.collected_by_contact_id, row.collected_by_user_id)
    assert out["me"] == out["portal"] == (200, "collected", "collected", w.rep.contact.id, None)


def test_p4_pt_revise_follows_the_setting_refused_when_off(world):
    w = world
    s.seed_revisions(w.sc, SPEC, enabled=False, allowed=["new"])
    mine, theirs = submitted(w.rep.me, w), submitted(w.rep.portal, w)
    a = w.rep.me.revise(KIND, mine, fields={"debtor_name": "ZZT Revised"})
    b = w.rep.portal.revise(KIND, theirs, fields={"debtor_name": "ZZT Revised"})
    s.not_a_missing_route(a)
    assert b.status_code != 200, b.text
    assert (a.status_code, a.json()) == (b.status_code, b.json())
    assert (pt_row(w, mine).revision_no or 0) == 0


def test_p4_pt_revise_works_when_the_setting_is_on(world):
    w = world
    s.seed_revisions(w.sc, SPEC, enabled=True, allowed=["new"])
    out = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = submitted(api, w)
        r = api.call("POST", f"{SUB}/{rid}/revise", json={
            "reason": "ZZT customer changed the order", "expected_revision_no": 0,
            "fields": {"debtor_name": "ZZT Revised Dealer"},
            "products": [{"product_id": w.product.id, "quantity": 5}],
        })
        s.not_a_missing_route(r)
        row = pt_row(w, rid)
        out[name] = (r.status_code, r.json().get("revision_no"), row.revision_no, row.debtor_name, row.lines[0].quantity)
    assert out["me"] == out["portal"] == (200, 1, 1, "ZZT Revised Dealer", 5)
    assert [r.kind for r in w.sc.revisions(KIND, rid)] == ["original", "revision"]


def test_p4_pt_debtor_picker_is_the_portals_multi_agent_list(world):
    w = world
    mine = s.ok(w.rep.me.call("GET", f"{LOOK}/debtors-for-agent")).json()
    assert mine == s.ok(w.rep.portal.call("GET", f"{LOOK}/debtors-for-agent")).json()
    codes = {d["customer_code"] for d in mine}
    assert codes == {c.customer_code for c in w.rep.customers} and len(codes) == 2, "both agents' customers"
    assert w.other.mine.customer_code not in codes
    one = s.ok(w.rep.me.call("GET", f"{LOOK}/debtors-for-agent", params={"q": w.rep.customers[1].customer_code})).json()
    assert [d["customer_code"] for d in one] == [w.rep.customers[1].customer_code]
    assert s.ok(w.other.me.call("GET", f"{LOOK}/debtors-for-agent")).json() == s.ok(w.other.portal.call("GET", f"{LOOK}/debtors-for-agent")).json()


def test_p4_pt_item_combo_and_line_pricing_lookups_equal_the_portal(world):
    w = world
    items = s.ok(w.rep.me.call("GET", f"{LOOK}/price-tag-items", params={"q": w.product.product_code}))
    assert items.json() == s.ok(w.rep.portal.call("GET", f"{LOOK}/price-tag-items", params={"q": w.product.product_code})).json()
    assert any(i["id"] == w.product.id for i in items.json()), "the seeded product should be found"
    combos = s.ok(w.rep.me.call("GET", f"{LOOK}/product-combos/{w.product.id}"))
    assert combos.json() == s.ok(w.rep.portal.call("GET", f"{LOOK}/product-combos/{w.product.id}")).json()
    body = {"lines": [{"key": "k1", "product_id": w.product.id, "part_product_ids": [], "candidate_product_ids": []}]}
    price = s.ok(w.rep.me.call("POST", f"{LOOK}/line-pricing", json=body))
    assert price.json() == s.ok(w.rep.portal.call("POST", f"{LOOK}/line-pricing", json=body)).json() and price.json()


def test_p4_pt_foreign_row_answers_what_the_portal_answers(world):
    w = world
    foreign = create(w.other.portal, w)["id"]
    foreign_sub = submitted(w.other.portal, w)
    create(w.rep.me, w)  # own row: the route is known to be mounted
    calls = {
        "get": ("GET", f"{SUB}/{foreign}", None),
        "put": ("PUT", f"{SUB}/{foreign}", {"notes": "ZZT x"}),
        "delete": ("DELETE", f"{SUB}/{foreign}", None),
        "submit": ("POST", f"{SUB}/{foreign}/submit", None),
        "approve": ("POST", f"{SUB}/{foreign_sub}/approve", None),
        "changes": ("POST", f"{SUB}/{foreign_sub}/request-changes", {"note": "ZZT x"}),
        "comments": ("GET", f"{SUB}/{foreign_sub}/review-comments", None),
        "collect": ("POST", f"{SUB}/{foreign_sub}/collect", None),
    }
    for name, (method, path, body) in calls.items():
        kw = {"json": body} if body is not None else {}
        mine = w.rep.me.call(method, path, **kw)
        theirs = w.rep.portal.call(method, path, **kw)
        s.not_a_missing_route(mine)
        assert theirs.status_code == 404, (name, theirs.status_code)
        assert (mine.status_code, mine.content) == (theirs.status_code, theirs.content), name
    assert pt_row(w, foreign).notes == "ZZT note"


def test_p4_pt_impersonation_acts_as_the_salesperson(world):
    from app.models.impersonation import ImpersonationSession

    w = world
    admin = s.make_user(w.sc.db, roles=["admin"], name="ZZT Impersonating Admin")
    w.sc.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=w.rep.actor.id))
    w.sc.db.commit()
    api = s.my_api(w.sc, admin, **{s.IMPERSONATE_HEADER: w.rep.actor.id})
    rid = create(api, w)["id"]
    assert pt_row(w, rid).contact_id == w.rep.contact.id
    rows = w.sc.audit(rid)
    assert rows, "no audit rows for the create"
    assert all(a.user_id == w.rep.actor.id for a in rows if a.user_id)
    assert any(a.real_user_id == admin.id for a in rows)
    s.ok(api.call("POST", f"{SUB}/{rid}/submit"))
    assert pt_row(w, rid).portal_draft_at is None


def test_p4_pt_attachments_on_the_draft_match_the_portal(world, monkeypatch):
    import app.services.storage_router as sr
    from app.models.resources import AttachmentType
    from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE

    class _Backend:
        def upload_file(self, *args, **kwargs):
            key = args[1] if len(args) > 1 else kwargs.get("file_path")
            return key, f"https://cdn.test/{key}"

    monkeypatch.setattr(sr, "default_provider", lambda: "s3")
    monkeypatch.setattr(sr, "get_backend", lambda provider: _Backend())
    monkeypatch.setattr(sr, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    w = world
    w.sc.db.add(AttachmentType(id=s.uid(), code=PORTAL_ATTACHMENT_TYPE_CODE, type_name="Portal Submission",
                               allowed_extensions="jpg,jpeg,png,pdf", max_file_size_mb=10))
    w.sc.db.commit()
    out = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = create(api, w)["id"]
        up = api.call("POST", "/attachments", data={"kind": KIND, "submission_id": rid},
                      files={"file": ("zzt.pdf", b"%PDF-1.4 zzt", "application/pdf")})
        s.not_a_missing_route(up)
        listed = api.call("GET", "/attachments", params={"kind": KIND, "submission_id": rid})
        out[name] = (up.status_code, listed.status_code, len(listed.json()))
    assert out["me"] == out["portal"]
    assert out["me"][0] in (200, 201) and out["me"][2] == 1


# ------------------------------------------------------------------ gates


def test_p4_pt_gate_no_session_is_401(world):
    _mounted(world)
    assert s.Api(world.client, s.MY, {}).call("POST", SUB, json=world.body()).status_code == 401


def test_p4_pt_gate_no_linked_contact_is_403(world):
    w = world
    _mounted(w)
    loner = s.make_user(w.sc.db, perms=[PT_VIEW_OWN, PT_CREATE], name="ZZT Loner")
    for method, path in (("POST", SUB), ("GET", SUB), ("GET", f"{LOOK}/debtors-for-agent")):
        resp = s.my_api(w.sc, loner).call(method, path, **({"json": w.body()} if method == "POST" else {}))
        assert resp.status_code == 403, (path, resp.text)
        s.not_a_missing_route(resp)


def test_p4_pt_gate_staff_view_holder_is_403_even_with_a_contact(world):
    w = world
    _mounted(w)
    contact, _portal = s.own_contact(w.sc)
    staff = s.make_user(w.sc.db, perms=[PT_VIEW, PT_VIEW_OWN, PT_CREATE], contact=contact, name="ZZT Staff")
    api = s.my_api(w.sc, staff)
    for method, path in (("POST", SUB), ("GET", SUB), ("GET", f"{LOOK}/debtors-for-agent")):
        resp = api.call(method, path, **({"json": w.body()} if method == "POST" else {}))
        assert resp.status_code == 403, (path, resp.text)
        s.not_a_missing_route(resp)


def test_p4_pt_gate_create_needs_create_but_reading_own_works(world):
    w = world
    _mounted(w)
    contact, _portal = s.own_contact(w.sc)
    reader = s.make_user(w.sc.db, perms=[PT_VIEW_OWN], contact=contact, name="ZZT Reader")
    resp = s.my_api(w.sc, reader).call("POST", SUB, json=w.body())
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)


def test_p4_pt_bad_body_is_422(world):
    w = world
    _mounted(w)
    assert w.rep.me.call("POST", SUB, json={"lines": "nope"}).status_code == 422
    assert w.rep.me.call("POST", SUB, json={"promotion_id": "x"}).status_code == 422  # extra="forbid"
    assert w.rep.me.call("POST", SUB, json={"print_by": "nobody"}).status_code == 422
