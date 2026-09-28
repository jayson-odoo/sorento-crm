"""Fix lane round 6 (#1288, PR #1305): duplicate codes collapse, lead time never blocks.

Owner rulings of 28 Sep 2026 (the round 6 work list on PR #1305):

- R3: "don't need Lead time (days)". A new link's `standard_lead_time_days` is the supplier's
  most common value across its links, else null; Apply never blocks on lead time (AC-S2-05 as
  amended).
- R6: rows with the same supplier code in one set collapse into ONE line carrying the FIRST
  row's cost, the other rows' notes and costs riding on that line; Apply is not blocked by
  duplicates, and the applied cost list records which row was used (AC-S1-10 as amended).
  The choice lives in one function, `choose_duplicate_row`, so a later ruling (lower cost,
  last row, per-line choice) is a one-function change.
"""
from __future__ import annotations

from decimal import Decimal

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import UPLOAD_PERM, VIEW_PERM, cost_price_env  # noqa: F401


def _setup(e, code: str, rows: list[tuple], *, current=10):
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code=code)
    e.link(product, supplier, unit_cost=current, currency="CNY")
    data = simple_price_list_workbook(rows, letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    return supplier, product, upload.json()


# --------------------------------------------------------------------- R6, two-row duplicate


def test_two_row_duplicate_collapses_to_the_first_row(cost_price_env):
    e = cost_price_env
    _, _, uploaded = _setup(
        e, "ZZCPC-R6-TWO",
        [("ZZCPC-R6-TWO(吊卡)", "cfg", 9.40), ("ZZCPC-R6-TWO(OPP)", "cfg", 9.90)],
    )
    set_id = uploaded["id"]

    lines = e.lines(set_id).json()["data"]
    assert len(lines) == 1, lines
    (line,) = lines
    assert line["code_note"] == "吊卡"
    assert line["new_unit_cost"] == 9.40
    assert line["skipped"] is False
    assert [(d["code_note"], d["new_unit_cost"]) for d in line["duplicate_rows"]] == [("OPP", 9.90)]
    assert line["duplicate_rows"][0]["row_no"] == line["row_no"] + 1

    detail = e.detail(set_id).json()
    assert detail["actions"]["can_apply"] is True, detail["actions"]
    assert detail["actions"]["apply_blocked_reason"] is None
    assert detail["actions"]["apply_count"] == 1


def test_two_row_duplicate_applies_the_first_rows_cost_and_records_the_row(cost_price_env):
    from app.models.audit import AuditLog
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    supplier, product, uploaded = _setup(
        e, "ZZCPC-R6-APPLY",
        [("ZZCPC-R6-APPLY(吊卡)", "cfg", 9.40), ("ZZCPC-R6-APPLY(OPP)", "cfg", 9.90)],
    )
    set_id = uploaded["id"]
    (line,) = e.lines(set_id).json()["data"]
    line_id, first_row = line["id"], line["row_no"]

    r = e.apply(set_id)
    assert r.status_code == 200, r.text

    link = e.db.query(ProductSupplier).filter_by(product_id=product.id, supplier_id=supplier.id).one()
    costs = e.db.query(ProductSupplierCost).filter_by(product_supplier_id=link.id).all()
    assert len(costs) == 1
    assert costs[0].unit_cost == Decimal("9.40")
    assert str(costs[0].source_change_line_id) == line_id

    # The cost list itself says which sheet and row the cost came from.
    e.as_user(e.superadmin())
    listed = e.cost_lists(str(supplier.id)).json()
    rows = [c for item in listed["data"] for c in item.get("costs", [])]
    sources = [c["source"] for c in rows if c.get("source")]
    assert sources and sources[0]["row_no"] == first_row and sources[0]["sheet"] == "Sheet", sources

    applied = (
        e.db.query(AuditLog)
        .filter(AuditLog.entity_type == "cost_price_change_sets", AuditLog.entity_id == set_id)
        .all()
    )
    changes = [
        c for row in applied
        if (row.new_values or {}).get("event") == "COST_SET_APPLY"
        for c in row.new_values["changes"]
    ]
    assert [(c["sheet"], c["row_no"], c["new_unit_cost"]) for c in changes] == [("Sheet", first_row, 9.40)]


# --------------------------------------------------------------------- R6, three-row duplicate


def test_three_row_duplicate_collapses_to_the_first_row(cost_price_env):
    from app.models.cost_price import ProductSupplierCost

    e = cost_price_env
    _, _, uploaded = _setup(
        e, "ZZCPC-R6-THREE",
        [
            ("ZZCPC-R6-THREE(OPP)", "cfg", 9.90),
            ("ZZCPC-R6-THREE(吊卡)", "cfg", 9.40),
            ("ZZCPC-R6-THREE(彩盒)", "cfg", 11.00),
        ],
    )
    set_id = uploaded["id"]

    lines = e.lines(set_id).json()["data"]
    assert len(lines) == 1, lines
    (line,) = lines
    first_row = line["row_no"]
    assert (line["code_note"], line["new_unit_cost"]) == ("OPP", 9.90)
    assert [(d["row_no"], d["code_note"], d["new_unit_cost"]) for d in line["duplicate_rows"]] == [
        (first_row + 1, "吊卡", 9.40),
        (first_row + 2, "彩盒", 11.00),
    ]

    r = e.apply(set_id)
    assert r.status_code == 200, r.text
    costs = e.db.query(ProductSupplierCost).all()
    assert [c.unit_cost for c in costs] == [Decimal("9.90")]


def test_skipping_the_used_row_promotes_the_next_one(cost_price_env):
    e = cost_price_env
    _, _, uploaded = _setup(
        e, "ZZCPC-R6-PROMOTE",
        [
            ("ZZCPC-R6-PROMOTE(A)", "cfg", 1.00),
            ("ZZCPC-R6-PROMOTE(B)", "cfg", 2.00),
            ("ZZCPC-R6-PROMOTE(C)", "cfg", 3.00),
        ],
    )
    set_id = uploaded["id"]
    first = e.lines(set_id).json()["data"][0]
    r = e.patch_line(set_id, first["id"], {"skipped": True, "skip_reason": "Not this one"})
    assert r.status_code == 200, r.text

    shown = [ln for ln in e.lines(set_id).json()["data"] if not ln["skipped"]]
    assert len(shown) == 1
    assert (shown[0]["code_note"], shown[0]["new_unit_cost"]) == ("B", 2.00)
    assert [d["code_note"] for d in shown[0]["duplicate_rows"]] == ["C"]


def test_the_choice_lives_in_one_function(cost_price_env, monkeypatch):
    """Changing `choose_duplicate_row` alone changes which row a duplicate uses."""
    from app.services.procurement import cost_price_change_service as svc

    monkeypatch.setattr(svc, "choose_duplicate_row", lambda rows: rows[-1])
    e = cost_price_env
    _, _, uploaded = _setup(
        e, "ZZCPC-R6-LAST",
        [("ZZCPC-R6-LAST(吊卡)", "cfg", 9.40), ("ZZCPC-R6-LAST(OPP)", "cfg", 9.90)],
    )
    (line,) = e.lines(uploaded["id"]).json()["data"]
    assert (line["code_note"], line["new_unit_cost"]) == ("OPP", 9.90)
    assert [d["code_note"] for d in line["duplicate_rows"]] == ["吊卡"]


# --------------------------------------------------------------------- R3, lead time


def test_new_link_with_no_supplier_links_applies_with_null_lead_time(cost_price_env):
    """AC-S2-05 as amended by the owner (28 Sep 2026): given no value to take, the new link's
    lead time stays empty and Apply goes through."""
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)  # no links at all
    new_product = e.product(code="ZZCPC-R6-LT-NULL")
    data = simple_price_list_workbook([("ZZCPC-R6-LT-NULL", "cfg", 80)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    set_id = upload.json()["id"]

    assert e.detail(set_id).json()["actions"]["can_apply"] is True
    r = e.apply(set_id)
    assert r.status_code == 200, r.text
    link = e.db.query(ProductSupplier).filter_by(product_id=new_product.id).one()
    assert link.standard_lead_time_days is None


def test_most_common_lead_time_ignores_links_without_one(cost_price_env):
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    user = e.user(UPLOAD_PERM, VIEW_PERM)
    e.as_user(user)
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    e.link(e.product(code="ZZCPC-R6-LT-N1"), supplier, lead_time_days=None)
    e.link(e.product(code="ZZCPC-R6-LT-N2"), supplier, lead_time_days=None)
    e.link(e.product(code="ZZCPC-R6-LT-45"), supplier, lead_time_days=45)
    new_product = e.product(code="ZZCPC-R6-LT-NEW")
    data = simple_price_list_workbook([("ZZCPC-R6-LT-NEW", "cfg", 80)], letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text

    r = e.apply(upload.json()["id"])
    assert r.status_code == 200, r.text
    link = e.db.query(ProductSupplier).filter_by(product_id=new_product.id).one()
    assert link.standard_lead_time_days == 45


def test_product_supplier_list_serves_a_link_without_lead_time(cost_price_env):
    """A null lead time must not 500 the product's suppliers list (response_model)."""
    e = cost_price_env
    user = e.superadmin()
    e.as_user(user)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    product = e.product(code="ZZCPC-R6-LT-READ")
    e.link(product, supplier, lead_time_days=None)
    r = e.product_suppliers_by_product(str(product.id))
    assert r.status_code == 200, r.text
    assert "standard_lead_time_days" in r.text
