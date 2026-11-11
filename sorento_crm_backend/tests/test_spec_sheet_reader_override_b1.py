"""SPEC-SHEET-DESIGNER-PARITY B1 leftovers: the reader needs the override values and the product
defaults on each page of the sheet detail, and the row PATCH merges them. Postgres only."""
from __future__ import annotations

from ._pg_fixture import blank_session
from .test_project_spec_sheet import MARKER, _chain  # noqa: F401  (helpers, not tests)
from .test_project_spec_sheets_v2 import _make


def _page(detail, key):
    return next(p for p in detail["pages"] if p["key"] == key)


def test_detail_pages_carry_the_override_and_the_product_defaults():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        c["basin"].spec_sheet_description = "Basin sheet copy"
        c["valve"].spec_sheet_description = "Valve sheet copy"
        db.flush()
        sheet = _make(db, c)
        set_key = f"set:{c['set'].id}"
        spec.update_sheet(
            db,
            sheet,
            {
                "rows": [
                    {"key": c["basin"].id, "description": "Typed on the page"},
                    {
                        "key": set_key,
                        "accessory_descriptions": {c["valve"].id: "Valve typed"},
                    },
                ]
            },
        )
        document = spec._document_of(db, sheet)
        detail = spec.detail_view(db, document, sheet, can_edit=True)

        basin = _page(detail, c["basin"].id)
        assert basin["description"] == "Typed on the page"
        assert basin["spec_sheet_description_default"] == "Basin sheet copy"
        assert basin["accessory_descriptions"] == {}

        page = _page(detail, set_key)
        assert page["description"] == ""
        assert page["accessory_descriptions"] == {c["valve"].id: "Valve typed"}
        assert "spec_sheet_description_default" in page
        by_code = {a["code"]: a for a in page["accessories"]}
        assert by_code[c["valve"].product_code]["spec_sheet_description"] == "Valve sheet copy"
        assert by_code[c["hose"].product_code]["spec_sheet_description"] == f"{MARKER} hose"
        # Private keys never leave the API.
        assert not [k for k in page if k.startswith("_")]


def test_the_cover_page_carries_empty_override_fields():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        detail = spec.detail_view(db, spec._document_of(db, sheet), sheet, can_edit=True)
        cover = _page(detail, "cover")
        assert cover["description"] == ""
        assert cover["accessory_descriptions"] == {}


def test_an_empty_description_in_a_row_patch_resets_the_override():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        spec.update_sheet(db, sheet, {"rows": [{"key": c["basin"].id, "description": "Typed"}]})
        spec.update_sheet(db, sheet, {"rows": [{"key": c["basin"].id, "description": ""}]})
        detail = spec.detail_view(db, spec._document_of(db, sheet), sheet, can_edit=True)
        assert _page(detail, c["basin"].id)["description"] == ""
