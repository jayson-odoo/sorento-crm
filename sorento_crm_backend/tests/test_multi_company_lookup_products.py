"""AC-B1/AC-B2/AC-B4 for `crm_master_products_list` (ProductService.list_products)
and `crm_master_product_attachments_list` (ProductService.list_product_attachments).

Modelled on tests/test_attachment_company_stamp_in_list.py. Postgres only.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.product_service import ProductAttachmentService, ProductService

from tests._mc_lookup_seed import (
    MOCHA_ID,
    attachment,
    attachment_type,
    product,
    product_attachment,
    seed_mocha,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        yield session


# =============================================================================
# master_products_list
# =============================================================================


def test_products_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    result = ProductService(db).list_products(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_products_list_ac_b2_none_in_either_company(db):
    """product_ids that resolve to nothing (both belong to real companies but
    neither product exists) - the union still comes from the rows only, so an
    unmatched product_ids filter naturally empties out before any company can
    be named. Exercised instead against an entities filter that spans both
    companies' products but a further filter drops every row - product_ids
    themselves are the company source here, so this is the "no rows, but the
    union was already known" case at the product-list level."""
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    # A status filter that matches neither seeded product removes every row
    # while product_ids alone still spans both companies.
    result = ProductService(db).list_products(
        product_ids=[p_sorento.id, p_mocha.id], status="discontinued"
    )

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_products_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    db.commit()

    result = ProductService(db).list_products(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None


# =============================================================================
# master_product_attachments_list
# =============================================================================


def test_product_attachments_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    type_id = attachment_type(db).id
    att_sorento = attachment(db, type_id=type_id, filename="ZZT-sorento.pdf")
    att_mocha = attachment(db, type_id=type_id, filename="ZZT-mocha.pdf")
    product_attachment(
        db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, attachment_id=att_sorento.id
    )
    product_attachment(
        db, company_id=MOCHA_ID, product_id=p_mocha.id, attachment_id=att_mocha.id
    )
    db.commit()

    result = ProductAttachmentService(db).list_product_attachments(
        product_ids=[p_sorento.id, p_mocha.id]
    )

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_product_attachments_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    # Neither product has any attachment row.
    db.commit()

    result = ProductAttachmentService(db).list_product_attachments(
        product_ids=[p_sorento.id, p_mocha.id]
    )

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_product_attachments_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    type_id = attachment_type(db).id
    att = attachment(db, type_id=type_id)
    product_attachment(
        db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, attachment_id=att.id
    )
    db.commit()

    result = ProductAttachmentService(db).list_product_attachments(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None
