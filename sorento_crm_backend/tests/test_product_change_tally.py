"""PRODUCT-CHANGE-TALLY (owner, 28 Oct 2026, SO426847 line 48): "I thought the email, popup
preview and the attachment supposed to tally". AutoCount swapped a line's product in place; the
Order Inquiry email printed ITEM CODE (old) / NEW ITEM CODE (new), the Confirm preview did not.

One fixture (`tests/fixtures/product_change_tally.json`) is the same line as the email context
carries it and as the split read (the preview's source) carries it. Here: the email (rendered
through the real template chain) and the attachment (`handover_xlsx`) print the fixture's
`expected`; the frontend's `productChangeTally.test.tsx` renders the preview from the same file
against the same `expected`. A real swap then proves the read and the email produce that shape.
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import openpyxl

from .scm.test_line_splits_api import _put, _sp, _url
from .test_oi_handover_excel import _drain_on_test_connection, _enabled_handover, stored  # noqa: F401
from .test_oi_product_follow_apply import _apply, _swap_fixture
from .test_oi_saved_line_email import _migration, _rows
from .test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
    _run_upgrade,
)
from .test_planning_change_apply_on_board import api, world  # noqa: F401 - fixtures reused

FIXTURE = Path(__file__).parent / "fixtures" / "product_change_tally.json"
#: The live template is `oihr_0006` converted by every later layout migration, in order.
TEMPLATE_CHAIN = (
    "oihr_0006_no_remark_column",
    "oihr_0007_excel_remark",
    "oihr_0008_so_table_on_top",
    "oihr_0009_split_rows",
    "oihr_0010_so_remark_column",
)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _email_cells(lines: list) -> list:
    """The email's line table (the real template, HTML part), as {heading: cell} per row."""
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService

    from ._pg_fixture import blank_session

    first = lines[0]
    context = {
        "handover": {
            "subject_scope": first["so_number"], "verbs": ["ORDER"], "headline": "NEW ITEM CODE",
            "orders": [{
                "so_number": first["so_number"], "so_date": first["so_date"],
                "customer": first["customer"], "project": first["project"], "remark": "",
            }],
            "lines": lines, "line_count": len(lines),
            "link": "https://crm.test/project-sales/order-inquiries",
        },
        "actor": {"name": "Tester", "email": "cs@example.com"},
        "today": "28/10/2026",
    }
    with blank_session() as db:
        for name in TEMPLATE_CHAIN:
            _run_upgrade(_migration(name), db)
        template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.code == "order_inquiry_handover_default")
            .one()
        )
        db.refresh(template)
        html = EmailTemplateService(db).render(template, context)["body_html"]
    rows = _rows(html)
    at = next(index for index, row in enumerate(rows) if row and row[0] == "LOCATION")
    heads = rows[at]
    return [dict(zip(heads, row)) for row in rows[at + 1 :] if len(row) == len(heads)]


def _sheet_cells(data: bytes) -> list:
    """The attachment's rows, as {heading: cell} (row 1 the title, row 2 the headings)."""
    sheet = openpyxl.load_workbook(io.BytesIO(data)).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    heads = list(rows[1])
    return [dict(zip(heads, row)) for row in rows[2:]]


def test_email_and_attachment_print_the_fixture_line_with_item_code_and_new_item_code():
    from app.services.order_inquiry_worklist_service import handover_xlsx

    fx = _fixture()
    expected = fx["expected"]
    [email] = _email_cells([fx["email_line"]])
    [sheet] = _sheet_cells(handover_xlsx([fx["email_line"]]))

    assert (email["ITEM CODE"], email["NEW ITEM CODE"]) == (
        expected["item_code"], expected["new_item_code"],
    ), email
    assert (sheet["ITEM CODE"], sheet["NEW ITEM CODE"]) == (
        expected["item_code"], expected["new_item_code"],
    ), sheet
    assert sheet["REMARK"] == expected["remark"], sheet
    if "REMARK" in email:
        assert email["REMARK"] == expected["remark"], email


def test_the_preview_read_of_the_fixture_line_is_the_email_line():
    """The split read line (the preview's source) states the same old/new pair and REMARK as
    the email line of the same fixture; the frontend renders this read."""
    from app.schemas.project_line_split import LineSplitLineOut

    fx = _fixture()
    expected = fx["expected"]
    read = LineSplitLineOut.model_validate(fx["split_read_line"])
    assert (read.was_item_code, read.item_code) == (
        expected["item_code"], expected["new_item_code"],
    )
    assert read.remark_generated == expected["remark"]
    email = fx["email_line"]
    assert (email["was"]["item_code"], email["item_code"]) == (
        read.was_item_code, read.item_code,
    )
    assert email["remark"] == read.remark_generated


def _handover_and_attachment(calls, stored, new_code):
    [call] = [c for c in _handover_calls(calls) if any(
        line["item_code"] == new_code for line in c["context"]["handover"]["lines"]
    )]
    lines = [line for line in call["context"]["handover"]["lines"] if line["item_code"] == new_code]
    [excel] = [
        a for a in call["context"].get("email_attachments", []) if a["filename"].endswith(".xlsx")
    ]
    [upload] = [u for u in stored if u["key"] == excel["storage_key"]]
    sheet = [row for row in _sheet_cells(upload["bytes"]) if row.get("NEW ITEM CODE") == new_code]
    return lines, sheet


def test_a_real_swap_reads_alike_in_preview_email_and_attachment(api, monkeypatch, stored):
    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    _drain_on_test_connection(monkeypatch, world)
    _enabled_handover(world)
    fx = _swap_fixture(api, acknowledged=True)
    old, new = fx["old"].product_code, fx["new"].product_code

    read = fx["client"].get(_url(fx["order"].id)).json()
    [preview] = [line for line in read["lines"] if line["line_id"] == str(fx["line"].id)]
    assert (preview["was_item_code"], preview["item_code"]) == (old, new), preview

    # The preview's REMARK: the board's saved words, else the read's own (`remark_generated`).
    # A swap with no saved draft has none, so the preview prints the read's words.
    board = fx["client"].get(
        "/api/v1/project-sales/fulfilment-planning/board",
        params={"orders": fx["order"].autocount_doc_no, "granularity": "week"},
    )
    assert board.status_code == 200, board.text
    [on_board] = [
        c for c in board.json()["contributions"] if c.get("project_line_id") == str(fx["line"].id)
    ]
    assert on_board["saved_remark"] is None, on_board["saved_remark"]

    calls.clear()
    response = _apply(fx)
    assert response.status_code == 200, response.text
    world.db.commit()

    lines, sheet = _handover_and_attachment(calls, stored, new)
    assert len(lines) == 1, lines
    [email] = _email_cells(lines)
    assert (email["ITEM CODE"], email["NEW ITEM CODE"]) == (old, new), email
    assert len(sheet) == 1, sheet
    assert (sheet[0]["ITEM CODE"], sheet[0]["NEW ITEM CODE"]) == (old, new), sheet
    assert preview["remark_generated"] == lines[0]["remark"] == sheet[0]["REMARK"], (
        preview["remark_generated"], lines[0]["remark"], sheet[0]["REMARK"],
    )


def test_a_split_swapped_line_prints_item_code_and_new_item_code_on_its_rows(
    api, monkeypatch, stored,
):
    """A swapped line the planner split: its email rows come from `line_plans`
    (`_queue_plan_rows`), and they carry the old code like the preview's read does."""
    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    _drain_on_test_connection(monkeypatch, world)
    _enabled_handover(world)
    fx = _swap_fixture(api, acknowledged=True)
    old, new = fx["old"].product_code, fx["new"].product_code
    line_id = str(fx["line"].id)
    s = SimpleNamespace(client=fx["client"], order=fx["order"])
    saved = _put(s, [{"line_id": line_id, "splits": [
        _sp(6, date(2026, 11, 20), on=line_id),
        _sp(4, date(2026, 12, 4), on=line_id),
    ]}])
    assert saved.status_code == 200, saved.text

    read = fx["client"].get(_url(fx["order"].id)).json()
    [preview] = [line for line in read["lines"] if line["line_id"] == line_id]
    assert (preview["was_item_code"], preview["item_code"]) == (old, new), preview

    calls.clear()
    response = _apply(fx)
    assert response.status_code == 200, response.text
    world.db.commit()

    lines, sheet = _handover_and_attachment(calls, stored, new)
    assert [line["qty"] for line in lines] == ["6", "4"], lines
    assert all((line["was"] or {}).get("item_code") == old for line in lines), lines
    email = _email_cells(lines)
    assert [(row["ITEM CODE"], row["NEW ITEM CODE"]) for row in email][0] == (old, new), email
    assert [row["NEW ITEM CODE"] for row in sheet] == [new, new], sheet
    assert sheet[0]["ITEM CODE"] == old, sheet


def test_a_swapped_line_with_a_saved_draft_reads_alike_on_board_email_and_attachment(
    api, monkeypatch, stored,
):
    """SWAP-REMARK-TALLY (follow-up of #1956): with a saved draft the Confirm review prints the
    board's `saved_remark` (`savedRemark ?? remarkGenerated`), so for a swapped line it must be
    the email line's remark, and the attachment's REMARK the same words."""
    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    _drain_on_test_connection(monkeypatch, world)
    _enabled_handover(world)
    fx = _swap_fixture(api, acknowledged=True)
    new = fx["new"].product_code
    params = {"orders": fx["order"].autocount_doc_no, "granularity": "week"}
    base = "/api/v1/project-sales/fulfilment-planning"

    def on_board():
        board = fx["client"].get(f"{base}/board", params=params)
        assert board.status_code == 200, board.text
        [got] = [
            c for c in board.json()["contributions"]
            if c.get("project_line_id") == str(fx["line"].id)
        ]
        return got

    saved = fx["client"].put(
        f"{base}/lines/{on_board()['key']}/draft",
        json={"decision": {
            "verdict": "amended", "reserve": [], "borrow": [], "buy_qty": "10",
            "reason": "Planner choice.",
        }},
    )
    assert saved.status_code == 200, saved.text
    saved_remark = on_board()["saved_remark"]

    calls.clear()
    response = _apply(fx)
    assert response.status_code == 200, response.text
    world.db.commit()

    lines, sheet = _handover_and_attachment(calls, stored, new)
    assert len(lines) == 1 and len(sheet) == 1, (lines, sheet)
    assert saved_remark == lines[0]["remark"] == sheet[0]["REMARK"], (
        saved_remark, lines[0]["remark"], sheet[0]["REMARK"],
    )
