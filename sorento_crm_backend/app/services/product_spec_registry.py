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
    # `is_accessory` is deliberately NOT a registry row. It is derived and stored on
    # every product (product_spec_derivation.derive) and read directly by the ranker's
    # accessory deboost (product_spec_search.py) — neither of those goes through this
    # registry. A row here would only invite the n8n parser to try extracting "is the
    # customer asking about an accessory" as a spec, which is not a thing a customer
    # states, and it showed up as a bare "is accessory: true" row in the product-facing
    # Specifications tab with no way to explain it. Keep it internal.
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
        "allowed_values": [
            "wall_hung",
            "floor_standing",
            "pedestal",
            "concealed",
            "counter_top",
            "under_counter",
            "pillar_mounted",
        ],
        "synonyms": {
            "wall_hung": ["wall hung", "wall mounted", "wall mount", "hang on wall"],
            "floor_standing": ["floor standing", "floor mounted", "free standing"],
            "pedestal": ["pedestal", "with pedestal"],
            "concealed": ["concealed", "hidden", "in wall"],
            "counter_top": ["counter top", "countertop", "above counter", "on counter", "top mount"],
            "under_counter": ["under counter", "undermount", "under mount", "below counter"],
            # 383 taps say PILLAR MOUNTED and 220 more just say PILLAR. In this catalog
            # the word always describes where the tap is fixed, which is why it moved
            # out of control_type.
            "pillar_mounted": ["pillar mounted", "pillar mount", "pillar tap", "pillar"],
        },
        "measured_coverage": 3289,
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
        # `mixer`, `pillar` and `bib` moved to product_type / mounting: they name the
        # product or where it is fixed, not how the water is controlled, and holding
        # them here let one product score the same fact twice.
        "allowed_values": ["single_lever", "two_way", "self_closing", "sensor"],
        "synonyms": {
            "single_lever": ["single lever", "single handle", "one lever"],
            "two_way": ["two way", "2 way", "dual"],
            "self_closing": ["self closing", "self-closing", "push", "delay action"],
            "sensor": ["sensor", "automatic", "auto", "touchless"],
        },
        "measured_coverage": 201,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "product_type",
        "label": "Type",
        "data_type": "enum",
        # The noun a customer says inside a class. Sits below `class` in weight because
        # it is narrower and less complete, but above the free-text leg: someone asking
        # for a "bib tap" means something specific that a generic tap does not satisfy.
        "allowed_values": [
            "angle_valve",
            "bib_tap",
            "basin_tap",
            "kitchen_tap",
            "shower_tap",
            "mixer_tap",
            "hand_shower",
            "rain_shower",
            "shower_set",
            "shower_head",
            "close_coupled",
            "one_piece",
            "art_basin",
            "mirror_cabinet",
        ],
        "synonyms": {
            "angle_valve": ["angle valve", "stop valve", "corner valve"],
            "bib_tap": ["bib tap", "hose bib", "bib", "garden tap"],
            "basin_tap": ["basin tap", "basin mixer", "wash basin tap"],
            "kitchen_tap": ["kitchen tap", "sink tap", "kitchen sink tap", "paip dapur"],
            "shower_tap": ["shower tap", "shower mixer"],
            "mixer_tap": ["mixer", "mixer tap", "hot and cold tap"],
            "hand_shower": ["hand shower", "handheld shower", "hand held shower"],
            "rain_shower": ["rain shower", "rainfall shower", "overhead shower"],
            "shower_set": ["shower set", "shower kit", "complete shower"],
            "shower_head": ["shower head", "showerhead"],
            "close_coupled": ["close coupled", "close-coupled", "two piece", "coupled"],
            "one_piece": ["one piece", "one-piece", "single piece"],
            "art_basin": ["art basin", "vessel basin", "designer basin"],
            "mirror_cabinet": ["mirror cabinet", "cabinet mirror"],
        },
        "measured_coverage": 5075,
        "rank_weight": 3.0,
    },
    {
        "spec_key": "spout_type",
        "label": "Spout",
        "data_type": "enum",
        "allowed_values": ["flexible", "double_flexible", "pull_out", "swivel", "gooseneck"],
        "synonyms": {
            "flexible": ["flexible", "flexible head", "flexi", "bendable", "hose spout"],
            "double_flexible": ["double flexible", "double spout"],
            "pull_out": ["pull out", "pull-out", "extendable", "pull down"],
            "swivel": ["swivel", "rotating", "turnable"],
            "gooseneck": ["gooseneck", "goose neck", "high arc"],
        },
        "measured_coverage": 641,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "trap_type",
        "label": "Trap",
        "data_type": "enum",
        # The one spec where being wrong means a toilet that cannot be installed: the
        # outlet is either in the floor (S) or the wall (P). Read ONLY where the
        # description says so; the `-P` code-suffix rule needs class gating and is not
        # in this release.
        "allowed_values": ["s_trap", "p_trap"],
        "synonyms": {
            "s_trap": ["s trap", "s-trap", "floor outlet", "floor waste"],
            "p_trap": ["p trap", "p-trap", "wall outlet", "wall waste"],
        },
        "measured_coverage": 1027,
        "rank_weight": 3.0,
    },
    {
        "spec_key": "trap_length",
        "label": "Trap outlet length",
        "data_type": "numeric",
        "unit": "mm",
        # Independent of trap_type: "150mm S-trap" and "300mm S-trap" are different
        # products a customer must not be shown interchangeably. The catalog spells the
        # separator three ways ("S-TRAP 300MM", "S-TRAP:250MM", "S- TRAP 250MM").
        "measured_coverage": 738,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "flush_type",
        "label": "Flush type",
        "data_type": "enum",
        "allowed_values": ["washdown", "siphonic", "twister"],
        "synonyms": {
            "washdown": ["washdown", "wash down", "wash-down"],
            "siphonic": ["siphonic", "syphonic"],
            # TWISTER is Sorento's own branded flush name, not generic language, but a
            # customer repeating a salesperson's or a poster's term still deserves it.
            "twister": ["twister flush", "twister flushing", "twister"],
        },
        "applies_when": {"class": ["Water Closet"]},
        "measured_coverage": 622,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "bowl_count",
        "label": "Number of bowls",
        "data_type": "numeric",
        "applies_when": {"class": ["Kitchen Sink"]},
        # A numeric key with synonyms, because customers say the number in words.
        # Without these "double bowl kitchen sink" only earned a substring hit on the
        # rendered sentence, so a SINGLE bowl sink scored the same and was never
        # demoted - the one distinction the customer actually cared about.
        "synonyms": {
            "1": ["single bowl", "one bowl", "1 bowl", "single sink"],
            "2": ["double bowl", "two bowl", "2 bowl", "twin bowl", "double sink"],
            "3": ["triple bowl", "three bowl", "3 bowl"],
        },
        # 106 of 1,148 kitchen sinks state this. Low coverage is not low value: someone
        # asking for a double bowl will reject every single bowl, so where the catalog
        # says it, it decides the answer. Weighted accordingly, and NULL elsewhere.
        "measured_coverage": 106,
        "rank_weight": 3.0,
    },
    {
        "spec_key": "has_drainer",
        "label": "Has a drainer board",
        "data_type": "boolean",
        "applies_when": {"class": ["Kitchen Sink"]},
        "synonyms": {"true": ["drainer", "with drainer", "drainer board", "drain board"]},
        "measured_coverage": 18,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "has_overflow",
        "label": "Has an overflow",
        "data_type": "boolean",
        "synonyms": {"true": ["overflow", "with overflow", "c/w overflow", "overflow hole"]},
        # 137 write it joined, 5 split ("OVER FLOW") — both read by the same rule.
        "measured_coverage": 142,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "has_fixing_screw",
        "label": "Comes with a fixing screw",
        "data_type": "boolean",
        "synonyms": {"true": ["basin screw", "fixing screw", "c/w screw", "with screw"]},
        "measured_coverage": 29,
        "rank_weight": 1.0,
    },
    {
        "spec_key": "is_smart",
        "label": "Intelligent / smart toilet",
        "data_type": "boolean",
        "applies_when": {"class": ["Water Closet"]},
        "synonyms": {
            "true": ["intelligent toilet", "intelligent", "smart toilet", "smart wc", "auto induction"]
        },
        # Rare (76 of 1,655 WCs) but decisive: a customer asking for one rejects every
        # ordinary WC, so where the catalog states it, it should dominate the result.
        "measured_coverage": 76,
        "rank_weight": 3.0,
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
