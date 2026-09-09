"""AC-A5 / AC-D2c - the invoice payload carries the supplier's own reference and the
container's seal number (Phase 3 round 1, item 2: "`serialize` emits `supplier_ref` and
`seal_ref`; list search matches `supplier_ref` too").

TEST-FIRST posture is moot for `serialize` itself (it already ships both fields) - this
file pins the CONTRACT (`response_model` silently drops undeclared fields is the standing
lesson this guards against, even though these routes return a plain dict with no
`response_model`): the JSON key for the model's `seal_ref` column is `seal_no` (the same
name the FE type and `ProformaInvoicePackingTab`'s convert-dialog carry-over read), so this
asserts THAT key, not the column name.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user
from tests.scm.test_proforma_invoice_packing_lines import World

pytestmark = requires_pg

VIEW_PERMISSION = "scm.dashboard.view"
MARKER = "ZZPISER"


def _u() -> str:
    return str(uuid.uuid4())


def _grant(db, uid: str, slug: str) -> None:
    from app.models.user import UserPermission, UserRole, UserRolePermission, UserRoleAssignment

    role = UserRole(id=_u(), slug=f"{MARKER}-role-{uuid.uuid4().hex[:6]}", name="role")
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


def _seed_pi_with_ref_and_seal(db):
    from app.models.scm import ProformaInvoice

    w = World(db)
    supplier = w.supplier(f"{MARKER} Supplier")
    invoice = ProformaInvoice(
        id=_u(),
        supplier_id=supplier.id,
        pi_number=f"{MARKER}-PI-{uuid.uuid4().hex[:8].upper()}",
        supplier_ref=f"{MARKER}-REF-77",
        seal_ref=f"{MARKER}-SEAL-99",
    )
    db.add(invoice)
    db.commit()
    return supplier, invoice


def _client(scm_app) -> TestClient:
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, VIEW_PERMISSION)
    return TestClient(app)


def test_the_list_row_carries_supplier_ref_and_the_seal_number(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, VIEW_PERMISSION)
    _supplier, invoice = _seed_pi_with_ref_and_seal(db)
    client = TestClient(app)

    r = client.get("/api/v1/scm/proforma-invoices", params={"query": invoice.pi_number})
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    row = next(row for row in rows if row["id"] == str(invoice.id))
    assert row["supplier_ref"] == f"{MARKER}-REF-77"
    assert row["seal_no"] == f"{MARKER}-SEAL-99"


def test_the_detail_payload_carries_supplier_ref_and_the_seal_number(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, VIEW_PERMISSION)
    _supplier, invoice = _seed_pi_with_ref_and_seal(db)
    client = TestClient(app)

    r = client.get(f"/api/v1/scm/proforma-invoices/{invoice.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["supplier_ref"] == f"{MARKER}-REF-77"
    assert body["seal_no"] == f"{MARKER}-SEAL-99"


def test_the_list_search_box_matches_the_suppliers_own_reference_too(scm_app):
    """AC-A5: "search matches either" - Ms Tee has the supplier's number in the email far
    more often than ours. Searching by `supplier_ref` alone (never mentioning `pi_number`)
    still finds the row."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, VIEW_PERMISSION)
    _supplier, invoice = _seed_pi_with_ref_and_seal(db)
    client = TestClient(app)

    r = client.get("/api/v1/scm/proforma-invoices", params={"query": f"{MARKER}-REF-77"})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert str(invoice.id) in ids
