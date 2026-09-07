"""`packing_list_service.apply()` files the uploaded workbook in Drive (R3, AC-B2).

`PLAN-scm-purchasing-consolidation-6sep.md` section 2 / UAC group B. The "Upload packing
list" CTA reads the file AND keeps a copy: on a real apply (never `validate_only`), the
bytes land as an `attachments` row of type Packing List, in that type's default folder,
bound onto every shipment the upload produced via `inbound_shipments.attachment_id`.

Three rules pinned here:
  * no `integration_log` row for this attachment - the reader already produced the
    shipment, so firing the n8n intake webhook would create a second one through the
    external route (R3);
  * a missing Packing List attachment type never fails the apply - the shipment still
    gets created, just without a filed copy (R4 is admin-set, not guaranteed to exist);
  * `file_in_drive` defaults to False - `apply()` has other callers (batch reprocessing,
    every OTHER test of this function) that must not suddenly start writing to storage
    just because they call it. Discovered the hard way: the shared dev DB already carries
    a real "Packing List" attachment type (admin data), and a first cut that filed
    unconditionally made every existing `pg_session` packing-list test perform a live
    upload against the configured storage bucket. The route is the one caller that opts
    in.

Postgres only, `tests/_pg_fixture.py::blank_session`, own seeded chain (`ZZT` marker).
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest

from app.models.base import set_company_scope
from app.models.import_alias import ImportFieldAlias
from app.models.integration import IntegrationLog
from app.models.procurement import InboundShipment, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.scm import packing_list_service
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZAT"

_ALIASES = [
    ("item_code", "产品型号"),
    ("product_name", "品名"),
    ("qty", "数量"),
    ("cartons", "箱数"),
    ("cbm_per_unit", "体积(cbm)"),
    ("cbm_total", "总体积(cbm)"),
    ("container_no", "货柜号"),
    ("remark", "备注"),
]


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _seed_aliases(db) -> None:
    for field, alias in _ALIASES:
        db.add(
            ImportFieldAlias(
                id=str(uuid.uuid4()), doc_type="packing_list", field=field, alias=alias, locale="zh"
            )
        )
    db.flush()


def _uom(db) -> str:
    uid = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uid, uom_code=unique_code("U")[:20], uom_name="pcs"))
    db.flush()
    return uid


def _category(db) -> str:
    cid = str(uuid.uuid4())
    db.add(
        ProductCategory(id=cid, category_code=unique_code("CAT"), category_name=f"{MARKER} category")
    )
    db.flush()
    return cid


def _product(db, code: str, *, category_id: str, uom_id: str) -> Product:
    p = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code(code),
        product_name=code,
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=0,
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _supplier(db) -> Supplier:
    s = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("SUP"),
        supplier_name=f"{MARKER} supplier",
        is_active=True,
    )
    db.add(s)
    db.flush()
    return s


def _directory(db) -> AttachmentDirectory:
    d = AttachmentDirectory(id=str(uuid.uuid4()), name=unique_code("Folder"))
    db.add(d)
    db.flush()
    return d


def _packing_list_type(db, *, default_directory_id: str | None) -> AttachmentType:
    t = AttachmentType(
        id=str(uuid.uuid4()),
        type_name="Packing List",
        code="packing_list",
        allowed_extensions="xlsx,xls",
        default_directory_id=default_directory_id,
    )
    db.add(t)
    db.flush()
    return t


def _workbook(container: str, rows: list[tuple[str, float, float, float, str]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([f"货柜号：{container}"])
    ws.append(["产品型号", "品名", "数量", "箱数", "体积(cbm)", "备注"])
    for code, qty, cartons, cbm, remark in rows:
        ws.append([code, "座厕", qty, cartons, cbm, remark])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# A real Packing List type exists, with a default folder
# --------------------------------------------------------------------------- #


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


def test_apply_files_the_upload_in_the_types_default_folder(db, monkeypatch):
    """Shipment + attachment, bound, no integration_log row."""
    _seed_aliases(db)
    category = _category(db)
    uom = _uom(db)
    product = _product(db, "TAP", category_id=category, uom_id=uom)
    supplier = _supplier(db)
    folder = _directory(db)
    att_type = _packing_list_type(db, default_directory_id=folder.id)
    db.commit()

    _stub_backend(monkeypatch)

    container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
    out = packing_list_service.apply(
        db,
        _workbook(container, [(product.product_code, 10, 2, 0.21, "note")]),
        supplier_id=str(supplier.id),
        source_ref="jiexia-packing-list.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_in_drive=True,
    )
    db.commit()

    assert out["shipments_created"] == 1

    shipment = (
        db.query(InboundShipment)
        .filter(InboundShipment.shipping_container_number == container)
        .one()
    )
    assert shipment.attachment_id is not None, "the shipment must be bound to the filed copy"

    attachment = db.query(Attachment).filter(Attachment.id == shipment.attachment_id).one()
    assert str(attachment.attachment_type_id) == str(att_type.id)
    assert str(attachment.directory_id) == str(folder.id)
    assert attachment.company_id == DEFAULT_COMPANY_ID
    # B1: the row must say where the bytes ACTUALLY went, not the schema default -
    # `_stub_backend` configures the provider as `r2`, never `s3` (the column's
    # `server_default`), so this fails if `storage_provider` is left unset again.
    assert attachment.storage_provider == "r2"

    # R3: never the n8n intake webhook for this one - the reader already produced the
    # shipment, so firing it would create a second one through the external route.
    logs = db.query(IntegrationLog).filter(IntegrationLog.business_id == str(attachment.id)).all()
    assert logs == []


def test_apply_twice_files_the_upload_only_once(db, monkeypatch):
    """S1 (review round 1): a re-upload of the same file resolves to the same
    shipment (AC-G3) and must not mint a second Drive copy of a file already filed
    on the first apply.
    """
    _seed_aliases(db)
    category = _category(db)
    uom = _uom(db)
    product = _product(db, "BASIN", category_id=category, uom_id=uom)
    supplier = _supplier(db)
    folder = _directory(db)
    _packing_list_type(db, default_directory_id=folder.id)
    db.commit()

    _stub_backend(monkeypatch)
    upload_calls: list[str] = []
    monkeypatch.setattr(
        "app.services.storage_router.get_backend",
        lambda provider: type(
            "CountingStubBackend",
            (),
            {
                "upload_file": staticmethod(
                    lambda **kw: (upload_calls.append("uploaded") or ("stub/key.xlsx", ""))
                ),
                "get_cloudfront_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
                "get_cdn_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
            },
        )(),
    )

    container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
    data = _workbook(container, [(product.product_code, 4, 1, 0.05, "")])

    packing_list_service.apply(
        db, data, supplier_id=str(supplier.id), source_ref="repeat.xlsx", file_in_drive=True,
    )
    db.commit()
    packing_list_service.apply(
        db, data, supplier_id=str(supplier.id), source_ref="repeat.xlsx", file_in_drive=True,
    )
    db.commit()

    assert len(upload_calls) == 1, "the second apply must not upload again"

    shipment = (
        db.query(InboundShipment)
        .filter(InboundShipment.shipping_container_number == container)
        .one()
    )
    assert db.query(Attachment).filter(Attachment.id == shipment.attachment_id).count() == 1


def test_apply_still_applies_the_shipment_when_filing_fails(db, monkeypatch):
    """B2 (review round 1): a failed filing attempt must not leave the session
    in `PendingRollbackError` for the rest of the apply - the shipment still
    gets created, exactly as when the type is simply missing.
    """
    _seed_aliases(db)
    category = _category(db)
    uom = _uom(db)
    product = _product(db, "BIDET", category_id=category, uom_id=uom)
    supplier = _supplier(db)
    folder = _directory(db)
    _packing_list_type(db, default_directory_id=folder.id)
    db.commit()

    _stub_backend(monkeypatch)

    def _boom(self, *args, **kwargs):
        raise RuntimeError("forced create_attachment failure")

    monkeypatch.setattr(
        "app.services.resources_service.AttachmentService.create_attachment", _boom
    )

    container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
    out = packing_list_service.apply(
        db,
        _workbook(container, [(product.product_code, 6, 1, 0.1, "")]),
        supplier_id=str(supplier.id),
        source_ref="boom.xlsx",
        file_in_drive=True,
    )
    db.commit()

    assert out["shipments_created"] == 1
    shipment = (
        db.query(InboundShipment)
        .filter(InboundShipment.shipping_container_number == container)
        .one()
    )
    assert shipment.attachment_id is None, "filing failed - nothing to bind"


# --------------------------------------------------------------------------- #
# `file_supplier_document` files a proforma invoice too, once migration 485 seeds
# the type (browser-test round, finding 3)
# --------------------------------------------------------------------------- #


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
    workbook itself vanished. This proves the SAME `file_supplier_document`
    `packing_list_service.apply()` already uses files a proforma just as well, once
    the type this migration seeds exists."""
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


# --------------------------------------------------------------------------- #
# No Packing List type at all - apply must still succeed
# --------------------------------------------------------------------------- #


def test_apply_still_succeeds_with_no_packing_list_type_seeded(db):
    _seed_aliases(db)
    category = _category(db)
    uom = _uom(db)
    product = _product(db, "SINK", category_id=category, uom_id=uom)
    supplier = _supplier(db)
    db.commit()

    container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
    out = packing_list_service.apply(
        db,
        _workbook(container, [(product.product_code, 5, 1, 0.1, "")]),
        supplier_id=str(supplier.id),
        source_ref="no-type.xlsx",
        file_in_drive=True,
    )
    db.commit()

    assert out["shipments_created"] == 1
    shipment = (
        db.query(InboundShipment)
        .filter(InboundShipment.shipping_container_number == container)
        .one()
    )
    assert shipment.attachment_id is None


# --------------------------------------------------------------------------- #
# `file_in_drive` is opt-in - every OTHER caller of `apply()` is unaffected
# --------------------------------------------------------------------------- #


def test_file_in_drive_defaults_to_false(db, monkeypatch):
    """A caller that does not ask for it gets exactly today's behaviour.

    Pinned because a real Packing List type already lives in the shared dev DB (admin
    data) - unconditional filing meant every OTHER test of `apply()` against that DB
    started performing a live storage upload the moment this feature landed.
    """
    _seed_aliases(db)
    category = _category(db)
    uom = _uom(db)
    product = _product(db, "BOWL", category_id=category, uom_id=uom)
    supplier = _supplier(db)
    folder = _directory(db)
    _packing_list_type(db, default_directory_id=folder.id)
    db.commit()

    called = []
    monkeypatch.setattr(
        "app.services.storage_router.get_backend",
        lambda provider: called.append("uploaded") or (_ for _ in ()).throw(
            AssertionError("storage must not be touched when file_in_drive is not requested")
        ),
    )

    container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
    out = packing_list_service.apply(
        db,
        _workbook(container, [(product.product_code, 3, 1, 0.05, "")]),
        supplier_id=str(supplier.id),
        source_ref="default-off.xlsx",
    )
    db.commit()

    assert not called
    assert out["shipments_created"] == 1
    shipment = (
        db.query(InboundShipment)
        .filter(InboundShipment.shipping_container_number == container)
        .one()
    )
    assert shipment.attachment_id is None
