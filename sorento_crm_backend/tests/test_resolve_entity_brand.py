"""A resolved product says which brand it belongs to, on every match path.

Why it exists: brand and company are different axes. Cabana is a BRAND under the
Sorento COMPANY, so `company_name` cannot distinguish a Cabana product from any
other Sorento one - downstream routing that needs "Cabana" has nothing to read.

Brand was emitted only when the resolver matched VIA brand access. A direct code
lookup - the overwhelmingly common path - returned no brand key at all, so a
promotion enquiry for a Cabana SKU routed to the Sorento team.

Attribution is additive: it must never change which rows resolve, only describe
them.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.entity_resolver import resolve_references, resolve_references_intersection

from ._pg_fixture import blank_session, unique_code

CODE = "ZZTCBS212-WH"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
        db.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _brand(db, *, code: str, name: str) -> tuple[str, str, str]:
    """Returns (id, code, name) - the codes are uniquified, so a caller that
    wants to assert on them has to be told what they became."""
    bid = str(uuid.uuid4())
    brand_code = unique_code(code)[:50]
    brand_name = unique_code(name)[:150]
    db.add(
        Brand(id=bid, brand_code=brand_code, brand_name=brand_name, company_id=DEFAULT_COMPANY_ID)
    )
    db.flush()
    return bid, brand_code, brand_name


def _product(db, *, code: str, brand_id: str | None) -> str:
    cat, uom = _refs(db)
    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid, product_code=code, product_name=code, category_id=cat,
            base_uom_id=uom, list_price=10, is_active=True,
            company_id=DEFAULT_COMPANY_ID, brand_id=brand_id,
        )
    )
    db.flush()
    return pid


def _match(db, token: str, product_id: str):
    result = resolve_references(db, token, allowed_entity_types=["product"])
    for tr in result.resolutions:
        for m in tr.matches:
            if m.uuid == product_id:
                return m
    return None


def test_exact_code_match_carries_brand(db):
    """The reported case: a code lookup that never touched the brand-access path."""
    bid, brand_code, brand_name = _brand(db, code="CABANA", name="Cabana")
    pid = _product(db, code=CODE, brand_id=bid)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    match = _match(db, CODE, pid)

    assert match is not None, "the product did not resolve at all"
    brand = match.display.get("brand")
    assert brand is not None, "exact product_code match carried no brand"
    assert brand["brand_id"] == bid
    assert brand["brand_code"] == brand_code
    assert brand["brand_name"] == brand_name


def test_prefix_match_carries_brand(db):
    """Tier 2 selects its own column tuple - it has to be covered separately."""
    bid, _, _ = _brand(db, code="CABANA", name="Cabana")
    pid = _product(db, code=CODE, brand_id=bid)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    match = _match(db, CODE[:-3], pid)

    assert match is not None, "the prefix did not resolve"
    assert match.match_tier in {"prefix", "substring"}
    assert (match.display.get("brand") or {}).get("brand_id") == bid


def test_and_mode_intersection_carries_brand(db):
    """AND mode is a separate result class with its own as_dict."""
    bid, _, _ = _brand(db, code="CABANA", name="Cabana")
    pid = _product(db, code=CODE, brand_id=bid)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = resolve_references_intersection(
        db, [CODE], allowed_entity_types=["product"]
    ).as_dict()

    row = next(m for m in payload["intersection"] if m["uuid"] == pid)
    assert (row["display"].get("brand") or {}).get("brand_id") == bid


def test_a_product_with_no_brand_says_so_explicitly(db):
    """The key is always present, so a consumer can tell "no brand" from "this
    match path forgot to send one" - which is exactly the bug being fixed."""
    pid = _product(db, code=CODE, brand_id=None)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    match = _match(db, CODE, pid)

    assert match is not None
    assert "brand" in match.display
    assert match.display["brand"] is None


def test_brand_is_never_derived_from_the_code(db):
    """A CBS-prefixed code whose brand relation says otherwise reports the
    relation. Prefix-derived branding mislabelled 1,934 rows before."""
    bid, brand_code, _ = _brand(db, code="NOLOGO", name="No Logo")
    pid = _product(db, code=CODE, brand_id=bid)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    match = _match(db, CODE, pid)

    assert match is not None
    assert match.display["brand"]["brand_code"] == brand_code


def test_the_payload_exposes_the_brand_field(db):
    """as_dict is the n8n-facing contract - the key must actually be in it."""
    bid, _, _ = _brand(db, code="CABANA", name="Cabana")
    _product(db, code=CODE, brand_id=bid)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = resolve_references(db, CODE, allowed_entity_types=["product"]).as_dict()

    match = next(
        m for tr in payload["resolutions"] for m in tr["matches"]
        if m["canonical_code"] == CODE
    )
    assert (match["display"].get("brand") or {}).get("brand_id") == bid


def test_brand_attribution_does_not_change_what_resolves(db):
    bid, _, _ = _brand(db, code="CABANA", name="Cabana")
    pid = _product(db, code=CODE, brand_id=bid)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    result = resolve_references(db, CODE, allowed_entity_types=["product"])

    uuids = [m.uuid for tr in result.resolutions for m in tr.matches]
    assert uuids == [pid], "brand stamping widened or narrowed the result"
