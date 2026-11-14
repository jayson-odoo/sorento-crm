"""SPEC-SHEET-DESIGNER-PARITY B3: the spec sheet print row carries the line and document fields
the variable registry reads (`line.*`, `doc.*`). Written test-FIRST. Postgres only.

Row contract: `quantity`, `uom`, `line_description`, `technical_spec`, `notes`, `item_label`,
`page_no`; inside `doc`: `subject_title`, `attn`, `recipient`, `project_code`, `page_count`.
"""
from __future__ import annotations

from decimal import Decimal

from ._pg_fixture import blank_session
from .test_project_spec_sheet import MARKER, _chain  # noqa: F401  (helpers, not tests)
from .test_project_spec_sheets_v2 import _make


def _basin_line(db, c):
    from app.models.projects import ProjectQuotationLine

    return (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.product_id == c["basin"].id)
        .order_by(ProjectQuotationLine.id)
        .first()
    )


def _fill(db, c):
    from app.models.projects import Project

    line = _basin_line(db, c)
    line.quantity = Decimal("7")
    line.uom = "unit"
    line.description_snapshot = f"{MARKER} quoted basin text"
    line.technical_spec = f"{MARKER} tech spec"
    line.notes = f"{MARKER} line note"
    line.item_label = "A1"
    document = c["document"]
    document.subject_title = f"{MARKER} Tower subject"
    document.attn_name = f"{MARKER} Attn Person"
    document.recipient_name_snapshot = f"{MARKER} Recipient Sdn Bhd"
    db.query(Project).filter(Project.id == document.project_id).update(
        {"project_code": "ZZTPRJ-1"}
    )
    db.flush()
    db.expire_all()
    return line


def test_the_line_row_carries_the_quoted_quantity_uom_text_spec_notes_and_label():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        _fill(db, c)
        sheet = _make(db, c)
        row = spec.build_print_payload(db, sheet, full=True)["resolvedData"][c["basin"].id]

        assert float(row["quantity"]) == 7
        assert row["uom"] == "unit"
        assert row["line_description"] == f"{MARKER} quoted basin text"
        assert row["technical_spec"] == f"{MARKER} tech spec"
        assert row["notes"] == f"{MARKER} line note"
        assert row["item_label"] == "A1"


def test_the_row_doc_carries_the_document_fields_and_the_page_numbers():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        _fill(db, c)
        sheet = _make(db, c)
        rows = spec.build_print_payload(db, sheet, full=True)["resolvedData"]
        set_key = f"set:{c['set'].id}"
        doc = rows[c["basin"].id]["doc"]

        assert doc["subject_title"] == f"{MARKER} Tower subject"
        assert doc["attn"] == f"{MARKER} Attn Person"
        assert doc["recipient"] == f"{MARKER} Recipient Sdn Bhd"
        assert doc["project_code"] == "ZZTPRJ-1"
        # Cover + basin + set: three printed pages.
        assert str(doc["page_count"]) == "3"
        numbers = {k: str(r["page_no"]) for k, r in rows.items() if k != "cover"}
        assert sorted(numbers.values()) == ["2", "3"]
        assert numbers[c["basin"].id] != numbers[set_key]


def test_the_values_are_frozen_with_the_items_and_an_older_snapshot_reads_empty():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        line = _fill(db, c)
        sheet = _make(db, c)
        line = _basin_line(db, c)
        line.quantity = Decimal("99")
        line.notes = "changed after the snapshot"
        db.flush()
        row = spec.build_print_payload(db, sheet, full=True)["resolvedData"][c["basin"].id]
        assert float(row["quantity"]) == 7
        assert row["notes"] == f"{MARKER} line note"

        # Items taken before this lane have none of the keys: quantity 1, empty strings.
        keep = {"key", "line_id", "product_id", "code", "description", "brand", "image_attachment_id",
                "drawing_attachment_id", "section", "unit_price", "set_parts"}
        sheet.items = [{k: v for k, v in item.items() if k in keep} for item in sheet.items]
        db.flush()
        old = spec.build_print_payload(db, sheet, full=True)["resolvedData"][c["basin"].id]
        assert float(old["quantity"]) == 1
        for field in ("uom", "line_description", "technical_spec", "notes", "item_label"):
            assert old[field] == ""
