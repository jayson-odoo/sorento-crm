"""OI-DOWNLOAD: the Order Inquiry PDF, on the detail page and on the lines list
(`documentation/plans/scm/PLAN-oi-download-21oct.md`).

Same shape as the OI Excel export (`tests/test_oi_export_async.py`): a `user_downloads` row and
an RQ job on `imports`; the file arrives in My Downloads. The PDF is the OI email's layout (S/O
table on top, then LOCATION / ITEM CODE / QTY / DELIVERY / REMARK lines) printed off the SAME
rows the OI Excel prints. A download never sends an email.

Postgres only (`blank_session` via the `api` fixture), every test seeds its own OI.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import text

from .test_oi_export_async import HEADERS_BASE, _NoCloseSession
from .test_oi_header_list import MARKER, _header, _uid, _user, api

__all__ = ["api"]  # re-exported fixture


def _fake_enqueue(calls: list):
    def _enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})
        return type("J", (), {"id": "fake-job-id"})()

    return _enqueue


def _no_email(monkeypatch) -> list:
    """Every automation dispatch (the handover email's only way out) is recorded."""
    from app.services.automation_service import AutomationService

    sent: list = []
    monkeypatch.setattr(
        AutomationService, "dispatch_event", lambda self, *a, **k: sent.append((a, k))
    )
    return sent


class _CapturingBackend:
    def __init__(self, captured: dict):
        self.captured = captured

    def upload_file(self, *, file_content, file_path, content_type):
        self.captured.update(bytes=file_content, path=file_path, content_type=content_type)
        return (file_path, None)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def test_detail_pdf_post_creates_download_row_and_enqueues(api, monkeypatch):
    from app.services import queue_service
    from app.tasks.export_tasks import generate_order_inquiry_xlsx

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id
    inquiry_no = seeded["inquiry"].inquiry_no
    calls: list = []
    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue(calls))
    sent = _no_email(monkeypatch)

    resp = client.post(f"{HEADERS_BASE}/{inquiry_id}/export/pdf")

    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["kind"] == "order_inquiry_pdf", body
    row = db.execute(text(
        "SELECT kind, source_entity_type, source_entity_id::text AS source_entity_id, "
        "       filename, user_id FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row["source_entity_type"] == "order_inquiry"
    assert row["source_entity_id"] == inquiry_id
    # The PR / sponsorship form naming: `<what it is>-<number>.pdf`.
    assert row["filename"] == f"order-inquiry-{inquiry_no}.pdf", row["filename"]

    assert len(calls) == 1, calls
    assert calls[0]["func"] is generate_order_inquiry_xlsx
    assert calls[0]["args"] == (body["id"], inquiry_id, row["user_id"])
    assert calls[0]["kwargs"] == {"fmt": "pdf", "queue_name": "imports", "job_timeout": 600}
    assert sent == [], "a download must never send an email"


def test_detail_pdf_post_404_for_unknown_inquiry(api):
    client, db, _company_id = api
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    resp = client.post(f"{HEADERS_BASE}/{_uid()}/export/pdf")

    assert resp.status_code == 404, resp.text
    assert db.execute(text("SELECT count(*) FROM user_downloads")).scalar() == before


def test_detail_pdf_and_excel_do_not_block_each_other(api, monkeypatch):
    """The in-flight guard is per format: a pending Excel never refuses a PDF click."""
    from app.services import queue_service

    client, db, company_id = api
    inquiry_id = _header(db, company_id)["inquiry"].id
    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue([]))

    assert client.post(f"{HEADERS_BASE}/{inquiry_id}/export").status_code in (200, 201)
    assert client.post(f"{HEADERS_BASE}/{inquiry_id}/export/pdf").status_code in (200, 201)
    assert client.post(f"{HEADERS_BASE}/{inquiry_id}/export/pdf").status_code == 409


def test_detail_pdf_needs_the_view_permission(monkeypatch):
    from .test_oi_header_list import _client_no_view, _restore, _sorento
    from ._pg_fixture import blank_session
    from app.models.base import company_scope
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        inquiry_id = _header(db, company_id)["inquiry"].id
        client, originals = _client_no_view(db)
        try:
            with company_scope(db, frozenset({company_id})):
                resp = client.post(f"{HEADERS_BASE}/{inquiry_id}/export/pdf")
                listed = client.post(f"{HEADERS_BASE}/export/pdf", json={})
        finally:
            _restore(originals)
    assert resp.status_code == 403, resp.text
    assert listed.status_code == 403, listed.text


def test_worklist_pdf_post_creates_download_row_and_enqueues_with_filters(api, monkeypatch):
    from app.services import queue_service
    from app.tasks.export_tasks import generate_order_inquiry_worklist_xlsx

    client, db, company_id = api
    _header(db, company_id)
    calls: list = []
    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue(calls))
    sent = _no_email(monkeypatch)

    resp = client.post(f"{HEADERS_BASE}/export/pdf", json={"state": "raised"})

    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["kind"] == "order_inquiry_worklist_pdf", body
    row = db.execute(text(
        "SELECT source_entity_id, filename, user_id FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row["source_entity_id"] is None
    assert re.match(r"^order-inquiries-\d{8}\.pdf$", row["filename"] or ""), row["filename"]

    assert len(calls) == 1, calls
    assert calls[0]["func"] is generate_order_inquiry_worklist_xlsx
    assert calls[0]["args"] == (body["id"], {"state": "raised"}, row["user_id"])
    assert calls[0]["kwargs"] == {
        "company_id": company_id, "fmt": "pdf", "queue_name": "imports", "job_timeout": 600,
    }
    assert sent == []


def test_worklist_pdf_and_excel_do_not_block_each_other(api, monkeypatch):
    from app.services import queue_service

    client, db, company_id = api
    _header(db, company_id)
    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue([]))

    assert client.post(f"{HEADERS_BASE}/export", json={}).status_code in (200, 201)
    assert client.post(f"{HEADERS_BASE}/export/pdf", json={}).status_code in (200, 201)
    assert client.post(f"{HEADERS_BASE}/export/pdf", json={}).status_code == 409


def test_worklist_pdf_post_rejects_bad_filter(api):
    client, db, _company_id = api
    resp = client.post(f"{HEADERS_BASE}/export/pdf", json={"project_id": "not-a-uuid"})
    assert resp.status_code in (400, 422), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_pdf'"
    )).scalar()
    assert count == 0


# --------------------------------------------------------------------------- #
# Tasks: real render
# --------------------------------------------------------------------------- #


def _pdf_text(pdf_bytes: bytes) -> str:
    import fitz  # PyMuPDF, already a backend dependency

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def test_detail_pdf_task_renders_the_excel_sheet(api, monkeypatch):
    """The real task + render: a PDF of the OI Excel sheet (its headings and the row's
    values), stored as `application/pdf` under the OI's own download row."""
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    client, db, company_id = api
    item_code = f"{MARKER}-PDFITEM"
    seeded = _header(
        db, company_id, so_date=date(2026, 9, 3),
        rows=[{"item_code": item_code, "stock_location": "BRW-BB", "qty": "7"}],
    )
    inquiry_id = seeded["inquiry"].id
    user_id = _user(db, f"{MARKER} pdf exporter")
    db.flush()
    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_pdf", source_entity_type="order_inquiry",
        source_entity_id=inquiry_id, filename="order-inquiry-OI.pdf",
    )
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    captured: dict = {}
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda p: _CapturingBackend(captured))
    sent = _no_email(monkeypatch)

    result = export_tasks.generate_order_inquiry_xlsx(str(dl.id), inquiry_id, user_id, fmt="pdf")

    assert result["status"] == "ready", result
    assert captured["content_type"] == "application/pdf"
    assert f"exports/order-inquiry-pdf/{dl.id}/" in captured["path"], captured["path"]
    assert captured["bytes"][:4] == b"%PDF"
    pdf = _pdf_text(captured["bytes"])
    flat = " ".join(pdf.split())
    squashed = "".join(pdf.split())  # a long test code may wrap inside its cell
    for heading in ("ORDER INQUIRY", "SO DATE", "S/O NO", "ITEM CODE", "QTY", "SUPPLIER",
                    "LOCATION", "ACKNOWLEDGED", "REMARK"):
        assert heading in flat, f"{heading!r} missing from the PDF: {flat}"
    assert seeded["core"].so_number in squashed
    assert "03/09/2026" in squashed
    assert item_code in squashed and "BRW-BB" in squashed
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready" and row.filename == "order-inquiry-OI.pdf"
    assert sent == []


def test_detail_xlsx_task_is_unchanged_by_the_pdf_format(api, monkeypatch):
    """No `fmt` (every job queued so far) is still the Excel - the email's own workbook."""
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    client, db, company_id = api
    inquiry_id = _header(db, company_id)["inquiry"].id
    user_id = _user(db, f"{MARKER} xlsx exporter")
    db.flush()
    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=inquiry_id, filename="OI.xlsx",
    )
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    captured: dict = {}
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda p: _CapturingBackend(captured))

    result = export_tasks.generate_order_inquiry_xlsx(str(dl.id), inquiry_id, user_id)

    assert result["status"] == "ready", result
    assert captured["bytes"][:2] == b"PK", "the Excel must still be an xlsx"
    assert f"exports/order-inquiry/{dl.id}/" in captured["path"]


def test_worklist_pdf_task_prints_only_the_filtered_rows(api, monkeypatch):
    from app.models.base import UNSET, set_company_scope
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    client, db, company_id = api
    kept = _header(db, company_id, rows=[{"item_code": f"{MARKER}-KEEPME"}])
    dropped = _header(db, company_id, rows=[{"item_code": f"{MARKER}-DROPME"}])
    user_id = _user(db, f"{MARKER} wl pdf exporter")
    db.flush()
    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_worklist_pdf", filename="order-inquiries.pdf",
    )
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    captured: dict = {}
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda p: _CapturingBackend(captured))

    set_company_scope(db, UNSET)
    result = export_tasks.generate_order_inquiry_worklist_xlsx(
        str(dl.id), {"query": kept["core"].so_number}, user_id,
        company_id=str(company_id), fmt="pdf",
    )

    assert result["status"] == "ready", result
    assert captured["content_type"] == "application/pdf"
    assert f"exports/order-inquiry-worklist-pdf/{dl.id}/" in captured["path"]
    pdf = "".join(_pdf_text(captured["bytes"]).split())  # cells may wrap
    assert f"{MARKER}-KEEPME" in pdf and kept["core"].so_number in pdf
    assert f"{MARKER}-DROPME" not in pdf and dropped["core"].so_number not in pdf


def test_worklist_pdf_task_never_prints_another_companys_rows(api, monkeypatch):
    """The list task adopts the enqueuing request's company: a matching OI of another
    company stays out of the PDF."""
    from app.models.base import UNSET, set_company_scope
    from app.models.company import Company
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    client, db, company_id = api
    other_id = _uid()
    db.add(Company(id=other_id, name=f"{MARKER} Other Co", code=f"ZZT{other_id[:6]}"))
    db.flush()
    item = f"{MARKER}-SCOPED"
    ours = _header(db, company_id, rows=[{"item_code": item}])
    set_company_scope(db, None)
    theirs = _header(db, other_id, rows=[{"item_code": item}])
    user_id = _user(db, f"{MARKER} scoped exporter")
    db.flush()
    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_worklist_pdf", filename="order-inquiries.pdf",
    )
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    captured: dict = {}
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda p: _CapturingBackend(captured))

    set_company_scope(db, UNSET)
    result = export_tasks.generate_order_inquiry_worklist_xlsx(
        str(dl.id), {"query": item}, user_id, company_id=str(company_id), fmt="pdf",
    )

    assert result["status"] == "ready", result
    pdf = "".join(_pdf_text(captured["bytes"]).split())  # cells may wrap
    assert ours["core"].so_number in pdf
    assert theirs["core"].so_number not in pdf


# --------------------------------------------------------------------------- #
# Layout (pure): the Excel sheet as a PDF - one table, the xlsx's own header and rows
# (owner, 21 Oct: "the pdf needs to be like Excel la, just in pdf format ... 1 table")
# --------------------------------------------------------------------------- #

from html.parser import HTMLParser


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = 0
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables += 1
        elif tag == "tr":
            self.rows.append([])
        elif tag in ("th", "td"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self._cell is not None:
            self.rows[-1].append("".join(self._cell))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


_SHEET_ROWS = [
    {"so_date": date(2025, 12, 1), "so_number": "SO380096", "item_code": "CWCY605",
     "qty": "5", "delivery_date": date(2026, 8, 3), "supplier": "TAIYANG",
     "project_customer": "SHING SOON HENG HARDWARE SDN BHD / LOT 1940 / MUAR",
     "location": "BRW-BB", "split_remark": "ORDER"},
    {"so_date": date(2025, 12, 1), "so_number": "SO380096", "item_code": "CWCY605",
     "qty": "3", "delivery_date": date(2026, 9, 1), "supplier": "TAIYANG",
     "project_customer": "SHING SOON HENG HARDWARE SDN BHD / LOT 1940 / MUAR",
     "location": "BRW-BB"},
    {"so_date": date(2026, 9, 14), "so_number": "SO394881", "item_code": "TGB1200W",
     "qty": "12", "delivery_date": None, "supplier": None,
     "project_customer": "BUIMACO SDN BHD / TUJU RESIDENCE", "location": "KLANG"},
]


def _xlsx_rows(rows):
    """The OI workbook's own header + data rows, read back from the real writer."""
    from openpyxl import Workbook

    from app.services.order_inquiry_worklist_service import (
        EXPORT_TITLE, OrderInquiryWorklistService,
    )

    wb = Workbook()
    wb.remove(wb.active)
    OrderInquiryWorklistService(db=None)._write_sheet(wb, EXPORT_TITLE, rows)
    ws = wb[EXPORT_TITLE]
    return [[cell.value for cell in row] for row in ws.iter_rows(min_row=2)]


def _pdf_html(rows):
    from app.services import order_inquiry_pdf
    from app.services.order_inquiry_worklist_service import (
        EXPORT_HEADINGS, OrderInquiryWorklistService,
    )

    values = OrderInquiryWorklistService(db=None)._sheet_values(rows)
    return order_inquiry_pdf.build_html(EXPORT_HEADINGS, values)


def test_pdf_is_one_table_whose_header_is_the_xlsx_header_row():
    html = _pdf_html(_SHEET_ROWS)
    parsed = _Tables()
    parsed.feed(html)

    xlsx = _xlsx_rows(_SHEET_ROWS)
    assert parsed.tables == 1, f"expected ONE table, got {parsed.tables}"
    assert parsed.rows[0] == list(xlsx[0]), parsed.rows[0]
    assert len(parsed.rows) == len(xlsx), "one PDF row per xlsx row"


def test_pdf_rows_are_the_xlsx_rows_cell_for_cell():
    from app.services.order_inquiry_pdf import cell_text

    parsed = _Tables()
    parsed.feed(_pdf_html(_SHEET_ROWS))
    xlsx = _xlsx_rows(_SHEET_ROWS)

    assert parsed.rows[1:] == [[cell_text(v) for v in row] for row in xlsx[1:]]
    # Spot values the way a reader sees them: dd/mm/yyyy dates, whole quantities, the
    # TOTAL QTY on the last row of a supplier + item code run.
    flat = [cell for row in parsed.rows[1:] for cell in row]
    assert "01/12/2025" in flat and "03/08/2026" in flat
    assert "8" in flat  # TOTAL QTY of the CWCY605 run (5 + 3)
    assert "5" in flat and "5.0" not in flat


def test_pdf_wears_the_house_style_landscape_with_a_repeating_header():
    html = _pdf_html(_SHEET_ROWS)

    assert "size: A4 landscape" in html
    assert "display: table-header-group" in html  # header row repeats on every page
    assert "#404040" in html and "#ffffff" in html.lower()  # dark header, white text
    assert "1px solid" in html and "wrap" in html


def test_pdf_with_no_rows_is_still_the_one_table_with_its_header():
    parsed = _Tables()
    parsed.feed(_pdf_html([]))
    from app.services.order_inquiry_worklist_service import EXPORT_HEADINGS

    assert parsed.tables == 1 and parsed.rows[0] == list(EXPORT_HEADINGS)


def test_pdf_escapes_text():
    from app.services import order_inquiry_pdf

    html = order_inquiry_pdf.build_html(("A", "B"), [["<b>x</b>", "a&b"]])
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "a&amp;b" in html
