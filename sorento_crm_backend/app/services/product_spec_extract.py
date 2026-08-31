"""Turn a pasted piece of text into PROPOSALS about one product. Writes no spec data.

Nothing about the product is written here (AC-B.1). The one row that IS written, and
only when a model answered, is the `AIAssistantUsageLog` the model call books against
itself - telemetry about the call, not a claim about the product.

Journey B: a merchandiser holds a flyer card or a supplier's paragraph, pastes it, and
gets back a short list they can accept or reject. The list is short because anything the
text merely restates is dropped entirely - a flyer repeats most of what the description
already produced, and fifteen rows of which two matter is a list nobody reads.

Two engines, one answer:

  * the rule pass (`propose_from_text`), which is the flyer-tuned knowledge lifted out of
    derivation. Always run, deterministic, free.
  * the model (`extract_specs_from_text`), run when one is reachable, adding keys the
    rules did not fire. When it is not reachable the response says so and the rule pass
    stands alone (AC-B.5) rather than the user getting a 502.

Both go through the same registry validation and the same `_apply_scope` gate derivation
uses, so neither can propose invented vocabulary or a key this product's class cannot
carry (AC-B.4).

**`kind` is computed here, not in the frontend** (AC-B.3), so milestone 2's supplier
review reads the same semantics byte for byte.

Plan: `PLAN-spec-authoring-verification.md` (PR 4). UAC: AC-B.1 to AC-B.5.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_spec import ProductSpecifications
from app.services.product_spec_derivation import (
    _apply_scope,
    _Derivation,
    configured_rules,
    configured_scopes,
    description_first_keys,
    propose_from_text,
)
from app.services.product_spec_understanding import (
    _validated_pairs,
    _vocabulary,
    extract_specs_from_text,
)
from app.services.product_spec_write import AUTHORED_SOURCES, _canonical_entry

# The longest text this reads. Not a truncation: over it the request is refused with a
# message, because silently reading half a document and proposing from it is worse than
# saying no (AC-B.2).
MAX_TEXT_LENGTH = 8000


def classify_spec_proposal(
    proposed_entry: dict,
    stored_entry,
    stored_stamp: dict | None,
    key: str,
) -> str:
    """How one proposed value stands against what the product holds today.

    ``"suppressed" | "unchanged" | "conflict" | "new" | "change"``, decided in that
    order of precedence. Lifted out of ``extract_spec_proposals`` rather than copied
    into the flyer batch, because the two surfaces MUST agree: a merchandiser reading
    a pasted card and a merchandiser reading a flyer batch are being told the same
    thing about the same product, and two copies of this table would disagree the
    first time either moved.

    ``proposed_entry`` and ``stored_entry`` are entries as ``values`` stores them
    (``{"value": ..., "unit": ...}``), so the comparison is the write choke point's
    own canonical one - 407 and "407" are the same value, and a re-ordered list of
    features is not an edit anybody made. ``stored_stamp`` is the matching
    ``provenance`` entry, which is where a tombstone lives.

    The two callers differ only in what they do with the answer, never in the answer:
    ``extract_spec_proposals`` folds ``suppressed`` into ``conflict`` and drops
    ``unchanged``; the flyer batch stores every kind and renders the last two
    read-only (AC-A.3).
    """
    stamp = stored_stamp or {}

    # A tombstone is a person's statement that this product does NOT carry the key,
    # so it holds provenance and no value. It is never a gap to fill.
    if stamp.get("absent"):
        return "suppressed"

    if stored_entry is not None and _canonical_entry(proposed_entry) == _canonical_entry(
        stored_entry
    ):
        return "unchanged"

    if stamp.get("source") in AUTHORED_SOURCES:
        return "conflict"

    if stored_entry is None:
        return "new"

    if key in description_first_keys():
        # The lifted "the description beats the flyer for sizes" rule. It is no
        # longer applied silently inside one derivation, because derivation no
        # longer reads the flyer at all; it survives as a proposal that arrives
        # unticked, which is the same precedence with a person in it.
        #
        # `description_first_keys()` with no argument reads the SHIPPED rules only,
        # cached on first call (#425) - not a live-configured registry, and not
        # re-read per call. A key is description-first when a row in the SHIPPED list
        # reads the product's own record or its own description; a `from_field`/
        # `description` row a merchandiser adds through the editor does not move this
        # set, because this comparison never asks the registry.
        return "conflict"

    return "change"


def extract_spec_proposals(
    db: Session, product: Product, text: str, *, user_id: str | None = None
) -> dict:
    """`{product_code, engine, model, proposals, unchanged}` for one product.

    `user_id` is only ever the actor stamped on the model call's usage-log row, so a
    reading made from the product page is counted beside every other model call. It
    reaches nothing else, and no product data is written here (AC-B.1).
    """
    described, index, open_values = _vocabulary(db)
    scopes_by_key = configured_scopes(db)

    rule_hits = propose_from_text(
        text,
        product.product_code or "",
        rules_by_key=configured_rules(db),
        scopes_by_key=scopes_by_key,
    )
    extraction = extract_specs_from_text(
        db, text, vocabulary=(described, index, open_values), user_id=user_id
    )

    # The rule pass first, so its evidence (the words it matched) wins where both
    # engines read the same key: it can point at the substring, the model quotes.
    raw: list[dict] = []
    evidence: dict[str, str] = {}
    for hit in rule_hits:
        key = hit["spec_key"]
        # A `code`-origin hit was read off the product's own code, not off the pasted
        # text, and derivation already reads the code every run - proposing it here
        # would present something the person never pasted as a reading of what they did.
        if hit.get("origin") == "code":
            continue
        if key in evidence:
            continue
        evidence[key] = hit.get("evidence") or ""
        raw.append({"key": key, "value": hit["value"]})
    for entry in extraction.specs:
        key = entry["key"]
        if key in evidence:
            continue
        evidence[key] = entry.get("evidence") or ""
        raw.append({"key": key, "value": entry["value"]})

    # One validation for both engines, and the one the model half already passed: a key
    # the registry does not define, or a value outside a closed vocabulary, is dropped
    # rather than coerced.
    candidates = _validated_pairs(raw, index, open_values, one_per_key=True)

    spec = (
        db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id == product.id)
        .first()
    )
    stored_values = dict((spec.values if spec else None) or {})
    stored_provenance = dict((spec.provenance if spec else None) or {})

    candidates = _in_scope(candidates, stored_values, stored_provenance, scopes_by_key)

    proposals: list[dict] = []
    unchanged = 0
    for entry in sorted(candidates, key=lambda item: item["key"]):
        key = entry["key"]
        row = index[key]
        stored_entry = stored_values.get(key)
        stored_stamp = stored_provenance.get(key) or {}

        proposed_entry: dict = {"value": entry["value"]}
        if row.unit:
            proposed_entry["unit"] = row.unit

        kind = classify_spec_proposal(proposed_entry, stored_entry, stored_stamp, key)

        # This surface has always dropped what the text merely restates, and has always
        # shown a tombstone as a conflict rather than under a word of its own. Both are
        # kept exactly as they were: the two extra kinds are vocabulary the STORED flyer
        # batch needs, and a caller of this function must not start seeing them.
        if kind == "unchanged":
            unchanged += 1
            continue
        if kind == "suppressed":
            kind = "conflict"

        proposals.append(
            {
                "spec_key": key,
                "label": row.label or key,
                "data_type": row.data_type,
                "value": entry["value"],
                "unit": row.unit or None,
                "evidence": evidence.get(key, ""),
                "kind": kind,
                "stored_value": _entry_field(stored_entry, "value"),
                "stored_unit": _entry_field(stored_entry, "unit"),
                "stored_source": stored_stamp.get("source") or None,
            }
        )

    return {
        "product_code": product.product_code,
        "engine": "semantic" if extraction.source == "semantic" else "deterministic",
        "model": extraction.model if extraction.source == "semantic" else None,
        "proposals": proposals,
        "unchanged": unchanged,
    }


def _entry_field(entry, field: str):
    if isinstance(entry, dict):
        return entry.get(field)
    return entry if field == "value" else None


def _in_scope(
    candidates: list[dict],
    stored_values: dict,
    stored_provenance: dict,
    scopes_by_key: dict[str, dict],
) -> list[dict]:
    """Drop a candidate this product's class cannot carry, using derivation's own gate.

    The gate is evaluated against what the PRODUCT already holds, not against what the
    pasted text says: a flyer card for a toilet seat states nothing about the class, so
    the only honest source of "what is this" is the product's own derived class. That is
    also why `_apply_scope` is reused rather than reimplemented - `applies_when` is
    edited in the registry UI, and a second copy of the gate rules would drift the first
    time somebody did.
    """
    gate = _Derivation()
    gate.values = dict(stored_values)
    gate.provenance = dict(stored_provenance)
    for entry in candidates:
        # `setdefault`, never assignment: a candidate that proposes a GATE key (a
        # pasted card read as naming "Kitchen Sink") must not overwrite the product's
        # own stored class before the gate is evaluated, or it would smuggle its
        # neighbours (bowl_count, applies_when class Kitchen Sink) past a gate that
        # exists to keep them off a Water Closet.
        gate.values.setdefault(entry["key"], {"value": entry["value"]})
        gate.provenance.setdefault(
            entry["key"], {"source": "derived", "confidence": 1.0, "evidence": ""}
        )
    _apply_scope(gate, scopes_by_key)
    return [entry for entry in candidates if entry["key"] in gate.values]
