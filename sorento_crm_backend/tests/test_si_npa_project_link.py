"""PROJECT-RELATED-RECORDS red tests: linking stock inquiries and new product applications to a
project, setting the project on any record at any time, and the portal project pickers.

UAC: documentation/plans/project-sales/project-related-records-12nov-acceptance-criteria.md
(AC-C1 .. AC-C7, AC-C6a). Contract: CONTRACT-project-related-records.md sections 1 to 4.

Postgres only: the migration checks read the migrated test database, everything else runs in a
`blank_session` and seeds its own chain with fake values (marker `zzt-prr`).
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.projects import Project

from ._own_scope_support import acting, sorento, uid, user
from ._pg_fixture import blank_session

MARKER = "zzt-prr"

SI = "/api/v1/procurement/stock-inquiries"
NPA = "/api/v1/procurement/new-product-applications"
PR = "/api/v1/procurement/purchase-requests"
CX = "/api/v1/complaints-management/complaints"

SI_VIEW, SI_EDIT = "procurement.stock_inquiries.view", "procurement.stock_inquiries.edit"
CX_VIEW, CX_EDIT = "complaint_management.complaints.view", "complaint_management.complaints.edit"
PR_VIEW = "procurement.purchase_requests.view"
SF_VIEW, SF_EDIT = "procurement.sponsorship_forms.view", "procurement.sponsorship_forms.edit"
NPA_P = "procurement.new_product_applications"
NPA_VIEW, NPA_CREATE = f"{NPA_P}.view", f"{NPA_P}.create"
NPA_APPROVE, NPA_OPEN = f"{NPA_P}.approve", f"{NPA_P}.open_code"

#: Everything a staff editor of all five kinds holds (no new slug is introduced by the lane).
EDITOR = {
    SI_VIEW, SI_EDIT, "procurement.stock_inquiries.add",
    CX_VIEW, CX_EDIT, "complaint_management.complaints.add",
    PR_VIEW, "procurement.purchase_requests.add", "procurement.purchase_requests.edit",
    SF_VIEW, SF_EDIT, "procurement.sponsorship_forms.add",
    NPA_VIEW, NPA_CREATE, NPA_APPROVE, NPA_OPEN,
}


# ------------------------------------------------------------------ AC-C1: migration + model


MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "prr_0001_si_npa_project_link.py"


def test_ac_c1_the_migration_file_exists_with_a_short_revision_id():
    assert MIGRATION.exists(), f"missing {MIGRATION.name}"
    source = MIGRATION.read_text()
    revision = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", source, re.M).group(1)
    assert revision == "prr_0001_si_npa_project"
    assert len(revision) <= 32


@pytest.mark.parametrize(
    "table,fk,index",
    [
        ("stock_inquiries", "fk_stock_inquiries_project_id", "ix_stock_inquiries_project"),
        ("new_product_applications", "fk_new_product_applications_project_id", "ix_new_product_applications_project"),
    ],
)
def test_ac_c1_the_migrated_column_is_nullable_with_a_set_null_fk(table, fk, index):
    """Read from the migrated test database (alembic head), not the blank scratch schema."""
    from app.database import engine

    with engine.connect() as connection:
        column = connection.execute(
            text(
                "select data_type, is_nullable from information_schema.columns "
                "where table_name = :t and column_name = 'project_id' and table_schema = current_schema()"
            ),
            {"t": table},
        ).first()
        assert column is not None, f"{table}.project_id missing"
        assert column.data_type == "uuid"
        assert column.is_nullable == "YES"
        constraint = connection.execute(
            text(
                "select confdeltype, confrelid::regclass::text as target from pg_constraint "
                "where conname = :c"
            ),
            {"c": fk},
        ).first()
        assert constraint is not None, f"{fk} missing"
        assert constraint.confdeltype == "n"  # ON DELETE SET NULL
        assert constraint.target.split(".")[-1] == "projects"
        assert connection.execute(
            text("select 1 from pg_indexes where indexname = :i"), {"i": index}
        ).first() is not None, f"{index} missing"


@pytest.mark.parametrize("model_path", ["app.models.procurement:StockInquiry", "app.models.new_product_application:NewProductApplication"])
def test_ac_c1_the_model_column_is_nullable_set_null(model_path):
    import importlib

    module, name = model_path.split(":")
    model = getattr(importlib.import_module(module), name)
    column = model.__table__.c.get("project_id")
    assert column is not None, f"{name}.project_id missing"
    assert column.nullable is True
    (fk,) = column.foreign_keys
    assert fk.target_fullname == "projects.projects.id"
    assert fk.ondelete == "SET NULL"


# ------------------------------------------------------------------ staff world


def _second_company(db) -> str:
    company_id = uid()
    db.execute(
        text("insert into companies (id, code, name, is_active) values (:i, :c, :n, true)"),
        {"i": company_id, "c": f"Z{uuid.uuid4().hex}".upper(), "n": f"{MARKER} other co"},
    )
    db.flush()
    return company_id


def _project(db, company_id: str, *, approval_state=None, title=None) -> Project:
    tag = uuid.uuid4().hex[:6]
    title = title or f"{MARKER} Project {tag}"
    row = Project(
        id=uid(), company_id=company_id, project_code=f"ZZT-PRR-{tag}", title=title,
        normalised_title=title.lower(), approval_state=approval_state,
    )
    db.add(row)
    db.flush()
    return row


def _inquiry(db, **kw):
    from app.models.procurement import StockInquiry

    values = dict(
        id=uid(), inquiry_number=f"SI26-Z{uuid.uuid4().hex[:4]}", product_code="ZZT-XY-1",
        item_description=f"{MARKER} sink", project_customer=f"{MARKER} DEVELOPER SDN BHD",
        project_name=f"{MARKER} RESIDENCE", quantity="55", delivery_date="2028-01-17",
        purchasing_response="Please apply for a new code.", status="responded",
    )
    values.update(kw)
    row = StockInquiry(**values)
    db.add(row)
    db.flush()
    return row


def _complaint(db, **kw):
    from app.models.complaints import Complaint

    values = dict(
        id=uid(), complaint_number=f"ZZT-CX-{uuid.uuid4().hex[:6]}", complaint_date=date(2026, 2, 1),
        defect_description=f"{MARKER} cracked tile", status="closed",
    )
    values.update(kw)
    row = Complaint(**values)
    db.add(row)
    db.flush()
    return row


def _request(db, kind, **kw):
    from app.models.procurement import PurchaseRequestHeader

    values = dict(
        id=uid(), request_type=kind, request_number=f"ZZT-RQ-{uuid.uuid4().hex[:6]}",
        status="processed_by_cs", approval_status="approved", project_title=f"{MARKER} typed",
    )
    values.update(kw)
    row = PurchaseRequestHeader(**values)
    db.add(row)
    db.flush()
    return row


def _npa(db, company_id, **kw):
    from app.models.new_product_application import NewProductApplication

    values = dict(
        id=uid(), company_id=company_id, application_no=f"NPA-{uuid.uuid4().int % 10**6:06d}",
        status="completed",
    )
    values.update(kw)
    row = NewProductApplication(**values)
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def staff():
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    with blank_session() as db:
        company_id = sorento(db)
        other_company = _second_company(db)
        foreign = _project(db, other_company)
        with company_scope(db, frozenset({company_id})):
            approved = _project(db, company_id)
            approved_2 = _project(db, company_id)
            pending = _project(db, company_id, approval_state="pending")
            editor = user(db, "Editor")
            viewer = user(db, "Viewer")
            db.flush()
            yield SimpleNamespace(
                db=db, company_id=company_id, approved=approved, approved_2=approved_2,
                pending=pending, foreign=foreign, editor=editor, viewer=viewer,
            )


def _as_editor(w):
    return acting(w.db, w.editor, EDITOR, roles={"admin"})


def _ok(response, *codes):
    assert response.status_code in (codes or (200, 201)), f"{response.request.method} {response.request.url.path} -> {response.status_code} {response.text}"
    return response.json()


def _assert_linked(body, project):
    assert body["project_id"] == str(project.id), body
    assert body["project_code"] == project.project_code, body
    assert body["project_title"] == project.title, body


# ------------------------------------------------------------------ AC-C2, AC-C5: staff SI

#: What the staff create requires today (StockInquiryService submission check).
_SI_REQUIRED = {
    "salesperson": f"{MARKER} Ali", "item_description": f"{MARKER} basin",
    "product_code": "ZZT-XY-2", "project_customer": f"{MARKER} DEVELOPER SDN BHD",
    "quantity": "4", "delivery_date": "2028-01-17", "project_name": f"{MARKER} typed tower",
}


def test_ac_c2_a_staff_stock_inquiry_saves_an_approved_project_and_answers_its_code(staff):
    w = staff
    with _as_editor(w) as client:
        created = _ok(client.post(f"{SI}/", json={
            **_SI_REQUIRED, "project_id": str(w.approved.id),
        }), 201, 200)
        _assert_linked(created, w.approved)
        assert created["project_name"] == f"{MARKER} typed tower"
        updated = _ok(client.put(f"{SI}/{created['id']}", json={"project_id": str(w.approved_2.id)}))
        _assert_linked(updated, w.approved_2)
        read = _ok(client.get(f"{SI}/{created['id']}"))
        _assert_linked(read, w.approved_2)


def test_ac_c2_a_staff_stock_inquiry_refuses_an_unapproved_project(staff):
    w = staff
    with _as_editor(w) as client:
        response = client.post(f"{SI}/", json={
            **_SI_REQUIRED,
            "project_id": str(w.pending.id),
        })
        assert response.status_code == 422, response.text
        assert "stock_inquiry_project_not_approved" in response.text
        row = _inquiry(w.db, status="new")
        refused = client.put(f"{SI}/{row.id}", json={"project_id": str(w.pending.id)})
        assert refused.status_code == 422, refused.text


def test_ac_c5_a_typed_project_name_never_fills_the_link(staff):
    w = staff
    with _as_editor(w) as client:
        created = _ok(client.post(f"{SI}/", json={
            **{**_SI_REQUIRED, "project_name": w.approved.title},
        }), 201, 200)
    assert "project_id" in created, "response must carry project_id"
    assert created["project_id"] is None
    assert created["project_name"] == w.approved.title


def test_ac_c2_the_link_can_be_cleared(staff):
    w = staff
    row = _inquiry(w.db, status="new", project_id=str(w.approved.id))
    with _as_editor(w) as client:
        cleared = _ok(client.put(f"{SI}/{row.id}", json={"project_id": None}))
    assert cleared["project_id"] is None
    assert cleared["project_code"] is None


# ------------------------------------------------------------------ AC-C2, AC-C4: staff NPA


def _npa_body(**over):
    body = {"customer_name": f"{MARKER} typed customer", "project_name": f"{MARKER} typed project", "lines": []}
    body.update(over)
    return body


def test_ac_c2_a_staff_npa_saves_an_approved_project_and_answers_its_code(staff):
    w = staff
    with acting(w.db, w.editor, {NPA_VIEW, NPA_CREATE}) as client:
        created = _ok(client.post(NPA, json=_npa_body(project_id=str(w.approved.id))), 201)
        _assert_linked(created, w.approved)
        updated = _ok(client.put(f"{NPA}/{created['id']}", json=_npa_body(project_id=str(w.approved_2.id))))
        _assert_linked(updated, w.approved_2)
        _assert_linked(_ok(client.get(f"{NPA}/{created['id']}")), w.approved_2)


def test_ac_c2_a_staff_npa_refuses_an_unapproved_project(staff):
    w = staff
    with acting(w.db, w.editor, {NPA_VIEW, NPA_CREATE}) as client:
        response = client.post(NPA, json=_npa_body(project_id=str(w.pending.id)))
    assert response.status_code == 422, response.text
    assert "new_product_application_project_not_approved" in response.text


def test_ac_c5_npa_project_name_never_fills_the_link(staff):
    w = staff
    with acting(w.db, w.editor, {NPA_VIEW, NPA_CREATE}) as client:
        created = _ok(client.post(NPA, json=_npa_body(project_name=w.approved.title)), 201)
    assert "project_id" in created, "response must carry project_id"
    assert created["project_id"] is None


def test_ac_c4_an_npa_raised_from_an_si_starts_with_the_si_project(staff):
    w = staff
    inquiry = _inquiry(w.db, project_id=str(w.approved.id))
    with acting(w.db, w.editor, {NPA_VIEW, NPA_CREATE}) as client:
        created = _ok(client.post(NPA, json=_npa_body(stock_inquiry_id=str(inquiry.id))), 201)
    _assert_linked(created, w.approved)


def test_ac_c4_an_explicit_null_project_stays_null(staff):
    w = staff
    inquiry = _inquiry(w.db, project_id=str(w.approved.id))
    with acting(w.db, w.editor, {NPA_VIEW, NPA_CREATE}) as client:
        created = _ok(client.post(NPA, json=_npa_body(stock_inquiry_id=str(inquiry.id), project_id=None)), 201)
    assert created["project_id"] is None


def test_ac_c4_the_person_can_pick_another_project_than_the_si(staff):
    w = staff
    inquiry = _inquiry(w.db, project_id=str(w.approved.id))
    with acting(w.db, w.editor, {NPA_VIEW, NPA_CREATE}) as client:
        created = _ok(client.post(NPA, json=_npa_body(
            stock_inquiry_id=str(inquiry.id), project_id=str(w.approved_2.id))), 201)
    _assert_linked(created, w.approved_2)


# ------------------------------------------------------------------ AC-C6, AC-C6a: PATCH .../project


def _closed_rows(w):
    """One closed / approved record per route, linked to `approved` so a change has an old value."""
    p = str(w.approved.id)
    return {
        "stock_inquiry": (SI, _inquiry(w.db, status="responded", project_id=p)),
        "complaint": (CX, _complaint(w.db, status="closed", project_id=p)),
        "purchase_request": (PR, _request(w.db, "purchase_request", project_id=p)),
        "sponsorship_form": (PR, _request(w.db, "sponsorship_form", project_id=p)),
        "new_product_application": (NPA, _npa(w.db, w.company_id, status="completed", project_id=p)),
    }


def _state(row):
    return (row.status, getattr(row, "approval_status", None))


@pytest.mark.parametrize(
    "kind", ["stock_inquiry", "complaint", "purchase_request", "sponsorship_form", "new_product_application"]
)
def test_ac_c6a_the_project_can_be_changed_on_a_closed_record_without_touching_its_status(staff, kind):
    from app.models.audit import AuditLog

    w = staff
    base, row = _closed_rows(w)[kind]
    before = _state(row)
    with _as_editor(w) as client:
        body = _ok(client.patch(f"{base}/{row.id}/project", json={"project_id": str(w.approved_2.id)}))
    assert body["project_id"] == str(w.approved_2.id)
    assert body["project_code"] == w.approved_2.project_code
    w.db.expire_all()
    fresh = w.db.get(type(row), row.id)
    assert str(fresh.project_id) == str(w.approved_2.id)
    assert _state(fresh) == before
    changes = [
        a for a in w.db.query(AuditLog).filter(AuditLog.entity_id == str(row.id)).all()
        if "project_id" in (a.new_values or {})
    ]
    assert changes, "no History row for the project change"
    last = changes[-1]
    assert str(last.new_values["project_id"]) == str(w.approved_2.id)
    assert str((last.old_values or {}).get("project_id")) == str(w.approved.id)


@pytest.mark.parametrize(
    "kind", ["stock_inquiry", "complaint", "purchase_request", "sponsorship_form", "new_product_application"]
)
def test_ac_c6a_the_project_can_be_cleared(staff, kind):
    w = staff
    base, row = _closed_rows(w)[kind]
    with _as_editor(w) as client:
        body = _ok(client.patch(f"{base}/{row.id}/project", json={"project_id": None}))
    assert body["project_id"] is None
    w.db.expire_all()
    assert w.db.get(type(row), row.id).project_id is None


@pytest.mark.parametrize(
    "kind", ["stock_inquiry", "complaint", "purchase_request", "sponsorship_form", "new_product_application"]
)
def test_ac_c6a_patch_refuses_an_unapproved_project(staff, kind):
    w = staff
    base, row = _closed_rows(w)[kind]
    with _as_editor(w) as client:
        response = client.patch(f"{base}/{row.id}/project", json={"project_id": str(w.pending.id)})
    assert response.status_code == 422, response.text
    w.db.expire_all()
    assert str(w.db.get(type(row), row.id).project_id) == str(w.approved.id)


_VIEW_ONLY = {
    "stock_inquiry": {SI_VIEW},
    "complaint": {CX_VIEW},
    "purchase_request": {PR_VIEW},
    "sponsorship_form": {SF_VIEW},
    "new_product_application": {NPA_VIEW},
}


@pytest.mark.parametrize("kind", list(_VIEW_ONLY))
def test_ac_c6a_patch_without_the_edit_permission_is_refused(staff, kind):
    w = staff
    base, row = _closed_rows(w)[kind]
    with acting(w.db, w.viewer, _VIEW_ONLY[kind]) as client:
        response = client.patch(f"{base}/{row.id}/project", json={"project_id": str(w.approved_2.id)})
    assert response.json() != {"detail": "Not Found"}, "route not mounted"
    assert response.status_code in (403, 404), response.text
    w.db.expire_all()
    assert str(w.db.get(type(row), row.id).project_id) == str(w.approved.id)


def test_set_record_project_is_the_one_shared_function(staff):
    """Contract section 3: one function behind all four routes."""
    from app.services.project_related_records import set_record_project

    w = staff
    row = _complaint(w.db, status="rejected")
    set_record_project(w.db, kind="complaint", record_id=str(row.id), project_id=str(w.approved.id), actor=w.editor)
    w.db.expire_all()
    fresh = w.db.get(type(row), row.id)
    assert str(fresh.project_id) == str(w.approved.id)
    assert fresh.status == "rejected"


# ------------------------------------------------------------------ AC-C3: portal pickers


from tests import _portal_p4_support as p4  # noqa: E402
from tests._portal_grant import link_contact_company  # noqa: E402
from tests._portal_p4_support import scene  # noqa: E402,F401  (pytest fixture)
from tests import _portal_p4_npa_support as p4npa  # noqa: E402
from tests._portal_p4_npa_support import world  # noqa: E402,F401  (pytest fixture)


def _portal_projects(db):
    own = _project(db, p4.SORENTO)
    foreign = _project(db, _second_company(db))
    db.commit()
    return own, foreign


def _create_and_submit(api, kind, body):
    """The refusal may land on create or on submit (the sponsorship form checks on submit)."""
    created = api.create(kind, body)
    if created.status_code >= 400:
        return created, None
    sid = created.json()["id"]
    return api.submit(kind, sid), sid


@pytest.mark.parametrize("kind", ["stock_inquiry", "complaint", "purchase_request"])
def test_ac_c3_portal_request_forms_take_only_the_contacts_own_company_projects(scene, kind):  # noqa: F811
    sc = scene
    spec = p4.SPECS[kind]
    link_contact_company(sc.db, sc.contact.id, p4.SORENTO)
    own, foreign = _portal_projects(sc.db)

    refused, _sid = _create_and_submit(sc.portal, kind, spec.body(sc, project_id=str(foreign.id)))
    assert refused.status_code == 422, refused.text

    saved, sid = _create_and_submit(sc.portal, kind, spec.body(sc, project_id=str(own.id)))
    p4.ok(saved)
    assert str(sc.row(spec, sid).project_id) == str(own.id)

    none, sid_none = _create_and_submit(sc.portal, kind, spec.body(sc))
    p4.ok(none)
    assert sc.row(spec, sid_none).project_id is None


def test_ac_c3_portal_npa_takes_only_the_contacts_own_company_projects(world):  # noqa: F811
    w = world
    db = w.sc.db
    own, foreign = _portal_projects(db)
    api = w.rep.portal

    refused = api.call("POST", p4npa.SUB, json=w.body(project_id=str(foreign.id)))
    if refused.status_code < 400:
        refused = api.call("POST", f"{p4npa.SUB}/{refused.json()['id']}/submit")
    assert refused.status_code == 422, refused.text

    created = p4.ok(api.call("POST", p4npa.SUB, json=w.body(project_id=str(own.id))), 201).json()
    p4.ok(api.call("POST", f"{p4npa.SUB}/{created['id']}/submit"))
    assert str(p4npa.npa_row(w, created["id"]).project_id) == str(own.id)

    plain = p4.ok(api.call("POST", p4npa.SUB, json=w.body()), 201).json()
    p4.ok(api.call("POST", f"{p4npa.SUB}/{plain['id']}/submit"))
    assert p4npa.npa_row(w, plain["id"]).project_id is None
