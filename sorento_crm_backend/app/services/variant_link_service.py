"""Variant graph derivation — ``products.variant_of_id`` self-FK link.

A product's parent is the **longest existing** product ``P'`` such that the
child's code starts with ``P'.code`` (both dash/whitespace-normalized), ``P'`` is
strictly shorter, and the character right after the prefix in the **original**
(un-normalized) child code is a ``-`` or an ASCII letter (never a continued
digit). Existence-anchoring (parent must be a real row) is what stops brand/
category prefixes like ``ACC`` / ``OX`` forming garbage families.

``reconcile_variant_links(db, code_or_id)`` is the single idempotent entry point,
called from ``product_service`` create / update / delete and the backfill. It is
"set-to-correct-value" (not update-where-null): it re-points *my* parent AND
adopts any orphan whose correct parent is now me.

See ``docs/plans/PLAN-suggest-on-miss-variant-graph.md`` §1.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.product import Product

logger = logging.getLogger(__name__)

# Dash/whitespace stripper — symmetric with the resolver's SQL normalizer
# ``lower(regexp_replace(col, '[-\s]', '', 'g'))``.
_STRIP_RE = re.compile(r"[-\s]")


def normalize_code(code: Optional[str]) -> str:
    """lowercased, dash/whitespace-stripped code (matches the SQL normalizer)."""
    if not code:
        return ""
    return _STRIP_RE.sub("", code).lower()


def boundary_ok(original_child: str, norm_prefix_len: int) -> bool:
    """Is the char right after a normalized prefix a variant boundary?

    Walks the ORIGINAL child code counting significant (non ``[-\\s]``) chars;
    after ``norm_prefix_len`` of them, the next original char must be a dash /
    whitespace or an ASCII letter to count as a variant boundary. A continued
    digit (or any other char) means the codes are different products, not a
    variant relationship.
    """
    if norm_prefix_len <= 0:
        return False
    count = 0
    for i, ch in enumerate(original_child):
        if _STRIP_RE.match(ch):
            continue
        count += 1
        if count == norm_prefix_len:
            nxt = original_child[i + 1] if i + 1 < len(original_child) else ""
            if nxt == "":
                return False  # nothing follows -> not strictly longer
            if _STRIP_RE.match(nxt):
                return True  # dash / whitespace boundary
            return bool(nxt.isascii() and nxt.isalpha())
    return False


# SQL fragment normalizing a column the same way ``normalize_code`` does.
def _norm_sql(col: str) -> str:
    return f"lower(regexp_replace({col}, '[-\\s]', '', 'g'))"


def _derive_parent_id(db: Session, product_id: str, product_code: str) -> Optional[str]:
    """Longest existing boundary-prefix parent for ``product_code``, or None."""
    norm_child = normalize_code(product_code)
    if not norm_child:
        return None
    n_norm = _norm_sql("product_code")
    # Candidate parents: strictly-shorter products whose normalized code is a
    # prefix of mine. ``left(:norm_child, len)`` avoids LIKE wildcard hazards
    # from ``_`` / ``%`` in codes. Longest first; tie-break by code for
    # determinism (matches the in-memory backfill).
    rows = db.execute(
        text(
            f"""
            SELECT id, product_code
            FROM products
            WHERE id <> :self_id
              AND {n_norm} <> ''
              AND length({n_norm}) < :nlen
              AND left(:norm_child, length({n_norm})) = {n_norm}
            ORDER BY length({n_norm}) DESC, product_code ASC
            """
        ),
        {"self_id": product_id, "norm_child": norm_child, "nlen": len(norm_child)},
    ).fetchall()
    for cand_id, cand_code in rows:
        if boundary_ok(product_code, len(normalize_code(cand_code))):
            return cand_id
    return None


def _adopt_orphans(db: Session, parent: Product) -> int:
    """Re-derive every product for which ``parent`` might now be the answer.

    Scope = products whose normalized code starts with mine (I could be their
    parent). For each, recompute the longest-existing parent and set-to-correct
    (a deeper existing product still wins over me). Returns #rows changed.
    """
    norm_me = normalize_code(parent.product_code)
    if not norm_me:
        return 0
    n_norm = _norm_sql("product_code")
    candidates = db.execute(
        text(
            f"""
            SELECT id, product_code, variant_of_id
            FROM products
            WHERE id <> :self_id
              AND length({n_norm}) > :nlen
              AND left({n_norm}, :nlen) = :norm_me
              AND variant_link_manual = false
            """
        ),
        {"self_id": parent.id, "norm_me": norm_me, "nlen": len(norm_me)},
    ).fetchall()
    changed = 0
    for child_id, child_code, current_parent in candidates:
        if not boundary_ok(child_code, len(norm_me)):
            continue
        correct = _derive_parent_id(db, child_id, child_code)
        if correct != current_parent:
            db.execute(
                text("UPDATE products SET variant_of_id = :p WHERE id = :id"),
                {"p": correct, "id": child_id},
            )
            changed += 1
    return changed


def reconcile_variant_links(db: Session, code_or_id: str) -> dict:
    """Idempotently re-derive one product's variant link and adopt its orphans.

    ``code_or_id`` may be a product id (UUID) or a product_code. When the row no
    longer exists (e.g. post-delete re-derivation of an ex-child by id that was
    itself removed) this is a no-op. Commits its own unit of work.
    """
    # Branch on UUID-ness: comparing the UUID `id` column against a non-UUID
    # product_code string makes Postgres cast the literal to UUID and raise
    # InvalidTextRepresentation before the OR can short-circuit. Detect in python.
    import uuid as _uuid

    try:
        _uuid.UUID(str(code_or_id))
        lookup = Product.id == code_or_id
    except (ValueError, TypeError, AttributeError):
        lookup = Product.product_code == code_or_id
    product = db.query(Product).filter(lookup).first()
    if product is None:
        return {"found": False, "self_changed": False, "orphans_adopted": 0}

    # D1 — a manually-curated row's OWN parent is sticky: never re-derive it.
    # (It still acts as a legitimate parent for auto children below.)
    if not getattr(product, "variant_link_manual", False):
        derived_parent = _derive_parent_id(db, product.id, product.product_code)
        self_changed = product.variant_of_id != derived_parent
        if self_changed:
            product.variant_of_id = derived_parent
    else:
        derived_parent, self_changed = product.variant_of_id, False

    orphans = _adopt_orphans(db, product)

    if self_changed or orphans:
        db.commit()
    return {
        "found": True,
        "self_changed": self_changed,
        "parent_id": derived_parent,
        "orphans_adopted": orphans,
    }


def child_ids_of(db: Session, product_id: str) -> list[str]:
    """Ids of products currently pointing at ``product_id`` — captured pre-delete
    so they can be re-derived (re-anchored to the next ancestor) afterwards."""
    rows = db.execute(
        text("SELECT id FROM products WHERE variant_of_id = :pid"),
        {"pid": product_id},
    ).fetchall()
    return [r[0] for r in rows]
