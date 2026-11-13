"""PROJECT-RELATED-RECORDS fix round 2: security + review findings.

- Portal revise and portal draft saves check a picked project exactly like submit does (B1, should-fix 3):
  a project of another company is refused with the ownership code and nothing is saved.
- The NPA PATCH follows the NPA edit rule: the applicant (or an admin), not any creator (S3).
- The purchase request PATCH refuses a caller without either edit right before reading the row (no
  404 / 403 oracle).
- The external stock inquiry create checks a given project against the caller's contact.

Postgres only; fake values (markers `zzt-prr`, `ZZT`).
"""
from __future__ import annotations

import uuid

import pytest

from tests import _portal_p4_support as p4
from tests._own_scope_support import acting, user
from tests._portal_grant import link_contact_company
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

from .test_project_related_records import NPA_VIEW
from .test_si_npa_project_link import (
    NPA,
    NPA_CREATE,
    PR,
    _as_editor,
    _npa as _npa_row,
    _portal_projects,
    staff,  # noqa: F401
)

NOT_YOURS = "sponsorship_project_not_permitted"


def _code(response) -> str | None:
    try:
        return response.json().get("code")
    except ValueError:  # pragma: no cover - a non-JSON body is the failure
        return None


# ------------------------------------------------------------------ B1: portal revise


@pytest.mark.parametrize("kind", ["stock_inquiry", "complaint", "purchase_request"])
def test_b1_revise_onto_another_companys_project_is_refused_and_nothing_saved(scene, kind):  # noqa: F811
    sc = scene
    spec = p4.SPECS[kind]
    link_contact_company(sc.db, sc.contact.id, p4.SORENTO)
    own, foreign = _portal_projects(sc.db)
    p4.seed_revisions(sc, spec, enabled=True)
    sid = p4._id(sc.portal.create(kind, spec.body(sc)))
    p4.ok(sc.portal.submit(kind, sid))
    p4.staff_to_final(sc, spec, sid)

    refused = sc.portal.revise(kind, sid, fields={"project_id": str(foreign.id)}, expected=0)
    assert refused.status_code == 422, refused.text
    assert _code(refused) == NOT_YOURS, refused.text
    sc.db.expire_all()
    assert sc.row(spec, sid).project_id is None

    p4.ok(sc.portal.revise(kind, sid, fields={"project_id": str(own.id)}, expected=0), 200)
    sc.db.expire_all()
    assert str(sc.row(spec, sid).project_id) == str(own.id)


# ------------------------------------------------------------------ should-fix 3: portal draft save


@pytest.mark.parametrize("kind", ["stock_inquiry", "complaint", "purchase_request", "sponsorship_form"])
def test_s3_a_draft_cannot_hold_another_companys_project(scene, kind):  # noqa: F811
    sc = scene
    spec = p4.SPECS[kind]
    link_contact_company(sc.db, sc.contact.id, p4.SORENTO)
    own, foreign = _portal_projects(sc.db)

    created = sc.portal.create(kind, spec.body(sc, project_id=str(foreign.id)))
    assert created.status_code == 422, created.text
    assert _code(created) == NOT_YOURS, created.text

    sid = p4._id(sc.portal.create(kind, spec.body(sc)))
    saved = sc.portal.save(kind, sid, spec.body(sc, project_id=str(foreign.id)))
    assert saved.status_code == 422, saved.text
    assert _code(saved) == NOT_YOURS, saved.text
    sc.db.expire_all()
    assert sc.row(spec, sid).project_id is None

    p4.ok(sc.portal.save(kind, sid, spec.body(sc, project_id=str(own.id))))
    sc.db.expire_all()
    assert str(sc.row(spec, sid).project_id) == str(own.id)


# ------------------------------------------------------------------ S3: NPA PATCH follows the edit rule


def test_s3_npa_patch_is_the_applicants_not_any_creators(staff):  # noqa: F811
    w = staff
    creator = user(w.db, "Another creator")
    row = _npa_row(w.db, w.company_id, status="completed", applicant_id=w.editor, project_id=str(w.approved.id))
    perms = {NPA_VIEW, NPA_CREATE}
    with acting(w.db, creator, perms) as client:
        refused = client.patch(f"{NPA}/{row.id}/project", json={"project_id": str(w.approved_2.id)})
    assert refused.status_code == 403, refused.text
    w.db.expire_all()
    assert str(w.db.get(type(row), row.id).project_id) == str(w.approved.id)
    with acting(w.db, w.editor, perms) as client:
        done = client.patch(f"{NPA}/{row.id}/project", json={"project_id": str(w.approved_2.id)})
    assert done.status_code == 200, done.text


# ------------------------------------------------------------------ security 5: PR PATCH, no oracle


def test_sec5_pr_patch_without_an_edit_right_is_403_before_the_row_is_read(staff):  # noqa: F811
    w = staff
    with acting(w.db, w.viewer, {"procurement.purchase_requests.view"}) as client:
        missing = client.patch(f"{PR}/{uuid.uuid4()}/project", json={"project_id": None})
    assert missing.status_code == 403, missing.text


# ------------------------------------------------------------------ security 4: external SI create


_EXT = "/api/v1/external/stock-inquiries/"


def _external_body(**over):
    body = {
        "salesperson": "ZZT Ali", "item_description": "zzt-prr basin", "product_code": "ZZT-XY-9",
        "project_customer": "ZZT DEVELOPER SDN BHD", "quantity": "4", "delivery_date": "2028-01-17",
        "project_name": "zzt-prr typed", "user_confirmed": True,
    }
    body.update(over)
    return body


@pytest.fixture()
def external(staff):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.dependencies import get_external_api_user
    from app.main import app

    app.dependency_overrides[get_external_api_user] = lambda: {"id": staff.editor, "email": "zzt@zzt.test"}
    try:
        with _as_editor(staff):
            yield staff, TestClient(app)
    finally:
        app.dependency_overrides.pop(get_external_api_user, None)


def test_sec4_external_create_with_a_project_and_no_contact_is_refused(external):
    w, client = external
    response = client.post(_EXT, json=_external_body(project_id=str(w.approved.id)))
    # The external create already needs the contact scope (400 VALIDATION_ERROR); a project must
    # never be the reason it gets through without one.
    assert response.status_code in (400, 422), response.text


def test_sec4_external_create_takes_only_the_contacts_own_company_project(external):
    from tests._own_scope_support import contact

    w, client = external
    mine = contact(w.db, "Ext")
    link_contact_company(w.db, mine.id, w.company_id)
    w.db.flush()
    foreign = client.post(_EXT, json=_external_body(project_id=str(w.foreign.id), contact_id=mine.id, space_id="1"))
    assert foreign.status_code == 422, foreign.text
    assert _code(foreign) == NOT_YOURS, foreign.text
    own = client.post(_EXT, json=_external_body(project_id=str(w.approved.id), contact_id=mine.id, space_id="1"))
    assert own.status_code in (200, 201), own.text
    assert own.json()["project_id"] == str(w.approved.id)

