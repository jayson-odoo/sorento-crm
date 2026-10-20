"""Seed the REAL family shape (CHAT-STATE r4): products that share `family_code`, with
`variant_of_id` NULL (2 of 15,439 prod-copy products carry it; 13,983 carry family_code)."""
from __future__ import annotations

import uuid

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code


def seed_registry(db, spec_key: str, allowed: list[str], synonyms: dict[str, list[str]]) -> None:
    db.add(ProductSpecRegistry(id=str(uuid.uuid4()), spec_key=spec_key, label=spec_key.title(), data_type="enum",
                               allowed_values=allowed, synonyms=synonyms))


def seed_rows(session_factory, rows: list[tuple[str, str | None, str, str]], *, registry: tuple | None = None,
              class_label: str = "Water Closet") -> dict[str, str]:
    """rows = [(product_code, family_code, spec_key, spec_value)]; variant_of_id stays NULL."""
    db = session_factory()
    if registry:
        seed_registry(db, *registry)
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("FC")[:50], category_name="ZZT FC",
                          class_label=class_label, company_id=DEFAULT_COMPANY_ID)
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    ids: dict[str, str] = {}
    for code, family, key, value in rows:
        p = Product(id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=cat.id,
                    base_uom_id=uom.id, list_price=1, company_id=DEFAULT_COMPANY_ID,
                    family_code=family, family_code_manual=True, variant_of_id=None)
        db.add(p)
        db.flush()
        ids[code] = p.id
        db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id,
                                     values={"class": {"value": class_label}, key: {"value": value}}))
    db.commit()
    return ids
