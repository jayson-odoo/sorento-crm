"""Regression matrix: every resolvable identifier x every separator spelling.

n8n strips dashes and whitespace from every entity token before calling
`/api/v1/system/references/resolve`, so the resolver must return the same row
whether a caller sends "ZZT-WT7438-GM", "ZZT WT7438 GM" or "ZZTWT7438GM". This
file pins that for EVERY entity type the resolver answers, at both the exact
(Tier 1) and prefix/substring (Tier 2) probes.

Why a separate file from `test_entity_resolver_trgm.py`: those cases gate on
real production SKUs via `_require_codes`, so they `pytest.skip` wholesale on a
freshly migrated CI database and prove nothing there. Everything here seeds its
own chain on a BLANK schema, so the table it queries contains exactly the row it
just wrote - the assertions are as strong in CI as they are locally.
"""
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import pytest

from app.models.base import company_scope
from app.models.marketing import Promotion
from app.models.order import Customer, Order, Transporter
from app.models.procurement import InboundShipment, PickingHeader, SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.services import entity_resolver as er
from app.services.certificate_service import CertificateService
from app.services.entity_resolver import _strip_all_ws
from tests._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# --------------------------------------------------------------------------- #
# The separator spellings a caller might send for one stored value
# --------------------------------------------------------------------------- #
def separator_variants(value: str) -> list[str]:
    """Every dash/space spelling of `value`, plus case variations.

    All of these normalize to the same string, so all of them must resolve to
    the same row. Includes `value` itself so the matrix also guards against a
    normalization change breaking the plain, unmodified token.
    """
    return sorted(
        {
            value,
            value.lower(),
            re.sub(r"[-\s]+", "", value),          # fully stripped (what n8n sends)
            re.sub(r"[-\s]+", "", value).lower(),
            re.sub(r"[-\s]+", " ", value),         # every separator a space
            re.sub(r"[-\s]+", " ", value).lower(),
            re.sub(r"[-\s]+", "-", value),         # every separator a dash
            re.sub(r"[-\s]+", "-", value).lower(),
        }
    )


def test_separator_variants_all_normalize_to_one_form():
    """The matrix is only meaningful if its variants really are the same token."""
    forms = {_strip_all_ws(v).lower() for v in separator_variants("ZZT-WT7438 GM")}
    assert forms == {"zztwt7438gm"}


# --------------------------------------------------------------------------- #
# Seeders — each returns the id of the row its token must resolve to
# --------------------------------------------------------------------------- #
def _uid() -> str:
    return str(uuid.uuid4())


def _product(db, code: str) -> str:
    cat = ProductCategory(id=_uid(), category_code=f"ZZTC{_uid()[:6]}", category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZTU{_uid()[:6]}", uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name="ZZT product",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=1,
    )
    db.add(row)
    db.flush()
    return row.id


def _order(db, number: str) -> str:
    row = Order(id=_uid(), order_number=number, debtor_name="ZZT debtor")
    db.add(row)
    db.flush()
    return row.id


def _customer(db, code: str) -> str:
    row = Customer(id=_uid(), customer_code=code, customer_name="ZZT customer")
    db.add(row)
    db.flush()
    return row.id


def _shipment(db, number: str, *, container: str | None = None) -> str:
    row = InboundShipment(
        id=_uid(),
        shipment_number=number,
        shipping_container_number=container,
        shipment_date=date(2026, 1, 1),
    )
    db.add(row)
    db.flush()
    return row.id


def _shipment_by_container(db, container: str) -> str:
    return _shipment(db, f"ZZT-SHP-{_uid()[:6]}", container=container)


def _warehouse(db, code: str) -> str:
    row = Warehouse(id=_uid(), warehouse_code=code, warehouse_name="ZZT warehouse")
    db.add(row)
    db.flush()
    return row.id


def _supplier(db, code: str) -> str:
    row = Supplier(id=_uid(), supplier_code=code, supplier_name="ZZT supplier")
    db.add(row)
    db.flush()
    return row.id


def _spo(db, number: str) -> str:
    shipment_id = _shipment(db, f"ZZT-SHP-{_uid()[:6]}")
    warehouse_id = _warehouse(db, f"ZZTW{_uid()[:6]}")
    product_id = _product(db, f"ZZTP{_uid()[:6]}")
    row = SPOAllocation(
        id=_uid(),
        spo_number=number,
        inbound_shipment_id=shipment_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        allocated_quantity=1,
    )
    db.add(row)
    db.flush()
    return row.id


def _grn(db, number: str) -> str:
    row = PickingHeader(
        id=_uid(),
        picking_number=number,
        picking_type="goods_received",
        picking_date=date(2026, 1, 1),
    )
    db.add(row)
    db.flush()
    return row.id


def _transporter(db, code: str) -> str:
    row = Transporter(id=_uid(), code=code, name="ZZT Transporter", normalized_name=f"ZZT {code}")
    db.add(row)
    db.flush()
    return row.id


def _promotion(db, description: str) -> str:
    row = Promotion(id=_uid(), description=description, is_active=True)
    db.add(row)
    db.flush()
    return row.id


def _certificate(db, number: str) -> str:
    cert = CertificateService(db).upsert_from_extraction(
        scheme="ZZTPPS",
        certificate_number=number,
        certifying_body="ZZT body",
        valid_from=date(2026, 1, 1),
        valid_until=date(2027, 1, 1),
        commit=False,
    )
    db.flush()
    return str(cert.id)


# --------------------------------------------------------------------------- #
# The matrix
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Case:
    name: str
    stored: str                      # the value as the database holds it
    seed: Callable[[Any, str], str]  # (db, stored) -> id the token must resolve to
    exact: Callable | None           # Tier-1 probe: (db, [token]) -> {token: [hit]}
    prefix: Callable | None          # Tier-2 probe: (db, token) -> [hit]
    partial: bool = True             # whether a truncated token should also hit Tier 2


CASES = [
    Case("product_code", "ZZT-WT7438-GM", _product, er._probe_product, er._prefix_probe_product),
    Case("order_number", "ZZT-DO-40021", _order, er._probe_customer_order, er._prefix_probe_customer_order),
    Case("customer_code", "ZZT-C043", _customer, er._probe_customer, er._prefix_probe_customer),
    Case("shipment_number", "ZZT-SHP-9001", _shipment, er._probe_inbound_shipment, er._prefix_probe_inbound_shipment),
    Case("container_number", "ZZT-CONT-4455", _shipment_by_container, er._probe_inbound_shipment, er._prefix_probe_inbound_shipment),
    Case("warehouse_code", "ZZT-WH-01", _warehouse, er._probe_warehouse, er._prefix_probe_warehouse),
    Case("supplier_code", "ZZT-SUP-77", _supplier, er._probe_supplier, er._prefix_probe_supplier),
    Case("spo_number", "ZZT-SPO-3321", _spo, er._probe_spo, er._prefix_probe_spo),
    Case("grn_number", "ZZT-GRN-8812", _grn, er._probe_grn, er._prefix_probe_grn),
    Case("transporter_code", "ZZT-TRP-01", _transporter, er._probe_transporter, er._prefix_probe_transporter),
    Case("certificate_number", "ZZT-PC-04124", _certificate, er._probe_certificate, er._prefix_probe_certificate),
    # Promotions have no exact tier - description is prose, matched at Tier 2 only.
    Case("promotion_description", "ZZT-KITCHEN SINK PROMO", _promotion, None, er._prefix_probe_promotion),
]

EXACT_PARAMS = [
    pytest.param(c, v, id=f"{c.name}-{v.replace(' ', '_')}")
    for c in CASES
    if c.exact
    for v in separator_variants(c.stored)
]
PREFIX_PARAMS = [
    pytest.param(c, v, id=f"{c.name}-{v.replace(' ', '_')}")
    for c in CASES
    if c.prefix
    for v in separator_variants(c.stored)
]


def _ids(hits) -> set[str]:
    return {h.uuid for h in hits if h.uuid}


@pytest.mark.parametrize("case, token", EXACT_PARAMS)
def test_tier1_exact_resolves_every_separator_spelling(db, case, token):
    seeded = case.seed(db, case.stored)
    with company_scope(db, frozenset({SORENTO})):
        hits = case.exact(db, [token])[token]
    assert seeded in _ids(hits), f"{case.name}: {token!r} did not resolve to the seeded row"


@pytest.mark.parametrize("case, token", PREFIX_PARAMS)
def test_tier2_prefix_resolves_every_separator_spelling(db, case, token):
    seeded = case.seed(db, case.stored)
    with company_scope(db, frozenset({SORENTO})):
        hits = case.prefix(db, token)
    assert seeded in _ids(hits), f"{case.name}: {token!r} did not resolve to the seeded row"


@pytest.mark.parametrize(
    "case", [pytest.param(c, id=c.name) for c in CASES if c.prefix and c.partial]
)
def test_tier2_resolves_a_truncated_stripped_token(db, case):
    """A caller who sends only the first half, with separators stripped."""
    seeded = case.seed(db, case.stored)
    stripped = re.sub(r"[-\s]+", "", case.stored)
    truncated = stripped[: max(4, len(stripped) - 3)]
    with company_scope(db, frozenset({SORENTO})):
        hits = case.prefix(db, truncated)
    assert seeded in _ids(hits), f"{case.name}: truncated {truncated!r} did not resolve"
