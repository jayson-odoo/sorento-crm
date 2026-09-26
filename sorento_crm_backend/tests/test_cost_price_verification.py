"""RED tests for verification (S2, built now and switched off) - #1288, Lane A.

Covers AC-S2-20, AC-S2-01 to AC-S2-04, AC-S2-08 to AC-S2-12
(`cost-price-lane-a-test-list.md`), against `cost-price-api-contract.md` sections 1.7,
1.8 and 3. AC-S2-05 to AC-S2-07 and AC-S2-13 (the apply mechanics common to both paths)
are `tests/test_cost_price_apply.py`.

TEST-FIRST: nothing under test exists yet - see the module docstring of
`tests/test_cost_price_upload_routes.py` for why every import sits inside its test.
"""
from __future__ import annotations

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import (
    SETTINGS_EDIT_PERM,
    SETTINGS_VIEW_PERM,
    UPLOAD_PERM,
    VERIFY_PERM,
    VIEW_PERM,
    cost_price_env,
)


def _seed_pending(e, *, uploader, code="ZZCPC-VER-001", current=100, new=120):
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code=code)
    e.link(product, supplier, unit_cost=current, currency="CNY")
    data = simple_price_list_workbook([(code, "cfg", new)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]
    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text
    return set_id


# --------------------------------------------------------------------------------- AC-S2-20


def test_setting_column_defaults_false_and_reaches_both_serialisers(cost_price_env):
    from app.models.audit import AuditLog
    from app.models.user import SystemSetting

    e = cost_price_env
    e.seed_settings()  # no override: exercises the column's own default
    row = e.db.query(SystemSetting).one()
    assert row.cost_price_verification_enabled is False

    viewer = e.user(SETTINGS_VIEW_PERM)
    e.as_user(viewer)
    got = e.get_settings()
    assert got.status_code == 200, got.text
    assert got.json()["settings"]["cost_price_verification_enabled"] is False

    editor = e.user(SETTINGS_EDIT_PERM)
    e.as_user(editor)
    updated = e.put_settings({"cost_price_verification_enabled": True})
    assert updated.status_code == 200, updated.text

    assert e.db.query(AuditLog).filter(AuditLog.action == "COST_VERIFICATION_SETTING").count() == 1

    no_perm = e.user()
    e.as_user(no_perm)
    refused = e.put_settings({"cost_price_verification_enabled": False})
    assert refused.status_code == 403, refused.text


# --------------------------------------------------------------------------------- AC-S2-01


def test_verifier_decides_a_line_with_reason(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)
    line_id = e.lines(set_id).json()["data"][0]["id"]

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    r = e.decide(set_id, line_id, {"decision": "accepted", "reason": "looks right"})

    assert r.status_code == 200, r.text
    line = r.json()["line"]
    assert line["decision"] == "accepted"
    assert line["decided_by_name"]


def test_decide_all(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    p1 = e.product(code="ZZCPC-VDA-001")
    p2 = e.product(code="ZZCPC-VDA-002")
    e.link(p1, supplier, unit_cost=100, currency="CNY")
    e.link(p2, supplier, unit_cost=100, currency="CNY")
    data = simple_price_list_workbook(
        [("ZZCPC-VDA-001", "cfg", 110), ("ZZCPC-VDA-002", "cfg", 120)], letterhead=LETTERHEAD_TEXT
    )
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]
    e.submit(set_id)

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    r = e.decide_all(set_id, "accepted")
    assert r.status_code == 200, r.text

    lines = e.lines(set_id).json()["data"]
    assert lines and all(ln["decision"] == "accepted" for ln in lines)


# --------------------------------------------------------------------------------- AC-S2-02


def test_apply_pending_refused_with_undecided_lines(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    r = e.apply(set_id)

    assert r.status_code == 422, r.text
    assert r.json().get("detail", {}).get("code") == "undecided_lines"


# --------------------------------------------------------------------------------- AC-S2-03


def test_uploader_cannot_decide_return_or_apply_own_set(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM, VERIFY_PERM)
    set_id = _seed_pending(e, uploader=uploader)
    line_id = e.lines(set_id).json()["data"][0]["id"]

    e.as_user(uploader)
    for label, resp in [
        ("decide", e.decide(set_id, line_id, {"decision": "accepted"})),
        ("decide_all", e.decide_all(set_id, "accepted")),
        ("return", e.return_set(set_id, "not right")),
        ("apply", e.apply(set_id)),
    ]:
        assert resp.status_code == 403, (label, resp.text)


def test_uploader_cannot_apply_own_set_even_as_superadmin(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.superadmin()
    set_id = _seed_pending(e, uploader=uploader)

    e.as_user(uploader)
    r = e.apply(set_id)
    assert r.status_code == 403, r.text


def test_second_user_with_verify_can(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)
    line_id = e.lines(set_id).json()["data"][0]["id"]

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    decided = e.decide(set_id, line_id, {"decision": "accepted"})
    assert decided.status_code == 200, decided.text
    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text


# --------------------------------------------------------------------------------- AC-S2-04


def test_verification_on_apply_draft_is_409_submit_first(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-SUBFIRST-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")
    data = simple_price_list_workbook([("ZZCPC-SUBFIRST-001", "cfg", 120)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]

    r = e.apply(set_id)
    assert r.status_code == 409, r.text


def test_submit_moves_to_pending_with_submitter(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)

    detail = e.detail(set_id).json()
    assert detail["status"] == "pending_verification"
    assert detail["submitted_by_name"]
    assert detail["submitted_at"]


def test_verification_off_submit_is_409(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=False)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-NOVER-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")
    data = simple_price_list_workbook([("ZZCPC-NOVER-001", "cfg", 120)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]

    r = e.submit(set_id)
    assert r.status_code == 409, r.text


# --------------------------------------------------------------------------------- AC-S2-08


def test_apply_pending_marks_verified_with_verifier(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)
    line_id = e.lines(set_id).json()["data"][0]["id"]

    verifier = e.user(VERIFY_PERM, VIEW_PERM, name="Kelvin")
    e.as_user(verifier)
    e.decide(set_id, line_id, {"decision": "accepted"})
    r = e.apply(set_id)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["status"] == "applied"


# --------------------------------------------------------------------------------- AC-S2-09


def test_return_needs_reason_clears_decisions_back_to_draft(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)
    line_id = e.lines(set_id).json()["data"][0]["id"]

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    e.decide(set_id, line_id, {"decision": "accepted"})

    no_reason = e.return_set(set_id, "")
    assert no_reason.status_code == 422, no_reason.text

    ok = e.return_set(set_id, "prices look wrong, please recheck")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["status"] == "draft"
    assert body["returned_reason"]

    line_after = e.lines(set_id).json()["data"][0]
    assert line_after["decision"] is None


# --------------------------------------------------------------------------------- AC-S2-10


def test_applied_set_is_frozen(cost_price_env):
    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=False)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-FROZEN-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")
    data = simple_price_list_workbook([("ZZCPC-FROZEN-001", "cfg", 120)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]
    line_id = e.lines(set_id).json()["data"][0]["id"]
    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text

    assert e.patch_line(set_id, line_id, {"skipped": True}).status_code == 409
    assert e.submit(set_id).status_code == 409
    assert e.return_set(set_id, "too late").status_code == 409


# --------------------------------------------------------------------------------- AC-S2-11


def test_supplier_channel_set_is_pending_with_setting_off(cost_price_env):
    from app.models.cost_price import CostPriceChangeLine, CostPriceChangeSet

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-SUPCH-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    change_set = CostPriceChangeSet(
        code="CPC-ZZT-0001", supplier_id=supplier.id, channel="supplier_page",
        status="pending_verification", currency="CNY",
    )
    e.db.add(change_set)
    e.db.flush()
    e.db.add(CostPriceChangeLine(
        change_set_id=change_set.id, sheet="Prices", row_no=1, line_no="1",
        supplier_code_raw="ZZCPC-SUPCH-001", supplier_code="ZZCPC-SUPCH-001",
        configuration="cfg", match_outcome="exact", product_id=product.id,
        current_unit_cost=100, current_currency="CNY", new_unit_cost=120,
        line_state="changed",
    ))
    e.db.commit()
    set_id = str(change_set.id)

    upload_only = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(upload_only)
    assert e.apply(set_id).status_code == 403

    settings_editor = e.user(SETTINGS_EDIT_PERM)
    e.as_user(settings_editor)
    toggled = e.put_settings({"cost_price_verification_enabled": True})
    assert toggled.status_code == 200, toggled.text

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    still_pending = e.detail(set_id).json()
    assert still_pending["status"] == "pending_verification"

    e.decide_all(set_id, "accepted")
    r = e.apply(set_id)
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------------- AC-S2-12


def test_submit_notifies_every_verifier_once(cost_price_env):
    from app.models.notification import Notification

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    verifier_a = e.user(VERIFY_PERM, VIEW_PERM)
    verifier_b = e.user(VERIFY_PERM, VIEW_PERM)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)

    notified_ids = {
        n.user_id for n in
        e.db.query(Notification).filter(Notification.source_entity_id == set_id).all()
    }
    assert notified_ids == {verifier_a["id"], verifier_b["id"]}


def test_apply_and_return_notify_the_submitter(cost_price_env):
    from app.models.notification import Notification

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    set_id = _seed_pending(e, uploader=uploader)

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_user(verifier)
    r = e.return_set(set_id, "please recheck the price")
    assert r.status_code == 200, r.text

    notes = e.db.query(Notification).filter(
        Notification.source_entity_id == set_id, Notification.user_id == uploader["id"],
    ).all()
    assert len(notes) >= 1
