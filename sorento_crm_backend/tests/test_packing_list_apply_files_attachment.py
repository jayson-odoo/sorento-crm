"""`packing_list_service.file_supplier_document()` files an uploaded workbook in Drive.

`PLAN-scm-purchasing-consolidation-6sep.md` section 2 / UAC group B originally pinned this
against `packing_list_service.apply()` (R3, AC-B2) - retired (S3 follow-up, captain ruling
9 Sep, `scm-supplier-documents-pi-first`): a packing list is born by convert or by hand
only now (AC-C1/C2), never by this upload path, and `apply`/`file_in_drive` no longer
exist. What survives is `file_supplier_document` itself, the filing primitive
`supplier_document_service.apply` now uses directly for both proforma invoice and
packing-list files - proven here against the Proforma Invoice type (browser-test round,
finding 3), since that is the one caller left that exercises it standalone.

Postgres only, `tests/_pg_fixture.py::blank_session`, own seeded chain (`ZZAT` marker).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.resources import Attachment, AttachmentType
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.scm import packing_list_service
from tests._pg_fixture import blank_session

MARKER = "ZZAT"


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _stub_backend(monkeypatch, *, provider: str = "r2") -> None:
    """Storage upload is a real network PUT everywhere else in this codebase - stubbed
    here to a fixed key, same shape `S3Service.upload_file` / `R2Service.upload_file`
    return (`(key, url)`), and the same two CDN-url methods `cdn_base_url` dispatches
    to depending on the provider.

    `provider` defaults to `r2`, deliberately NOT the schema/DB default (`s3`) for
    `attachments.storage_provider` - a test that stubbed the configured provider AS
    `s3` could not have caught review B1 (the row landing on `s3` regardless of what
    the bytes were actually uploaded to).
    """
    monkeypatch.setattr("app.services.storage_router.default_provider", lambda: provider)
    monkeypatch.setattr(
        "app.services.storage_router.get_backend",
        lambda provider: type(
            "StubBackend",
            (),
            {
                "upload_file": staticmethod(lambda **kw: ("stub/key.xlsx", "")),
                "get_cloudfront_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
                "get_cdn_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
            },
        )(),
    )


def _proforma_invoice_type(db, *, default_directory_id: str | None = None) -> AttachmentType:
    t = AttachmentType(
        id=str(uuid.uuid4()),
        type_name="Proforma Invoice",
        code="proforma_invoice",
        allowed_extensions="xlsx,xls,pdf",
        max_file_size_mb=10,
        default_directory_id=default_directory_id,
    )
    db.add(t)
    db.flush()
    return t


def test_file_supplier_document_files_a_proforma_invoice(db, monkeypatch):
    """Before migration 485 (browser-test round) no attachment type resolved
    `code = 'proforma_invoice'` at all, so a proforma invoice uploaded through the
    supplier-documents dialog was never filed in Drive - it landed a PI row, but the
    workbook itself vanished. This proves `file_supplier_document` files a proforma just
    as well as a packing list, once the type this migration seeds exists."""
    att_type = _proforma_invoice_type(db)
    db.commit()
    _stub_backend(monkeypatch)

    attachment_id = packing_list_service.file_supplier_document(
        db,
        data=b"pretend proforma invoice bytes",
        filename="2026JXL0726.xls",
        content_type="application/vnd.ms-excel",
        actor_id=None,
        type_code="proforma_invoice",
        type_name="Proforma Invoice",
    )
    db.commit()

    assert attachment_id is not None
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).one()
    assert str(attachment.attachment_type_id) == str(att_type.id)
    assert attachment.original_filename == "2026JXL0726.xls"
