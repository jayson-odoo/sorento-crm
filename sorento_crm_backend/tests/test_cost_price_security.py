"""RED tests for the cost price security review findings (#1288, Lane A).

Written BEFORE the coder's fixes, against the implementation as it stands after the S1/S2
slices (`app/services/procurement/cost_price_change_service.py`,
`app/services/procurement/supplier_price_list_reader.py`,
`app/api/v1/procurement/cost_price_changes.py`). Every finding below was confirmed by
reading that code, not guessed: the module docstring on each test names the exact line/gap.

Uses `tests.support.cost_price_env` (the same harness the rest of this lane's backend
suite uses) - see that module's own docstring for why `blank_session()` and why every
seed carries the `ZZCPC` marker.
"""
from __future__ import annotations

import io
import uuid
import zipfile

import pytest

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import (
    PS_EDIT_PERM,
    UPLOAD_PERM,
    VERIFY_PERM,
    VIEW_PERM,
    cost_price_env,
)


def _upload_one_line(e, supplier, code, price, **kwargs) -> dict:
    data = simple_price_list_workbook([(code, "cfg", price)], letterhead=LETTERHEAD_TEXT)
    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY", **kwargs)
    assert r.status_code == 201, r.text
    return r.json()


# ============================================================ B1: cross-company product refs
#
# `patch_line` (cost_price_change_service.py ~line 685) sets `line.product_id = body[
# "product_id"]` with NO check that the id names a real product in the caller's own
# company - and `apply` (~line 934) looks the link up by `(supplier_id, product_id)` alone,
# so a line bound this way would create a REAL `ProductSupplier` row (company-stamped to the
# CALLER's company) whose `product_id` FK points at another company's product.


def test_map_to_other_companys_product_is_422(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    foreign_product = e.product_in_company(e.company_b, code="ZZCPC-FOREIGN-001")
    uploaded = _upload_one_line(e, supplier, "ZZCPC-SEC-UNMATCHED-001", 100)
    set_id = uploaded["id"]
    line = e.lines(set_id).json()["data"][0]

    r = e.patch_line(set_id, line["id"], {"product_id": str(foreign_product.id)})
    assert r.status_code == 422, r.text

    refreshed = e.lines(set_id).json()["data"][0]
    assert refreshed["product"] is None
    assert refreshed["match_outcome"] == "unmatched"


def test_map_to_non_uuid_product_is_422(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    uploaded = _upload_one_line(e, supplier, "ZZCPC-SEC-UNMATCHED-002", 100)
    set_id = uploaded["id"]
    line = e.lines(set_id).json()["data"][0]

    r = e.patch_line(set_id, line["id"], {"product_id": "not-a-uuid-at-all"})
    assert r.status_code == 422, r.text


def test_apply_refuses_line_bound_to_foreign_product(cost_price_env):
    from app.models.cost_price import CostPriceChangeLine, ProductSupplierCost
    from app.models.procurement import ProductSupplier
    from app.models.scm import SupplierProductCodeAlias

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    foreign_product = e.product_in_company(e.company_b, code="ZZCPC-FOREIGN-002")
    uploaded = _upload_one_line(e, supplier, "ZZCPC-SEC-UNMATCHED-003", 100)
    set_id = uploaded["id"]
    line_id = e.lines(set_id).json()["data"][0]["id"]

    # Seeded directly in the DB - B1's first two tests already pin PATCH's own gate;
    # Apply must refuse this independently, in case a line ever carries a foreign
    # `product_id` some other way (a future channel, a data-repair script).
    db_line = e.db.query(CostPriceChangeLine).filter_by(id=line_id).one()
    db_line.product_id = foreign_product.id
    db_line.match_outcome = "manual"
    db_line.line_state = "new_link"
    # A `new_link` line with no lead time and no supplier default would ALSO be blocked
    # by `lead_time_required` (AC-S2-05) - a different check, satisfied here so the ONLY
    # refusal Apply can raise is the one this test pins.
    db_line.new_link_lead_time_days = 45
    e.db.commit()

    r = e.apply(set_id)
    assert r.status_code == 422, r.text
    assert r.json().get("code") == "invalid_product", r.text

    assert e.db.query(ProductSupplier).filter_by(product_id=foreign_product.id).count() == 0
    assert e.db.query(ProductSupplierCost).count() == 0
    assert e.db.query(SupplierProductCodeAlias).filter_by(supplier_id=supplier.id).count() == 0


# ============================================================================== B2: impersonation
#
# Every audit/created_by write in cost_price_change_service.py uses `current_user.get("id")`
# directly - never `app.dependencies.get_actor_user_id(request, current_user)` - and
# `_assert_not_same_person` (~line 405) compares ONLY that same effective id against
# `created_by_user_id`/`submitted_by_user_id`. An admin who uploads a set, then impersonates
# a DIFFERENT verify-holder, is therefore nobody's "same person" under that check and can
# apply their own upload wearing someone else's identity.


def test_impersonated_verifier_cannot_apply_own_upload(cost_price_env):
    from app.models.audit import AuditLog

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    admin = e.superadmin()
    e.as_user(admin)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-IMP-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")
    uploaded = _upload_one_line(e, supplier, "ZZCPC-IMP-001", 120)
    set_id = uploaded["id"]

    upload_audit = e.db.query(AuditLog).filter(AuditLog.action == "COST_SET_UPLOAD").one()
    assert upload_audit.user_id == admin["id"]

    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text

    verifier = e.user(VERIFY_PERM, VIEW_PERM)
    e.as_impersonated(admin, verifier)  # admin, wearing the verifier's identity
    line_id = e.lines(set_id).json()["data"][0]["id"]

    decided = e.decide(set_id, line_id, {"decision": "accepted"})
    assert decided.status_code == 403, decided.text
    assert decided.json().get("code") == "SAME_PERSON_CANNOT_VERIFY"

    applied = e.apply(set_id)
    assert applied.status_code == 403, applied.text
    assert applied.json().get("code") == "SAME_PERSON_CANNOT_VERIFY"


# ==================================================================== S1: returned supplier set
#
# `submit()` (~line 748) refuses with `verification_off` whenever the GLOBAL setting is off,
# with no exception for `channel == 'supplier_page'`; `apply()`'s `draft` branch (~line 897)
# checks the same global toggle, also with no channel exception. Both contradict AC-S2-11 /
# plan section 7.2 ("a supplier's submission always waits for a Sorento verifier, whatever
# the setting"): a RETURNED supplier-channel set (status back to `draft`) must still refuse
# a direct Apply and must still be resubmittable, even with the global setting off.


def test_returned_supplier_set_cannot_be_applied_as_draft(cost_price_env):
    from app.models.cost_price import CostPriceChangeLine, CostPriceChangeSet

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-RETSUP-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")

    change_set = CostPriceChangeSet(
        code="CPC-ZZT-RET1", supplier_id=supplier.id, channel="supplier_page",
        status="pending_verification", currency="CNY",
    )
    e.db.add(change_set)
    e.db.flush()
    e.db.add(CostPriceChangeLine(
        change_set_id=change_set.id, sheet="Prices", row_no=1, line_no="1",
        supplier_code_raw="ZZCPC-RETSUP-001", supplier_code="ZZCPC-RETSUP-001",
        configuration="cfg", match_outcome="exact", product_id=product.id,
        current_unit_cost=100, current_currency="CNY", new_unit_cost=130,
        line_state="changed",
    ))
    e.db.commit()
    set_id = str(change_set.id)

    verifier = e.user(VERIFY_PERM, VIEW_PERM, UPLOAD_PERM)
    e.as_user(verifier)
    returned = e.return_set(set_id, "please recheck the price")
    assert returned.status_code == 200, returned.text
    assert e.detail(set_id).json()["status"] == "draft"

    applied = e.apply(set_id)
    assert applied.status_code == 409, applied.text
    assert applied.json().get("code") == "submit_first"

    resubmitted = e.submit(set_id)
    assert resubmitted.status_code == 200, resubmitted.text
    assert e.detail(set_id).json()["status"] == "pending_verification"


# ===================================================================== S2: unsafe file handling
#
# `read_supplier_price_list` (supplier_price_list_reader.py ~line 175) checks the ON-DISK
# (compressed) byte count against `_MAX_FILE_BYTES` and the filename extension, then calls
# `openpyxl.load_workbook` directly - nothing inspects the ZIP's OWN declared uncompressed
# size or a macro-project member first. A small, highly-compressible zip (real 80MB of
# zero bytes compresses to roughly 80KB - see the assertion below) sails through the size
# cap and hands openpyxl tens of megabytes to decompress; a `.xlsx`-renamed macro workbook
# (an `xl/vbaProject.bin` member) sails through the extension check too.


def _zip_bomb_bytes(uncompressed_mb: int = 80) -> bytes:
    buf = io.BytesIO()
    payload = b"\x00" * (uncompressed_mb * 1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", payload)
    return buf.getvalue()


def test_upload_refuses_zip_bomb_before_loading(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    data = _zip_bomb_bytes()
    assert len(data) < 1_000_000, "fixture must stay small on disk"

    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY", filename="bomb.xlsx")
    assert r.status_code == 422, r.text
    assert r.json().get("code") == "file_too_large"


def _macro_workbook_bytes() -> bytes:
    base = simple_price_list_workbook([("ZZCPC-MACRO-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("xl/vbaProject.bin", b"fake macro bytes, not a real OLE stream")
    return buf.getvalue()


def test_macro_workbook_renamed_xlsx_is_refused(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)

    r = e.upload(_macro_workbook_bytes(), supplier_id=str(supplier.id), currency="CNY", filename="list.xlsx")
    assert r.status_code == 422, r.text
    assert r.json().get("code") == "file_type"


# ============================================================== S3: source-file download header
#
# `download_source_file` (`app/api/v1/procurement/cost_price_changes.py` ~line 186) builds
# `Content-Disposition` with a bare f-string: `f'attachment; filename="{filename}"'`, no
# RFC 5987 `filename*=` fallback for non-ASCII (a raw CJK byte in an HTTP header value is
# invalid and raises before headers can even be encoded to latin-1) and no escaping of a
# literal `"` in the name (a name containing one can close the quoted string early and open
# a second `filename=` parameter of the attacker's choosing).


def test_source_file_download_with_chinese_filename(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    data = simple_price_list_workbook([("ZZCPC-FN-CN-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)

    uploaded = e.upload(data, supplier_id=str(supplier.id), currency="CNY", filename="报价单 20260926.xlsx")
    assert uploaded.status_code == 201, uploaded.text

    r = e.source_file(uploaded.json()["id"])
    assert r.status_code == 200, r.text
    disposition = r.headers.get("content-disposition", "")
    assert "filename*=UTF-8''" in disposition, disposition


def test_source_file_download_with_a_quote_in_the_filename_cannot_inject_a_second_parameter(cost_price_env):
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    data = simple_price_list_workbook([("ZZCPC-FN-Q-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    evil_name = 'x"; filename="evil.exe.xlsx'

    uploaded = e.upload(data, supplier_id=str(supplier.id), currency="CNY", filename=evil_name)
    assert uploaded.status_code == 201, uploaded.text

    r = e.source_file(uploaded.json()["id"])
    assert r.status_code == 200, r.text
    disposition = r.headers.get("content-disposition", "")
    assert disposition.count("filename=") <= 1, disposition


def test_source_file_download_with_a_long_filename_is_truncated_not_a_500(cost_price_env):
    """A name over 255 chars (`file_name` is `VARCHAR(255)`) is truncated to at most 255,
    keeping the `.xlsx` extension - not a 500 at commit."""
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    data = simple_price_list_workbook([("ZZCPC-FN-LONG-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    long_name = ("a" * 300) + ".xlsx"  # 305 chars, well over the 255 column limit
    assert len(long_name) > 255

    uploaded = e.upload(data, supplier_id=str(supplier.id), currency="CNY", filename=long_name)
    assert uploaded.status_code == 201, uploaded.text
    set_id = uploaded.json()["id"]

    detail = e.detail(set_id).json()
    assert len(detail["file_name"]) <= 255
    assert detail["file_name"].endswith(".xlsx")

    r = e.source_file(set_id)
    assert r.status_code == 200, r.text


# ============================================================================ S4: deferred column
#
# `CostPriceChangeSet.source_file_bytes` (`app/models/cost_price.py`) is a plain
# `Column(LargeBinary, ...)`, not wrapped in `deferred(...)` - so `GET /` (the list) and
# every ORM read of the set touches the raw spreadsheet bytes on every row, not just the one
# download route that actually needs them.


def test_source_bytes_column_is_deferred():
    from app.models.cost_price import CostPriceChangeSet

    prop = CostPriceChangeSet.__mapper__.column_attrs.get("source_file_bytes")
    assert prop is not None, "source_file_bytes is not even a mapped column"
    assert prop.deferred is True, "source_file_bytes loads eagerly on every query"


# ======================================================================= S5: the line mapper
#
# `_assert_not_same_person` only ever compares against `created_by_user_id`/
# `submitted_by_user_id` - never against any line's `mapped_by_user_id`. Someone who
# remapped an unmatched code to a product (deciding which product gets the new price) is
# not neutral either, and today they can still verify and apply the very set they steered.
# `patch_line` also never sets `mapped_by_user_id` at all (AC-S1-12's own field).


def test_line_mapper_cannot_verify_the_set(cost_price_env):
    from app.models.cost_price import CostPriceChangeLine

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    a = e.user(UPLOAD_PERM, VIEW_PERM, name="A")
    e.as_user(a)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    manual_target = e.product(code="ZZCPC-MAPPER-TARGET")
    uploaded = _upload_one_line(e, supplier, "ZZCPC-MAPPER-UNMATCHED-001", 90)
    set_id = uploaded["id"]
    line = e.lines(set_id).json()["data"][0]

    v = e.user(UPLOAD_PERM, VERIFY_PERM, VIEW_PERM, name="V")
    e.as_user(v)
    mapped = e.patch_line(set_id, line["id"], {"product_id": str(manual_target.id)})
    assert mapped.status_code == 200, mapped.text

    e.as_user(a)
    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text

    e.as_user(v)
    line_id = e.lines(set_id).json()["data"][0]["id"]
    decided = e.decide(set_id, line_id, {"decision": "accepted"})
    assert decided.status_code == 403, decided.text
    assert decided.json().get("code") == "SAME_PERSON_CANNOT_VERIFY"

    applied = e.apply(set_id)
    assert applied.status_code == 403, applied.text

    db_line = e.db.query(CostPriceChangeLine).filter_by(id=line["id"]).one()
    assert db_line.mapped_by_user_id == v["id"]


# ===================================================================================== Nits


def test_verifier_notifications_stay_in_company(cost_price_env):
    """`_verifier_user_ids` (cost_price_change_service.py ~line 730) queries every user
    holding `verify`, company-unfiltered - a verify-holder with no `user_companies` grant
    for the set's own company still gets notified today."""
    from app.models.notification import Notification

    e = cost_price_env
    e.seed_settings(cost_price_verification_enabled=True)
    outsider = e.user(VERIFY_PERM, VIEW_PERM)  # no user_companies row for company_a at all
    uploader = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(uploader)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-NOTIFY-SCOPE-001")
    e.link(product, supplier, unit_cost=100, currency="CNY")
    uploaded = _upload_one_line(e, supplier, "ZZCPC-NOTIFY-SCOPE-001", 120)
    set_id = uploaded["id"]

    submitted = e.submit(set_id)
    assert submitted.status_code == 200, submitted.text

    notified_ids = {
        n.user_id for n in
        e.db.query(Notification).filter(Notification.source_entity_id == set_id).all()
    }
    assert outsider["id"] not in notified_ids


def test_remap_of_alias_bound_line_applies(cost_price_env):
    """A line bound through an EXISTING alias, then remapped by hand to a different
    product, must apply cleanly and leave the alias pointing at the new product - not
    500 on the unique (company, supplier, code) index when Apply tries to insert a SECOND
    `auto`/`manual` row for a code an alias already answers."""
    from app.models.scm import SupplierProductCodeAlias

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    original_target = e.product(code="ZZCPC-REMAP-ORIGINAL")
    new_target = e.product(code="ZZCPC-REMAP-NEW")
    # A lead time for this supplier already exists (AC-S2-05), so remapping to a product
    # with no link of its own does not ALSO trip `lead_time_required` - a different,
    # already-covered gap (`test_new_link_without_default_needs_lead_time`), not this one.
    e.link(e.product(code="ZZCPC-REMAP-LEADTIME-SEED"), supplier, lead_time_days=30)
    e.db.add(SupplierProductCodeAlias(
        id=str(uuid.uuid4()), supplier_id=supplier.id, supplier_code="REMAP-RAW-CODE",
        product_id=original_target.id, source="manual", matched_by="manual",
    ))
    e.db.commit()

    data = simple_price_list_workbook([("REMAP-RAW-CODE", "cfg", 90)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]
    line = e.lines(set_id).json()["data"][0]
    assert line["match_outcome"] == "alias"
    assert line["product"]["id"] == str(original_target.id)

    remapped = e.patch_line(set_id, line["id"], {"product_id": str(new_target.id)})
    assert remapped.status_code == 200, remapped.text

    applied = e.apply(set_id)
    assert applied.status_code == 200, applied.text

    alias = (
        e.db.query(SupplierProductCodeAlias)
        .filter_by(supplier_id=supplier.id, supplier_code="REMAP-RAW-CODE")
        .one()
    )
    assert str(alias.product_id) == str(new_target.id)


def test_negative_lead_time_is_422(cost_price_env):
    """`patch_line` stores `new_link_lead_time_days` with no bound check at all."""
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    uploaded = _upload_one_line(e, supplier, "ZZCPC-NEGLEAD-001", 90)  # new_link, no existing links
    set_id = uploaded["id"]
    line_id = e.lines(set_id).json()["data"][0]["id"]

    r = e.patch_line(set_id, line_id, {"new_link_lead_time_days": -5})
    assert r.status_code == 422, r.text


def test_bad_start_date_on_upload_is_422(cost_price_env):
    """`upload()` does `date.fromisoformat(start_date)` with no try/except (~line 323)."""
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    data = simple_price_list_workbook([("ZZCPC-BADDATE-001", "cfg", 90)], letterhead=LETTERHEAD_TEXT)

    r = e.upload(data, supplier_id=str(supplier.id), currency="CNY", start_date="not-a-date")
    assert r.status_code == 422, r.text


def test_bad_start_date_on_cost_edit_is_422(cost_price_env):
    """`create_cost` does the same unguarded `date.fromisoformat` (supplier_cost_service.py
    ~line 167)."""
    e = cost_price_env
    editor = e.user(PS_EDIT_PERM)
    e.as_user(editor)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier)

    r = e.post_cost(link.id, {"unit_cost": 90.0, "currency": "CNY", "start_date": "not-a-date"})
    assert r.status_code == 422, r.text


def test_currency_longer_than_3_chars_is_422(cost_price_env):
    """`currency` is stored as-is with no length check; the column is `VARCHAR(3)`, so
    Postgres itself refuses it, uncaught, as a 500."""
    e = cost_price_env
    editor = e.user(PS_EDIT_PERM)
    e.as_user(editor)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier)

    r = e.post_cost(link.id, {"unit_cost": 90.0, "currency": "TOOLONG", "start_date": None, "end_date": None})
    assert r.status_code == 422, r.text


def test_non_uuid_set_id_on_apply_is_422(cost_price_env):
    """No route in this file except `GET /{id}` calls `validate_uuid_path` - `apply`'s
    `_get_set_or_404` runs the malformed id straight into a `WHERE id = :set_id` against a
    UUID column."""
    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)

    r = e.apply("not-a-uuid-at-all")
    assert r.status_code == 422, r.text


def test_settings_verification_enabled_null_is_422(cost_price_env):
    """`cost_price_verification_enabled` is NOT NULL; PUT .../general's generic
    `setattr(settings, key, value)` loop applies a literal JSON `null` straight through and
    Postgres refuses it as a 500, not a 422."""
    e = cost_price_env
    e.seed_settings()
    editor = e.user("user_management.settings.edit")
    e.as_user(editor)

    r = e.put_settings({"cost_price_verification_enabled": None})
    assert r.status_code == 422, r.text


def test_migration_downgrade_removes_only_the_new_slugs():
    """Static source read (running the migration is exercised elsewhere,
    `test_cost_price_permissions.py`): `downgrade()` must delete exactly the 8 slugs
    `_NEW_PERMS` names, and nothing naming an existing role or an unrelated permission."""
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "cpc1_supplier_cost_lists.py"
    source = path.read_text()

    tree = ast.parse(source)
    new_perms_slugs = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_NEW_PERMS" for t in node.targets
        ):
            new_perms_slugs = [elt.elts[0].value for elt in node.value.elts]
    assert new_perms_slugs, "could not find _NEW_PERMS in the migration"

    expected = {
        "procurement.cost_price_changes.upload",
        "procurement.cost_price_changes.view",
        "procurement.cost_price_changes.verify",
        "procurement.suppliers.price_link",
        "procurement.product_suppliers.view",
        "procurement.product_suppliers.add",
        "procurement.product_suppliers.edit",
        "procurement.product_suppliers.delete",
    }
    assert set(new_perms_slugs) == expected

    downgrade_src = source[source.index("def downgrade"):]
    assert "DELETE FROM user_role_permissions" in downgrade_src
    assert "DELETE FROM user_permissions WHERE slug = ANY(:slugs)" in downgrade_src
    assert "_NEW_PERMS" in downgrade_src
    assert "scm.proforma_invoice.upload" not in downgrade_src
    assert "'admin'" not in downgrade_src
    assert '"admin"' not in downgrade_src
