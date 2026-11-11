"""SPEC-SHEET-DESIGNER-PARITY B2: the spec sheet line row carries `accessories`, the page's picked
lines and set parts as `TagAccessory`-shaped items (kind "product").

Written test-FIRST: `accessories` is not on the print payload row yet. Postgres only.
"""
from __future__ import annotations

from ._pg_fixture import blank_session
from .test_project_spec_sheet import MARKER, _chain, _sheet  # noqa: F401  (helpers, not tests)
from .test_project_spec_sheets_v2 import _make

SHAPE = {
    "kind",
    "id",
    "code",
    "name",
    "brand",
    "description",
    "spec_sheet_description",
    "dimensions",
    "image",
    "spec_lines",
}


def test_a_set_page_lists_its_parts_as_product_accessories_in_page_order():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        c["valve"].spec_sheet_description = "Valve sheet text"
        db.flush()
        sheet = _make(db, c)
        rows = spec.build_print_payload(db, sheet, full=True)["resolvedData"]
        accessories = rows[f"set:{c['set'].id}"]["accessories"]

        assert [a["code"] for a in accessories] == [c["valve"].product_code, c["hose"].product_code]
        for item in accessories:
            assert SHAPE <= set(item)
            assert item["kind"] == "product"
            assert item["image"] is None
        valve, hose = accessories
        assert valve["id"] == c["valve"].id
        assert valve["name"] == c["valve"].product_name
        assert valve["description"] == f"{MARKER} angle valve"
        assert valve["spec_sheet_description"] == "Valve sheet text"
        # Fallback to the plain description.
        assert hose["spec_sheet_description"] == f"{MARKER} hose"
        assert isinstance(valve["spec_lines"], list)


def test_picked_lines_follow_the_set_parts_apply_the_override_and_keep_no_page_of_their_own():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        set_key = f"set:{c['set'].id}"
        sheet = _sheet(
            db,
            c,
            rows=[
                {
                    "key": set_key,
                    "accessories": [c["basin"].id],
                    "accessory_descriptions": {c["basin"].id: "Basin override"},
                }
            ],
        )
        payload = spec.build_print_payload(db, sheet, full=True)
        rows = payload["resolvedData"]

        accessories = rows[set_key]["accessories"]
        assert [a["code"] for a in accessories] == [
            c["valve"].product_code,
            c["hose"].product_code,
            c["basin"].product_code,
        ]
        assert accessories[2]["spec_sheet_description"] == "Basin override"
        # Existing behaviour: a picked line has no page of its own.
        assert c["basin"].id not in rows
        assert [s for s in rows if s not in ("cover", set_key)] == []


def test_a_page_without_accessories_carries_an_empty_list():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        rows = spec.build_print_payload(db, sheet, full=True)["resolvedData"]
        assert rows[c["basin"].id]["accessories"] == []
