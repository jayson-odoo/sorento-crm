"""Seed helpers for the shared-brand-attachments UAC (groups B, C, D, H).

`documentation/plans/multi-company/shared-brand-attachments-acceptance-criteria.md`
+ `PLAN-shared-brand-attachments.md`. Postgres only, via `tests/_pg_fixture.py`'s
`blank_session` - own chain per test, ``ZZT-`` marker throughout.

Mocha here is the REAL id the plan and the migrations use
(`5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f`), not the `...002` placeholder some
unrelated suites (`tests/_mc_lookup_seed.py`, a different UAC) use - the two
are not interchangeable, and mixing them would seed a company nothing else in
this file's tests expects.

Not a test module itself - the leading underscore keeps pytest from
collecting it, matching `_pg_fixture.py`'s own convention.
"""
from __future__ import annotations

import uuid

from app.models.company import Company, UserCompany
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code

SORENTO_ID = DEFAULT_COMPANY_ID
MOCHA_ID = "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f"


def seed_mocha(db) -> Company:
    """Register Mocha. Sorento is already seeded into every `blank_session`
    schema by `conftest.py`."""
    row = Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20], is_active=True)
    db.add(row)
    db.flush()
    return row


def user(db, *, email: str | None = None, name: str = "ZZT Actor") -> User:
    row = User(
        id=str(uuid.uuid4()),
        email=email or f"zzt-{uuid.uuid4().hex[:8]}@example.test",
        name=name,
        status="ACTIVE",
    )
    db.add(row)
    db.flush()
    return row


def grant(db, *, user_id: str, company_id: str) -> UserCompany:
    row = UserCompany(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id)
    db.add(row)
    db.flush()
    return row


def category(db, *, company_id: str) -> ProductCategory:
    row = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("CAT")[:50],
        category_name="ZZT Category",
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def uom(db, *, company_id: str) -> UnitOfMeasure:
    row = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=unique_code("UOM")[:50],
        uom_name="Each",
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def product(
    db, *, company_id: str, code: str, category_id: str, uom_id: str
) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=0,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def twin_products(db, *, code: str, sorento_cat, sorento_uom, mocha_cat, mocha_uom):
    """A product-code twin: one row in Sorento, one in Mocha, same `product_code`."""
    s = product(db, company_id=SORENTO_ID, code=code, category_id=sorento_cat, uom_id=sorento_uom)
    m = product(db, company_id=MOCHA_ID, code=code, category_id=mocha_cat, uom_id=mocha_uom)
    return s, m


def att_type(
    db, *, is_shared: bool = False, name: str | None = None, is_certificate: bool = False
) -> AttachmentType:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=name or unique_code("Type")[:50],
        allowed_extensions="pdf",
        is_shared=is_shared,
        is_certificate=is_certificate,
    )
    db.add(row)
    db.flush()
    return row


def folder(
    db,
    *,
    company_id: str | None,
    name: str | None = None,
    parent_id: str | None = None,
    is_deleted: bool = False,
) -> AttachmentDirectory:
    row = AttachmentDirectory(
        id=str(uuid.uuid4()),
        name=name or unique_code("Folder")[:100],
        parent_id=parent_id,
        company_id=company_id,
        is_deleted=is_deleted,
    )
    db.add(row)
    db.flush()
    return row


def attachment(
    db,
    *,
    company_id: str | None,
    type_id: str,
    directory_id: str | None = None,
    filename: str | None = None,
    target_entity_type: str | None = None,
    target_field_keys: list[str] | None = None,
    is_deleted: bool = False,
) -> Attachment:
    fn = filename or f"{unique_code('file')}.pdf"
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=fn,
        stored_filename=fn,
        file_path=f"https://cdn.test/{fn}",
        attachment_type_id=type_id,
        directory_id=directory_id,
        company_id=company_id,
        is_deleted=is_deleted,
        target_entity_type=target_entity_type,
        target_field_keys=target_field_keys,
    )
    db.add(row)
    db.flush()
    return row


def product_attachment(
    db,
    *,
    company_id: str,
    product_id: str,
    attachment_id: str,
    is_primary: bool = False,
    sort_order: int | None = None,
    access_levels: list[str] | None = None,
    linked_via_set_id: str | None = None,
) -> ProductAttachment:
    row = ProductAttachment(
        id=str(uuid.uuid4()),
        product_id=product_id,
        attachment_id=attachment_id,
        company_id=company_id,
        is_primary=is_primary,
        sort_order=sort_order,
        access_levels=access_levels or ["dealer"],
        linked_via_set_id=linked_via_set_id,
    )
    db.add(row)
    db.flush()
    return row
