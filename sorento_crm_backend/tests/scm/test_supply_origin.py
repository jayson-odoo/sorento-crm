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
    from app.models.user import SystemSetting

    # PLAN-local-buy-routing-toggle.md: the resolver now reads the setting first, off
    # by default, so it must be ON here for this file's ON-behaviour pins to hold.
    row = db.query(SystemSetting).first() or SystemSetting(id=_u())
    db.add(row)
    db.flush()
    db.query(SystemSetting).filter(SystemSetting.id == row.id).update(
        {SystemSetting.local_buy_routing_enabled: True}
    )

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
    from app.models.user import SystemSetting

    # PLAN-local-buy-routing-toggle.md: the resolver now reads the setting first, off
    # by default, so it must be ON here for this file's ON-behaviour pins to hold.
    row = db.query(SystemSetting).first() or SystemSetting(id=_u())
    db.add(row)
    db.flush()
    db.query(SystemSetting).filter(SystemSetting.id == row.id).update(
        {SystemSetting.local_buy_routing_enabled: True}
    )

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


# --------------------------------------------------------------------------------- #
# PLAN-brand-flows-to-purchasing.md (owner ruling 22 Sep 2026, R4-R7): a brand can be
# marked `flows_to_purchasing = false`, and a product on that brand answers "local"
# whatever the toggle state and whatever its supplier's country.
#
# RED for Phase 2: `brands.flows_to_purchasing` does not exist yet (no such column,
# no such model attribute), so every test below fails against TODAY's code with an
# AttributeError / UndefinedColumn - not a fixture bug.
# --------------------------------------------------------------------------------- #


def _set_toggle(db, value: bool):
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_u())
        db.add(row)
        db.flush()
    db.query(SystemSetting).filter(SystemSetting.id == row.id).update(
        {SystemSetting.local_buy_routing_enabled: value}
    )
    db.flush()


def _brand(db, *, flows_to_purchasing=True):
    from app.models.product import Brand

    brand = Brand(
        id=_u(), brand_code=_code("BRD"), brand_name=_code("brand"),
        is_active=True, flows_to_purchasing=flows_to_purchasing,
    )
    db.add(brand)
    db.flush()
    return brand


def test_blocked_brand_answers_local_toggle_off(db, chain):
    """AC-5: toggle off (the default), a blocked-brand product answers "local", a
    default-brand product answers None."""
    from app.services.scm.supply_origin import buy_origin_by_product

    _set_toggle(db, False)

    f = chain
    blocked_brand = _brand(db, flows_to_purchasing=False)
    blocked_product = f["product"]
    blocked_product.brand_id = blocked_brand.id
    db.flush()

    default_brand = _brand(db, flows_to_purchasing=True)
    default_product = _add_product(db, f, stem="DFLT")
    default_product.brand_id = default_brand.id
    db.flush()

    origins = buy_origin_by_product(db, [blocked_product.id, default_product.id])

    assert origins[str(blocked_product.id)] == "local"
    assert origins[str(default_product.id)] is None


def test_brand_read_is_one_statement_toggle_off_two_total_on_three(db, chain):
    """Red 1a: the brand read never scales with the toggle and never runs more than
    once per call. Toggle off: exactly 2 statements (the settings read + the brand
    read). Toggle on: exactly 3 (settings + brand + the supplier-country chain)."""
    from sqlalchemy import event

    from app.services.scm.supply_origin import buy_origin_by_product

    f = chain
    blocked_brand = _brand(db, flows_to_purchasing=False)
    product = f["product"]
    product.brand_id = blocked_brand.id
    db.flush()

    def _count(connection, on):
        _set_toggle(db, on)
        calls = {"n": 0}

        def _capture(conn, cursor, statement, parameters, context, executemany):
            calls["n"] += 1

        event.listen(connection, "before_cursor_execute", _capture)
        try:
            buy_origin_by_product(db, [product.id])
        finally:
            event.remove(connection, "before_cursor_execute", _capture)
        return calls["n"]

    connection = db.connection()
    assert _count(connection, False) == 2
    assert _count(connection, True) == 3


def test_blocked_brand_answers_local_toggle_on_whatever_the_supplier_country(db, chain):
    """AC-6: toggle on, a blocked-brand product answers "local" for a MY-supplier link
    AND for an overseas one, while a default-brand MY-supplier product is unaffected
    (still "local" through the existing supplier-country chain)."""
    from app.services.scm.supply_origin import buy_origin_by_product

    _set_toggle(db, True)

    f = chain
    my = _country(db, "MY", "Malaysia")
    cn = _country(db, "CN", "China")
    blocked_brand = _brand(db, flows_to_purchasing=False)

    my_blocked = f["product"]
    my_blocked.brand_id = blocked_brand.id
    my_supplier = _supplier(db, "brand blocked my sdn bhd")
    my_supplier.country_id = my.id
    db.flush()
    _link(db, my_blocked, my_supplier, primary=True)

    cn_blocked = _add_product(db, f, stem="CNBLOCK")
    cn_blocked.brand_id = blocked_brand.id
    cn_supplier = _supplier(db, "brand blocked cn factory")
    cn_supplier.country_id = cn.id
    db.flush()
    _link(db, cn_blocked, cn_supplier, primary=True)

    default_product = _add_product(db, f, stem="DFLTMY")
    default_supplier = _supplier(db, "default brand my sdn bhd")
    default_supplier.country_id = my.id
    db.flush()
    _link(db, default_product, default_supplier, primary=True)

    origins = buy_origin_by_product(
        db, [my_blocked.id, cn_blocked.id, default_product.id]
    )

    assert origins[str(my_blocked.id)] == "local"
    assert origins[str(cn_blocked.id)] == "local"
    assert origins[str(default_product.id)] == "local"


def test_product_with_no_brand_is_unaffected(db, chain):
    """Red 3: a product with no brand at all answers exactly as it did before this
    lane - None while the toggle is off, and by supplier country while it is on."""
    from app.services.scm.supply_origin import buy_origin_by_product

    f = chain
    my = _country(db, "MY", "Malaysia")
    product = f["product"]
    assert product.brand_id is None
    supplier = _supplier(db, "no brand my sdn bhd")
    supplier.country_id = my.id
    db.flush()
    _link(db, product, supplier, primary=True)

    _set_toggle(db, False)
    assert buy_origin_by_product(db, [product.id])[str(product.id)] is None

    _set_toggle(db, True)
    assert buy_origin_by_product(db, [product.id])[str(product.id)] == "local"
