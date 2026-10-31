"""PORTAL-P4-REQUESTS security-review fixes: red tests.

1. Upload kind mismatch: the gate reads path/query `kind` first, the upload acts on the FORM `kind`.
2. An impersonated comment records the impersonating admin (author_user_id).
3. Module gating per kind (complaints -> `complaints`, stock inquiry -> `procurement`,
   price tag -> `dealer_kit`), as the staff routers are mounted.
"""
from __future__ import annotations

import pytest

from app.models.app_modules import AppModuleCatalog, TenantModule
from app.models.entity_attachment import EntityAttachmentLink
from app.models.impersonation import ImpersonationSession
from app.models.resources import Attachment, AttachmentType
from app.modules.runtime.installer import DEFAULT_TENANT_ID
from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE
from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

SI, CO = s.SPECS["stock_inquiry"], s.SPECS["complaint"]


class _Backend:
    def upload_file(self, *args, **kwargs):
        key = args[1] if len(args) > 1 else kwargs.get("file_path")
        return key, f"https://cdn.test/{key}"


@pytest.fixture
def storage(monkeypatch, scene):  # noqa: F811
    import app.services.storage_router as sr

    monkeypatch.setattr(sr, "default_provider", lambda: "s3")
    monkeypatch.setattr(sr, "get_backend", lambda provider: _Backend())
    monkeypatch.setattr(sr, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    scene.db.add(AttachmentType(id=s.uid(), code=PORTAL_ATTACHMENT_TYPE_CODE, type_name="Portal Submission",
                                allowed_extensions="jpg,jpeg,png,pdf", max_file_size_mb=10))
    scene.db.commit()


def _only_si_salesperson(sc):
    """A salesperson holding ONLY the stock inquiry view_own, linked to the scene's contact."""
    other_contact = sc.other_contact
    return s.make_user(sc.db, perms=[SI.view_own, SI.add], contact=other_contact, name="ZZT SI only")


def _complaint_of(sc, actor):
    """A complaint owned by `actor`'s contact, created by a full-access salesperson (the portal)."""
    return s._id(sc.other_portal.create("complaint", CO.body(sc, contact=sc.other_contact)))


def _upload(api, sid, *, query_kind=None, form_kind):
    return api.call("POST", "/attachments", params={"kind": query_kind} if query_kind else None,
                    data={"kind": form_kind, "submission_id": sid},
                    files={"file": ("zzt.pdf", b"%PDF-1.4 zzt", "application/pdf")})


def _link_count(sc, sid):
    sc.db.expire_all()
    return sc.db.query(EntityAttachmentLink).filter(EntityAttachmentLink.entity_id == sid).count()


# ---------------------------------------------------------------- 1. upload kind mismatch

def test_sec_upload_query_kind_held_form_kind_not_held_is_422_and_writes_nothing(scene, storage):
    me = _only_si_salesperson(scene)
    sid = _complaint_of(scene, me)
    api = s.my_api(scene, me)
    r = _upload(api, sid, query_kind="stock_inquiry", form_kind="complaint")
    assert r.status_code == 422, (r.status_code, r.text)
    assert _link_count(scene, sid) == 0


def test_sec_upload_form_kind_not_held_is_403(scene, storage):
    me = _only_si_salesperson(scene)
    sid = _complaint_of(scene, me)
    r = _upload(s.my_api(scene, me), sid, form_kind="complaint")
    assert r.status_code == 403, (r.status_code, r.text)
    assert _link_count(scene, sid) == 0


def test_sec_upload_matching_kind_still_works(scene, storage):
    me = _only_si_salesperson(scene)
    api = s.my_api(scene, me)
    sid = s._id(api.create("stock_inquiry", SI.body(scene, contact=scene.other_contact)))
    r = _upload(api, sid, query_kind="stock_inquiry", form_kind="stock_inquiry")
    assert r.status_code == 200, (r.status_code, r.text)  # the portal upload answers 200
    assert _link_count(scene, sid) == 1


# ---------------------------------------------------------------- 2. impersonated comment

def _comment_author_user_ids(sc, sid):
    from app.models.entity_conversation import EntityConversationMessage  # noqa: F401

    sc.db.expire_all()
    rows = sc.db.query(EntityConversationMessage).filter(EntityConversationMessage.entity_id == sid).all()
    return [r.author_user_id for r in rows]


def test_sec_impersonated_comment_records_the_admin(scene):
    sid = s._id(scene.me.create("stock_inquiry", SI.body(scene)))
    s.ok(scene.me.submit("stock_inquiry", sid))
    admin = s.make_user(scene.db, roles=["admin"], name="ZZT Impersonating Admin")
    scene.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=scene.sp.id))
    scene.db.commit()
    api = s.my_api(scene, admin, **{s.IMPERSONATE_HEADER: scene.sp.id})
    s.ok(api.comment("stock_inquiry", sid, "ZZT as admin"), 201)
    assert _comment_author_user_ids(scene, sid) == [admin.id]


def test_sec_plain_salesperson_comment_keeps_author_user_none(scene):
    sid = s._id(scene.me.create("stock_inquiry", SI.body(scene)))
    s.ok(scene.me.submit("stock_inquiry", sid))
    s.ok(scene.me.comment("stock_inquiry", sid, "ZZT plain"), 201)
    assert _comment_author_user_ids(scene, sid) == [None]


# ---------------------------------------------------------------- 3. module gating per kind

def _modules(db, enabled: dict):
    for key, on in enabled.items():
        if not db.query(AppModuleCatalog).filter(AppModuleCatalog.module_key == key).first():
            db.add(AppModuleCatalog(id=s.uid(), module_key=key, display_name=key, dependencies=[]))
            db.flush()
        db.add(TenantModule(id=s.uid(), tenant_id=DEFAULT_TENANT_ID, module_key=key, enabled=on))
    db.commit()


def test_sec_complaints_module_off_refuses_complaint_but_not_stock_inquiry(scene, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "module_guard_strict", True)
    _modules(scene.db, {"complaints": False, "procurement": True})
    r = scene.me.create("complaint", CO.body(scene))
    assert r.status_code == 403, (r.status_code, r.text)
    assert scene.db.query(CO.model).filter(CO.model.contact_id == scene.contact.id).count() == 0
    s.ok(scene.me.create("stock_inquiry", SI.body(scene)))


def test_sec_dealer_kit_off_refuses_price_tag_routes(scene, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "module_guard_strict", True)
    pt = s.make_user(scene.db, perms=["dealer_kit.price_tag_requests.view_own",
                                      "dealer_kit.price_tag_requests.create"],
                     contact=scene.other_contact, name="ZZT PT")
    _modules(scene.db, {"dealer_kit": False, "procurement": True})
    api = s.my_api(scene, pt)
    r = api.call("GET", "/submissions/price_tag_request")
    assert r.status_code == 403, (r.status_code, r.text)
    r = api.call("POST", "/submissions/price_tag_request", json={})
    assert r.status_code == 403, (r.status_code, r.text)


# ---------------------------------------------------------------- 4. write-route classification guard

#: Every write route under /api/v1/my-requests -> the extra write slug it needs, or None for
#: "view_own only" (what the portal allows: draft save, submit, comments, attachments ...).
WRITE_ROUTES = {
    # portal parity: POST /ai-extract on public/ai_extract.py, view_own only, no extra write slug
    ("POST", "/ai-extract"): None,
    ("POST", "/attachments"): None,
    ("DELETE", "/attachments/{link_id}"): None,
    ("POST", "/lookups/line-pricing"): None,
    ("POST", "/sales-opportunities"): "sales.opportunities.add",
    ("PATCH", "/sales-opportunities/{opportunity_id}"): "sales.opportunities.edit",
    ("POST", "/submissions/new_product_application"): "procurement.new_product_applications.create",
    ("PUT", "/submissions/new_product_application/{application_id}"): None,
    ("POST", "/submissions/new_product_application/{application_id}/cancel"): None,
    ("POST", "/submissions/new_product_application/{application_id}/revise"): None,
    ("POST", "/submissions/new_product_application/{application_id}/submit"): None,
    ("POST", "/submissions/price_tag_request"): "dealer_kit.price_tag_requests.create",
    ("DELETE", "/submissions/price_tag_request/{request_id}"): None,
    ("PUT", "/submissions/price_tag_request/{request_id}"): None,
    ("POST", "/submissions/price_tag_request/{request_id}/approve"): None,
    ("POST", "/submissions/price_tag_request/{request_id}/collect"): None,
    ("POST", "/submissions/price_tag_request/{request_id}/export"): None,
    ("POST", "/submissions/price_tag_request/{request_id}/request-changes"): None,
    ("POST", "/submissions/price_tag_request/{request_id}/submit"): None,
    ("POST", "/submissions/sample_request"): "projects.sample_requests.create",
    ("PUT", "/submissions/sample_request/{request_id}"): None,
    ("POST", "/submissions/sample_request/{request_id}/cancel"): None,
    ("POST", "/submissions/sample_request/{request_id}/submit"): None,
    ("POST", "/submissions/{kind}"): "<kind>.add",
    ("DELETE", "/submissions/{kind}/{submission_id}"): None,
    ("PUT", "/submissions/{kind}/{submission_id}"): None,
    ("POST", "/submissions/{kind}/{submission_id}/comments"): None,
    ("DELETE", "/submissions/{kind}/{submission_id}/comments/{comment_id}"): None,
    ("PATCH", "/submissions/{kind}/{submission_id}/comments/{comment_id}"): None,
    ("POST", "/submissions/{kind}/{submission_id}/revise"): None,
    ("DELETE", "/submissions/{kind}/{submission_id}/revision-draft"): None,
    ("PUT", "/submissions/{kind}/{submission_id}/revision-draft"): None,
    ("POST", "/submissions/{kind}/{submission_id}/submit"): None,
}

#: The reads that need an extra write slug besides view_own. The quotation pre-fill (#1985) reads
#: a quotation of the caller's own project for a NEW request, so it needs the create slug, as the
#: staff route does (its own-project scope: tests/test_sample_request_quotation_prefill_scope.py).
READ_ROUTES_WITH_WRITE_SLUG = {
    ("GET", "/sample-request/quotation-prefill"): "projects.sample_requests.create",
}


def test_sec_every_my_requests_write_route_is_classified():
    from fastapi.routing import APIRoute

    from app.api.v1 import my_requests
    from app.main import app

    base = "/api/v1/my-requests"
    mounted = {
        (m, r.path_format[len(base):])
        for r in app.routes
        if isinstance(r, APIRoute) and r.path_format.startswith(base)
        for m in r.methods - {"GET", "HEAD", "OPTIONS"}
    }
    assert mounted - set(WRITE_ROUTES) == set(), f"unclassified write routes: {sorted(mounted - set(WRITE_ROUTES))}"
    assert set(WRITE_ROUTES) - mounted == set(), f"classified but gone: {sorted(set(WRITE_ROUTES) - mounted)}"
    reads = {
        (m, r.path_format[len(base):])
        for r in app.routes
        if isinstance(r, APIRoute) and r.path_format.startswith(base)
        for m in r.methods & {"GET"}
    }
    assert set(READ_ROUTES_WITH_WRITE_SLUG) <= reads, sorted(set(READ_ROUTES_WITH_WRITE_SLUG) - reads)
    # the extra write slugs the guard module enforces agree with the table
    required = {k: v for k, v in WRITE_ROUTES.items() if v and not v.startswith("<")}
    assert required == {k: v for k, v in my_requests._WRITE_SLUGS.items() if k in required}
    assert {k: v for k, v in my_requests._WRITE_SLUGS.items() if k[0] == "GET"} == READ_ROUTES_WITH_WRITE_SLUG
    assert set(my_requests._WRITE_SLUGS) <= set(WRITE_ROUTES) | set(READ_ROUTES_WITH_WRITE_SLUG)
