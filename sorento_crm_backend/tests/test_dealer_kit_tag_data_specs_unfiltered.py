"""AC-19: `tag_data_service.product_specs` is byte-identical for any spec
visibility policy - dealer kit tags are a staff-driven print, out of scope for
this feature (PLAN "Out of scope").

UAC `documentation/plans/chatbot/spec-visibility-policy-acceptance-criteria.md`
AC-19. Precedent copied from `tests/test_dealer_kit_tag_data.py::TestProductSpecs`.

Postgres only, own product/registry chain (CI's database has none).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _product(db):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTSV")
    category = ProductCategory(id=str(uuid.uuid4()), category_code=stem, category_name=f"ZZT cat {stem}")
    brand = Brand(id=str(uuid.uuid4()), brand_code=stem[:50], brand_name=f"ZZT brand {stem}")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal("1599.00"),
    )
    db.add(product)
    db.flush()
    return product


def _registry_key(db, key: str, label: str, *, is_active: bool = True):
    from app.models.product_spec import ProductSpecRegistry

    row = ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key=key, label=label, data_type="numeric", is_active=is_active
    )
    db.add(row)
    db.flush()
    return row


def _spec_values(db, product, values: dict):
    from app.models.product_spec import ProductSpecifications

    db.add(
        ProductSpecifications(
            id=str(uuid.uuid4()),
            product_id=product.id,
            values=values,
            provenance={},
            rendered_text="ZZT rendered",
        )
    )
    db.flush()


def _default_policy_hiding(db, keys: list[str]) -> None:
    """A default `spec_visibility_policies` row hiding `keys` for every contact -
    the staff dealer-kit print must never read it."""
    from sqlalchemy import text as sa_text

    db.execute(
        sa_text(
            "INSERT INTO spec_visibility_policies (id, spec_keys, excluded_spec_keys) "
            "VALUES (gen_random_uuid(), NULL, :excluded)"
        ),
        {"excluded": keys},
    )
    db.flush()


def test_tag_data_product_specs_still_lists_thickness_for_any_contact_policy(db):
    from app.services.dealer_kit import tag_data_service

    stem = unique_code("zztsv").lower()
    thickness_key = f"{stem}_thickness"
    _registry_key(db, thickness_key, "Thickness", is_active=True)
    product = _product(db)
    _spec_values(db, product, {thickness_key: {"value": 0.8}})
    _default_policy_hiding(db, [thickness_key])

    specs = tag_data_service.product_specs(db, product)

    assert any(
        row["key"] == thickness_key and row["label"] == "Thickness" for row in specs
    )
