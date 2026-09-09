"""S5 - import column mappings, visible and editable (`documentation/plans/scm/scm-
supplier-documents-pi-first-acceptance-criteria.md`, section E, AC-E1).

TEST-FIRST (Phase 2): `app/api/v1/system/import_field_aliases.py` does not exist yet, so
every route test below is expected to be RED with a 404 (route not mounted) until AC-E1
lands. Route/permission wiring modelled on `tests/scm/test_proforma_invoice_routes.py`
(the same `scm_app`/company-user pattern, reused here since it is app-wide, not SCM-
specific) and `tests/scm/test_numbering_crm_spo.py` (the sibling `system.numbering_rules`
permission this lane's grant sweep is supposed to mirror).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.import_alias import ImportFieldAlias
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401 - re-exported fixture
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

URL = "/api/v1/system/import-field-aliases"
VIEW_PERMISSION = "system.import_field_aliases.view"
EDIT_PERMISSION = "system.import_field_aliases.edit"
MARKER = "ZZIFA"


def _u() -> str:
    return str(uuid.uuid4())


def _grant(db, uid: str, slug: str) -> None:
    from app.models.user import UserPermission, UserRole, UserRolePermission, UserRoleAssignment

    tag = uuid.uuid4().hex[:8]
    role = UserRole(id=_u(), slug=f"{MARKER}-role-{tag}", name=f"{MARKER} role {tag}")
    db.add(role)
    db.flush()
    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
    if perm is None:
        perm = UserPermission(id=_u(), slug=slug, name=slug)
        db.add(perm)
        db.flush()
    db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role.id))
    db.flush()


def _client(scm_app, *, view: bool = False, edit: bool = False):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    if view:
        _grant(db, uid, VIEW_PERMISSION)
    if edit:
        _grant(db, uid, EDIT_PERMISSION)
    return TestClient(app), db


def _clear(db, doc_type: str) -> None:
    db.execute(
        text("DELETE FROM import_field_alias WHERE doc_type = :d AND alias LIKE :m"),
        {"d": doc_type, "m": f"{MARKER}%"},
    )
    db.flush()


def test_list_without_the_view_permission_is_403(scm_app):
    client, _db = _client(scm_app, view=False, edit=False)
    r = client.get(f"{URL}?doc_type=proforma_invoice")
    assert r.status_code == 403, r.text


def test_list_groups_aliases_by_field(scm_app):
    client, db = _client(scm_app, view=True)
    _clear(db, "proforma_invoice")
    field = f"{MARKER}_field_1"
    db.add(
        ImportFieldAlias(
            id=_u(), doc_type="proforma_invoice", field=field, alias=f"{MARKER}_型号",
        )
    )
    db.commit()

    r = client.get(f"{URL}?doc_type=proforma_invoice")
    assert r.status_code == 200, r.text
    body = r.json()
    group = next((g for g in body if g["field"] == field), None)
    assert group is not None, body
    assert any(a["alias"] == f"{MARKER}_型号" for a in group["aliases"])


def test_create_then_409_on_the_same_triple(scm_app):
    client, db = _client(scm_app, view=True, edit=True)
    _clear(db, "proforma_invoice")
    field = f"{MARKER}_field_2"
    payload = {"doc_type": "proforma_invoice", "field": field, "alias": f"{MARKER}_alias"}

    r1 = client.post(URL, json=payload)
    assert r1.status_code in (200, 201), r1.text

    r2 = client.post(URL, json=payload)
    assert r2.status_code == 409, r2.text


def test_create_without_the_edit_permission_is_403(scm_app):
    client, _db = _client(scm_app, view=True, edit=False)
    r = client.post(
        URL,
        json={"doc_type": "proforma_invoice", "field": f"{MARKER}_x", "alias": f"{MARKER}_y"},
    )
    assert r.status_code == 403, r.text


def test_delete_removes_the_alias(scm_app):
    client, db = _client(scm_app, view=True, edit=True)
    _clear(db, "proforma_invoice")
    row_id = _u()
    db.add(
        ImportFieldAlias(
            id=row_id, doc_type="proforma_invoice", field=f"{MARKER}_field_3",
            alias=f"{MARKER}_deleteme",
        )
    )
    db.commit()

    r = client.delete(f"{URL}/{row_id}")
    assert r.status_code == 204, r.text

    remaining = db.query(ImportFieldAlias).filter(ImportFieldAlias.id == row_id).one_or_none()
    assert remaining is None


def test_fields_list_is_built_from_the_readers_own_declared_fields(scm_app):
    client, _db = _client(scm_app, view=True)
    r = client.get(f"{URL}/fields?doc_type=proforma_invoice")
    assert r.status_code == 200, r.text
    fields = {row["field"] for row in r.json()}
    # `ProformaLine`/`ProformaDocument` fields the reader itself declares (AliasResolver
    # asks for these by name in `proforma_invoice_reader.py`) - never a hand-typed list.
    assert "item_code" in fields
    assert "qty" in fields
