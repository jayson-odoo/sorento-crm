"""FULFIL-SO-REMARK template (AC-11 layout half, AC-14, AC-15): migration `oihr_0010_so_remark_column`
puts REMARK last in the SO table (HTML and text), only while the row is exactly `oihr_0009`'s."""
from __future__ import annotations

import logging

from app.models.email_template import EmailTemplate

from ._pg_fixture import blank_session
from .test_oi_saved_line_email import _line, _migration, _rows
from .test_order_inquiry_handover_automation import _run_downgrade, _run_upgrade

CODE = "order_inquiry_handover_default"
CHAIN = (
    "oihr_0006_no_remark_column",
    "oihr_0007_excel_remark",
    "oihr_0008_so_table_on_top",
    "oihr_0009_split_rows",
)
NEW = "oihr_0010_so_remark_column"


def _row(db):
    return db.query(EmailTemplate).filter(EmailTemplate.code == CODE).one()


def _at_0009(db):
    for name in CHAIN:
        _run_upgrade(_migration(name), db)
    row = _row(db)
    db.refresh(row)
    return row


def _context(orders, lines):
    return {
        "handover": {
            "subject_scope": "SO425879", "verbs": ["ORDER"], "headline": "ORDER",
            "orders": orders, "lines": lines, "line_count": len(lines),
            "link": "https://crm.test/project-sales/order-inquiries?query=SO425879",
        },
        "actor": {"name": "Aisyah", "email": "cs@example.com"},
        "today": "25/10/2026",
    }


def _order(remark):
    return {
        "so_number": "SO425879", "so_date": "10/10/2026", "customer": "UNIJOH DEVELOPMENT SDN BHD",
        "project": "RESIDENSI A", "remark": remark,
    }


def _render(db, orders, lines):
    from app.services.email_template_service import EmailTemplateService

    row = _row(db)
    db.refresh(row)
    return EmailTemplateService(db).render(row, _context(orders, lines))


def test_ac14_upgrade_puts_remark_last_in_the_so_table_html_and_text():
    with blank_session() as db:
        _at_0009(db)
        _run_upgrade(_migration(NEW), db)

        rendered = _render(db, [_order("Mockup")], [_line()])
        rows = _rows(rendered["body_html"])
        assert rows[0] == ["S/O NO", "SO DATE", "CUSTOMER", "PROJECT", "REMARK"], rows[0]
        assert rows[1] == [
            "SO425879", "10/10/2026", "UNIJOH DEVELOPMENT SDN BHD", "RESIDENSI A", "Mockup",
        ], rows[1]
        assert "S/O NO | SO DATE | CUSTOMER | PROJECT | REMARK" in rendered["body_text"]
        assert "SO425879 | 10/10/2026 | UNIJOH DEVELOPMENT SDN BHD | RESIDENSI A | Mockup" in (
            rendered["body_text"]
        )


def test_ac11_blank_remark_prints_a_blank_cell():
    with blank_session() as db:
        _at_0009(db)
        _run_upgrade(_migration(NEW), db)

        rows = _rows(_render(db, [_order("")], [_line()])["body_html"])
        assert rows[1][-1] == "", rows[1]
        assert len(rows[1]) == 5


def test_ac15_the_line_table_is_unchanged():
    with blank_session() as db:
        _at_0009(db)
        _run_upgrade(_migration(NEW), db)

        rows = _rows(_render(db, [_order("")], [_line()])["body_html"])
        assert rows[2] == ["LOCATION", "ITEM CODE", "QTY", "DELIVERY", "REMARK"], rows[2]
        assert rows[3] == ["BRW-BB", "SRTWC8826-SC", "4", "15/11/2026", "ORDER"], rows[3]


def test_ac14_upgrade_is_idempotent():
    with blank_session() as db:
        _at_0009(db)
        module = _migration(NEW)
        _run_upgrade(module, db)
        row = _row(db)
        db.refresh(row)
        first = (row.body_text, row.body_html)
        _run_upgrade(module, db)
        db.refresh(row)
        assert (row.body_text, row.body_html) == first
        assert row.body_text == module._BODY_TEXT


def test_ac14_an_admin_edited_row_is_left_alone_with_a_warning(caplog):
    with blank_session() as db:
        row = _at_0009(db)
        row.body_text = (row.body_text or "") + "\nAdmin footer."
        db.flush()
        edited = row.body_text

        with caplog.at_level(logging.WARNING):
            _run_upgrade(_migration(NEW), db)

        db.refresh(row)
        assert row.body_text == edited
        assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_ac14_a_missing_row_is_inserted():
    with blank_session() as db:
        db.query(EmailTemplate).filter(EmailTemplate.code == CODE).delete()
        db.flush()

        _run_upgrade(_migration(NEW), db)

        row = _row(db)
        assert "REMARK" in row.body_text


def test_ac14_downgrade_restores_oihr_0009_layout():
    with blank_session() as db:
        previous = _migration("oihr_0009_split_rows")
        row = _at_0009(db)
        module = _migration(NEW)
        _run_upgrade(module, db)

        _run_downgrade(module, db)

        db.refresh(row)
        assert row.body_text == previous._BODY_TEXT
        assert row.layout_json == previous._LAYOUT
