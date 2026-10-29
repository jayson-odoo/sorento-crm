"""SAMPLE-FROM-QUOTE, red-first. Every test cites its UAC id.

UAC: documentation/plans/project-sales/sample-from-quote-29oct-acceptance-criteria.md.
Quotations are built through the quotation services (document, scope, version 1) and the
lines / later versions / issues are added as rows, so each test states exactly the shape it
reads. Postgres only (tests/_pg_fixture.py); the `world` and `portal` fixtures are the SR-CORE
suites' own.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._sample_request_seed import BASE, full_payload, make_product, make_project
from .test_portal_sample_request import _as, portal  # noqa: F401  (fixture)
from .test_sample_requests_core import SR, world  # noqa: F401  (fixture)

PORTAL_PREFILL = "/api/v1/public/portal/sample-request/quotation-prefill"


def _prefill_url(project_id: str) -> str:
    return f"{BASE}/projects/{project_id}/sample-requests/quotation-prefill"


# ------------------------------------------------------------------ builders


def _document(db, project, actor, scopes=("Units",)):
    """A never-issued document with one scope per label, each at version 1."""
    from app.services import project_quotation_document_service as documents
    from app.services import project_quotation_service as quotations

    doc = documents.create_document(db, project=project, actor_user_id=actor)
    out = []
    for order, label in enumerate(scopes):
        q = quotations.create_quotation(
            db,
            project=project,
            actor_user_id=actor,
            payload={"scope_label": label},
            document_id=doc.id,
        )
        q.sort_order = order
        out.append(SimpleNamespace(scope=q, v1=quotations.current_version(db, q.id)))
    db.flush()
    return SimpleNamespace(doc=doc, scopes=out)


def _line(db, version, *, product=None, parts=None, desc=None, order=0):
    from app.models.projects import ProjectQuotationLine

    row = ProjectQuotationLine(
        company_id=version.company_id,
        version_id=version.id,
        product_id=product.id if product is not None else None,
        set_parts_snapshot=(
            [
                {
                    "product_id": p.id,
                    "product_code": p.product_code,
                    "description": p.product_name,
                    "quantity": "1",
                    "is_driver": i == 0,
                }
                for i, p in enumerate(parts)
            ]
            if parts
            else None
        ),
        product_code_snapshot=product.product_code if product is not None else None,
        description_snapshot=desc,
        unit_price=123,
        quantity=40,
        sort_order=order,
    )
    db.add(row)
    db.flush()
    return row


def _next_version(db, scope, version_no):
    from app.models.projects import ProjectQuotationVersion

    v = ProjectQuotationVersion(
        company_id=scope.company_id, quotation_id=scope.id, version_no=version_no
    )
    db.add(v)
    db.flush()
    return v


def _issue(db, doc, issue_no, pairs, when=None):
    """An issue holding the given (scope, version) pairs."""
    from app.models.projects import ProjectQuotationIssue, ProjectQuotationIssueScope

    issue = ProjectQuotationIssue(
        company_id=doc.company_id,
        document_id=doc.id,
        issue_no=issue_no,
        our_ref_text=f"{doc.document_no} (R{issue_no})",
    )
    if when is not None:
        issue.issued_at = when
    db.add(issue)
    db.flush()
    for order, (scope, version) in enumerate(pairs):
        db.add(
            ProjectQuotationIssueScope(
                company_id=doc.company_id,
                issue_id=issue.id,
                quotation_id=scope.id,
                version_id=version.id,
                sort_order=order,
            )
        )
    db.flush()
    return issue


def _fresh_project(w):
    project = make_project(w.db, w.company_id, w.admin)
    w.db.flush()
    return project


def _read(w, project_id, user=None, **params):
    res = w.api.as_(user or w.sales).get(_prefill_url(project_id), params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _codes(body):
    return [line["product_code"] for line in body["lines"]]


# ------------------------------------------------------------------ SFQ-1


def test_sfq_1_project_without_a_quotation_prefills_nothing(world):
    body = _read(world, _fresh_project(world).id)
    assert body["documents"] == []
    assert body["lines"] == []
    assert body["skipped"] == []
    assert body["document_id"] is None and body["issue_id"] is None


# ------------------------------------------------------------------ SFQ-2


def test_sfq_2_never_issued_uses_current_versions_in_scope_then_line_order(world):
    w = world
    project = _fresh_project(w)
    a, b, c = make_product(w.db), make_product(w.db), make_product(w.db)
    q = _document(w.db, project, w.admin, scopes=("Units", "Common area"))
    units, common = q.scopes
    _line(w.db, common.v1, product=c, order=0)
    _line(w.db, units.v1, product=b, order=1)
    _line(w.db, units.v1, product=a, order=0)
    # A later working version of Units replaces v1's lines.
    v2 = _next_version(w.db, units.scope, 2)
    _line(w.db, v2, product=b, order=0)
    w.db.commit()

    body = _read(w, project.id)
    assert body["document_id"] == q.doc.id
    assert body["issue_id"] is None
    assert _codes(body) == [b.product_code, c.product_code]


# ------------------------------------------------------------------ SFQ-3


def test_sfq_3_issued_uses_the_version_each_scope_had_in_the_latest_issue(world):
    w = world
    project = _fresh_project(w)
    in_r1, in_r2, in_working = make_product(w.db), make_product(w.db), make_product(w.db)
    q = _document(w.db, project, w.admin)
    units = q.scopes[0]
    _line(w.db, units.v1, product=in_r1)
    _issue(w.db, q.doc, 1, [(units.scope, units.v1)])
    v2 = _next_version(w.db, units.scope, 2)
    _line(w.db, v2, product=in_r2)
    r2 = _issue(w.db, q.doc, 2, [(units.scope, v2)])
    # Revised after R2: the customer does not hold v3.
    v3 = _next_version(w.db, units.scope, 3)
    _line(w.db, v3, product=in_working)
    w.db.commit()

    body = _read(w, project.id)
    assert body["issue_id"] == r2.id
    assert _codes(body) == [in_r2.product_code]


# ------------------------------------------------------------------ SFQ-4 / SFQ-5


def test_sfq_4_a_set_line_contributes_its_parts(world):
    w = world
    project = _fresh_project(w)
    single, p1, p2, p3 = (make_product(w.db) for _ in range(4))
    q = _document(w.db, project, w.admin)
    _line(w.db, q.scopes[0].v1, product=single, order=0)
    _line(w.db, q.scopes[0].v1, parts=[p1, p2, p3], desc="a set", order=1)
    w.db.commit()

    assert _codes(_read(w, project.id)) == [
        single.product_code,
        p1.product_code,
        p2.product_code,
        p3.product_code,
    ]


def test_sfq_5_the_same_product_appears_once(world):
    w = world
    project = _fresh_project(w)
    basin, other = make_product(w.db), make_product(w.db)
    q = _document(w.db, project, w.admin, scopes=("Type A", "Type B"))
    type_a, type_b = q.scopes
    _line(w.db, type_a.v1, product=basin, order=0)
    _line(w.db, type_a.v1, product=basin, order=1)
    _line(w.db, type_b.v1, product=basin, order=0)
    _line(w.db, type_b.v1, parts=[other, basin], desc="a set", order=1)
    w.db.commit()

    assert _codes(_read(w, project.id)) == [basin.product_code, other.product_code]


# ------------------------------------------------------------------ SFQ-6 / SFQ-7


def test_sfq_6_free_text_and_inactive_lines_are_skipped_with_a_reason(world):
    w = world
    project = _fresh_project(w)
    kept = make_product(w.db)
    gone = make_product(w.db, active=False)
    q = _document(w.db, project, w.admin)
    _line(w.db, q.scopes[0].v1, desc="Bespoke vanity top", order=0)
    _line(w.db, q.scopes[0].v1, product=gone, order=1)
    _line(w.db, q.scopes[0].v1, product=kept, order=2)
    w.db.commit()

    body = _read(w, project.id)
    assert _codes(body) == [kept.product_code]
    assert body["skipped"] == [
        {"reason": "no_product", "description": "Bespoke vanity top"},
        {"reason": "inactive", "description": gone.product_code},
    ]


def test_sfq_7_discontinued_but_active_products_prefill(world):
    w = world
    project = _fresh_project(w)
    old = make_product(w.db)
    old.is_discontinued = True
    q = _document(w.db, project, w.admin)
    _line(w.db, q.scopes[0].v1, product=old)
    w.db.commit()

    body = _read(w, project.id)
    assert _codes(body) == [old.product_code]
    assert body["skipped"] == []


# ------------------------------------------------------------------ SFQ-8


def test_sfq_8_several_documents_list_issued_first_and_can_be_picked(world):
    from datetime import datetime, timedelta

    w = world
    project = _fresh_project(w)
    pa, pb, pc = make_product(w.db), make_product(w.db), make_product(w.db)
    older = _document(w.db, project, w.admin)
    _line(w.db, older.scopes[0].v1, product=pa)
    _issue(w.db, older.doc, 1, [(older.scopes[0].scope, older.scopes[0].v1)],
           when=datetime.utcnow() - timedelta(days=5))
    newer = _document(w.db, project, w.admin)
    _line(w.db, newer.scopes[0].v1, product=pb)
    _issue(w.db, newer.doc, 1, [(newer.scopes[0].scope, newer.scopes[0].v1)],
           when=datetime.utcnow() - timedelta(days=1))
    draft = _document(w.db, project, w.admin)
    _line(w.db, draft.scopes[0].v1, product=pc)
    w.db.commit()

    body = _read(w, project.id)
    assert [d["id"] for d in body["documents"]] == [newer.doc.id, older.doc.id, draft.doc.id]
    labels = [d["label"] for d in body["documents"]]
    assert labels == [
        f"{newer.doc.document_no} (R1)",
        f"{older.doc.document_no} (R1)",
        f"{draft.doc.document_no} (not issued)",
    ]
    assert body["document_id"] == newer.doc.id
    assert _codes(body) == [pb.product_code]

    picked = _read(w, project.id, document_id=draft.doc.id)
    assert picked["document_id"] == draft.doc.id
    assert picked["issue_id"] is None
    assert _codes(picked) == [pc.product_code]


def test_sfq_8_a_document_of_another_project_is_refused(world):
    w = world
    project = _fresh_project(w)
    elsewhere = _document(w.db, _fresh_project(w), w.admin)
    w.db.commit()

    res = w.api.as_(w.sales).get(
        _prefill_url(project.id), params={"document_id": elsewhere.doc.id}
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_QUOTATION_INVALID"


# ------------------------------------------------------------------ SFQ-9


def test_sfq_9_no_prices_leave_the_read(world):
    w = world
    project = _fresh_project(w)
    p = make_product(w.db)
    q = _document(w.db, project, w.admin)
    _line(w.db, q.scopes[0].v1, product=p)
    w.db.commit()

    line = _read(w, project.id)["lines"][0]
    assert set(line) == {"product_id", "product_code", "product_name", "brand_name"}
    assert line["product_id"] == p.id


# ------------------------------------------------------------------ SFQ-10


def test_sfq_10_staff_read_needs_create(world):
    w = world
    res = w.api.as_(w.stranger).get(_prefill_url(w.project.id))
    assert res.status_code == 403, res.text


def test_sfq_10_unknown_project_is_the_write_answer(world):
    from ._sample_request_seed import uid

    res = world.api.as_(world.sales).get(_prefill_url(uid()))
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_PROJECT_INVALID"


# ------------------------------------------------------------------ SFQ-11


def test_sfq_11_portal_reads_its_own_project(portal):
    p = portal
    product = make_product(p.db)
    q = _document(p.db, p.inside, _owner(p))
    _line(p.db, q.scopes[0].v1, product=product)
    p.db.commit()

    res = _as(p, p.granted).get(PORTAL_PREFILL, params={"project_id": p.inside.id})
    assert res.status_code == 200, res.text
    assert [line["product_id"] for line in res.json()["lines"]] == [product.id]


def test_sfq_11_portal_refuses_a_project_outside_its_lookup(portal):
    p = portal
    res = _as(p, p.granted).get(PORTAL_PREFILL, params={"project_id": p.outside.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_PROJECT_NOT_ALLOWED"


def _owner(p):
    from ._sample_request_seed import make_user

    return make_user(p.db, "zzt-sr quotation owner")


# ------------------------------------------------------------------ SFQ-12 / SFQ-13


def _source(w):
    project = _fresh_project(w)
    p = make_product(w.db)
    q = _document(w.db, project, w.admin)
    _line(w.db, q.scopes[0].v1, product=p)
    issue = _issue(w.db, q.doc, 1, [(q.scopes[0].scope, q.scopes[0].v1)])
    w.db.commit()
    return SimpleNamespace(project=project, product=p, doc=q.doc, issue=issue)


def test_sfq_12_the_source_quotation_is_recorded_and_shown(world):
    w = world
    s = _source(w)
    body = full_payload(
        product_id=s.product.id,
        project_id=s.project.id,
        project_title=None,
        quotation_document_id=s.doc.id,
        quotation_issue_id=s.issue.id,
    )
    res = w.api.as_(w.sales).post(SR, json=body)
    assert res.status_code == 201, res.text
    got = res.json()
    assert got["quotation_document_id"] == s.doc.id
    assert got["quotation_issue_id"] == s.issue.id
    assert got["quotation_ref"] == f"{s.doc.document_no} (R1)"

    cleared = w.api.as_(w.sales).put(
        f"{SR}/{got['id']}", json={"quotation_document_id": None, "quotation_issue_id": None}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["quotation_document_id"] is None
    assert cleared.json()["quotation_ref"] is None


def test_sfq_12_a_never_issued_source_has_no_issue(world):
    w = world
    project = _fresh_project(w)
    p = make_product(w.db)
    q = _document(w.db, project, w.admin)
    w.db.commit()
    res = w.api.as_(w.sales).post(
        SR,
        json=full_payload(
            product_id=p.id, project_id=project.id, project_title=None,
            quotation_document_id=q.doc.id,
        ),
    )
    assert res.status_code == 201, res.text
    assert res.json()["quotation_issue_id"] is None
    assert res.json()["quotation_ref"] == f"{q.doc.document_no} (not issued)"


@pytest.mark.parametrize("case", ["other_project", "foreign_issue", "issue_without_document"])
def test_sfq_13_a_source_that_does_not_belong_is_refused(world, case):
    w = world
    s = _source(w)
    other = _source(w)
    over = {
        "other_project": {"quotation_document_id": other.doc.id},
        "foreign_issue": {"quotation_document_id": s.doc.id, "quotation_issue_id": other.issue.id},
        "issue_without_document": {"quotation_issue_id": s.issue.id},
    }[case]
    res = w.api.as_(w.sales).post(
        SR,
        json=full_payload(
            product_id=s.product.id, project_id=s.project.id, project_title=None, **over
        ),
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_QUOTATION_INVALID"


def test_sfq_13_moving_the_request_to_another_project_needs_the_source_cleared(world):
    w = world
    s = _source(w)
    created = w.api.as_(w.sales).post(
        SR,
        json=full_payload(
            product_id=s.product.id, project_id=s.project.id, project_title=None,
            quotation_document_id=s.doc.id,
        ),
    ).json()
    res = w.api.as_(w.sales).put(f"{SR}/{created['id']}", json={"project_id": w.other_project.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_QUOTATION_INVALID"
