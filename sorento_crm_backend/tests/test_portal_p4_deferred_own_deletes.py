"""PORTAL-P4-REQUESTS D7 red tests: a salesperson's destructive actions on the CRM request pages
are server-deferred pending actions (owner direction, crew answer a85478781).

  my_request.delete                  delete a draft; hard-delete window (10s); entity_type = the kind
                                     (stock_inquiry, complaint, purchase_request, sponsorship_form,
                                     price_tag_request), entity_id = the request id
  my_request_attachment.unlink       remove the salesperson's own upload; reversible window (5s);
                                     entity_type = my_request_attachment, entity_id = the link id

What runs when the window lapses is the PORTAL's own delete, under the salesperson who parked it.
Refusals are the portal DELETE's own, at park time. Postgres only, every row seeded here.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.entity_attachment import EntityAttachmentLink
from app.models.impersonation import ImpersonationSession
from app.models.sla import SlaFormAction
from tests import _portal_p4_pt_support as pt
from tests import _portal_p4_support as s
from tests._portal_p4_pt_support import world  # noqa: F401  (fixture)
from tests._portal_p4_support import scene  # noqa: F401  (fixture)
from tests.test_portal_p4_my_requests_attachments import (  # noqa: F401  (autouse storage stub + helpers)
    _draft as _att_draft,
    _rows as _att_rows,
    _staff_file,
    _storage,
    _upload,
)

PENDING = "/api/v1/pending-actions"
DEL, UNLINK = "my_request.delete", "my_request_attachment.unlink"


def _park(client, headers, key, entity_type, entity_id):
    return client.post(PENDING, headers=headers, json={
        "action_key": key, "entity_type": entity_type, "entity_id": entity_id, "payload": {}})


def _known(r):
    """A refusal must come from the action's own gate, not from the registry not knowing the key."""
    s.not_a_missing_route(r)
    assert "Unknown action" not in r.text, r.text
    return r


def _lapse(db, action_id):
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False)
    db.commit()


def _settle(client, headers, entity_type, entity_id):
    r = client.get(f"{PENDING}/current", headers=headers, params={"entity_type": entity_type, "entity_id": entity_id})
    assert r.status_code == 200, r.text
    return r.json()


def _exists(sc, spec, sid):
    sc.db.expire_all()
    return sc.db.query(spec.model).filter(spec.model.id == sid).first() is not None


def _deletes(sc, sid):
    return [a for a in sc.audit(sid) if str(a.action).lower().startswith("delet")]


def _assert_impersonated_trace(rows, sp, admin):
    assert rows, "the hard delete wrote no audit_logs row"
    assert all(a.user_id == sp.id for a in rows), [a.user_id for a in rows]
    assert all(a.real_user_id == admin.id for a in rows), [a.real_user_id for a in rows]
    assert all(a.auth_method == "impersonation" for a in rows), [a.auth_method for a in rows]


def _assert_own_trace(rows, sp):
    assert rows, "the hard delete wrote no audit_logs row"
    assert all(a.user_id == sp.id for a in rows), [a.user_id for a in rows]
    assert all(a.real_user_id in (None, sp.id) for a in rows), [a.real_user_id for a in rows]
    assert all(a.auth_method != "impersonation" for a in rows), [a.auth_method for a in rows]


def _draft(sc, kind, api=None):
    return s._id((api or sc.me).create(kind, s.SPECS[kind].body(sc)))


# ----------------------------------------------------------------------------- my_request.delete


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_parks_then_commits_like_the_portal_delete(scene, kind):
    spec, sid = s.SPECS[kind], _draft(scene, kind)
    r = _park(scene.client, scene.sp.headers, DEL, kind, sid)
    s.not_a_missing_route(r)
    assert r.status_code == 202, r.text
    assert r.json()["window_seconds"] == 10
    assert _exists(scene, spec, sid), "the row must survive the window"

    _lapse(scene.db, r.json()["id"])
    out = _settle(scene.client, scene.sp.headers, kind, sid)
    assert out["last_outcome"]["status"] == "committed", out
    assert not _exists(scene, spec, sid)
    _assert_own_trace(_deletes(scene, sid), scene.sp)
    # the control: the portal's own delete leaves the same trace (gone row, 204)
    ctl = _draft(scene, kind, scene.portal)
    assert scene.portal.delete(kind, ctl).status_code == 204
    assert not _exists(scene, spec, ctl)


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_cancel_within_the_window_leaves_the_row(scene, kind):
    spec, sid = s.SPECS[kind], _draft(scene, kind)
    r = _park(scene.client, scene.sp.headers, DEL, kind, sid)
    assert r.status_code == 202, r.text
    c = scene.client.post(f"{PENDING}/{r.json()['id']}/cancel", headers=scene.sp.headers)
    assert c.status_code == 200, c.text
    assert _exists(scene, spec, sid)
    assert _settle(scene.client, scene.sp.headers, kind, sid)["pending"] is None


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_refuses_a_submitted_row_as_the_portal_does(scene, kind):
    spec = s.SPECS[kind]
    mine, theirs = _draft(scene, kind), _draft(scene, kind, scene.portal)
    s.ok(scene.me.submit(kind, mine))
    s.ok(scene.portal.submit(kind, theirs))
    portal = scene.portal.delete(kind, theirs)
    assert portal.status_code >= 400
    r = _park(scene.client, scene.sp.headers, DEL, kind, mine)
    _known(r)
    assert r.status_code == portal.status_code, (r.status_code, r.text, portal.text)
    assert _exists(scene, spec, mine)
    assert _settle(scene.client, scene.sp.headers, kind, mine)["pending"] is None


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_refuses_a_foreign_row_as_the_portal_does(scene, kind):
    spec = s.SPECS[kind]
    other_c, other_api = s.own_contact(scene)
    foreign = s._id(other_api.create(kind, spec.body(scene, contact=other_c)))
    portal = scene.portal.delete(kind, foreign)
    assert portal.status_code >= 400
    r = _park(scene.client, scene.sp.headers, DEL, kind, foreign)
    _known(r)
    assert r.status_code == portal.status_code, (r.status_code, r.text, portal.text)
    assert _exists(scene, spec, foreign)


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_refuses_a_staff_view_holder(scene, kind):
    spec = s.SPECS[kind]
    c, portal = s.own_contact(scene)
    staff = s.make_user(scene.db, perms=[spec.view, spec.view_own, spec.add], contact=c, name="ZZT Staff")
    sid = s.ok(portal.create(kind, spec.body(scene, contact=c))).json()["id"]
    r = _park(scene.client, staff.headers, DEL, kind, sid)
    _known(r)
    assert r.status_code == 403, r.text  # as /my-requests DELETE refuses a `.view` holder
    assert _exists(scene, spec, sid)


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_as_an_impersonating_admin_is_the_salespersons(scene, kind):
    spec, sid = s.SPECS[kind], _draft(scene, kind)
    admin = s.make_user(scene.db, roles=["admin"], name="ZZT Impersonating Admin")
    scene.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=scene.sp.id))
    scene.db.commit()
    headers = {**admin.headers, s.IMPERSONATE_HEADER: scene.sp.id}
    r = _park(scene.client, headers, DEL, kind, sid)
    assert r.status_code == 202, r.text
    scene.db.expire_all()
    row = scene.db.query(SlaFormAction).filter(SlaFormAction.id == r.json()["id"]).one()
    assert row.requested_by_id == scene.sp.id, "the actor is the salesperson, not the admin"
    _lapse(scene.db, row.id)
    assert _settle(scene.client, scene.sp.headers, kind, sid)["last_outcome"]["status"] == "committed"
    assert not _exists(scene, spec, sid)
    _assert_impersonated_trace(_deletes(scene, sid), scene.sp, admin)


def test_my_request_delete_price_tag_request_parks_commits_cancels_and_refuses(world):
    w, rep = world, world.rep
    h = rep.actor.headers

    def exists(rid):
        w.sc.db.expire_all()
        from app.models.price_tag import PriceTagRequest
        return w.sc.db.query(PriceTagRequest).filter(PriceTagRequest.id == rid).first() is not None

    rid = pt.create(rep.me, w)["id"]
    r = _park(w.client, h, DEL, pt.KIND, rid)
    s.not_a_missing_route(r)
    assert r.status_code == 202 and r.json()["window_seconds"] == 10, r.text
    assert exists(rid)
    _lapse(w.sc.db, r.json()["id"])
    assert _settle(w.client, h, pt.KIND, rid)["last_outcome"]["status"] == "committed"
    assert not exists(rid)

    kept = pt.create(rep.me, w)["id"]
    p = _park(w.client, h, DEL, pt.KIND, kept)
    assert w.client.post(f"{PENDING}/{p.json()['id']}/cancel", headers=h).status_code == 200
    assert exists(kept)

    sent = pt.submitted(rep.me, w)
    portal = rep.portal.call("DELETE", f"{pt.SUB}/{sent}")
    assert portal.status_code >= 400
    assert _known(_park(w.client, h, DEL, pt.KIND, sent)).status_code == portal.status_code
    assert exists(sent)

    foreign = pt.create(w.other.portal, w)["id"]  # another salesperson's draft
    portal = rep.portal.call("DELETE", f"{pt.SUB}/{foreign}")
    assert portal.status_code >= 400
    assert _known(_park(w.client, h, DEL, pt.KIND, foreign)).status_code == portal.status_code
    assert exists(foreign)
    # a `.view` holder with their own contact (users.respond_contact_id is unique) owning a draft
    viewer = w.person("PT Staff", perms=[pt.PT_VIEW, pt.PT_VIEW_OWN, pt.PT_CREATE])
    mine = pt.create(viewer.portal, w)["id"]
    assert _known(_park(w.client, viewer.actor.headers, DEL, pt.KIND, mine)).status_code == 403
    assert exists(mine)


# ----------------------------------------------------------------------------- my_request_attachment.unlink

ATT_KINDS = ["stock_inquiry", "purchase_request", "sponsorship_form", "complaint"]


def _link_exists(sc, kind, sid, link_id):
    return any(str(l.id) == link_id for l, _ in _att_rows(sc, kind, sid))


@pytest.mark.parametrize("kind", ATT_KINDS)
def test_attachment_unlink_own_upload_is_removed_after_the_window(scene, kind):
    sid = _att_draft(scene, kind)
    link = s.ok(_upload(scene.me, kind, sid)).json()["link_id"]
    r = _park(scene.client, scene.sp.headers, UNLINK, "my_request_attachment", link)
    s.not_a_missing_route(r)
    assert r.status_code == 202, r.text
    assert r.json()["window_seconds"] == 5
    assert _link_exists(scene, kind, sid, link)
    _lapse(scene.db, r.json()["id"])
    assert _settle(scene.client, scene.sp.headers, "my_request_attachment", link)["last_outcome"]["status"] == "committed"
    assert not _link_exists(scene, kind, sid, link)
    _assert_own_trace(_deletes(scene, link), scene.sp)


@pytest.mark.parametrize("kind", ATT_KINDS)
def test_attachment_unlink_staff_upload_is_refused_locked(scene, kind):
    sid = _att_draft(scene, kind)
    staff_link = _staff_file(scene, kind, sid)
    r = _park(scene.client, scene.sp.headers, UNLINK, "my_request_attachment", staff_link)
    _known(r)
    assert r.status_code == 403, r.text
    assert "STAFF_UPLOAD_LOCKED" in r.text or "added by our team" in r.text
    assert _link_exists(scene, kind, sid, staff_link)


@pytest.mark.parametrize("kind", ATT_KINDS)
def test_attachment_unlink_cancel_keeps_the_file(scene, kind):
    sid = _att_draft(scene, kind)
    link = s.ok(_upload(scene.me, kind, sid)).json()["link_id"]
    r = _park(scene.client, scene.sp.headers, UNLINK, "my_request_attachment", link)
    assert r.status_code == 202, r.text
    assert scene.client.post(f"{PENDING}/{r.json()['id']}/cancel", headers=scene.sp.headers).status_code == 200
    assert _link_exists(scene, kind, sid, link)


def test_attachment_unlink_foreign_submission_refused_as_the_portal_refuses(scene):
    kind = "stock_inquiry"
    other_c, other_api = s.own_contact(scene)
    foreign = s._id(other_api.create(kind, s.SPECS[kind].body(scene, contact=other_c)))
    link = s.ok(_upload(other_api, kind, foreign)).json()["link_id"]
    portal = scene.portal.call("DELETE", f"/attachments/{link}")
    assert portal.status_code >= 400
    r = _park(scene.client, scene.sp.headers, UNLINK, "my_request_attachment", link)
    _known(r)
    assert r.status_code == portal.status_code, (r.status_code, r.text, portal.text)
    assert _link_exists(scene, kind, foreign, link)


def test_attachment_unlink_as_an_impersonating_admin_is_the_salespersons(scene):
    kind = "stock_inquiry"
    sid = _att_draft(scene, kind)
    link = s.ok(_upload(scene.me, kind, sid)).json()["link_id"]
    admin = s.make_user(scene.db, roles=["admin"], name="ZZT Impersonating Admin")
    scene.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=scene.sp.id))
    scene.db.commit()
    r = _park(scene.client, {**admin.headers, s.IMPERSONATE_HEADER: scene.sp.id},
              UNLINK, "my_request_attachment", link)
    assert r.status_code == 202, r.text
    scene.db.expire_all()
    row = scene.db.query(SlaFormAction).filter(SlaFormAction.id == r.json()["id"]).one()
    assert row.requested_by_id == scene.sp.id
    _lapse(scene.db, row.id)
    assert _settle(scene.client, scene.sp.headers, "my_request_attachment", link)["last_outcome"]["status"] == "committed"
    assert not _link_exists(scene, kind, sid, link)
    _assert_impersonated_trace(_deletes(scene, link), scene.sp, admin)


# ----------------------------------------------------------------------------- unlink: the other two kinds

from types import SimpleNamespace  # noqa: E402

from app.models.user import User  # noqa: E402

NPA_PT_KINDS = ["new_product_application", "price_tag_request"]


@pytest.fixture(params=NPA_PT_KINDS)
def req(request, scene):  # noqa: F811
    """One salesperson world per kind (NPA and price tag keep their own seeding), as a flat handle."""
    kind = request.param
    if kind == "new_product_application":
        from tests import _portal_p4_npa_support as m

        w = m.World(sc=scene, rep=None, other=None, company_id=s.SORENTO)
    else:
        from tests import _portal_p4_pt_support as m

        w = m.World(sc=scene, rep=None, other=None, product=m._ptag_r9_seed.seed_product(scene.db),
                    company_id=s.SORENTO)
        scene.db.flush()
    w.rep = w.person("Rep")
    w.other = w.person("Other")
    scene.db.commit()
    return SimpleNamespace(
        kind=kind, w=w, rep=w.rep, headers=w.rep.actor.headers,
        make=lambda api=None: m.create(api or w.rep.me, w)["id"],
        submit=lambda sid: s.ok(w.rep.me.call("POST", f"/submissions/{kind}/{sid}/submit")),
    )


def _up(req, sid):
    return s.ok(_upload(req.rep.me, req.kind, sid)).json()["link_id"]


def test_attachment_unlink_npa_and_price_tag_own_upload_is_removed_after_the_window(req):
    sc = req.w.sc
    sid = req.make()
    link = _up(req, sid)
    r = _park(sc.client, req.headers, UNLINK, "my_request_attachment", link)
    s.not_a_missing_route(r)
    assert r.status_code == 202, r.text
    assert r.json()["window_seconds"] == 5
    assert _link_exists(sc, req.kind, sid, link)
    _lapse(sc.db, r.json()["id"])
    assert _settle(sc.client, req.headers, "my_request_attachment", link)["last_outcome"]["status"] == "committed"
    assert not _link_exists(sc, req.kind, sid, link)
    _assert_own_trace(_deletes(sc, link), req.rep.actor)


def test_attachment_unlink_npa_and_price_tag_staff_upload_is_refused_locked(req):
    sc = req.w.sc
    sid = req.make()
    staff_link = _staff_file(sc, req.kind, sid)
    r = _park(sc.client, req.headers, UNLINK, "my_request_attachment", staff_link)
    _known(r)
    assert r.status_code == 403, r.text
    assert "STAFF_UPLOAD_LOCKED" in r.text or "added by our team" in r.text
    assert _link_exists(sc, req.kind, sid, staff_link)


def test_attachment_unlink_npa_and_price_tag_cancel_keeps_the_file(req):
    sc = req.w.sc
    sid = req.make()
    link = _up(req, sid)
    r = _park(sc.client, req.headers, UNLINK, "my_request_attachment", link)
    assert r.status_code == 202, r.text
    assert sc.client.post(f"{PENDING}/{r.json()['id']}/cancel", headers=req.headers).status_code == 200
    assert _link_exists(sc, req.kind, sid, link)


def test_attachment_unlink_npa_and_price_tag_foreign_row_refused_as_the_portal_refuses(req):
    sc = req.w.sc
    foreign = req.make(req.w.other.portal)
    link = s.ok(_upload(req.w.other.portal, req.kind, foreign)).json()["link_id"]
    portal = req.rep.portal.call("DELETE", f"/attachments/{link}")
    assert portal.status_code >= 400
    r = _park(sc.client, req.headers, UNLINK, "my_request_attachment", link)
    _known(r)
    assert r.status_code == portal.status_code, (r.status_code, r.text, portal.text)
    assert _link_exists(sc, req.kind, foreign, link)


# ----------------------------------------------------------------------------- commit re-checks the gates


def _assert_commit_refused(client, headers, entity_type, entity_id):
    out = _settle(client, headers, entity_type, entity_id)
    assert out["pending"] is None, out
    assert out["last_outcome"] is not None, "the lapsed action left no outcome"
    assert out["last_outcome"]["status"] != "committed", out


@pytest.mark.parametrize("kind", s.KINDS)
def test_my_request_delete_commit_refuses_when_the_draft_was_submitted_inside_the_window(scene, kind):
    spec, sid = s.SPECS[kind], _draft(scene, kind)
    r = _park(scene.client, scene.sp.headers, DEL, kind, sid)
    assert r.status_code == 202, r.text
    s.ok(scene.me.submit(kind, sid))
    _lapse(scene.db, r.json()["id"])
    _assert_commit_refused(scene.client, scene.sp.headers, kind, sid)
    assert _exists(scene, spec, sid), "a submitted request must survive a delete parked while it was a draft"


def test_my_request_delete_price_tag_commit_refuses_when_submitted_inside_the_window(world):
    w, rep = world, world.rep
    rid = pt.create(rep.me, w)["id"]
    r = _park(w.client, rep.actor.headers, DEL, pt.KIND, rid)
    assert r.status_code == 202, r.text
    s.ok(rep.me.call("POST", f"{pt.SUB}/{rid}/submit"))
    _lapse(w.sc.db, r.json()["id"])
    _assert_commit_refused(w.client, rep.actor.headers, pt.KIND, rid)
    assert pt.pt_row(w, rid) is not None, "the submitted price tag request must survive"


def test_my_request_delete_price_tag_commit_refuses_when_the_user_lost_their_contact_inside_the_window(world):
    w, rep = world, world.rep
    rid = pt.create(rep.me, w)["id"]
    r = _park(w.client, rep.actor.headers, DEL, pt.KIND, rid)
    assert r.status_code == 202, r.text
    w.sc.db.query(User).filter(User.id == rep.actor.id).update({"respond_contact_id": None}, synchronize_session=False)
    w.sc.db.commit()
    _lapse(w.sc.db, r.json()["id"])
    _assert_commit_refused(w.client, rep.actor.headers, pt.KIND, rid)
    assert pt.pt_row(w, rid) is not None


def test_attachment_unlink_commit_refuses_when_the_parent_stopped_being_editable_inside_the_window(req):
    sc = req.w.sc
    sid = req.make()
    link = _up(req, sid)
    r = _park(sc.client, req.headers, UNLINK, "my_request_attachment", link)
    assert r.status_code == 202, r.text
    req.submit(sid)
    _lapse(sc.db, r.json()["id"])
    _assert_commit_refused(sc.client, req.headers, "my_request_attachment", link)
    assert _link_exists(sc, req.kind, sid, link), "a file on a submitted request must survive"


def test_attachment_unlink_commit_refuses_when_the_user_lost_their_contact_inside_the_window(scene):
    kind = "stock_inquiry"
    sid = _att_draft(scene, kind)
    link = s.ok(_upload(scene.me, kind, sid)).json()["link_id"]
    r = _park(scene.client, scene.sp.headers, UNLINK, "my_request_attachment", link)
    assert r.status_code == 202, r.text
    scene.db.query(User).filter(User.id == scene.sp.id).update({"respond_contact_id": None}, synchronize_session=False)
    scene.db.commit()
    _lapse(scene.db, r.json()["id"])
    _assert_commit_refused(scene.client, scene.sp.headers, "my_request_attachment", link)
    assert _link_exists(scene, kind, sid, link)
