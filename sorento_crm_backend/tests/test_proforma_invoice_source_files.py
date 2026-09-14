"""S8 / AC-8.3, AC-8.4 - the proforma invoice's Source files block carries real files.

TEST-FIRST (`PLAN-scm-ui-feedback-14sep.md`, J6). Today `serialize`'s `source_files[]`
emits `{id, name, type, uploaded_at, download_url}` and the detail page ignores it entirely,
printing two hand-rolled rows off `source_ref` (a bare filename string) instead. The card
the packing list already uses needs three more facts per entry - the attachment's own id,
its size and its mime type - and those are what is asserted here.

`attachment_id` is the one that matters most: the id on the link row is the LINK's, and a
Preview/Download button handed that id asks the attachments API about a record that does not
exist. The FE cannot tell the two apart, which is exactly why this is pinned in a test.

AC-8.4 is expressed through `supplier_document_service._link_source_file` rather than
through `apply` end-to-end on purpose: `packing_list_service.file_supplier_document` writes
the bytes to S3/R2, and this suite must not make a live storage call (the same reason
`test_supplier_document_service.py` deliberately seeds no attachment type). What the test
owns is the half that is ours - that a packing-list workbook filed against an invoice is
reachable from that invoice's `source_files`, under the Packing List type's own name.

Postgres via `pg_session`, every FK target seeded here. The attachment type is get-or-create:
CI's database has none at all, and a local prod copy may already hold it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.resources import Attachment, AttachmentType
from app.services.scm import proforma_invoice_service as svc
from app.services.scm import supplier_document_service as doc_svc
from app.services.scm.packing_list_service import (
    _PACKING_LIST_TYPE_CODE,
    _PACKING_LIST_TYPE_NAME,
)

from ._pg_fixture import pg_session
from .scm.test_proforma_invoice_import import World, _invoices, _lines, workbook

MARKER = "ZZPISF"


def _u() -> str:
    return str(uuid.uuid4())


def _invoice(db, world: World):
    """One invoice with one line, minted the way an upload mints it."""
    code = world.code("A")
    svc.apply(
        db,
        workbook([["产品型号", "数量", "PRICE"], [code, 5, 12.5]]),
        supplier_id=str(world.supplier.id),
        currency="USD",
        source_ref=f"{MARKER}-invoice.xlsx",
    )
    db.flush()
    return _invoices(db, world)[0]


def _attachment_type(db, *, code: str, type_name: str) -> AttachmentType:
    row = (
        db.query(AttachmentType).filter(AttachmentType.type_name == type_name).first()
    )
    if row is None:
        row = AttachmentType(
            id=_u(),
            code=code,
            type_name=type_name,
            allowed_extensions="xls,xlsx",
            max_file_size_mb=10,
        )
        db.add(row)
        db.flush()
    return row


def _attachment(
    db,
    *,
    filename: str,
    type_name: str,
    type_code: str,
    size_bytes: int,
    mime_type: str,
) -> Attachment:
    attachment_type = _attachment_type(db, code=type_code, type_name=type_name)
    row = Attachment(
        id=_u(),
        attachment_type_id=attachment_type.id,
        original_filename=filename,
        stored_filename=f"{_u()}-{filename}",
        file_path=f"s3://zz-test/{filename}",
        file_size_bytes=size_bytes,
        mime_type=mime_type,
        uploaded_at=datetime(2026, 8, 1, 2, 0, 0),
    )
    db.add(row)
    db.flush()
    return row


def _source_files(db, invoice) -> list[dict]:
    return svc.serialize(db, invoice)["source_files"]


# --------------------------------------------------------------------------------- #
# AC-8.3 - every entry carries what a file card needs
# --------------------------------------------------------------------------------- #

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_a_source_file_entry_names_the_attachment_its_size_and_its_type():
    with pg_session() as db:
        world = World(db)
        invoice = _invoice(db, world)
        attachment = _attachment(
            db,
            filename=f"{MARKER}-invoice.xlsx",
            type_name="Proforma Invoice",
            type_code="proforma_invoice",
            size_bytes=18342,
            mime_type=_XLSX_MIME,
        )
        doc_svc._link_source_file(db, [str(invoice.id)], str(attachment.id))
        db.flush()

        files = _source_files(db, invoice)

        assert len(files) == 1, files
        entry = files[0]
        assert entry["name"] == f"{MARKER}-invoice.xlsx"
        assert entry["type"] == "Proforma Invoice"
        assert entry["uploaded_at"] is not None
        # The three the card cannot be drawn without.
        assert entry["attachment_id"] == str(attachment.id)
        assert entry["file_size_bytes"] == 18342
        assert entry["mime_type"] == _XLSX_MIME


def test_the_attachment_id_is_the_attachments_own_not_the_links():
    """The two are different uuids, and a Preview button handed the link's asks the
    attachments API about a record that does not exist - a 404 the FE would report as a
    broken file."""
    with pg_session() as db:
        world = World(db)
        invoice = _invoice(db, world)
        attachment = _attachment(
            db,
            filename=f"{MARKER}-invoice.xlsx",
            type_name="Proforma Invoice",
            type_code="proforma_invoice",
            size_bytes=1,
            mime_type=_XLSX_MIME,
        )
        doc_svc._link_source_file(db, [str(invoice.id)], str(attachment.id))
        db.flush()

        entry = _source_files(db, invoice)[0]

        assert entry["attachment_id"] == str(attachment.id)
        assert entry["attachment_id"] != entry["id"]


def test_a_file_with_no_stated_size_or_type_says_so_rather_than_dropping_the_entry():
    """An older row, filed before the columns were populated. The card falls back to the
    name alone; the ENTRY still has to be there, with the keys present and null."""
    with pg_session() as db:
        world = World(db)
        invoice = _invoice(db, world)
        attachment = _attachment(
            db,
            filename=f"{MARKER}-legacy.xls",
            type_name="Proforma Invoice",
            type_code="proforma_invoice",
            size_bytes=0,
            mime_type="",
        )
        attachment.file_size_bytes = None
        attachment.mime_type = None
        db.flush()
        doc_svc._link_source_file(db, [str(invoice.id)], str(attachment.id))
        db.flush()

        entry = _source_files(db, invoice)[0]

        assert entry["attachment_id"] == str(attachment.id)
        assert entry["file_size_bytes"] is None
        assert entry["mime_type"] is None


# --------------------------------------------------------------------------------- #
# AC-8.4 - the packing workbook is one of the invoice's source files
# --------------------------------------------------------------------------------- #


def test_a_packing_workbook_filed_against_an_invoice_is_one_of_its_source_files():
    """Two files on one invoice - the one that priced it and the one that packed it - which
    is what the buyer opens the General tab to find."""
    with pg_session() as db:
        world = World(db)
        invoice = _invoice(db, world)
        pi_file = _attachment(
            db,
            filename=f"{MARKER}-invoice.xlsx",
            type_name="Proforma Invoice",
            type_code="proforma_invoice",
            size_bytes=18342,
            mime_type=_XLSX_MIME,
        )
        packing_file = _attachment(
            db,
            filename=f"{MARKER}-packing.xlsx",
            type_name=_PACKING_LIST_TYPE_NAME,
            type_code=_PACKING_LIST_TYPE_CODE,
            size_bytes=9021,
            mime_type=_XLSX_MIME,
        )
        doc_svc._link_source_file(db, [str(invoice.id)], str(pi_file.id))
        doc_svc._link_source_file(db, [str(invoice.id)], str(packing_file.id))
        db.flush()

        files = _source_files(db, invoice)

        by_name = {entry["name"]: entry for entry in files}
        assert set(by_name) == {f"{MARKER}-invoice.xlsx", f"{MARKER}-packing.xlsx"}
        packing = by_name[f"{MARKER}-packing.xlsx"]
        assert packing["type"] == _PACKING_LIST_TYPE_NAME
        assert packing["attachment_id"] == str(packing_file.id)
        assert packing["file_size_bytes"] == 9021
        assert packing["mime_type"] == _XLSX_MIME
