"""RED tests for the cost-price audit trail (#1288, Lane A, per #1281's standard).

Covers AC-AU-01, AC-AU-02, AC-AU-03 (`cost-price-lane-a-test-list.md`), against
`cost-price-api-contract.md` and plan section 9.

TEST-FIRST: nothing under test exists yet - see the module docstring of
`tests/test_cost_price_upload_routes.py` for why every import sits inside its test.
"""
from __future__ import annotations

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import PS_EDIT_PERM, UPLOAD_PERM, VIEW_PERM, cost_price_env


# --------------------------------------------------------------------------------- AC-AU-01


def test_new_tables_and_product_suppliers_are_audit_tracked():
    from app.models.cost_price import (
        CostPriceChangeLine,
        CostPriceChangeSet,
        ProductSupplierCost,
        SupplierPriceLink,
    )
    from app.models.procurement import ProductSupplier

    for model in (
        ProductSupplierCost, CostPriceChangeSet, CostPriceChangeLine,
        SupplierPriceLink, ProductSupplier,
    ):
        assert getattr(model, "__audit_track__", False) is True, model.__name__


# --------------------------------------------------------------------------------- AC-AU-02


def test_named_events_written_for_upload_apply_submit_return(cost_price_env):
    from app.models.audit import AuditLog

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-AUDIT-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    data = simple_price_list_workbook([("ZZCPC-AUDIT-001", "cfg", 120)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]

    def _count(action):
        return e.db.query(AuditLog).filter(AuditLog.action == action).count()

    assert _count("COST_SET_UPLOAD") == 1

    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text
    assert _count("COST_SET_SUBMIT") == 1

    returned = e.return_set(set_id, "please recheck")
    assert returned.status_code == 200, returned.text
    assert _count("COST_SET_RETURN") == 1

    resubmitted = e.submit(set_id)
    assert resubmitted.status_code == 200, resubmitted.text

    verifier = e.user("procurement.cost_price_changes.verify", VIEW_PERM)
    e.as_user(verifier)
    line_id = e.lines(set_id).json()["data"][0]["id"]
    e.decide(set_id, line_id, {"decision": "accepted"})

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text
    apply_row = e.db.query(AuditLog).filter(AuditLog.action == "COST_SET_APPLY").one()
    new_values = apply_row.new_values or {}
    assert new_values.get("verified") is True
    assert new_values.get("changes") or new_values.get("lines")


def test_named_event_written_for_hand_edit(cost_price_env):
    from app.models.audit import AuditLog

    e = cost_price_env
    editor = e.user(PS_EDIT_PERM)
    e.as_user(editor)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier)

    r = e.post_cost(link.id, {"unit_cost": 90.0, "currency": "CNY", "start_date": None, "end_date": None})
    assert r.status_code == 201, r.text

    assert e.db.query(AuditLog).filter(AuditLog.action == "SUPPLIER_COST_LIST_EDIT").count() == 1


# --------------------------------------------------------------------------------- AC-AU-03


def test_apply_audit_rows_share_one_trace_id(cost_price_env):
    from app.models.audit import AuditLog

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=False)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-TRACE-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    data = simple_price_list_workbook([("ZZCPC-TRACE-001", "cfg", 130)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text

    apply_row = e.db.query(AuditLog).filter(AuditLog.action == "COST_SET_APPLY").one()
    trace_id = apply_row.trace_id
    assert trace_id

    touched = e.db.query(AuditLog).filter(
        AuditLog.entity_type.in_(("product_suppliers", "product_supplier_costs")),
        AuditLog.trace_id == trace_id,
    ).all()
    assert touched, "expected at least one product_suppliers/product_supplier_costs row on this trace"
