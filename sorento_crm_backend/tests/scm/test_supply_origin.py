"""`app.services.scm.supply_origin.buy_origin_by_product` (S3, PLAN-local-supplier-oi-routing.md,
UAC AC-2.12, AC-2.13).

RED for Phase 2: the module does not exist yet. Contract this file drives:

`buy_origin_by_product(db, product_ids: Iterable[str]) -> dict[str, str]` - one supplier
per product (primary `product_suppliers` link, else the newest PO supplier by
`purchase_orders.issue_date DESC NULLS LAST, created_at DESC` - the same tiebreak
`summary_order_service._last_po_supplier_map` (S15) uses), then `"local"` iff that
supplier's `country.code` (case-insensitive) equals `HOME_COUNTRY_CODE`. No supplier, or a
supplier with no country, is `"overseas"`. A product absent from the input dict is never
asserted on here - only products actually resolved to a supplier need appear (or, if the
coder chooses to enumerate every input id, `"overseas"` is still the value fetched for a
product with neither a link nor a PO, so either shape satisfies these assertions).

`HOME_COUNTRY_CODE` lives beside `BASE_CURRENCY` in `app.services.scm.money` per the plan.

Fixtures copied from `tests/scm/test_supplier_last_po_s15.py` (`chain`, `db`, `_supplier`,
`_po`, `_link` in `tests/scm/test_summary_order_service.py`) with the justification that
earned them there: this is the same product/supplier/PO graph, real Postgres via
`pg_session`, no sqlite.
"""
from __future__ import annotations

import uuid

import pytest

from tests.scm.test_summary_order_service import _link, _po, _supplier, chain, db  # noqa: F401

MARKER = "ZZTORIGIN"


def _u() -> str:
    return str(uuid.uuid4())


def _country(db, code, name):
    """Get-or-create by code, case-insensitive.

    `db` is `pg_session` - the real, rolled-back lane database - which now carries the
    249-row ISO seed from `510_countries`, so `MY` and `CN` already exist and a plain
    insert collides on `uq_countries_code_lower`. Looked up rather than a monkeypatched
    `HOME_COUNTRY_CODE`, so this stays correct however the module names the home country.
    """
    from sqlalchemy import func

    from app.models.country import Country

    existing = (
        db.query(Country).filter(func.lower(Country.code) == code.lower()).first()
    )
    if existing is not None:
        return existing
    country = Country(id=_u(), code=code, name=name)
    db.add(country)
    db.flush()
    return country


def test_origin_chain(db, chain):
    """Four products, four resolutions:

    * primary link to a MY supplier -> local
    * no link, newest PO from a MY supplier -> local
    * no link, no PO at all -> overseas
    * link to a supplier with no country -> overseas
    """
    from app.services.scm.supply_origin import buy_origin_by_product

    f = chain
    my = _country(db, "MY", "Malaysia")

    p_primary_local = f["product"]
    my_supplier = _supplier(db, "primary sdn bhd")
    my_supplier.country_id = my.id
    db.flush()
    _link(db, p_primary_local, my_supplier, primary=True)

    p_po_local = _add_product(db, f, stem="POLOCAL")
    po_supplier = _supplier(db, "po sdn bhd")
    po_supplier.country_id = my.id
    db.flush()
    _po(db, p_po_local, f["bin"], 10, supplier=po_supplier)

    p_no_history = _add_product(db, f, stem="NOHIST")

    p_no_country = _add_product(db, f, stem="NOCTRY")
    no_country_supplier = _supplier(db, "no country supplier")
    _link(db, p_no_country, no_country_supplier, primary=True)

    origins = buy_origin_by_product(
        db,
        [p_primary_local.id, p_po_local.id, p_no_history.id, p_no_country.id],
    )

    assert origins[str(p_primary_local.id)] == "local"
    assert origins[str(p_po_local.id)] == "local"
    assert origins.get(str(p_no_history.id), "overseas") == "overseas"
    assert origins[str(p_no_country.id)] == "overseas"


def test_primary_link_beats_newer_po(db, chain):
    """A product whose primary link is Malaysian but whose NEWEST PO is Chinese still
    resolves local - the primary link wins (plan decision 3 / AC-2.13)."""
    from app.services.scm.supply_origin import buy_origin_by_product

    f = chain
    my = _country(db, "MY", "Malaysia")
    cn = _country(db, "CN", "China")

    product = f["product"]
    my_supplier = _supplier(db, "primary my sdn bhd")
    my_supplier.country_id = my.id
    cn_supplier = _supplier(db, "newer cn factory")
    cn_supplier.country_id = cn.id
    db.flush()

    _link(db, product, my_supplier, primary=True)
    _po(db, product, f["bin"], 10, supplier=cn_supplier, issued_days_ago=2)

    origins = buy_origin_by_product(db, [product.id])

    assert origins[str(product.id)] == "local"


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _add_product(db, f, *, stem="SKU"):
    from app.models.product import Product

    product = Product(
        id=_u(), product_code=_code(stem), product_name="extra product",
        category_id=f["cat"].id, base_uom_id=f["uom"].id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product
