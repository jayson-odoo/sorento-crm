"""Catalog-wide spec derivation, on the worker.

Derivation touches every product code (11,414 of them, 22,805 rows), so it never runs
in the request path. Chunked and resumable: pass the codes still outstanding to pick up
where a previous run stopped.

Runs with the ALL-COMPANIES scope on purpose. A product code exists once per company,
and one derivation must land on every copy or the two drift with nothing detecting it.
"""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.product import Product
from app.services.product_spec_derivation import derive_all

logger = logging.getLogger(__name__)


def derive_product_specs(
    codes: list[str] | None = None,
    chunk_size: int = 500,
    run_label: str | None = None,
) -> dict:
    """Derive specs for `codes`, or the whole catalog when omitted.

    `run_label` is only for log correlation, so a resumed run can be tied to the one
    it continues.
    """
    with SessionLocal() as db:
        # None = every company. Under a single-company scope this would silently cover
        # half the catalog; see derive_all's docstring.
        with company_scope(db, None):
            if codes is None:
                codes = [c for (c,) in db.query(Product.product_code).distinct().all()]

            logger.info(
                "spec derivation starting: %s codes, chunk=%s, run=%s",
                len(codes),
                chunk_size,
                run_label,
            )
            result = derive_all(db, codes=codes, chunk_size=chunk_size, commit=True)
            logger.info("spec derivation finished: %s run=%s", result, run_label)
            return result


def derive_specs_for_class(class_label: str, chunk_size: int = 500) -> dict:
    """Derive one product class. The T0 tracer runs this for Kitchen Sink."""
    from app.models.product import ProductCategory

    with SessionLocal() as db:
        with company_scope(db, None):
            codes = [
                c
                for (c,) in db.query(Product.product_code)
                .join(ProductCategory, ProductCategory.id == Product.category_id)
                .filter(ProductCategory.class_label == class_label)
                .distinct()
                .all()
            ]
    return derive_product_specs(codes=codes, chunk_size=chunk_size, run_label=f"class:{class_label}")
