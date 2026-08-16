"""AC-B1/AC-B2/AC-B4 for `crm_order_management_orders_list`
(OrderService.list_orders) and `crm_order_management_orders_by_product_list`
(OrderService.list_orders_by_product). Modelled on
tests/test_attachment_company_stamp_in_list.py. Postgres only.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.order_service import OrderService

from tests._mc_lookup_seed import (
    MOCHA_ID,
    customer,
    order,
    order_line,
    product,
    seed_mocha,
    warehouse,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        yield session


def _seed_order(db, *, company_id, product_id, warehouse_id):
    cust = customer(db, company_id=company_id)
    ord_row = order(db, company_id=company_id, customer_id=cust.id)
    order_line(
        db, company_id=company_id, order_id=ord_row.id, product_id=product_id,
        warehouse_id=warehouse_id,
    )
    return ord_row


# =============================================================================
# orders_list
# =============================================================================


def test_orders_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    wh_mocha = warehouse(db, company_id=MOCHA_ID)
    _seed_order(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    _seed_order(db, company_id=MOCHA_ID, product_id=p_mocha.id, warehouse_id=wh_mocha.id)
    db.commit()

    result = OrderService(db).list_orders(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_orders_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    # No order carries either product.
    db.commit()

    result = OrderService(db).list_orders(product_ids=[p_sorento.id, p_mocha.id])

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_orders_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    _seed_order(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    db.commit()

    result = OrderService(db).list_orders(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None


# =============================================================================
# orders_by_product_list
# =============================================================================


def test_orders_by_product_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    wh_mocha = warehouse(db, company_id=MOCHA_ID)
    _seed_order(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    _seed_order(db, company_id=MOCHA_ID, product_id=p_mocha.id, warehouse_id=wh_mocha.id)
    db.commit()

    result = OrderService(db).list_orders_by_product(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_orders_by_product_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    result = OrderService(db).list_orders_by_product(product_ids=[p_sorento.id, p_mocha.id])

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_orders_by_product_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    _seed_order(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    db.commit()

    result = OrderService(db).list_orders_by_product(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None
