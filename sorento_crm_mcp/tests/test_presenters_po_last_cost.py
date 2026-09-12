"""AC-20..AC-24 (chatbot-last-purchase-cost): the `_po_last_cost` presenter and its
ToolSpec, `crm_procurement_po_last_cost_list`.

`documentation/plans/chatbot/PLAN-chatbot-last-purchase-cost.md`;
`documentation/plans/chatbot/chatbot-last-purchase-cost-acceptance-criteria.md`.

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
    }
    base.update(overrides)
    return base


def test_ac20_presenter_exact_order() -> None:
    """A row carrying every field renders EXACTLY, in this order: PO Number, Product
    Code, PO Quantity, PO Date, Cost / unit, Discount / unit, Cost after discount / unit,
    Warehouse. Asserted as an exact list, not a membership test."""
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
    ]


def test_ac21_presenter_if_any_absence() -> None:
    """A row with `discount_per_unit` None renders no Discount / unit line; a row with
    `warehouse` None renders no Warehouse line; nothing renders with an empty value."""
    out = env(TOOL, {"data": [_row(discount_per_unit=None, warehouse=None)]})
    labels = [f["label"] for f in out["items"][0]["fields"]]
    # An exact list, not a membership check: a presenter that fell back to raw keys
    # (no "Discount / unit"/"Warehouse" by CONSTRUCTION, for the wrong reason) must not
    # read as satisfying this AC.
    assert labels == [
        "PO Number",
        "Product Code",
        "PO Quantity",
        "PO Date",
        "Cost / unit",
        "Cost after discount / unit",
    ], labels
    for field in out["items"][0]["fields"]:
        assert field["value"] not in (None, ""), field


def test_ac22_money_format() -> None:
    """Cost / unit renders CNY 110.00; Discount / unit renders CNY 66.00; Cost after
    discount / unit renders CNY 44.00."""
    out = env(TOOL, {"data": [_row()]})
    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["Cost / unit"] == "CNY 110.00"
    assert fields["Discount / unit"] == "CNY 66.00"
    assert fields["Cost after discount / unit"] == "CNY 44.00"


def test_ac23_restricted_keys_in_envelope() -> None:
    """The envelope's `restricted_fields` maps `unit_cost`, `discount_per_unit` and
    `unit_cost_after_discount` to `purchase_orders.cost`."""
    out = env(TOOL, {"data": [_row()]})
    assert out.get("restricted_fields") == {
        "unit_cost": "purchase_orders.cost",
        "discount_per_unit": "purchase_orders.cost",
        "unit_cost_after_discount": "purchase_orders.cost",
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
