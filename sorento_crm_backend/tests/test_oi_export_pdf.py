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


def test_detail_pdf_task_renders_the_email_layout(api, monkeypatch):
    """The real task + render: a PDF whose text carries the email's S/O table and its
    item lines, stored as `application/pdf` under the OI's own download row."""
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
    for heading in ("ORDER INQUIRY", "S/O NO", "SO DATE", "CUSTOMER", "PROJECT",
                    "LOCATION", "ITEM CODE", "QTY", "DELIVERY", "REMARK"):
        assert heading in pdf, f"{heading!r} missing from the PDF: {pdf}"
    assert seeded["core"].so_number in pdf
    assert "03/09/2026" in pdf
    assert item_code in pdf and "BRW-BB" in pdf
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
    pdf = _pdf_text(captured["bytes"])
    assert f"{MARKER}-KEEPME" in pdf and kept["core"].so_number in pdf
    assert f"{MARKER}-DROPME" not in pdf and dropped["core"].so_number not in pdf


# --------------------------------------------------------------------------- #
# Layout (pure): the email's columns and split-row rule
# --------------------------------------------------------------------------- #


def test_layout_one_block_per_so_and_split_rows_follow_the_email():
    from app.services.order_inquiry_pdf import build_html, orders

    rows = [
        {"so_number": "SO2", "so_date": date(2026, 9, 2), "customer_name": "B CO",
         "project_title": "P2", "so_line_id": "l2", "item_code": "B1", "location": "KL",
         "qty": "5", "delivery_date": date(2026, 10, 1), "split_remark": "ORDER"},
        {"so_number": "SO1", "so_date": date(2026, 9, 1), "customer_name": "A CO",
         "project_title": "P1", "so_line_id": "l1", "item_code": "A1", "location": "JB",
         "qty": "10", "delivery_date": date(2026, 10, 5), "change_qty": 4,
         "change_date": date(2026, 11, 1), "split_remark": "SPLIT 1",
         "plan_key": (date(2026, 10, 5), "l1", 0)},
        {"so_number": "SO1", "so_date": date(2026, 9, 1), "customer_name": "A CO",
         "project_title": "P1", "so_line_id": "l1", "item_code": "A1", "location": "JB",
         "qty": None, "delivery_date": None, "change_qty": 6, "change_date": None,
         "split_remark": "SPLIT 2", "plan_key": (date(2026, 10, 5), "l1", 1)},
    ]

    built = orders(rows)

    assert [o["so_number"] for o in built] == ["SO1", "SO2"]
    first, second = built[0]["lines"]
    assert first == {"location": "JB", "item_code": "A1", "qty": "10", "new_qty": "4",
                     "delivery": "05/10/2026", "new_date": "01/11/2026", "remark": "SPLIT 1"}
    # A split line's later row: LOCATION / ITEM CODE / QTY / DELIVERY blank (AC-G6, AC-G11).
    assert second["location"] == second["item_code"] == second["qty"] == second["delivery"] == ""
    assert second["new_qty"] == "6" and second["remark"] == "SPLIT 2"

    html = build_html(rows)
    # NEW QTY / NEW DATE only on the S/O whose lines moved, as the email.
    so1, so2 = html.split('<div class="so">')[1:]
    assert "NEW QTY" in so1 and "NEW DATE" in so1
    assert "NEW QTY" not in so2 and "NEW DATE" not in so2
    assert "01/09/2026" in so1 and "A CO" in so1 and "P1" in so1


def test_layout_escapes_text():
    from app.services.order_inquiry_pdf import build_html

    html = build_html([{"so_number": "SO<1>", "item_code": "<b>x</b>", "split_remark": "a&b"}])
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "a&amp;b" in html
