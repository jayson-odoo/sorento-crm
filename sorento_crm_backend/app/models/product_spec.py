"""Spec search storage: the vocabulary, and later the values derived against it.

Kept out of `product.py` because this is a separate concern with its own lifecycle:
`product.py` models the catalog as the business maintains it, this models what spec
search derives from it.

See documentation/plans/products/PLAN-spec-search.md section 6.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # How close a NUMERIC value must be to count as a match. These are properties of
    # the quantity, not of the ranker, which is why they live here: one module-level
    # "+/- 5" was a millimetre intuition applied to every numeric key, and it made a
    # one-bowl sink an EXACT match for "double bowl" (1 and 2 are within 5).
    #
    #   match_tolerance : distance still scored as a perfect match
    #   match_decay     : distance at which the score reaches zero. 0 means
    #                     exact-or-nothing, which is what a COUNT needs.
    #
    # Defaulted from `unit` at seed time, then owned by whoever tunes them — the same
    # split as rank_weight.
    match_tolerance = Column(Numeric(10, 3), nullable=False, server_default=text("0"))
    match_decay = Column(Numeric(10, 3), nullable=False, server_default=text("0"))
    # How many catalog codes carried this key when it was seeded. Recorded so a later
    # reviewer can see why a key is weighted low without redoing the measurement.
    measured_coverage = Column(Integer, nullable=True)
    # Hand-flippable. A key with no source yet (bowl_count) ships inactive so the
    # parser never extracts it and the ranker never weights it.
    is_active = Column(Boolean, nullable=False, server_default=text("true"), default=True)
    # `seed` | `user`. The seed REPAIRS drift on every deploy so the CRM ranker and the
    # n8n parser can never disagree about what a value is called — that guarantee is
    # why this table exists. A user-created key has no seed to drift from, so it is
    # never touched. Without the flag, "editable from the UI" and "repaired on deploy"
    # are the same row fighting each other, and the deploy always wins.
    source = Column(String(16), nullable=False, server_default=text("'seed'"))
    # Extra customer phrasings added by staff, merged with (never replacing) the seed's
    # synonyms at read time. Adding a word for a shipped key is the common case and
    # should not require taking ownership of the whole row.
    user_synonyms = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=func.now())


class ProductSpecifications(Base):
    """Derived spec values for one product row.

    Keyed on `product_id`, but derived and reviewed per `product_code`: the same model
    exists once per company (11,414 codes across 22,805 rows), and deriving per row
    would let the two copies disagree with nothing detecting it. One derivation fans
    out to every row sharing the code.
    """

    __tablename__ = "product_specifications"

    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # {"diameter": {"value": 407, "unit": "mm"}, "material": {"value": "ceramic"}}
    values = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Same keys as `values`: {"source", "confidence", "evidence"}. `source='human'`
    # marks a reviewer-confirmed value, which re-derivation must never overwrite.
    provenance = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # The code-free spec sentence that gets embedded. Populated in T0d, not here.
    rendered_text = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, server_default="derived")
    # Hash of the derivation inputs. Equal hash means nothing to do, so a re-run over
    # the whole catalog costs one read per code instead of a rewrite.
    derived_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=func.now())

    __table_args__ = (
        Index("ix_product_specifications_values", "values", postgresql_using="gin"),
        Index("ix_product_specifications_status", "status"),
    )


class ProductSpecException(Base):
    """Something a human needs to look at. Exceptions only, never routine successes.

    If this table fills with successes the filter is wrong, and the queue becomes the
    data-entry programme the design exists to avoid.
    """

    __tablename__ = "product_spec_exceptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_code = Column(String(100), nullable=False)
    spec_key = Column(String(64), nullable=False)
    # shape_mismatch  - stored L/W/H describe a round or square product
    # column_conflict - the description disagrees with a stored column
    # low_confidence  - derived below the review threshold
    reason = Column(String(48), nullable=False)
    proposed = Column(JSONB, nullable=True)
    stored = Column(JSONB, nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolved_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "ix_product_spec_exceptions_open",
            "product_code",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )
