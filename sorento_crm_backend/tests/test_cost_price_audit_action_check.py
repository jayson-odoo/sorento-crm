"""Every cost-price audit write passes production's `audit_logs_action_check` (#1288, round 4).

Round 3's upload wrote `action='COST_SET_UPLOAD'`; the constraint migration 271 defines
admits only CREATE/READ/UPDATE/DELETE/IMPORT, so every real upload died with a
CheckViolation (a 500). The suite stayed green because `blank_session()` and CI's
`scripts.bootstrap_env` build `audit_logs` from the ORM model, which does not carry that
constraint. `cost_price_env` now installs it (`install_audit_action_check`), and these tests
drive each named event through the real routes and services against it. The event name
rides in `new_values["event"]`; the History endpoint surfaces it as `action`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import (
    AUDIT_ACTION_CHECK_MIGRATIONS,
    BASE,
    PS_ADD_PERM,
    PS_DELETE_PERM,
    PS_EDIT_PERM,
    SETTINGS_EDIT_PERM,
    UPLOAD_PERM,
    VERIFY_PERM,
    VIEW_PERM,
    admitted_audit_actions,
    cost_price_env,
)

ADMITTED = {"CREATE", "READ", "UPDATE", "DELETE", "IMPORT", "EVENT"}


def test_only_the_known_migrations_define_the_action_check():
    """The fixture copies the constraint from its newest definition (aud_0001, main's audit
    backbone #1299, which superseded 271); a later migration redefining it would make that
    copy stale, so this names the files to update when that happens."""
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    defining = sorted(p.name for p in versions.glob("*.py") if "audit_logs_action_check" in p.read_text())
    assert defining == sorted(AUDIT_ACTION_CHECK_MIGRATIONS)
    assert {a.strip("'") for a in admitted_audit_actions().strip("()").split(",")} == ADMITTED


def test_fixture_carries_the_real_constraint(cost_price_env):
    from sqlalchemy import text

    e = cost_price_env
    definition = e.db.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'audit_logs_action_check' AND conrelid = 'audit_logs'::regclass"
    )).scalar()
    assert definition and "IMPORT" in definition


def test_upload_writes_an_admitted_import_row(cost_price_env):
    """The owner's round 3 failure: POST /cost-price-changes answered 500."""
    from app.models.audit import AuditLog

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    e.as_user(e.user(UPLOAD_PERM, VIEW_PERM))
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    e.link(e.product(code="ZZCPC-CHK-001"), supplier, unit_cost=100, currency="CNY")

    data = simple_price_list_workbook([("ZZCPC-CHK-001", "cfg", 120)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]

    row = e.db.query(AuditLog).filter(
        AuditLog.entity_type == "cost_price_change_sets", AuditLog.entity_id == set_id,
        AuditLog.new_values["event"].astext == "COST_SET_UPLOAD",
    ).one()
    assert row.action == "IMPORT"
    assert row.new_values["rows"] == 1
    assert row.new_values["file_name"]

    history = e.history(set_id).json()["data"]
    assert "COST_SET_UPLOAD" in [h["action"] for h in history]


def test_every_named_event_writes_an_admitted_action(cost_price_env):
    from app.models.audit import AuditLog
    from app.models.cost_price import ProductSupplierCost
    from app.services.procurement.supplier_cost_service import refresh_prices_in_force

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM, SETTINGS_EDIT_PERM, PS_ADD_PERM, PS_EDIT_PERM, PS_DELETE_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    link = e.link(e.product(code="ZZCPC-EVT-ACC"), supplier, unit_cost=100, currency="CNY")
    mapped_product = e.product(code="ZZCPC-EVT-MAP")

    data = simple_price_list_workbook(
        [("ZZCPC-EVT-ACC", "cfg", 110), ("ZZCPC-EVT-UNM", "cfg", 50), ("ZZCPC-EVT-SKIP", "cfg", 60)],
        letterhead=LETTERHEAD_TEXT,
    )
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]
    by_code = {r["supplier_code_raw"]: r for r in e.lines(set_id).json()["data"]}

    assert e.client.post(f"{BASE}/{set_id}/refresh-prices").status_code == 200
    assert e.patch_line(set_id, by_code["ZZCPC-EVT-UNM"]["id"], {"product_id": str(mapped_product.id)}).status_code == 200
    assert e.patch_line(set_id, by_code["ZZCPC-EVT-SKIP"]["id"], {"skipped": True}).status_code == 200
    assert e.submit(set_id).status_code == 200

    e.as_user(e.user(VERIFY_PERM, VIEW_PERM))
    assert e.decide(set_id, by_code["ZZCPC-EVT-ACC"]["id"], {"decision": "accepted"}).status_code == 200
    assert e.decide_all(set_id, "accepted").status_code == 200
    assert e.apply(set_id).status_code == 200, "apply"

    e.as_user(uploader)
    added = e.post_cost(link.id, {"unit_cost": 90.0, "currency": "CNY", "start_date": None, "end_date": None})
    assert added.status_code == 201, added.text
    cost_id = added.json()["id"]
    assert e.put_cost(link.id, cost_id, {"unit_cost": 95.0}).status_code == 200
    assert e.delete_cost(link.id, cost_id).status_code in (200, 204)
    assert e.put_settings({"cost_price_verification_enabled": False}).status_code == 200

    today = date(2026, 9, 28)
    e.db.add(ProductSupplierCost(
        product_supplier_id=link.id, unit_cost=Decimal("70.00"), currency="CNY", start_date=today,
    ))
    e.db.commit()
    assert refresh_prices_in_force(e.db, today) >= 1

    rows = e.db.query(AuditLog).all()
    assert {r.action for r in rows} <= ADMITTED
    events = {(r.new_values or {}).get("event") for r in rows}
    assert {
        "COST_SET_UPLOAD", "COST_SET_REFRESH_PRICES", "COST_LINE_MAP", "COST_LINE_SKIP",
        "COST_SET_SUBMIT", "COST_LINE_DECISION", "COST_SET_APPLY", "SUPPLIER_COST_LIST_EDIT",
        "COST_VERIFICATION_SETTING", "SUPPLIER_COST_TICK",
    } <= events


def test_return_writes_an_admitted_action(cost_price_env):
    from app.models.audit import AuditLog

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    e.as_user(e.user(UPLOAD_PERM, VIEW_PERM))
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    e.link(e.product(code="ZZCPC-RET-001"), supplier, unit_cost=100, currency="CNY")
    data = simple_price_list_workbook([("ZZCPC-RET-001", "cfg", 120)], letterhead=LETTERHEAD_TEXT)
    set_id = e.upload(data, supplier_id=str(supplier.id), currency="CNY").json()["id"]
    assert e.submit(set_id).status_code == 200

    e.as_user(e.user(VERIFY_PERM, VIEW_PERM))
    returned = e.return_set(set_id, "please recheck")
    assert returned.status_code == 200, returned.text

    row = e.db.query(AuditLog).filter(AuditLog.new_values["event"].astext == "COST_SET_RETURN").one()
    assert row.action == "UPDATE"
