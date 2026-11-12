"""SPEC-SHEET-DESIGNER-PARITY A4: `{{product.description}}` on a spec sheet page.

The print payload's line row and each of its parts carry the product master's plain
`description`, the field `{{product.description}}` reads (frontend `merge-fields.ts`).
Postgres only, every chain seeded here.
"""
from __future__ import annotations

from ._pg_fixture import blank_session
from .test_project_spec_sheet import MARKER, _chain  # noqa: F401  (helpers, not tests)
from .test_project_spec_sheets_v2 import _make


def test_the_print_payload_carries_the_product_description_on_lines_and_parts():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        payload = spec.build_print_payload(db, sheet, full=True)
        rows = payload["resolvedData"]

        assert rows[c["basin"].id]["description"] == f"{MARKER} basin"
        part_descriptions = {
            part["description"] for row in rows.values() for part in row.get("parts") or []
        }
        assert {f"{MARKER} angle valve", f"{MARKER} hose"} <= part_descriptions
        # The cover has no product: the field is there and empty.
        assert rows["cover"]["description"] is None
