"""A1 - product spec projection in `output_structurer` (AC-901, AC-902).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.

No spec TOOL exists in the catalog - this is `crm_master_products_list`'s own
envelope (`result_type: "products"`), gated only on that, never on
`field_vocabulary`/`spec_vocabulary` truthiness (that would break the
zero-spec case: a product with no derived specs must still answer with
today's four fields, not be skipped by the gate).
"""
from __future__ import annotations

from app.services.chatbot.lanes.business import fetch


def _product_envelope(*, specs: list[dict] | None = None) -> dict:
    fields = [
        {"key": "company_name", "label": "Company", "value": "Sorento"},
        {"label": "Product Code", "value": "SRTWC8517"},
        {"label": "Product Name", "value": "Wall Hung Closet"},
        {"label": "List Price", "value": "MYR 199.00"},
        {"label": "Dimensions", "value": "500 x 360 x 350 mm"},
    ]
    for spec in specs or []:
        fields.append(
            {"key": f"spec:{spec['key']}", "label": spec["label"], "value": spec["value"]}
        )
    return {
        "result_type": "products",
        "intro": "Here are the matching products.",
        "items": [{"title": "SRTWC8517", "fields": fields}],
        "spec_vocabulary": {s["key"]: s["label"] for s in (specs or [])},
        "has_result": True,
    }


_FOUR_SPECS = [
    {"key": "wattage", "label": "Wattage", "value": "60 W"},
    {"key": "thickness", "label": "Thickness", "value": "1.2 mm"},
    {"key": "material", "label": "Material", "value": "Ceramic"},
    {"key": "color", "label": "Color", "value": "White"},
]


def test_no_attributes_asked_keeps_base_fields_plus_one_compact_specs_line():
    envelope = _product_envelope(specs=_FOUR_SPECS)
    out = fetch.output_structurer(envelope, {"semantic_input": {}})
    fields = out["answers"][0]["fields"]
    labels = [f["label"] for f in fields]
    # today's four fields, unchanged
    assert labels[:4] == ["Company", "Product Code", "Product Name", "List Price"]
    assert "Dimensions" in labels
    # exactly ONE additional line, not four separate spec fields
    specs_fields = [f for f in fields if f["label"] == "Specs"]
    assert len(specs_fields) == 1
    assert "Wattage: 60 W" in specs_fields[0]["value"]
    assert "Thickness: 1.2 mm" in specs_fields[0]["value"]
    assert "no spec:" not in out["response"]


def test_compact_line_caps_at_eight_then_says_and_n_more():
    many = [
        {"key": f"k{i}", "label": f"Key{i}", "value": str(i)}
        for i in range(10)
    ]
    envelope = _product_envelope(specs=many)
    out = fetch.output_structurer(envelope, {"semantic_input": {}})
    specs_field = next(f for f in out["answers"][0]["fields"] if f["label"] == "Specs")
    assert "and 2 more" in specs_field["value"]
    assert specs_field["value"].count(":") <= 9  # 8 "Keyn: n" pairs + trailing note


def test_no_spec_key_at_all_is_the_plain_four_field_answer():
    envelope = _product_envelope(specs=[])
    out = fetch.output_structurer(envelope, {"semantic_input": {}})
    fields = out["answers"][0]["fields"]
    assert not any(f["label"] == "Specs" for f in fields)
    assert [f["label"] for f in fields] == ["Company", "Product Code", "Product Name", "List Price", "Dimensions"]


def test_single_key_ask_returns_only_that_key_plus_identity():
    envelope = _product_envelope(specs=_FOUR_SPECS)
    ctx = {"semantic_input": {"requested_attributes": ["wattage"]}}
    out = fetch.output_structurer(envelope, ctx)
    fields = out["answers"][0]["fields"]
    labels = [f["label"] for f in fields]
    assert labels == ["Company", "Product Code", "Wattage"]
    assert fields[2]["value"] == "60 W"


def test_single_key_ask_matches_by_label_synonym_word():
    """AC-902: "wattage" matches the registry LABEL text, not only the raw key -
    here asking with different casing/spacing still resolves to the same spec."""
    envelope = _product_envelope(specs=_FOUR_SPECS)
    ctx = {"semantic_input": {"requested_attributes": ["Wattage"]}}
    out = fetch.output_structurer(envelope, ctx)
    fields = out["answers"][0]["fields"]
    assert any(f["label"] == "Wattage" for f in fields)


def test_asked_key_the_product_lacks_answers_no_label_recorded():
    envelope = _product_envelope(specs=_FOUR_SPECS)
    ctx = {"semantic_input": {"requested_attributes": ["voltage"]}}
    out = fetch.output_structurer(envelope, ctx)
    fields = out["answers"][0]["fields"]
    miss = next(f for f in fields if f["label"] == "voltage")
    assert miss["value"] == "no voltage recorded for SRTWC8517"


def test_asked_key_the_product_lacks_uses_registry_label_when_known():
    """The product has none of `_FOUR_SPECS`' keys BUT another product in the same
    result set carries the registry entry, so `spec_vocabulary` knows the label."""
    envelope = _product_envelope(specs=[])
    envelope["spec_vocabulary"] = {"wattage": "Wattage"}
    ctx = {"semantic_input": {"requested_attributes": ["wattage"]}}
    out = fetch.output_structurer(envelope, ctx)
    fields = out["answers"][0]["fields"]
    miss = next(f for f in fields if f["label"] == "Wattage")
    assert miss["value"] == "no wattage recorded for SRTWC8517"
