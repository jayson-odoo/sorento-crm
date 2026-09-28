"""RED tests for the cost-price audit trail (#1288, Lane A, per #1281's standard).

Covers AC-AU-01, AC-AU-02, AC-AU-03 (`cost-price-lane-a-test-list.md`), against
`cost-price-api-contract.md` and plan section 9.

TEST-FIRST: nothing under test exists yet - see the module docstring of
`tests/test_cost_price_upload_routes.py` for why every import sits inside its test.
"""
from __future__ import annotations

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import (
    PS_EDIT_PERM,
    UPLOAD_PERM,
    VERIFY_PERM,
    VIEW_PERM,
    cost_price_env,
)


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
        return e.db.query(AuditLog).filter(AuditLog.new_values["event"].astext == action).count()

    assert _count("COST_SET_UPLOAD") == 1

    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text
    assert _count("COST_SET_SUBMIT") == 1

    # Return needs `verify` (contract 1.7) and refuses the uploader on their own set
    # (AC-S2-03), so a second person does it.
    verifier = e.user("procurement.cost_price_changes.verify", VIEW_PERM)
    e.as_user(verifier)
    returned = e.return_set(set_id, "please recheck")
    assert returned.status_code == 200, returned.text
    assert _count("COST_SET_RETURN") == 1

    e.as_user(uploader)
    resubmitted = e.submit(set_id)
    assert resubmitted.status_code == 200, resubmitted.text

    e.as_user(verifier)
    line_id = e.lines(set_id).json()["data"][0]["id"]
    e.decide(set_id, line_id, {"decision": "accepted"})

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text
    apply_row = e.db.query(AuditLog).filter(AuditLog.new_values["event"].astext == "COST_SET_APPLY").one()
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

    assert e.db.query(AuditLog).filter(AuditLog.new_values["event"].astext == "SUPPLIER_COST_LIST_EDIT").count() == 1


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

    apply_row = e.db.query(AuditLog).filter(AuditLog.new_values["event"].astext == "COST_SET_APPLY").one()
    trace_id = apply_row.trace_id
    assert trace_id

    touched = e.db.query(AuditLog).filter(
        AuditLog.entity_type.in_(("product_suppliers", "product_supplier_costs")),
        AuditLog.trace_id == trace_id,
    ).all()
    assert touched, "expected at least one product_suppliers/product_supplier_costs row on this trace"


# --------------------------------------------------------------------------------- AC-AU-04 / J14


def test_history_lists_line_decisions_and_maps(cost_price_env):
    """J14 ("... sees who uploaded, mapped, skipped, submitted, decided, returned and
    applied") + AC-AU-04 + contract 1.11: `GET /{id}/history` must carry one row per
    line map, per line skip, and per verifier decision (with the reason, for a reject) -
    not just the four SET-level events AC-AU-02 already covers. Today `patch_line()`
    writes no audit row for a manual map or a skip, and `decide()` writes no audit row
    at all, so none of `COST_LINE_MAP`, `COST_LINE_SKIP` or `COST_LINE_DECISION` ever
    appear in the history this endpoint returns - a reviewer who opens an applied set's
    History tab afterwards cannot see which line was rejected, by whom, or why (tester
    finding 1, browser evidence run)."""
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM, name="Uploader U")
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    accepted_product = e.product(code="ZZCPC-HIST-ACC")
    e.link(accepted_product, supplier, unit_cost=100, currency="CNY")
    rejected_product = e.product(code="ZZCPC-HIST-REJ")
    e.link(rejected_product, supplier, unit_cost=200, currency="CNY")
    mapped_product = e.product(code="ZZCPC-HIST-MAP")

    data = simple_price_list_workbook(
        [
            ("ZZCPC-HIST-ACC", "cfg", 110),
            ("ZZCPC-HIST-REJ", "cfg", 210),
            ("ZZCPC-HIST-UNMATCHED", "cfg", 50),
            ("ZZCPC-HIST-SKIP", "cfg", 60),
        ],
        letterhead=LETTERHEAD_TEXT,
    )
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]

    rows = e.lines(set_id).json()["data"]
    by_code = {r["supplier_code_raw"]: r for r in rows}
    accept_line = by_code["ZZCPC-HIST-ACC"]
    reject_line = by_code["ZZCPC-HIST-REJ"]
    unmatched_line = by_code["ZZCPC-HIST-UNMATCHED"]
    skip_line = by_code["ZZCPC-HIST-SKIP"]

    mapped = e.patch_line(set_id, unmatched_line["id"], {"product_id": str(mapped_product.id)})
    assert mapped.status_code == 200, mapped.text
    skipped = e.patch_line(set_id, skip_line["id"], {"skipped": True, "skip_reason": "duplicate row"})
    assert skipped.status_code == 200, skipped.text

    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text

    verifier = e.user(VERIFY_PERM, VIEW_PERM, name="Verifier V")
    e.as_user(verifier)
    accept_decision = e.decide(set_id, accept_line["id"], {"decision": "accepted"})
    assert accept_decision.status_code == 200, accept_decision.text
    reject_decision = e.decide(
        set_id, reject_line["id"], {"decision": "rejected", "reason": "price looks wrong"},
    )
    assert reject_decision.status_code == 200, reject_decision.text
    map_decision = e.decide(set_id, unmatched_line["id"], {"decision": "accepted"})
    assert map_decision.status_code == 200, map_decision.text

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text

    history = e.history(set_id)
    assert history.status_code == 200, history.text
    entries = history.json()["data"]
    actions = [row["action"] for row in entries]

    map_rows = [row for row in entries if row["action"] == "COST_LINE_MAP"]
    assert map_rows, f"expected a COST_LINE_MAP row, got actions {actions}"
    assert any("ZZCPC-HIST-UNMATCHED" in (row["summary"] or "") for row in map_rows), map_rows

    skip_rows = [row for row in entries if row["action"] == "COST_LINE_SKIP"]
    assert skip_rows, f"expected a COST_LINE_SKIP row, got actions {actions}"
    assert any("ZZCPC-HIST-SKIP" in (row["summary"] or "") for row in skip_rows), skip_rows

    decision_rows = [row for row in entries if row["action"] == "COST_LINE_DECISION"]
    assert len(decision_rows) >= 3, f"expected 3 COST_LINE_DECISION rows, got {decision_rows}"
    assert all(row["actor_name"] == "Verifier V" for row in decision_rows), decision_rows

    reject_rows = [row for row in decision_rows if "ZZCPC-HIST-REJ" in (row["summary"] or "")]
    assert reject_rows, f"expected a decision row naming ZZCPC-HIST-REJ, got {decision_rows}"
    reject_summary = reject_rows[0]["summary"] or ""
    assert "reject" in reject_summary.lower(), reject_summary
    assert "price looks wrong" in reject_summary, reject_summary

    accept_rows = [row for row in decision_rows if "ZZCPC-HIST-ACC" in (row["summary"] or "")]
    assert accept_rows, f"expected a decision row naming ZZCPC-HIST-ACC, got {decision_rows}"
    assert "accept" in (accept_rows[0]["summary"] or "").lower(), accept_rows
