"""SPEC-SHEET-DESIGNER-PARITY B1: the "Spec sheet description" product field and its per-sheet
override (plan `PLAN-spec-sheet-designer-parity-b-11nov.md`, B1).

Written test-FIRST: `products.spec_sheet_description` and the row keys `description` /
`accessory_descriptions` do not exist yet. Postgres only, every chain seeded here.

Accessory override key (contract assumption, B1): the accessory's product id, the same id a
hand-picked accessory is stored under in the row's `accessories` list.
"""
from __future__ import annotations

from ._pg_fixture import blank_session
from .test_product_price_tag_description import (  # noqa: F401  (fixtures)
    STEM,
    _scope_listeners,
    api,
    db,
    world,
)
from .test_project_spec_sheet import MARKER, _chain  # noqa: F401  (helpers, not tests)
from .test_project_spec_sheets_v2 import _make


# ------------------------------------------------------------------ product master


def test_the_product_model_has_a_nullable_spec_sheet_description_column():
    from app.models.product import Product

    column = Product.__table__.c.get("spec_sheet_description")
    assert column is not None, "products.spec_sheet_description is missing"
    assert column.nullable is True
    assert column.type.__class__.__name__ == "Text"


def test_put_sets_and_returns_the_spec_sheet_description(api, world, db):
    pid = world["product"](f"{STEM}-SSD1")
    db.commit()

    text = "Wall hung WC\nSoft close seat"
    res = api.put(f"/api/v1/master-data/products/{pid}", json={"spec_sheet_description": text})
    assert res.status_code == 200, res.text
    assert res.json()["spec_sheet_description"] == text
    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json()["spec_sheet_description"] == text


def test_the_spec_sheet_description_is_null_when_unset_and_kept_by_an_unrelated_put(api, world, db):
    pid = world["product"](f"{STEM}-SSD2")
    db.commit()
    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert "spec_sheet_description" in detail.json()
    assert detail.json()["spec_sheet_description"] is None

    api.put(f"/api/v1/master-data/products/{pid}", json={"spec_sheet_description": "Keep me"})
    res = api.put(f"/api/v1/master-data/products/{pid}", json={"product_name": f"{STEM}-SSD2 renamed"})
    assert res.status_code == 200, res.text
    assert res.json()["spec_sheet_description"] == "Keep me"


def test_the_spec_sheet_description_is_cleaned_like_the_price_tag_description(api, world, db):
    pid = world["product"](f"{STEM}-SSD3")
    db.commit()

    res = api.put(
        f"/api/v1/master-data/products/{pid}",
        json={"spec_sheet_description": "<p>Solid brass<script>alert(1)</script></p>"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["spec_sheet_description"] == "<p>Solid brass</p>"

    res = api.put(f"/api/v1/master-data/products/{pid}", json={"spec_sheet_description": "<p></p>"})
    assert res.status_code == 200, res.text
    assert res.json()["spec_sheet_description"] is None


def test_a_spec_sheet_description_over_20000_characters_is_422(api, world, db):
    pid = world["product"](f"{STEM}-SSD4")
    db.commit()
    res = api.put(
        f"/api/v1/master-data/products/{pid}", json={"spec_sheet_description": "a" * 20_001}
    )
    assert res.status_code == 422


# ------------------------------------------------------------------ spec sheet print payload


def _set_field(db, product, value):
    product.spec_sheet_description = value
    db.flush()


def test_the_print_payload_prefers_the_field_then_falls_back_to_the_description():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        _set_field(db, c["basin"], f"{MARKER} basin sheet text")
        _set_field(db, c["valve"], None)
        sheet = _make(db, c)
        rows = spec.build_print_payload(db, sheet, full=True)["resolvedData"]

        assert rows[c["basin"].id]["spec_sheet_description"] == f"{MARKER} basin sheet text"
        # Plain description stays what {{product.description}} reads.
        assert rows[c["basin"].id]["description"] == f"{MARKER} basin"
        set_row = rows[f"set:{c['set'].id}"]
        by_code = {p["code"]: p for p in set_row["parts"]}
        # No field on the valve: falls back to its description, never empty.
        assert by_code[c["valve"].product_code]["spec_sheet_description"] == f"{MARKER} angle valve"
        assert by_code[c["hose"].product_code]["spec_sheet_description"] == f"{MARKER} hose"
        assert rows["cover"]["spec_sheet_description"] is None


def test_a_sheet_override_replaces_the_text_for_that_sheet_only():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        _set_field(db, c["basin"], f"{MARKER} basin sheet text")
        one = _make(db, c)
        two = _make(db, c)
        set_key = f"set:{c['set'].id}"
        spec.update_sheet(
            db,
            one,
            {
                "rows": [
                    {
                        "key": c["basin"].id,
                        "description": "  Override for this sheet  ",
                    },
                    {
                        "key": set_key,
                        "description": "Set override",
                        "accessory_descriptions": {c["valve"].id: "Valve override"},
                    },
                ]
            },
        )

        first = spec.build_print_payload(db, one, full=True)["resolvedData"]
        other = spec.build_print_payload(db, two, full=True)["resolvedData"]

        assert first[c["basin"].id]["spec_sheet_description"] == "Override for this sheet"
        assert first[set_key]["spec_sheet_description"] == "Set override"
        parts = {p["code"]: p for p in first[set_key]["parts"]}
        assert parts[c["valve"].product_code]["spec_sheet_description"] == "Valve override"
        assert parts[c["hose"].product_code]["spec_sheet_description"] == f"{MARKER} hose"

        # The other sheet of the same document and the product row are untouched.
        assert other[c["basin"].id]["spec_sheet_description"] == f"{MARKER} basin sheet text"
        db.refresh(c["basin"])
        assert c["basin"].spec_sheet_description == f"{MARKER} basin sheet text"


def test_the_override_is_kept_trimmed_capped_and_merged_by_update_sheet():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        spec.update_sheet(
            db,
            sheet,
            {
                "rows": [
                    {
                        "key": c["basin"].id,
                        "description": f"  {'x' * 30000}  ",
                        "accessory_descriptions": {c["valve"].id: "  v  "},
                    }
                ]
            },
        )
        row = next(r for r in sheet.rows if r["key"] == c["basin"].id)
        assert 0 < len(row["description"]) <= 20000
        assert row["description"] == "x" * len(row["description"])
        assert row["accessory_descriptions"] == {c["valve"].id: "v"}

        # A later save that names another row keeps the stored override (merge).
        spec.update_sheet(db, sheet, {"rows": [{"key": f"set:{c['set'].id}", "comment": "hi"}]})
        row = next(r for r in sheet.rows if r["key"] == c["basin"].id)
        assert row["accessory_descriptions"] == {c["valve"].id: "v"}


def test_an_empty_override_string_is_no_override():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        _set_field(db, c["basin"], f"{MARKER} basin sheet text")
        sheet = _make(db, c)
        spec.update_sheet(db, sheet, {"rows": [{"key": c["basin"].id, "description": "Custom"}]})
        spec.update_sheet(db, sheet, {"rows": [{"key": c["basin"].id, "description": "   "}]})

        rows = spec.build_print_payload(db, sheet, full=True)["resolvedData"]
        assert rows[c["basin"].id]["spec_sheet_description"] == f"{MARKER} basin sheet text"
