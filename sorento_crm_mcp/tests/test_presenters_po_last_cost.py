"""AC-20..AC-24 (chatbot-last-purchase-cost): the `_po_last_cost` presenter and its
ToolSpec, `crm_procurement_po_last_cost_list`.

`documentation/plans/_archive/chatbot/PLAN-chatbot-last-purchase-cost.md`;
`documentation/plans/_archive/chatbot/chatbot-last-purchase-cost-acceptance-criteria.md`.

Owner ruling from live verification, 12 Sep 2026, verbatim: "we should always show
discount even though it is null or 0" - `Discount / unit` is no longer an "if any" field;
it always renders, `CNY 0.00` when the line carries no discount. Only `Warehouse` (and now
`Supplier`) stay "if any".

Second owner ruling, same round: "we should show supplier also" - `Supplier` renders LAST,
after `Warehouse`, and is RESTRICTED under the SAME field-reveal key
`purchase_orders.supplier` the sibling tool `crm_procurement_po_placed_list` already uses
(`_purchase_orders_placed`'s own `b.restrict("supplier", "purchase_orders.supplier")`).

Mirrors `tests/test_presenters.py`'s own `_spo_last_receipt` coverage (same `env()`
helper, same exact-list assertion for field order) - none of this exists yet, so every
test here is RED until the presenter, its `_BUILDERS` registration and its `ToolSpec`
land.
"""
from __future__ import annotations

import json

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import present_response

TOOL = "crm_procurement_po_last_cost_list"


def env(tool: str, data: dict) -> dict:
    return json.loads(present_response(tool, json.dumps(data)))


def _row(**overrides) -> dict:
    base = {
        "po_number": "PO-2026/09-0013",
        "product_code": "M218",
        "po_quantity": 19,
        "po_date": "2026-05-01",
        "currency": "CNY",
        "unit_cost": 110.0,
        "discount_per_unit": 66.0,
        "unit_cost_after_discount": 44.0,
        "warehouse": "BRW-SMC",
        "supplier": "Acme Supplies",
    }
    base.update(overrides)
    return base


def test_ac20_presenter_exact_order() -> None:
    """A row carrying every field renders EXACTLY, in this order: PO Number, Product
    Code, PO Quantity, PO Date, Cost / unit, Discount / unit, Cost after discount / unit,
    Warehouse, Supplier. Asserted as an exact list, not a membership test."""
    out = env(TOOL, {"data": [_row()]})
    item = out["items"][0]
    assert [f["label"] for f in item["fields"]] == [
        "PO Number",
        "Product Code",
        "PO Quantity",
        "PO Date",
        "Cost / unit",
        "Discount / unit",
        "Cost after discount / unit",
        "Warehouse",
        "Supplier",
    ]


def test_ac21_discount_always_shown_only_warehouse_and_supplier_are_if_any() -> None:
    """Owner ruling, 12 Sep 2026: "we should always show discount even though it is null
    or 0" - a zero-discount row still renders `Discount / unit: CNY 0.00`. A row with
    `warehouse` None and `supplier` None renders the FULL list minus only those two
    lines; nothing renders with an empty value."""
    out = env(TOOL, {"data": [_row(discount_per_unit=0.0, warehouse=None, supplier=None)]})
    fields = out["items"][0]["fields"]
    labels = [f["label"] for f in fields]
    # An exact list, not a membership check: a presenter that fell back to raw keys
    # (no "Discount / unit"/"Warehouse"/"Supplier" by CONSTRUCTION, for the wrong reason)
    # must not read as satisfying this AC.
    assert labels == [
        "PO Number",
        "Product Code",
        "PO Quantity",
        "PO Date",
        "Cost / unit",
        "Discount / unit",
        "Cost after discount / unit",
    ], labels
    values = {f["label"]: f["value"] for f in fields}
    assert values["Discount / unit"] == "CNY 0.00"
    for field in fields:
        assert field["value"] not in (None, ""), field


def test_ac21b_warehouse_and_supplier_are_independently_if_any() -> None:
    """A row with a warehouse but no supplier keeps Warehouse and drops only Supplier;
    the reverse keeps Supplier and drops only Warehouse - each is its own "if any", not a
    joint one."""
    out_no_supplier = env(TOOL, {"data": [_row(supplier=None)]})
    assert [f["label"] for f in out_no_supplier["items"][0]["fields"]] == [
        "PO Number",
        "Product Code",
        "PO Quantity",
        "PO Date",
        "Cost / unit",
        "Discount / unit",
        "Cost after discount / unit",
        "Warehouse",
    ]

    out_no_warehouse = env(TOOL, {"data": [_row(warehouse=None)]})
    assert [f["label"] for f in out_no_warehouse["items"][0]["fields"]] == [
        "PO Number",
        "Product Code",
        "PO Quantity",
        "PO Date",
        "Cost / unit",
        "Discount / unit",
        "Cost after discount / unit",
        "Supplier",
    ]


def test_ac22_money_format() -> None:
    """Cost / unit renders CNY 110.00; Discount / unit renders CNY 66.00; Cost after
    discount / unit renders CNY 44.00; a zero discount renders CNY 0.00 (owner ruling,
    12 Sep 2026 - discount is always shown, never omitted for being zero)."""
    out = env(TOOL, {"data": [_row()]})
    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["Cost / unit"] == "CNY 110.00"
    assert fields["Discount / unit"] == "CNY 66.00"
    assert fields["Cost after discount / unit"] == "CNY 44.00"

    zero_out = env(TOOL, {"data": [_row(discount_per_unit=0.0)]})
    zero_fields = {f["label"]: f["value"] for f in zero_out["items"][0]["fields"]}
    assert zero_fields["Discount / unit"] == "CNY 0.00"


def test_ac23_restricted_keys_in_envelope() -> None:
    """The envelope's `restricted_fields` maps `unit_cost`, `discount_per_unit` and
    `unit_cost_after_discount` to `purchase_orders.cost`, and `supplier` to
    `purchase_orders.supplier` - the SAME key `crm_procurement_po_placed_list` already
    uses for its own `supplier` field."""
    out = env(TOOL, {"data": [_row()]})
    assert out.get("restricted_fields") == {
        "unit_cost": "purchase_orders.cost",
        "discount_per_unit": "purchase_orders.cost",
        "unit_cost_after_discount": "purchase_orders.cost",
        "supplier": "purchase_orders.supplier",
    }


def test_ac24_catalog_description() -> None:
    """The ToolSpec description names the row order, says the three money figures are
    per unit derived from the line amount, and says the answer is restricted to a
    contact holding `purchase_orders.cost`."""
    specs_by_name = {spec.name: spec for spec in CATALOG}
    assert TOOL in specs_by_name, f"{TOOL} is not registered in the catalog yet"
    spec = specs_by_name[TOOL]
    lowered = spec.description.lower()
    for phrase in (
        "po number",
        "product code",
        "po quantity",
        "po date",
        "cost / unit",
        "discount / unit",
        "cost after discount / unit",
        "warehouse",
    ):
        assert phrase in lowered, f"description missing {phrase!r}: {spec.description}"
    assert "per unit" in lowered
    assert "line" in lowered
    assert "restrict" in lowered
    assert "purchase_orders.cost" in spec.description
