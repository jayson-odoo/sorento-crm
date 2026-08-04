"""Spec search storage: the vocabulary, and later the values derived against it.

Kept out of `product.py` because this is a separate concern with its own lifecycle:
`product.py` models the catalog as the business maintains it, this models what spec
search derives from it.

See documentation/plans/products/PLAN-spec-search.md section 6.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class ProductSpecRegistry(Base):
    """The spec vocabulary, read by BOTH the CRM ranker and the n8n parser.

    One source of truth on purpose. If the parser held its own copy, the two would
    drift the first time a value was renamed, and the drift is silent: the parser
    emits a value the ranker never matches, every query scores worse, and nothing
    logs an error.
    """

    __tablename__ = "product_spec_registry"

    spec_key = Column(String(64), primary_key=True)
    label = Column(String(150), nullable=False)
    # enum | numeric | boolean. Drives extraction (an enum is matched against
    # allowed_values, a numeric is parsed and compared with tolerance).
    data_type = Column(String(16), nullable=False)
    unit = Column(String(16), nullable=True)
    # Closed vocabulary for enum keys. Empty for `class` and `brand`, which are open
    # and sourced from product_categories: a frozen list there would go stale the
    # moment a category is added.
    allowed_values = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # value -> [customer phrasings]. Customer language is not catalog language: nobody
    # types "stainless_steel", they type "s/steel" or "stainless".
    synonyms = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Empty list means "every class". Otherwise the key is only proposed for the
    # classes listed, so wc_form is never offered for a kitchen sink.
    applies_to_classes = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Conditional gate on ANOTHER spec's value, e.g. diameter only applies when
    # shape is round or square. Ungated, diameter would be proposed for a rectangular
    # product, where it is meaningless.
    applies_when = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Multiplier on this key's contribution to the match score. Hand-tuned against the
    # eval baseline, so the seed must never overwrite it.
    rank_weight = Column(Numeric(6, 3), nullable=False, server_default=text("1.0"))
    # How many catalog codes carried this key when it was seeded. Recorded so a later
    # reviewer can see why a key is weighted low without redoing the measurement.
    measured_coverage = Column(Integer, nullable=True)
    # Hand-flippable. A key with no source yet (bowl_count) ships inactive so the
    # parser never extracts it and the ranker never weights it.
    is_active = Column(Boolean, nullable=False, server_default=text("true"), default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=func.now())
