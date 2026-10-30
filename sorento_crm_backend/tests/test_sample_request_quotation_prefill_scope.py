"""SAMPLE-FROM-QUOTE security fix B1 / N1, red-first.

A salesperson limited to their own projects reads the pre-fill through /api/v1/my-requests (the
shared portal route). It must give them their own projects only, as the staff route does
(SFQ-10), and the read needs the create slug like the staff route.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from tests import _portal_p4_support as s
from tests._portal_p4_sr_so_support import REP_PERMS, SR_VIEW_OWN, scene, world  # noqa: F401
from tests._sample_request_seed import make_project
from tests.test_sample_request_quotation_prefill import _document, _line

PREFILL = "/sample-request/quotation-prefill"
LIMITED = REP_PERMS + ["projects.projects.view_own"]


def _quoted_project(w, owner_id):
    db = w.sc.db
    project = make_project(db, w.company_id, owner_id)
    q = _document(db, project, owner_id)
    _line(db, q.scopes[0].v1, product=w.product)
    db.commit()
    return project, q.doc


def test_b1_limited_rep_cannot_read_another_owners_project(world):
    w = world
    owner = s.make_user(w.sc.db, perms=["projects.projects.view"], name="ZZT foreign owner")
    rep = w.person("Limited", perms=LIMITED)
    project, _ = _quoted_project(w, owner.id)

    res = rep.me.call("GET", PREFILL, params={"project_id": project.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_PROJECT_NOT_ALLOWED"


def test_b1_limited_rep_reads_their_own_project(world):
    w = world
    rep = w.person("Limited", perms=LIMITED)
    project, _ = _quoted_project(w, rep.actor.id)

    res = rep.me.call("GET", PREFILL, params={"project_id": project.id})
    assert res.status_code == 200, res.text
    assert [line["product_id"] for line in res.json()["lines"]] == [w.product.id]


def test_b1_limited_rep_cannot_record_another_owners_quotation(world):
    w = world
    owner = s.make_user(w.sc.db, perms=["projects.projects.view"], name="ZZT foreign owner")
    rep = w.person("Limited", perms=LIMITED)
    project, doc = _quoted_project(w, owner.id)

    res = rep.me.call(
        "POST",
        "/submissions/sample_request",
        json=w.sr_body(project_id=project.id, project_title=None, quotation_document_id=doc.id),
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_PROJECT_NOT_ALLOWED"


def test_b1_limited_rep_cannot_record_another_owners_quotation_by_update(world):
    """A plain draft on another owner's project is allowed (the company-wide portal rule); recording
    that project's quotation on it later is not (re-review K6)."""
    w = world
    owner = s.make_user(w.sc.db, perms=["projects.projects.view"], name="ZZT foreign owner")
    rep = w.person("Limited", perms=LIMITED)
    project, doc = _quoted_project(w, owner.id)
    created = rep.me.call(
        "POST", "/submissions/sample_request", json=w.sr_body(project_id=project.id, project_title=None)
    )
    assert created.status_code == 201, created.text

    res = rep.me.call(
        "PUT",
        f"/submissions/sample_request/{created.json()['id']}",
        json={"quotation_document_id": doc.id},
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_PROJECT_NOT_ALLOWED"


def test_k12_limited_rep_cannot_search_another_owners_quotation(world):
    """Re-review K12: the product search names a quotation only of the rep's own projects."""
    w = world
    owner = s.make_user(w.sc.db, perms=["projects.projects.view"], name="ZZT foreign owner")
    rep = w.person("Limited", perms=LIMITED)
    _, doc = _quoted_project(w, owner.id)

    res = rep.me.call("GET", "/sample-request/products", params={"q": "", "quotation_document_id": doc.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_PROJECT_NOT_ALLOWED"


def test_n1_my_requests_read_needs_create(world):
    w = world
    viewer = w.person("Viewer", perms=[SR_VIEW_OWN, "projects.projects.view_own"])
    project, _ = _quoted_project(w, viewer.actor.id)

    res = viewer.me.call("GET", PREFILL, params={"project_id": project.id})
    assert res.status_code == 403, res.text
