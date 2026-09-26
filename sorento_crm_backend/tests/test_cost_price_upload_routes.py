"""RED tests for the cost-price change-set upload/review routes (#1288, Lane A).

Covers AC-S1-06 to AC-S1-14, AC-S1-17, AC-S1-18, AC-S1-23 (`cost-price-lane-a-test-list.md`),
against `cost-price-api-contract.md` sections 1.1 to 1.5, 1.9 and 1.10.

TEST-FIRST: none of `app/services/procurement/supplier_price_list_reader.py`,
`app/services/procurement/cost_price_change_service.py`, `app/models/cost_price.py` or the
`/api/v1/procurement/cost-price-changes` routes exist yet. Every route call below therefore
404s until the coder mounts them; every ORM seed of a not-yet-existing model is imported
inside the test body so it fails only that test.
"""
from __future__ import annotations

import io
import uuid

import openpyxl
import pytest

from tests.fixtures.cost_price.taiyang_shapes import (
    LETTERHEAD_TEXT,
    SEPARATOR_CODE_RAW,
    simple_price_list_workbook,
)
from tests.support.cost_price_env import (
    UPLOAD_PERM,
    VIEW_PERM,
    cost_price_env,
)


def _header_with_currency_token() -> bytes:
    """A one-sheet workbook whose 价格 header itself names the currency (AC-S1-07)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(5):
        ws.append([None, None, None, None])
    ws.cell(row=1, column=1, value=LETTERHEAD_TEXT)
    ws.append(["序号", "型号", "产品配置", "价格(RMB)"])
    ws.append([1, "ZZCPC-HDRCUR-001", "configuration", 100])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------------- AC-S1-06


def test_probe_suggests_the_one_supplier_named_in_the_letterhead(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    data = simple_price_list_workbook([("ZZCPC-A", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    r = e.probe(data)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggested_supplier"]["id"] == str(supplier.id)


def test_probe_suggests_nothing_when_zero_or_two_suppliers_match(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM)
    e.as_user(user)

    data = simple_price_list_workbook([("ZZCPC-A", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    zero = e.probe(data)
    assert zero.status_code == 200, zero.text
    assert zero.json()["suggested_supplier"] is None

    e.supplier(name=LETTERHEAD_TEXT)
    e.supplier(name=LETTERHEAD_TEXT)
    two = e.probe(data)
    assert two.status_code == 200, two.text
    assert two.json()["suggested_supplier"] is None


# --------------------------------------------------------------------------------- AC-S1-07


def test_currency_from_supplier_links(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product()
    e.link(product, supplier, unit_cost=50, currency="CNY")

    data = simple_price_list_workbook([("ZZCPC-A", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    r = e.probe(data)

    assert r.status_code == 200, r.text
    assert r.json()["currency"] == {"code": "CNY", "source": "supplier"}


def test_currency_header_token_wins(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product()
    e.link(product, supplier, unit_cost=50, currency="MYR")  # deliberately NOT CNY

    r = e.probe(_header_with_currency_token())

    assert r.status_code == 200, r.text
    assert r.json()["currency"] == {"code": "CNY", "source": "header"}


def test_currency_null_when_unresolved_and_upload_requires_it(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)  # brand new: no links yet

    data = simple_price_list_workbook([("ZZCPC-A", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    probe = e.probe(data)
    assert probe.status_code == 200, probe.text
    assert probe.json()["currency"] == {"code": None, "source": None}

    upload = e.upload(data, supplier_id=str(supplier.id), currency=None)
    assert upload.status_code == 422, upload.text
    assert upload.json().get("detail", {}).get("code") == "currency_required" or "currency" in upload.text


# --------------------------------------------------------------------------------- AC-S1-08


def test_upload_binds_with_the_shared_engine_remember_false(cost_price_env, monkeypatch):
    """Spies on the exact functions the PI apply calls (plan section 3.7), which the
    captain's test list pins as this AC's seam.

    CAVEAT the coder should reconcile if this goes red for the wrong reason: this
    monkeypatches the SOURCE modules
    (`app.services.scm.proforma_invoice_service._products_by_code`,
    `app.services.scm.supplier_code_matcher.resolve`). That only observes a caller that
    accesses them through the module (`proforma_invoice_service._products_by_code(...)`),
    not one that does `from ... import _products_by_code` into its own namespace at
    import time. If the coder's `cost_price_change_service` does the latter, move the
    patch target there instead of arguing the test is wrong about behaviour - the
    matching itself is what AC-S1-08 cares about.
    """
    import app.services.scm.proforma_invoice_service as pi_service
    import app.services.scm.supplier_code_matcher as matcher

    calls = {"products_by_code": 0, "resolve_kwargs": None}
    real_products_by_code = pi_service._products_by_code
    real_resolve = matcher.resolve

    def _spy_products_by_code(db, codes):
        calls["products_by_code"] += 1
        return real_products_by_code(db, codes)

    def _spy_resolve(db, supplier_id, codes, **kwargs):
        calls["resolve_kwargs"] = kwargs
        return real_resolve(db, supplier_id, codes, **kwargs)

    monkeypatch.setattr(pi_service, "_products_by_code", _spy_products_by_code)
    monkeypatch.setattr(matcher, "resolve", _spy_resolve)

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    exact_product = e.product(code="ZZCPC-EXACT-001")
    separator_product = e.product(code="CB2500SS-GY")

    data = simple_price_list_workbook(
        [
            ("ZZCPC-EXACT-001", "cfg exact", 100),
            (SEPARATOR_CODE_RAW, "cfg ladder", 110),
            ("ZZCPC-TOTALLY-UNKNOWN", "cfg unmatched", 120),
        ],
        letterhead=LETTERHEAD_TEXT,
    )
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]

    assert calls["products_by_code"] >= 1
    assert calls["resolve_kwargs"] is not None
    assert calls["resolve_kwargs"].get("remember") is False

    lines = e.lines(set_id).json()["data"]
    by_code = {ln["supplier_code"]: ln for ln in lines}
    assert by_code["ZZCPC-EXACT-001"]["match_outcome"] == "exact"
    assert by_code["ZZCPC-EXACT-001"]["product"]["id"] == str(exact_product.id)
    assert by_code["CB2500SS GY"]["match_outcome"] == "ladder"
    assert by_code["CB2500SS GY"]["match_rung"] == "separator"
    assert by_code["CB2500SS GY"]["product"]["id"] == str(separator_product.id)
    assert by_code["ZZCPC-TOTALLY-UNKNOWN"]["match_outcome"] == "unmatched"
    assert {ln["match_outcome"] for ln in lines} <= {"exact", "alias", "ladder", "manual", "unmatched"}


def test_upload_binds_a_recorded_alias(cost_price_env):
    from app.models.scm import SupplierProductCodeAlias

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-ALIAS-TARGET")
    e.db.add(SupplierProductCodeAlias(
        id=str(uuid.uuid4()), supplier_id=supplier.id, supplier_code="AL-RAW-CODE",
        product_id=product.id, source="manual", matched_by="manual",
    ))
    e.db.commit()

    data = simple_price_list_workbook([("AL-RAW-CODE", "cfg", 90)], letterhead=LETTERHEAD_TEXT)
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text

    lines = e.lines(r.json()["id"]).json()["data"]
    assert lines[0]["match_outcome"] == "alias"
    assert lines[0]["product"]["id"] == str(product.id)


# --------------------------------------------------------------------------------- AC-S1-09


def test_line_records_price_in_force_new_price_and_change_pct(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-CHG-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    data = simple_price_list_workbook([("ZZCPC-CHG-001", "cfg", 107)], letterhead=LETTERHEAD_TEXT)
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text

    line = e.lines(r.json()["id"]).json()["data"][0]
    assert line["current_unit_cost"] == 100.0
    assert line["current_currency"] == "CNY"
    assert line["new_unit_cost"] == 107.0
    assert line["change_pct"] == 7.0
    assert line["line_state"] == "changed"


def test_unlinked_product_is_new_link(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-NEWLINK-001")  # no ProductSupplier row seeded

    data = simple_price_list_workbook([("ZZCPC-NEWLINK-001", "cfg", 55)], letterhead=LETTERHEAD_TEXT)
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text

    line = e.lines(r.json()["id"]).json()["data"][0]
    assert line["line_state"] == "new_link"
    assert line["current_unit_cost"] is None


# --------------------------------------------------------------------------------- AC-S1-10


def test_two_lines_binding_one_product_are_both_duplicate(cost_price_env):
    from app.models.scm import SupplierProductCodeAlias

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-DUP-001")
    e.db.add(SupplierProductCodeAlias(
        id=str(uuid.uuid4()), supplier_id=supplier.id, supplier_code="DUP-ALIAS-CODE",
        product_id=product.id, source="manual", matched_by="manual",
    ))
    e.db.commit()

    data = simple_price_list_workbook(
        [("ZZCPC-DUP-001", "cfg", 100), ("DUP-ALIAS-CODE", "cfg", 100)],
        letterhead=LETTERHEAD_TEXT,
    )
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]

    lines = e.lines(set_id).json()["data"]
    assert len(lines) == 2
    for line in lines:
        assert "duplicate_code" in line["flags"], line

    blocked = e.apply(set_id)
    assert blocked.status_code == 422, blocked.text


# --------------------------------------------------------------------------------- AC-S1-11


def test_apply_refused_while_unmatched_or_needs_attention_line_unresolved(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    data = simple_price_list_workbook(
        [("ZZCPC-UNMATCHED-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT
    )
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text

    blocked = e.apply(r.json()["id"])
    assert blocked.status_code == 422, blocked.text
    body = blocked.json()
    assert body.get("detail", {}).get("code") == "unresolved_lines" or "1" in blocked.text


# --------------------------------------------------------------------------------- AC-S1-12


def test_manual_map_is_stored_and_aliases_written_only_on_apply(cost_price_env):
    from app.models.scm import SupplierProductCodeAlias

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    exact_product = e.product(code="ZZCPC-MANUAL-EXACT")
    manual_target = e.product(code="ZZCPC-MANUAL-TARGET")

    data = simple_price_list_workbook(
        [
            ("ZZCPC-MANUAL-EXACT", "cfg", 100),
            (SEPARATOR_CODE_RAW, "cfg", 110),
            ("ZZCPC-NEEDS-MANUAL-MAP", "cfg", 90),
        ],
        letterhead=LETTERHEAD_TEXT,
    )
    e.product(code="CB2500SS-GY")  # the separator-rung target
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]

    lines = e.lines(set_id).json()["data"]
    unmatched = next(ln for ln in lines if ln["supplier_code"] == "ZZCPC-NEEDS-MANUAL-MAP")

    mapped = e.patch_line(set_id, unmatched["id"], {"product_id": str(manual_target.id)})
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["line"]["match_outcome"] == "manual"

    before_apply = e.db.query(SupplierProductCodeAlias).filter_by(supplier_id=supplier.id).count()
    assert before_apply == 0

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text

    aliases = e.db.query(SupplierProductCodeAlias).filter_by(supplier_id=supplier.id).all()
    sources = {a.source for a in aliases}
    assert "manual" in sources
    assert "auto" in sources


def test_discarded_set_teaches_nothing(cost_price_env):
    from app.models.scm import SupplierProductCodeAlias

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    manual_target = e.product(code="ZZCPC-DISCARD-TARGET")

    data = simple_price_list_workbook(
        [("ZZCPC-DISCARD-UNMATCHED", "cfg", 90)], letterhead=LETTERHEAD_TEXT
    )
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]
    line_id = e.lines(set_id).json()["data"][0]["id"]
    e.patch_line(set_id, line_id, {"product_id": str(manual_target.id)})

    discard = e.discard(set_id)
    assert discard.status_code == 200, discard.text

    aliases = e.db.query(SupplierProductCodeAlias).filter_by(supplier_id=supplier.id).count()
    assert aliases == 0


# --------------------------------------------------------------------------------- AC-S1-13


def test_equal_price_without_dates_is_unchanged_and_never_applied(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-SAME-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    data = simple_price_list_workbook([("ZZCPC-SAME-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert r.status_code == 201, r.text

    line = e.lines(r.json()["id"]).json()["data"][0]
    assert line["line_state"] == "unchanged"


def test_equal_price_with_dates_is_changed(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-SAMEDATE-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    data = simple_price_list_workbook(
        [("ZZCPC-SAMEDATE-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT
    )
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY", start_date="2026-10-01")
    assert r.status_code == 201, r.text

    line = e.lines(r.json()["id"]).json()["data"][0]
    assert line["line_state"] == "changed"


# --------------------------------------------------------------------------------- AC-S1-14


def test_second_upload_for_supplier_with_open_set_is_409_naming_it(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    data = simple_price_list_workbook([("ZZCPC-FIRST-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    first = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert first.status_code == 201, first.text
    open_code = first.json()["code"]

    second = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["detail"]["open_set"]["code"] == open_code


# --------------------------------------------------------------------------------- AC-S1-15


def test_upload_refuses_wrong_type_and_too_many_rows_and_stores_nothing(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    wrong_type = e.upload(b"not excel", supplier_id=str(supplier.id), currency="CNY",
                           filename="list.csv")
    assert wrong_type.status_code == 422, wrong_type.text

    big_rows = [(f"ZZCPC-BIG-{i:05d}", "cfg", 100) for i in range(5001)]
    data = simple_price_list_workbook(big_rows, letterhead=LETTERHEAD_TEXT)
    too_many = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert too_many.status_code == 422, too_many.text

    listed = e.list_sets()
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


# --------------------------------------------------------------------------------- AC-S1-17


def test_multi_company_session_is_refused(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM)
    e.as_user(user, scope=frozenset({e.company_a, e.company_b}))

    data = simple_price_list_workbook([("ZZCPC-A", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    probe = e.probe(data)
    assert probe.status_code == 422, probe.text

    upload = e.upload(data, supplier_id=str(uuid.uuid4()), currency="CNY")
    assert upload.status_code == 422, upload.text


# --------------------------------------------------------------------------------- AC-S1-18


def test_source_file_retained_and_downloadable(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    data = simple_price_list_workbook([("ZZCPC-SRC-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY", filename="taiyang.xlsx")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]

    r = e.source_file(set_id)
    assert r.status_code == 200, r.text
    assert r.content == data
    assert "taiyang.xlsx" in r.headers.get("content-disposition", "")

    detail = e.detail(set_id).json()
    assert detail["file_name"] == "taiyang.xlsx"
    assert detail["sheets"]


# --------------------------------------------------------------------------------- AC-S1-23


def test_discard_hard_deletes_a_draft(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    data = simple_price_list_workbook([("ZZCPC-DEL-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]

    r = e.discard(set_id)
    assert r.status_code == 200, r.text

    gone = e.detail(set_id)
    assert gone.status_code == 404


def test_pending_or_applied_set_cannot_be_deleted(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-NODEL-001")
    e.link(product, supplier, unit_cost=90, currency="CNY")
    data = simple_price_list_workbook([("ZZCPC-NODEL-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    set_id = upload.json()["id"]

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text

    r = e.discard(set_id)
    assert r.status_code == 409, r.text


def test_discard_form_action_is_registered():
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE
    from app.services.form_action_registry import get_action

    action = get_action("cost_price_change_set.discard")
    assert action is not None
    assert action.entity_types == ("cost_price_change_set",)
    assert action.window == WINDOW_DESTRUCTIVE
    assert action.permission == UPLOAD_PERM
