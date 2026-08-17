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

    # Surrogate uuid PK, per ADR-PRODUCT-STANDARDS: the polymorphic key columns can
    # only be typed uuid if every id is one. `spec_key` stays the key people use - it is
    # unique, it just is not the primary key.
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    spec_key = Column(String(64), nullable=False, unique=True)
    label = Column(String(150), nullable=False)
    # enum | numeric | boolean. Drives extraction (an enum is matched against
    # allowed_values, a numeric is parsed and compared with tolerance).
    data_type = Column(String(16), nullable=False)
    unit = Column(String(16), nullable=True)
    # Closed vocabulary for enum keys. Empty for `class` and `brand`, which are open
    # and sourced from product_categories: a frozen list there would go stale the
    # moment a category is added.
    allowed_values = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Values that EXIST in the catalog but are not things a customer searches for.
    # `brand` holds OTHERS and NO LOGO, which record the absence of a brand; offered to
    # a model as options they read as "none of the above", so any word it could not
    # place got filed under one — "interlignet wc" came back branded OTHERS. Excluded
    # here they are simply not offered, and the unplaceable word stays a free term.
    # A tuning knob, not vocabulary: seeded once, then owned by whoever tunes it.
    excluded_values = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
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
    # Values staff added to a SHIPPED key. Additive and never seed-repaired, exactly as
    # user_synonyms is: `allowed_values` is the parser's contract and an edit there would
    # be reverted on deploy, which left "add the value first" as an instruction nobody
    # could follow. Read merged with allowed_values; see merged_allowed_values().
    user_values = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # {value: [words this business does NOT use for it]}. The mirror of user_synonyms:
    # staff-owned, never seed-repaired, subtracted at read time. Nothing is deleted, so
    # un-suppressing a word puts it straight back.
    suppressed_synonyms = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Shipped VALUES this business has taken away, on the same bargain as the words
    # above: staff-owned, never seed-repaired, subtracted at read time. `user_values`
    # could only ever ADD, so a shipped value was permanent - a business that does not
    # sell french gold had no way to stop the ranker offering it.
    suppressed_values = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # A standing preference for particular VALUES of this key: {"SORENTO": 1.5}. Applied
    # to any product carrying the value, whether or not the customer asked for it, so
    # "our own brand first" is a setting rather than a deploy. NOT applied when the
    # customer named this key themselves - someone who asks for Bravat is asking for
    # Bravat, and a house preference that overrode that would be a bug, not a boost.
    # Calibration, like rank_weight: seeded once, then owned by whoever tunes it.
    value_weights = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # HOW this key is read out of a product's text, as an ordered list of rules. First
    # match wins, so order is priority ("STAINLESS STEEL" must sit above "STEEL").
    #
    #   {"match": "contains",    "pattern": "S/STEEL 304", "value": "stainless_steel"}
    #   {"match": "ends_with",   "pattern": "SQUATTING PAN", "value": "Squatting Pan"}
    #   {"match": "present",     "pattern": "OVER\\s*FLOW", "value": true}
    #   {"match": "regex",       "pattern": "(\\d+)MM S-TRAP", "capture": 1, "unit": "mm"}
    #   {"match": "code_suffix", "pattern": "BL", "value": "black"}
    #
    # Optional "source": "any" (default) | "description" | "flyer". These were Python
    # lists, which meant a key created in the UI could never be populated - the form
    # made a promise the engine could not keep.
    derivation_rules = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=func.now())


class ProductFlyerText(Base):
    """What the printed flyer says about a product code.

    RETIRED AS AN INPUT (PR 4, AC-B.18): derivation no longer reads this table, and a
    flyer reaches specs only as reviewed proposals from pasted text. The table stays
    until the later deploy that drops it (RUNBOOK-flyer-promote.md, step 6), so a
    rollback still has the text. It was a second text source for derivation, keyed on
    the CODE for the same reason derivation is - one card describes the model, and the
    model exists once per company.
    """

    __tablename__ = "product_flyer_text"

    # Surrogate uuid PK, per ADR-PRODUCT-STANDARDS: the polymorphic key columns can
    # only be typed uuid if every id is one. `product_code` stays the key people use - it is
    # unique, it just is not the primary key.
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_code = Column(String(100), nullable=False, unique=True)
    # Which flyer, in words a person recognises ("SORENTO A3 FLYER 2025-2026").
    source_label = Column(String(200), nullable=False)
    source_id = Column(String(64), nullable=True)
    lines = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    text = Column(Text, nullable=False, server_default="")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=func.now())


class ProductSpecSearchPolicy(Base):
    """The ranker's scoring knobs, as data.

    These were module constants, which meant "discontinued products should rank lower"
    needed an engineer. Each row is one number the ranker reads at search time, seeded
    with the constant it replaced so the behaviour on day one is identical.
    """

    __tablename__ = "product_spec_search_policy"

    # Surrogate uuid PK, per ADR-PRODUCT-STANDARDS: the polymorphic key columns can
    # only be typed uuid if every id is one. `policy_key` stays the key people use - it is
    # unique, it just is not the primary key.
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_key = Column(String(64), nullable=False, unique=True)
    label = Column(String(150), nullable=False)
    value = Column(Numeric(10, 3), nullable=False)
    # Shown next to the field. A number with no explanation gets tuned by guesswork.
    help_text = Column(Text, nullable=False, server_default="")
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

    # Surrogate uuid PK, per ADR-PRODUCT-STANDARDS: the polymorphic key columns can
    # only be typed uuid if every id is one. `product_id` stays the key people use - it is
    # unique, it just is not the primary key.
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # {"diameter": {"value": 407, "unit": "mm"}, "material": {"value": "ceramic"}}
    values = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Same keys as `values`: {"source", "confidence", "evidence"}. A source in
    # `product_spec_write.AUTHORED_SOURCES` marks a value a person set, which
    # re-derivation must never overwrite - test membership in that set, never `==
    # 'human'`. An authored entry may also carry `absent: true`, a tombstone saying this
    # product does not have this spec, in which case the key is deliberately NOT in
    # `values`. All three columns are written in `product_spec_write` and nowhere else.
    provenance = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # The code-free spec sentence that gets embedded. Rendered inside
    # `product_spec_write.write_spec_row` so it can never drift from `values`.
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


class ProductFindabilityRun(Base):
    """One sweep of a flyer, asking every card for its own product.

    Persisted rather than printed because the point is comparison: the number after a
    vocabulary change only means something next to the number before it. Keyed on the
    flyer's `source_id`, so the Cabana and Mocha flyers are new rows, not new code.
    """

    __tablename__ = "product_findability_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(64), nullable=True)
    source_label = Column(String(200), nullable=True)
    # A full flyer takes about half an hour, so the sweep runs in the background and
    # this is how the screen knows whether it is watching a total or a work in progress.
    status = Column(String(16), nullable=False, server_default="running")
    error = Column(Text, nullable=True)
    # How deep a result still counts as found.
    window = Column(Integer, nullable=False, server_default=text("25"))
    cards = Column(Integer, nullable=False, server_default=text("0"))
    # Found from the card's own printed words - the angle that catches a missing spec.
    found_by_card = Column(Integer, nullable=False, server_default=text("0"))
    # Found from every spec the flyer states, together. The best case.
    found_by_specs = Column(Integer, nullable=False, server_default=text("0"))
    not_found = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class ProductFindabilityResult(Base):
    """One card, and every way of asking for it."""

    __tablename__ = "product_findability_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_findability_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_code = Column(String(100), nullable=False)
    # A discontinued code losing to the live one that replaced it is the ranker working.
    is_discontinued = Column(Boolean, nullable=False, server_default=text("false"))
    phrase = Column(Text, nullable=False, server_default="")
    # The easiest question that finds it: "one:product_type", "card", "all", or "none".
    boundary = Column(String(64), nullable=False, server_default="none")
    # {"all": 1, "one:finish": null, ...} - every angle and where it landed, so the
    # screen can show WHICH way of asking failed without re-running the sweep.
    ranks = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_findability_results_run", "run_id"),
        Index("ix_findability_results_boundary", "boundary"),
    )
