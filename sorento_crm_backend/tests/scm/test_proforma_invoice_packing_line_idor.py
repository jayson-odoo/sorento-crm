"""Cross-company IDOR and bad-uuid guards on the packing-row routes (Phase 3 round 2,
tests owed by the round 1 outcome: "cross-company IDOR on
`.../packing-lines/{row_id}/dismiss`... bad-uuid per new route").

`app/api/v1/scm/proforma_invoices.py`'s dismiss/undo/match routes read the row through
`_row_or_404`, whose query carries `ProformaInvoicePackingLine`'s `CompanyScopedMixin`
filter - a row belonging to another company reads as 404, never leaked or overwritten.
These tests pin that behaviour (and the bad-uuid short-circuit ahead of it) so a future
edit that widens the query, or drops the `_is_uuid` pre-check, is caught here rather than
in production. Modelled on `test_outstanding_import_routes.py`'s `as_company_user` (a
FRESH company per call - never borrowed) and `test_proforma_invoice_packing_lines.py`'s
own `_seed_one_packing_row`/`_grant`, reused rather than re-typed.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user
from tests.scm.test_proforma_invoice_packing_lines import (
    UPLOAD_PERMISSION,
    _grant,
    _seed_one_packing_row,
)

pytestmark = requires_pg


def _company_b_client(app, db, gcu, gcuk) -> TestClient:
    """A second user, scoped to a SECOND, freshly-created company, holding the same
    upload permission - so a 404 below is the company filter, not a missing grant."""
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    return TestClient(app)


def test_dismiss_on_another_companys_row_is_404_and_changes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    company_a = as_company_user(app, db, gcu, gcuk, role=None)  # company A
    _supplier, invoice, row = _seed_one_packing_row(db)

    client = _company_b_client(app, db, gcu, gcuk)  # company B

    r = client.post(f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{row.id}/dismiss")
    assert r.status_code == 404, r.text

    # Read back as company A - the SESSION's scope now reads as company B, and a
    # read under the wrong scope would find nothing regardless of what the request
    # did, which would prove nothing about the route.
    from app.models.base import set_company_scope

    set_company_scope(db, company_a)
    db.expire_all()
    from app.models.scm import ProformaInvoicePackingLine

    unchanged = (
        db.query(ProformaInvoicePackingLine).filter(ProformaInvoicePackingLine.id == row.id).one()
    )
    assert unchanged.match_state == "unmatched"


def test_undo_dismiss_on_another_companys_row_is_404_and_changes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    company_a = as_company_user(app, db, gcu, gcuk, role=None)  # company A
    _supplier, invoice, row = _seed_one_packing_row(db)
    row.match_state = "dismissed"
    db.commit()

    client = _company_b_client(app, db, gcu, gcuk)  # company B

    r = client.delete(f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{row.id}/dismiss")
    assert r.status_code == 404, r.text

    from app.models.base import set_company_scope

    set_company_scope(db, company_a)
    db.expire_all()
    from app.models.scm import ProformaInvoicePackingLine

    unchanged = (
        db.query(ProformaInvoicePackingLine).filter(ProformaInvoicePackingLine.id == row.id).one()
    )
    assert unchanged.match_state == "dismissed"


def test_match_on_another_companys_row_is_404_and_changes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    company_a = as_company_user(app, db, gcu, gcuk, role=None)  # company A
    _supplier, invoice, row = _seed_one_packing_row(db)

    client = _company_b_client(app, db, gcu, gcuk)  # company B
    # A REAL product, visible under company B's OWN scope (seeded after the switch
    # above) - so the 404 this test checks for can only be the packing-row/invoice
    # lookup under the wrong company, never `_product_or_404` refusing a product id
    # that happens not to exist at all.
    from tests.scm.test_proforma_invoice_packing_lines import World

    product = World(db).product(f"ZZPIIDOR-{uuid.uuid4().hex[:8].upper()}")
    db.commit()

    r = client.post(
        f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{row.id}/match",
        json={"product_id": str(product.id)},
    )
    assert r.status_code == 404, r.text

    from app.models.base import set_company_scope

    set_company_scope(db, company_a)
    db.expire_all()
    from app.models.scm import ProformaInvoicePackingLine

    unchanged = (
        db.query(ProformaInvoicePackingLine).filter(ProformaInvoicePackingLine.id == row.id).one()
    )
    assert unchanged.product_id is None
    assert unchanged.proforma_invoice_line_id is None


@pytest.mark.parametrize("method", ["post_dismiss", "delete_dismiss", "post_match"])
def test_a_row_id_that_is_not_a_uuid_is_a_404_not_a_500(scm_app, method):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    _supplier, invoice, _row = _seed_one_packing_row(db)
    client = TestClient(app)

    bad_row_id = "not-a-uuid-at-all"
    if method == "post_dismiss":
        r = client.post(f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{bad_row_id}/dismiss")
    elif method == "delete_dismiss":
        r = client.delete(f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{bad_row_id}/dismiss")
    else:
        r = client.post(
            f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{bad_row_id}/match",
            json={"product_id": str(uuid.uuid4())},
        )
    assert r.status_code == 404, r.text


def test_an_invoice_id_that_is_not_a_uuid_is_also_a_404_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    _supplier, _invoice, row = _seed_one_packing_row(db)
    client = TestClient(app)

    r = client.post(f"/api/v1/scm/proforma-invoices/not-a-uuid-either/packing-lines/{row.id}/dismiss")
    assert r.status_code == 404, r.text
