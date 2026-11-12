"""SPLIT-SHEET-LOCATION owner change request (9 Nov 2026, ~16:40): "when I confirm, is it
supposed to show the Location and New Location column also in preview, email and attachment?"

Ruling, mirroring QTY | NEW QTY and DELIVERY | NEW DATE: LOCATION prints the line's previous
location and NEW LOCATION, right after it, the new one, filled only on a line whose location
changed (blank otherwise); the column shows only when some line in the email moved. The REMARK
`NEW LOCATION (was X)` stays. A line carries the move as `was.location`, as a cut carries
`was.qty`.
"""
from __future__ import annotations

import io

from .test_oi_saved_line_email import _context, _line, _migration, _rows

#: The path a real database takes to today's document.
_CHAIN = (
    "oihr_0006_no_remark_column", "oihr_0007_excel_remark", "oihr_0008_so_table_on_top",
    "oihr_0009_split_rows", "oihr_0010_so_remark_column", "oihr_0011_item_code_wrap",
    "oihr_0012_new_location",
)


def _render(lines):
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService

    from ._pg_fixture import blank_session
    from .test_order_inquiry_handover_automation import _run_upgrade

    with blank_session() as db:
        for name in _CHAIN:
            _run_upgrade(_migration(name), db)
        template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.code == "order_inquiry_handover_default")
            .one()
        )
        assert template.body_text and "NEW LOCATION" in template.body_text, (
            "premise: oihr_0012 converted the seeded document"
        )
        return EmailTemplateService(db).render(template, _context(lines))

MOVED = dict(location="BRW", was={"location": "BRW-IB"}, remark="NEW LOCATION (was BRW-IB)")


def test_the_email_prints_location_then_new_location_on_a_moved_line():
    rendered = _render([_line(**MOVED), _line(item_code="SRTWCY8826", qty="2", remark="ORDER")])
    rows = _rows(rendered["body_html"])
    assert rows[2] == [
        "LOCATION", "NEW LOCATION", "ITEM CODE", "QTY", "DELIVERY", "REMARK",
    ], rows[2]
    assert rows[3] == [
        "BRW-IB", "BRW", "SRTWC8826-SC", "4", "15/11/2026", "NEW LOCATION (was BRW-IB)",
    ], rows[3]
    # A line that did not move: its own location, NEW LOCATION blank (like NEW QTY).
    assert rows[4] == ["BRW-BB", "", "SRTWCY8826", "2", "15/11/2026", "ORDER"], rows[4]
    text = rendered["body_text"]
    assert "LOCATION | NEW LOCATION | ITEM CODE | QTY | DELIVERY | REMARK" in text, text
    assert "BRW-IB | BRW | SRTWC8826-SC | 4 | 15/11/2026 | NEW LOCATION (was BRW-IB)" in text, text
    assert "BRW-BB |  | SRTWCY8826 | 2 | 15/11/2026 | ORDER" in text, text


def test_no_moved_line_no_new_location_column():
    rendered = _render([_line()])
    rows = _rows(rendered["body_html"])
    assert rows[2] == ["LOCATION", "ITEM CODE", "QTY", "DELIVERY", "REMARK"], rows[2]
    assert "NEW LOCATION" not in rendered["body_text"]


def test_a_moved_line_with_a_new_qty_prints_both_pairs():
    rows = _rows(_render([_line(
        qty="8", location="BRW", was={"location": "BRW-IB", "qty": "10"},
        remark="CANCEL 2, NEW LOCATION (was BRW-IB)",
    )])["body_html"])
    assert rows[2] == [
        "LOCATION", "NEW LOCATION", "ITEM CODE", "QTY", "NEW QTY", "DELIVERY", "REMARK",
    ], rows[2]
    assert rows[3][:5] == ["BRW-IB", "BRW", "SRTWC8826-SC", "10", "8"], rows[3]


def _sheet(lines):
    import openpyxl

    from app.services.order_inquiry_worklist_service import handover_xlsx

    sheet = openpyxl.load_workbook(io.BytesIO(handover_xlsx(lines))).active
    rows = [list(r) for r in sheet.iter_rows(values_only=True)]
    head = [h for h in rows[0] if h is not None]
    return head, [dict(zip(head, r)) for r in rows[1:] if any(v is not None for v in r)]


def test_the_attachment_prints_location_then_new_location_on_a_moved_line():
    head, records = _sheet([_line(**MOVED), _line(item_code="SRTWCY8826", remark="ORDER")])
    at = head.index("LOCATION")
    assert head[at + 1] == "NEW LOCATION", head
    assert (records[0]["LOCATION"], records[0]["NEW LOCATION"]) == ("BRW-IB", "BRW")
    assert (records[1]["LOCATION"], records[1]["NEW LOCATION"]) == ("BRW-BB", None)


def test_the_attachment_has_no_new_location_column_when_nothing_moved():
    head, _records = _sheet([_line()])
    assert "NEW LOCATION" not in head, head


def test_the_layout_migration_downgrades_to_oihr_0011s_document():
    from app.models.email_template import EmailTemplate

    from ._pg_fixture import blank_session
    from .test_order_inquiry_handover_automation import _run_downgrade, _run_upgrade

    with blank_session() as db:
        for name in _CHAIN:
            _run_upgrade(_migration(name), db)
        _run_downgrade(_migration("oihr_0012_new_location"), db)
        row = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.code == "order_inquiry_handover_default")
            .one()
        )
        previous = _migration("oihr_0011_item_code_wrap")
        assert row.body_text == previous._BODY_TEXT
        assert row.layout_json == previous._LAYOUT
