"""AC-G1..G4 (PLAN-shared-brand-attachments.md S5, UAC group G):
`AttachmentService.get_linked_entities` on a SHARED attachment widens its
product/certificate queries to the CALLER's own granted companies, and tags
each row with `company_id` / `company_name` / `in_scope`. A single-company
attachment is untouched (AC-G3). The three new fields survive the
`LinkedEntityRef` schema (AC-G4).

Postgres only, own seeded `ZZT-` chain. `blank_session`'s `create_all` already
seeds the Sorento company row (see `_pg_fixture.py`).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.certificate import Certificate, CertificateRevision
from app.models.company import Company, UserCompany
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.models.user import User
from app.schemas.resources import LinkedEntityRef
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.resources_service import AttachmentService

from tests._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _user_with_grants(db, company_ids: list[str]) -> str:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('user')}@test.local", name="ZZT Grantee")
    db.add(user)
    db.flush()
    for cid in company_ids:
        db.add(UserCompany(id=str(uuid.uuid4()), user_id=user.id, company_id=cid))
    db.flush()
    return user.id


def _type(db) -> str:
    row = AttachmentType(
        id=str(uuid.uuid4()), type_name=unique_code("ZZT-Photo")[:50], allowed_extensions="jpg",
    )
    db.add(row)
    db.flush()
    return row.id


def _twin_products(db, code: str) -> tuple[Product, Product]:
    """One product code, one row per company - the twin shape."""
    cat_s = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=DEFAULT_COMPANY_ID)
    cat_m = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=MOCHA_ID)
    uom_s = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    uom_m = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=MOCHA_ID)
    db.add_all([cat_s, cat_m, uom_s, uom_m])
    db.flush()
    p_s = Product(id=str(uuid.uuid4()), product_code=code, product_name=code, category_id=cat_s.id, base_uom_id=uom_s.id, list_price=1, company_id=DEFAULT_COMPANY_ID)
    p_m = Product(id=str(uuid.uuid4()), product_code=code, product_name=code, category_id=cat_m.id, base_uom_id=uom_m.id, list_price=1, company_id=MOCHA_ID)
    db.add_all([p_s, p_m])
    db.flush()
    return p_s, p_m


def _attachment(db, *, company_id, type_id: str) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{unique_code('ZZT-file')}.jpg",
        stored_filename=f"{unique_code('ZZT-file')}.jpg",
        file_path="https://cdn.test/zzt.jpg",
        attachment_type_id=type_id,
        is_deleted=False,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _link(db, *, product_id: str, attachment_id: str, company_id) -> ProductAttachment:
    row = ProductAttachment(
        id=str(uuid.uuid4()), product_id=product_id, attachment_id=attachment_id, company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


# --- AC-G1 / AC-G2: widening follows the CALLER's own grants -----------------


def test_g1_shared_file_both_twins_granted_both_companies(db):
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=_type(db))
    _link(db, product_id=p_s.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID)
    _link(db, product_id=p_m.id, attachment_id=att.id, company_id=MOCHA_ID)
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    linked = AttachmentService(db).get_linked_entities(att.id, actor_id=user_id)

    rows = {r["id"]: r for r in linked["linked_products"]}
    assert set(rows) == {p_s.id, p_m.id}
    assert rows[p_s.id]["company_id"] == DEFAULT_COMPANY_ID
    assert rows[p_s.id]["in_scope"] is True
    assert rows[p_m.id]["company_id"] == MOCHA_ID
    assert rows[p_m.id]["in_scope"] is False
    assert rows[p_m.id]["company_name"] == "Mocha"


def test_g2_shared_file_only_sorento_grant_sees_only_sorento(db):
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=_type(db))
    _link(db, product_id=p_s.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID)
    _link(db, product_id=p_m.id, attachment_id=att.id, company_id=MOCHA_ID)
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    linked = AttachmentService(db).get_linked_entities(att.id, actor_id=user_id)

    rows = {r["id"] for r in linked["linked_products"]}
    assert rows == {p_s.id}


# --- AC-G3: single-company attachment is untouched ----------------------------


def test_g3_single_company_attachment_returns_todays_shape(db):
    p_s, _p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=DEFAULT_COMPANY_ID, type_id=_type(db))
    _link(db, product_id=p_s.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID)
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    linked = AttachmentService(db).get_linked_entities(att.id, actor_id=user_id)

    assert len(linked["linked_products"]) == 1
    row = linked["linked_products"][0]
    assert row["id"] == p_s.id
    assert row["in_scope"] is True


def test_g3_no_actor_id_never_widens(db):
    """Callers that don't pass actor_id (upload-activity's summary builder)
    keep today's single-scope result even for a shared attachment."""
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=_type(db))
    _link(db, product_id=p_s.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID)
    _link(db, product_id=p_m.id, attachment_id=att.id, company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    linked = AttachmentService(db).get_linked_entities(att.id)

    rows = {r["id"] for r in linked["linked_products"]}
    assert rows == {p_s.id}


# --- AC-G4: the fields survive response_model ---------------------------------


def test_g4_linked_entity_ref_declares_the_three_fields():
    ref = LinkedEntityRef.model_validate(
        {
            "id": "x",
            "name": "y",
            "company_id": MOCHA_ID,
            "company_name": "Mocha",
            "in_scope": False,
        }
    )
    dumped = ref.model_dump()
    assert dumped["company_id"] == MOCHA_ID
    assert dumped["company_name"] == "Mocha"
    assert dumped["in_scope"] is False


def test_g4_defaults_when_absent(db):
    """A ref built the OLD way (no company keys at all) still validates, with
    in_scope defaulting True - so a single-company payload round-trips."""
    ref = LinkedEntityRef.model_validate({"id": "x", "name": "y"})
    dumped = ref.model_dump()
    assert dumped["company_id"] is None
    assert dumped["company_name"] is None
    assert dumped["in_scope"] is True


# --- certificates follow the same widening rule --------------------------------


def test_g1_linked_certificates_carry_the_same_fields(db):
    type_id = _type(db)
    att = _attachment(db, company_id=None, type_id=type_id)
    cert = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=unique_code("SCHEME")[:60], certificate_number=unique_code("CERT")[:120],
        company_id=None,
    )
    db.add(cert)
    db.flush()
    revision = CertificateRevision(
        id=str(uuid.uuid4()), certificate_id=cert.id, attachment_id=att.id,
        revision_no=1, is_current=True,
    )
    db.add(revision)
    db.flush()
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    linked = AttachmentService(db).get_linked_entities(att.id, actor_id=user_id)

    assert len(linked["linked_certificates"]) == 1
    row = linked["linked_certificates"][0]
    assert row["company_id"] is None
    assert row["in_scope"] is True
