"""Matching a catalogue photo's printed codes to the product master (CATALOG-IMAGES, R3, R5).

Read-only, and every query is ORM so the company filter applies: a code that exists only under
another company is simply not found. Reuses the flyer matcher's bulk code lookup and its "did you
mean" suggestion so both screens offer the same guess for the same miss.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
from app.models.scm import SupplierProductCodeAlias
from app.services.dealer_kit.flyer_matching import _products_by_code, _suggestions


@dataclass(frozen=True)
class CodeMatch:
    code: str
    rung: str  # exact | normalised | suffix | alias | none
    product_id: Optional[str]
    product_code: Optional[str]
    confidence: str  # high | medium | low | none
    suggestion: Optional[str]


def _normalise(code: str) -> str:
    return re.sub(r"[\s.]", "", code).upper()


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _suffix_candidates(db: Session, code: str) -> list[Product]:
    """Products whose code is this one plus a ``-SUFFIX``, or this one minus its ``-SUFFIX``."""
    stems = []
    parts = code.split("-")
    for cut in range(1, len(parts)):
        stems.append("-".join(parts[:cut]))
    conditions = [Product.product_code.like(f"{_like_escape(code)}-%", escape="\\")]
    if stems:
        conditions.append(Product.product_code.in_(stems))
    rows = db.query(Product).filter(or_(*conditions)).order_by(Product.product_code, Product.id).all()
    unique: dict[str, Product] = {}
    for product in rows:
        unique.setdefault(product.product_code, product)
    return list(unique.values())


def match_codes(db: Session, codes: list[str]) -> dict[str, CodeMatch]:
    if not codes:
        return {}
    wanted = list(dict.fromkeys(codes))
    result: dict[str, CodeMatch] = {}

    def hit(code: str, rung: str, product: Product, confidence: str) -> None:
        result[code] = CodeMatch(code, rung, product.id, product.product_code, confidence, None)

    exact = _products_by_code(db, wanted)
    for code in wanted:
        if code in exact:
            hit(code, "exact", exact[code], "high")

    pending = [code for code in wanted if code not in result]
    normalised = {code: _normalise(code) for code in pending}
    by_norm = _products_by_code(db, sorted({n for n in normalised.values() if n}))
    for code in pending:
        product = by_norm.get(normalised[code])
        if product is not None:
            hit(code, "normalised", product, "medium")

    ambiguous: set[str] = set()
    for code in [c for c in wanted if c not in result]:
        candidates = _suffix_candidates(db, normalised.get(code) or code)
        if len(candidates) == 1:
            hit(code, "suffix", candidates[0], "medium")
        elif len(candidates) > 1:
            ambiguous.add(code)

    for code in [c for c in wanted if c not in result and c not in ambiguous]:
        rows = (
            db.query(Product)
            .join(SupplierProductCodeAlias, SupplierProductCodeAlias.product_id == Product.id)
            .filter(SupplierProductCodeAlias.supplier_code == code)
            .order_by(Product.product_code, Product.id)
            .all()
        )
        if len({product.id for product in rows}) == 1:
            hit(code, "alias", rows[0], "medium")

    misses = [code for code in wanted if code not in result]
    suggestions = _suggestions(db, misses) if misses else {}
    for code in misses:
        suggestion = suggestions.get(code)
        result[code] = CodeMatch(
            code,
            "none",
            None,
            None,
            "low" if suggestion else "none",
            suggestion.product_code if suggestion else None,
        )
    return {code: result[code] for code in codes}


def already_on_file(db: Session, product_id: str, sha256: str) -> bool:
    """R5: the product already links an attachment with exactly these bytes."""
    return (
        db.query(ProductAttachment.id)
        .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
        .filter(
            ProductAttachment.product_id == product_id,
            Attachment.file_hash == sha256,
            Attachment.is_deleted.is_(False),
        )
        .first()
        is not None
    )
