"""Seed and maintain the Spec Registry.

Ownership is split, and the split is the whole point of this module:

  * the SEED owns vocabulary  - label, type, unit, allowed_values, synonyms, gates.
    These must match what the parser extracts against, so a drifted value is repaired
    on every re-seed rather than preserved.
  * a HUMAN owns calibration  - rank_weight and is_active. Weights are tuned against
    the eval baseline and that tuning is the only calibration the ranker has, so the
    seed must never overwrite it.

Scope is the T0 tracer's pilot keys (jayson-odoo/sorento-crm#73). The remaining keys
measured present in the catalog (trap_type, wc_form, rimless, seat_material, ...) land
in T1, and `bowl_count` ships inactive there because nothing in the catalog carries it.

Coverage figures below are measurements taken against the live catalog copy over
11,584 distinct active codes. They are recorded on the row so a later reviewer can see
why a key is weighted the way it is without redoing the work.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product_spec import ProductSpecRegistry

# Fields the seed owns. Anything not listed here is left alone once a row exists.
_SEED_OWNED = (
    "label",
    "data_type",
    "unit",
    "allowed_values",
    "synonyms",
    "applies_to_classes",
    "applies_when",
    "measured_coverage",
)

SPEC_REGISTRY_SEED: list[dict] = [
    {
        "spec_key": "class",
        "label": "Product class",
        "data_type": "enum",
        # Open vocabulary: sourced from product_categories.class_label, which grows.
        "allowed_values": [],
        "synonyms": {},
        # Total coverage (every product has a category) and the highest-precision
        # signal available, so it carries the largest weight in the ranker.
        "measured_coverage": 11584,
        "rank_weight": 5.0,
    },
    {
        "spec_key": "brand",
        "label": "Brand",
        "data_type": "enum",
        "allowed_values": [],
        "synonyms": {},
        "measured_coverage": 11584,
        # Rankable, never a filter: every brand in the master is Sorento-sellable.
        "rank_weight": 1.5,
    },
    {
        "spec_key": "is_accessory",
        "label": "Is an accessory or spare part",
        "data_type": "boolean",
        "measured_coverage": 2302,
        # Zero because this is not a match boost. The ranker applies it as a heavy
        # DEBOOST, so that "kitchen sink" cannot return a sink drainer or a tail pipe.
        "rank_weight": 0.0,
    },
    {
        "spec_key": "shape",
        "label": "Shape",
        "data_type": "enum",
        "allowed_values": ["round", "square", "rectangular", "oval"],
        "synonyms": {
            "round": ["round", "circular"],
            "square": ["square"],
            "rectangular": ["rectangular", "rectangle"],
            "oval": ["oval", "ellipse"],
        },
        "measured_coverage": 365,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "diameter",
        "label": "Diameter",
        "data_type": "numeric",
        "unit": "mm",
        # A rectangular product has no diameter. Ungated this would be proposed for
        # every sink, and the ranker would compare a width against it.
        "applies_when": {"shape": ["round", "square"]},
        "measured_coverage": 365,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "dim_length",
        "label": "Length",
        "data_type": "numeric",
        "unit": "mm",
        # Deliberately NOT gated on shape: shape is unknown for most rows (no ROUND
        # or SQUARE token in the description), and gating would drop every unlabelled
        # rectangular product.
        "measured_coverage": 3390,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "dim_width",
        "label": "Width",
        "data_type": "numeric",
        "unit": "mm",
        "measured_coverage": 3390,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "dim_height",
        "label": "Height",
        "data_type": "numeric",
        "unit": "mm",
        "measured_coverage": 3390,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "depth",
        "label": "Depth",
        "data_type": "numeric",
        "unit": "mm",
        "measured_coverage": 365,
        "rank_weight": 1.0,
    },
    {
        "spec_key": "thickness",
        "label": "Thickness",
        "data_type": "numeric",
        "unit": "mm",
        # Only 136 codes carry the 4th dimension, so it is weighted low: a key that is
        # NULL for 99% of rows must not dominate a score.
        "measured_coverage": 136,
        "rank_weight": 1.0,
    },
    {
        "spec_key": "material",
        "label": "Material",
        "data_type": "enum",
        "allowed_values": ["stainless_steel", "ceramic", "glass", "pvc", "brass", "acrylic"],
        "synonyms": {
            "stainless_steel": ["stainless", "stainless steel", "s/steel", "steel", "inox"],
            "ceramic": ["ceramic", "porcelain"],
            "glass": ["glass", "tempered glass"],
            "pvc": ["pvc", "plastic"],
            "brass": ["brass"],
            "acrylic": ["acrylic"],
        },
        "measured_coverage": 2316,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "mounting",
        "label": "Mounting",
        "data_type": "enum",
        "allowed_values": ["wall_hung", "floor_standing", "pedestal", "concealed", "counter_top"],
        "synonyms": {
            "wall_hung": ["wall hung", "wall mounted", "wall mount", "hang on wall"],
            "floor_standing": ["floor standing", "floor mounted", "free standing"],
            "pedestal": ["pedestal", "with pedestal"],
            "concealed": ["concealed", "hidden", "in wall"],
            "counter_top": ["counter top", "countertop", "above counter", "on counter"],
        },
        "measured_coverage": 1539,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "finish",
        "label": "Finish or colour",
        "data_type": "enum",
        "allowed_values": [
            "black",
            "gunmetal",
            "nickel",
            "grey",
            "rose_gold",
            "chrome",
            "french_gold",
            "white",
            "satin_chrome",
        ],
        "synonyms": {
            "black": ["black", "matt black", "matte black"],
            "gunmetal": ["gunmetal", "gun metal"],
            "nickel": ["nickel", "brushed nickel"],
            "grey": ["grey", "gray"],
            "rose_gold": ["rose gold", "rosegold"],
            "chrome": ["chrome", "polished chrome"],
            "french_gold": ["french gold", "gold"],
            "white": ["white"],
            "satin_chrome": ["satin chrome", "satin"],
        },
        "measured_coverage": 1600,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "control_type",
        "label": "Control type",
        "data_type": "enum",
        "allowed_values": ["mixer", "pillar", "bib", "single_lever"],
        "synonyms": {
            "mixer": ["mixer", "mixer tap"],
            "pillar": ["pillar", "pillar tap"],
            "bib": ["bib", "bib tap", "hose bib"],
            "single_lever": ["single lever", "single handle", "one lever"],
        },
        "measured_coverage": 1804,
        "rank_weight": 1.5,
    },
]

PILOT_SPEC_KEYS: tuple[str, ...] = tuple(entry["spec_key"] for entry in SPEC_REGISTRY_SEED)


def _seed_values(entry: dict) -> dict:
    """Normalise a seed entry into the seed-owned column values."""
    return {
        "label": entry["label"],
        "data_type": entry["data_type"],
        "unit": entry.get("unit"),
        "allowed_values": entry.get("allowed_values", []),
        "synonyms": entry.get("synonyms", {}),
        "applies_to_classes": entry.get("applies_to_classes", []),
        "applies_when": entry.get("applies_when", {}),
        "measured_coverage": entry.get("measured_coverage"),
    }


def seed_spec_registry(db: Session, *, commit: bool = False) -> dict:
    """Create missing registry rows and repair drifted vocabulary on existing ones.

    Idempotent: a re-seed with nothing to fix writes nothing. Runs on every deploy as
    the key set grows, so it must never clobber a hand-tuned `rank_weight` or a
    hand-flipped `is_active` - those are the reviewer's, not the seed's.
    """
    created = 0
    updated = 0

    existing = {row.spec_key: row for row in db.query(ProductSpecRegistry).all()}

    for entry in SPEC_REGISTRY_SEED:
        key = entry["spec_key"]
        values = _seed_values(entry)
        row = existing.get(key)

        if row is None:
            db.add(
                ProductSpecRegistry(
                    spec_key=key,
                    rank_weight=entry.get("rank_weight", 1.0),
                    is_active=entry.get("is_active", True),
                    **values,
                )
            )
            created += 1
            continue

        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
        if changed:
            updated += 1

    db.flush()
    if commit:
        db.commit()

    return {"created": created, "updated": updated}


def active_registry(db: Session) -> list[ProductSpecRegistry]:
    """Active keys only, ordered stably so a cached render is byte-comparable."""
    return (
        db.query(ProductSpecRegistry)
        .filter(ProductSpecRegistry.is_active.is_(True))
        .order_by(ProductSpecRegistry.spec_key)
        .all()
    )
