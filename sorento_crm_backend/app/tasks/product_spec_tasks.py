"""Catalog-wide spec derivation and re-embedding, on the worker.

Derivation touches every product code (11,414 of them, 22,805 rows), so it never runs
in the request path. Chunked and resumable: pass the codes still outstanding to pick up
where a previous run stopped.

Runs with the ALL-COMPANIES scope on purpose. A product code exists once per company,
and one derivation must land on every copy or the two drift with nothing detecting it.
"""
from __future__ import annotations

import logging
from typing import Sequence

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.product import Product
from app.services.product_spec_change_listener import enqueue_spec_embedding
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


def enqueue_spec_embeddings(
    product_ids: Sequence[str] | None = None,
    chunk_size: int = 500,
    run_label: str | None = None,
) -> dict:
    """Queue a `product_spec` re-embed for each product row, in chunks.

    The batch the change listener hands over is as large as the write that produced it,
    so a catalogue import arrives here with thousands of ids. A session per chunk keeps
    a long run from holding one transaction open for its whole duration.

    Best-effort per id, like everything else on this path: one product whose enqueue
    fails is reported in the result and does not take the rest of the batch with it.
    `run_label` is only for log correlation.
    """
    ids = [str(product_id) for product_id in (product_ids or [])]
    logger.info(
        "spec embedding enqueue starting: %s products, chunk=%s, run=%s",
        len(ids),
        chunk_size,
        run_label,
    )

    queued = failed = 0
    for start in range(0, len(ids), max(1, chunk_size)):
        with SessionLocal() as db:
            # None = every company, exactly as the embedding worker runs: a spec row
            # exists per company copy and each one carries its own document.
            with company_scope(db, None):
                for product_id in ids[start : start + max(1, chunk_size)]:
                    try:
                        enqueue_spec_embedding(db, product_id)
                        queued += 1
                    except Exception:
                        failed += 1
                        logger.warning(
                            "spec embedding enqueue failed for %s", product_id, exc_info=True
                        )
                    finally:
                        # `queue_event` commits on success; anything still open is a
                        # half-finished attempt that would otherwise ride along on the
                        # next product's commit.
                        db.rollback()

    result = {"products": len(ids), "queued": queued, "failed": failed}
    logger.info("spec embedding enqueue finished: %s run=%s", result, run_label)
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
