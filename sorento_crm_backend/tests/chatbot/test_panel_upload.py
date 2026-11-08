"""AGENT-PANEL-COMPOSER Phase 2 (red): the panel's upload and delete routes.

UAC: documentation/plans/chatbot/agent-panel-composer-8nov-acceptance-criteria.md, C1 to C11.

Real: routes, quota check, renditions (Pillow), PyMuPDF, openpyxl, Postgres blank schema, Redis rate
limit. Faked: the storage backend only (`_panel_files_helpers.MemoryStore`).

Errors are asserted by status plus a message fragment searched in the whole body, so the test does not
care whether the envelope is `{"detail": {"message"}}` or `{"message"}`.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment
from tests.chatbot._panel_files_helpers import (
    DEALERS,
    DRAFT,
    UPLOAD_URL,
    act_as,
    csv_bytes,
    jpeg_bytes,
    panel,  # noqa: F401  (fixture)
    pdf_bytes,
    png_bytes,
    store,  # noqa: F401  (fixture)
    upload,
    xlsx_bytes,
    zip_with,
)
from tests.chatbot.test_panel_principal import (  # noqa: F401  (fixtures and helpers)
    USE,
    _scope_listeners,
    grants,
    seed_staff,
    staff,
)

MACRO_MESSAGE = "Macro workbooks are not read"
MISMATCH = "The file's content does not match its type."
UNREADABLE = "This file cannot be read."


def rows_of(panel_, attachment_id: str):
    db = panel_.factory()
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    links = db.query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id == attachment_id).all()
    return att, links


# --------------------------------------------------------------------------- #
# 201 shapes
# --------------------------------------------------------------------------- #


def test_png_upload_returns_an_image_with_a_thumbnail(panel):
    resp = upload(panel.client, "screenshot.png", png_bytes(), "image/png")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"id", "filename", "size", "mime_type", "kind", "thumb_url", "sheets", "pages"}
    assert body["filename"] == "screenshot.png"
    assert body["kind"] == "image"
    assert body["mime_type"] == "image/png"
    assert body["size"] == len(png_bytes())
    assert isinstance(body["thumb_url"], str) and body["thumb_url"]
    assert body["sheets"] == [] and body["pages"] is None


def test_the_upload_is_a_draft_link_owned_by_the_caller(panel):
    body = upload(panel.client, "p.png", png_bytes(), "image/png").json()

    att, links = rows_of(panel, body["id"])
    assert att is not None and str(att.uploaded_by) == panel.staff.user_id
    assert att.uploader_kind == "user"
    assert len(links) == 1
    assert (links[0].entity_type, str(links[0].entity_id)) == (DRAFT, panel.staff.user_id)
    assert att.file_path in panel.store.objects, "the bytes never reached storage"


def test_xlsx_upload_lists_only_the_non_empty_sheets_with_row_counts(panel):
    data = xlsx_bytes({"Empty A": [], "Dealers": DEALERS, "Empty B": []})

    resp = upload(panel.client, "Dealer contacts Nov.xlsx", data)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "sheet"
    assert body["sheets"] == [{"name": "Dealers", "rows": 2}]
    assert body["pages"] is None and body["thumb_url"] is None


def test_xlsx_with_two_real_sheets_lists_both_in_order(panel):
    data = xlsx_bytes({"Zed": DEALERS, "Alpha": DEALERS[:2]})

    body = upload(panel.client, "two.xlsx", data).json()

    assert body["sheets"] == [{"name": "Zed", "rows": 2}, {"name": "Alpha", "rows": 1}]


def test_csv_upload_is_a_sheet_with_one_unnamed_or_named_sheet_of_rows(panel):
    resp = upload(panel.client, "people.csv", csv_bytes(3), "text/csv")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "sheet"
    assert len(body["sheets"]) == 1 and body["sheets"][0]["rows"] == 3


def test_pdf_upload_reports_its_page_count(panel):
    resp = upload(panel.client, "spec.pdf", pdf_bytes(3), "application/pdf")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "pdf" and body["pages"] == 3
    assert body["sheets"] == [] and body["thumb_url"] is None


def test_a_jpeg_is_an_image_too(panel):
    body = upload(panel.client, "p.JPG", jpeg_bytes(), "image/jpeg").json()
    assert body["kind"] == "image"


# --------------------------------------------------------------------------- #
# C1 to C7: validation
# --------------------------------------------------------------------------- #


def test_c1_an_extension_outside_the_list_is_refused_with_the_allowed_list(panel):
    resp = upload(panel.client, "notes.docx", b"PK\x03\x04whatever")

    assert resp.status_code == 422
    assert "csv" in resp.text and "xlsx" in resp.text and "pdf" in resp.text


def test_c1_xlsm_gets_the_macro_message(panel):
    resp = upload(panel.client, "macros.xlsm", xlsx_bytes({"S": DEALERS}))

    assert resp.status_code == 422
    assert MACRO_MESSAGE in resp.text and "save as .xlsx" in resp.text


def test_c1_heic_is_refused(panel):
    resp = upload(panel.client, "photo.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64)
    assert resp.status_code == 422


def test_c2_a_file_over_10_mb_is_refused(panel):
    big = b"Phone,Name\n" + b"x" * (10 * 1024 * 1024 + 1)

    resp = upload(panel.client, "big.csv", big, "text/csv")

    assert resp.status_code == 422
    assert "File exceeds 10 MB limit." in resp.text
    assert panel.store.objects == {}


@pytest.mark.parametrize(
    "name,data",
    [
        ("fake.png", b"MZ\x90\x00" + b"\x00" * 200),  # an exe named png
        ("fake.pdf", b"just some text, not a pdf\n"),
        ("fake.csv", b"a,b\n1,\x002\n"),  # NUL byte
        ("fake.xlsx", b"%PDF-1.4 not a zip"),
        ("fake.xls", b"PK\x03\x04 a zip is not OLE"),
        ("fake.jpg", png_bytes()),  # right file, wrong extension
    ],
)
def test_c3_content_must_match_the_extension(panel, name, data):
    resp = upload(panel.client, name, data)

    assert resp.status_code == 422, resp.text
    assert MISMATCH in resp.text
    assert panel.store.objects == {}


def test_c3_a_zip_without_a_workbook_part_is_not_an_xlsx(panel):
    resp = upload(panel.client, "empty.xlsx", zip_with({"hello.txt": b"hi"}))

    assert resp.status_code == 422
    assert MISMATCH in resp.text


def test_c4_an_xlsx_carrying_a_vba_project_is_refused_as_a_macro_workbook(panel):
    members = {"xl/workbook.xml": b"<workbook/>", "xl/vbaProject.bin": b"\x00macro"}

    resp = upload(panel.client, "sneaky.xlsx", zip_with(members))

    assert resp.status_code == 422
    assert MACRO_MESSAGE in resp.text
    assert panel.store.objects == {}


def test_c4_a_macro_enabled_content_type_is_refused(panel):
    types = (
        b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Override PartName="/xl/workbook.xml" '
        b'ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/></Types>'
    )
    resp = upload(panel.client, "sneaky2.xlsx", zip_with({"xl/workbook.xml": b"<workbook/>", "[Content_Types].xml": types}))

    assert resp.status_code == 422
    assert MACRO_MESSAGE in resp.text


def test_c4_a_zip_with_a_huge_compression_ratio_is_refused(panel):
    bomb = zip_with({"xl/workbook.xml": b"<workbook/>", "xl/worksheets/sheet1.xml": b"\x00" * (30 * 1024 * 1024)})
    assert len(bomb) < 1024 * 1024  # it really is a bomb: tiny on the wire

    resp = upload(panel.client, "bomb.xlsx", bomb)

    assert resp.status_code == 422
    assert panel.store.objects == {}


def test_c4_the_shared_guard_passes_a_clean_workbook_and_stops_macros_and_bombs():
    from app.services.xlsx_guard import inspect_xlsx_zip

    inspect_xlsx_zip(xlsx_bytes({"S": DEALERS}))  # no raise
    with pytest.raises(Exception):
        inspect_xlsx_zip(zip_with({"xl/workbook.xml": b"<w/>", "xl/vbaProject.bin": b"x"}))
    with pytest.raises(Exception):
        inspect_xlsx_zip(zip_with({"xl/workbook.xml": b"<w/>", "xl/big.xml": b"\x00" * (101 * 1024 * 1024)}))


def test_c4_the_supplier_reader_still_imports_the_shared_guard():
    from app.services import xlsx_guard
    from app.services.procurement import supplier_price_list_reader as reader

    assert getattr(reader, "inspect_xlsx_zip", None) is xlsx_guard.inspect_xlsx_zip
    assert not hasattr(reader, "_inspect_zip"), "the guard was copied, not moved"


def test_c6_a_corrupt_workbook_is_unreadable(panel):
    resp = upload(panel.client, "corrupt.xlsx", zip_with({"xl/workbook.xml": b"this is not xml at all"}))

    assert resp.status_code == 422
    assert UNREADABLE in resp.text
    assert panel.store.objects == {}


def test_c6_a_corrupt_pdf_is_unreadable(panel):
    resp = upload(panel.client, "corrupt.pdf", b"%PDF-1.4\n" + b"garbage" * 50)

    assert resp.status_code == 422
    assert UNREADABLE in resp.text


def test_c6_an_image_pillow_cannot_open_is_unreadable(panel):
    resp = upload(panel.client, "broken.png", b"\x89PNG\r\n\x1a\n" + b"not really image data" * 10)

    assert resp.status_code == 422
    assert UNREADABLE in resp.text


def test_c7_a_pdf_over_20_pages_is_refused(panel):
    resp = upload(panel.client, "long.pdf", pdf_bytes(21), "application/pdf")

    assert resp.status_code == 422
    assert "PDFs over 20 pages are not read." in resp.text


def test_c7_a_20_page_pdf_is_fine(panel):
    resp = upload(panel.client, "just-right.pdf", pdf_bytes(20), "application/pdf")
    assert resp.status_code == 201, resp.text


# --------------------------------------------------------------------------- #
# C8, C9: caps
# --------------------------------------------------------------------------- #


def test_c8_a_sixth_unsent_draft_is_refused(panel):
    for i in range(5):
        assert upload(panel.client, f"f{i}.csv", csv_bytes(), "text/csv").status_code == 201

    resp = upload(panel.client, "f5.csv", csv_bytes(), "text/csv")

    assert resp.status_code == 422, resp.text


def test_c8_the_cap_is_per_user(panel, session_factory):
    other = seed_staff(session_factory)
    for i in range(5):
        assert upload(panel.client, f"f{i}.csv", csv_bytes(), "text/csv").status_code == 201

    act_as(other)
    assert upload(panel.client, "mine.csv", csv_bytes(), "text/csv").status_code == 201


def test_c9_the_21st_upload_in_a_minute_is_rate_limited(panel):
    for i in range(20):
        resp = upload(panel.client, f"f{i}.csv", csv_bytes(), "text/csv")
        assert resp.status_code == 201, f"upload {i}: {resp.text}"
        assert panel.client.delete(f"{UPLOAD_URL}/{resp.json()['id']}").status_code == 204  # keep under the 5-draft cap

    resp = upload(panel.client, "one-too-many.csv", csv_bytes(), "text/csv")

    assert resp.status_code == 429, resp.text


# --------------------------------------------------------------------------- #
# C10: permission, and delete
# --------------------------------------------------------------------------- #


def test_c10_upload_without_the_chat_slug_is_403(panel):
    panel.grants.discard(USE)

    resp = upload(panel.client, "a.csv", csv_bytes(), "text/csv")

    assert resp.status_code == 403
    assert panel.store.objects == {}


def test_c10_delete_without_the_chat_slug_is_403(panel):
    made = upload(panel.client, "a.csv", csv_bytes(), "text/csv").json()
    panel.grants.discard(USE)

    assert panel.client.delete(f"{UPLOAD_URL}/{made['id']}").status_code == 403


def test_c10_c11_deleting_own_draft_removes_storage_link_and_row(panel):
    made = upload(panel.client, "p.png", png_bytes(), "image/png").json()
    att, _ = rows_of(panel, made["id"])
    key = att.file_path
    assert len(panel.store.objects) >= 2, "the original and at least one rendition should be stored"

    resp = panel.client.delete(f"{UPLOAD_URL}/{made['id']}")

    assert resp.status_code == 204
    assert resp.content == b""
    att_after, links_after = rows_of(panel, made["id"])
    assert att_after is None and links_after == []
    assert key in panel.store.deleted
    assert panel.store.objects == {}, "an object or a rendition was left behind"


def test_c10_deleting_a_draft_frees_a_slot(panel):
    ids = [upload(panel.client, f"f{i}.csv", csv_bytes(), "text/csv").json()["id"] for i in range(5)]
    assert panel.client.delete(f"{UPLOAD_URL}/{ids[0]}").status_code == 204

    assert upload(panel.client, "again.csv", csv_bytes(), "text/csv").status_code == 201


def test_c10_another_users_file_is_404_and_untouched(panel, session_factory):
    made = upload(panel.client, "mine.csv", csv_bytes(), "text/csv").json()
    other = seed_staff(session_factory)
    act_as(other)

    resp = panel.client.delete(f"{UPLOAD_URL}/{made['id']}")

    assert resp.status_code == 404
    att, links = rows_of(panel, made["id"])
    assert att is not None and len(links) == 1
    assert panel.store.deleted == []


def test_c10_an_already_sent_file_is_404_and_untouched(panel):
    made = upload(panel.client, "sent.csv", csv_bytes(), "text/csv").json()
    db = panel.factory()
    link = db.query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id == made["id"]).one()
    link.entity_type = "ai_assistant_conversation"
    link.entity_id = panel.staff.conv_id
    db.commit()

    resp = panel.client.delete(f"{UPLOAD_URL}/{made['id']}")

    assert resp.status_code == 404
    att, _ = rows_of(panel, made["id"])
    assert att is not None
    assert panel.store.deleted == []


@pytest.mark.parametrize("bad_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_c10_an_unknown_or_malformed_id_is_the_same_404(panel, bad_id):
    assert panel.client.delete(f"{UPLOAD_URL}/{bad_id}").status_code == 404
