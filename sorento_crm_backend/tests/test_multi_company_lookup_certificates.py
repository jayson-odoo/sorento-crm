"""AC-B1/AC-B2/AC-B4 for `crm_certificates_list`
(CertificateQueryService.list_certificates).

`data` rows come back already Pydantic-serialized (`self.core.serialize_many`),
so the missing `company_name` reads as an absent attribute rather than a raw
dict key - `getattr(row, "company_name", None)` distinguishes "field declared
but null" from "field not declared at all" the same way as everywhere else in
this suite. Postgres only.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.services.certificate_query_service import CertificateQueryService
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import (
    MOCHA_ID,
    attachment_type,
    certificate,
    certificate_product,
    product,
    seed_mocha,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        yield session


def test_certificates_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    type_id = attachment_type(db).id
    cert_sorento = certificate(db, company_id=DEFAULT_COMPANY_ID, attachment_type_id=type_id)
    cert_mocha = certificate(db, company_id=MOCHA_ID, attachment_type_id=type_id)
    certificate_product(db, certificate_id=cert_sorento.id, product_id=p_sorento.id)
    certificate_product(db, certificate_id=cert_mocha.id, product_id=p_mocha.id)
    db.commit()

    result = CertificateQueryService(db).list_certificates(
        product_ids=[p_sorento.id, p_mocha.id]
    )

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_certificates_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    # No certificate covers either product.
    db.commit()

    result = CertificateQueryService(db).list_certificates(
        product_ids=[p_sorento.id, p_mocha.id]
    )

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_certificates_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    type_id = attachment_type(db).id
    cert_sorento = certificate(db, company_id=DEFAULT_COMPANY_ID, attachment_type_id=type_id)
    certificate_product(db, certificate_id=cert_sorento.id, product_id=p_sorento.id)
    db.commit()

    result = CertificateQueryService(db).list_certificates(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None
