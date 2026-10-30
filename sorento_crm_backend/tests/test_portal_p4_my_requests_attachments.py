"""PORTAL-P4-REQUESTS S-ATT red tests (UAC P4-16): a salesperson's attachments through /api/v1/my-requests.

Same rows as a portal upload for the same contact; the list shows staff and salesperson files; the
salesperson removes only their own file; a staff file is refused (403 STAFF_UPLOAD_LOCKED); a
foreign submission is refused as the portal refuses it. The my-requests attachment routes exist
since S0, so on the backend these are regression guards; P4_CONTROL=1 re-points them at the portal.
"""
from __future__ import annotations

import pytest

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType
from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE
from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

KINDS = ["stock_inquiry", "purchase_request", "sponsorship_form", "complaint"]
ENTITY = {"sponsorship_form": "purchase_request"}


class _Backend:
    def upload_file(self, *args, **kwargs):
        key = args[1] if len(args) > 1 else kwargs.get("file_path")
        return key, f"https://cdn.test/{key}"


@pytest.fixture(autouse=True)
def _storage(monkeypatch, scene):  # noqa: F811
    import app.services.storage_router as sr

    monkeypatch.setattr(sr, "default_provider", lambda: "s3")
    monkeypatch.setattr(sr, "get_backend", lambda provider: _Backend())
    monkeypatch.setattr(sr, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    scene.db.add(AttachmentType(id=s.uid(), code=PORTAL_ATTACHMENT_TYPE_CODE, type_name="Portal Submission",
                                allowed_extensions="jpg,jpeg,png,pdf", max_file_size_mb=10))
    scene.db.commit()


def _upload(api, kind, sid, name="zzt.pdf"):
    return api.call("POST", "/attachments", data={"kind": kind, "submission_id": sid},
                    files={"file": (name, b"%PDF-1.4 zzt", "application/pdf")})


def _list(api, kind, sid):
    return api.call("GET", "/attachments", params={"kind": kind, "submission_id": sid})


def _staff_file(sc, kind, sid):
    att = Attachment(id=s.uid(), original_filename="staff.pdf", stored_filename="staff.pdf",
                     file_path="https://cdn.test/staff.pdf", uploaded_by=sc.staff.id, uploader_kind="user")
    sc.db.add(att)
    sc.db.flush()
    link = EntityAttachmentLink(entity_type=ENTITY.get(kind, kind), entity_id=sid, attachment_id=att.id)
    sc.db.add(link)
    sc.db.commit()
    return str(link.id)


def _draft(sc, kind, api=None):
    spec = s.SPECS[kind]
    return s._id((api or sc.me).create(kind, spec.body(sc)))


def _rows(sc, kind, sid):
    sc.db.expire_all()
    links = sc.db.query(EntityAttachmentLink).filter(
        EntityAttachmentLink.entity_type == ENTITY.get(kind, kind), EntityAttachmentLink.entity_id == sid).all()
    return [(l, sc.db.query(Attachment).get(l.attachment_id)) for l in links]


@pytest.mark.parametrize("kind", KINDS)
def test_p4_16_upload_matches_a_portal_upload(scene, kind):
    mine, theirs = _draft(scene, kind), _draft(scene, kind, scene.portal)
    a, b = s.ok(_upload(scene.me, kind, mine)).json(), s.ok(_upload(scene.portal, kind, theirs)).json()
    assert set(a) == set(b) and a["filename"] == b["filename"] == "zzt.pdf"
    (_, att_a), (_, att_b) = _rows(scene, kind, mine)[0], _rows(scene, kind, theirs)[0]
    for col in ("uploader_kind", "uploaded_by_contact_id", "mime_type", "uploaded_by"):
        assert getattr(att_a, col) == getattr(att_b, col), col
    assert att_a.uploader_kind == "contact" and att_a.uploaded_by_contact_id == scene.contact.id


@pytest.mark.parametrize("kind", KINDS)
def test_p4_16_list_shows_staff_and_own_files(scene, kind):
    sid = _draft(scene, kind)
    s.ok(_upload(scene.me, kind, sid, "mine.pdf"))
    _staff_file(scene, kind, sid)
    items = s.ok(_list(scene.me, kind, sid)).json()["items"]
    assert len(items) == 2
    assert items == s.ok(_list(scene.portal, kind, sid)).json()["items"]


@pytest.mark.parametrize("kind", KINDS)
def test_p4_16_delete_own_upload_ok_staff_upload_refused(scene, kind):
    sid = _draft(scene, kind)
    own = s.ok(_upload(scene.me, kind, sid)).json()["link_id"]
    staff_link = _staff_file(scene, kind, sid)
    refused = scene.me.call("DELETE", f"/attachments/{staff_link}")
    s.not_a_missing_route(refused)
    assert refused.status_code == 403, refused.text
    assert "STAFF_UPLOAD_LOCKED" in refused.text or "added by our team" in refused.text
    s.ok(scene.me.call("DELETE", f"/attachments/{own}"))
    left = [l for l, _ in _rows(scene, kind, sid)]
    assert [str(l.id) for l in left] == [staff_link]


@pytest.mark.parametrize("kind", KINDS)
def test_p4_16_foreign_submission_refused_as_the_portal_refuses(scene, kind):
    other_c, other_api = s.own_contact(scene)
    foreign = s._id(other_api.create(kind, s.SPECS[kind].body(scene, contact=other_c)))
    theirs_up = _upload(scene.portal, kind, foreign)
    mine_up = _upload(scene.me, kind, foreign)
    s.not_a_missing_route(mine_up)
    assert mine_up.status_code == theirs_up.status_code and mine_up.status_code >= 400
    assert _rows(scene, kind, foreign) == []
    mine_ls, theirs_ls = _list(scene.me, kind, foreign), _list(scene.portal, kind, foreign)
    assert mine_ls.status_code == theirs_ls.status_code and mine_ls.status_code >= 400
    # Deleting a link on a foreign row.
    link = _staff_file(scene, kind, foreign)
    d_mine, d_theirs = scene.me.call("DELETE", f"/attachments/{link}"), scene.portal.call("DELETE", f"/attachments/{link}")
    assert d_mine.status_code == d_theirs.status_code and d_mine.status_code >= 400
    assert len(_rows(scene, kind, foreign)) == 1
