"""Seed and maintain the Spec Registry.

Ownership is split, and the split is the whole point of this module:

  * the SEED owns vocabulary  - label, type, unit, allowed_values, synonyms, gates.
    These must match what the parser extracts against, so a drifted value is repaired
    on every re-seed rather than preserved.
  * a HUMAN owns calibration  - rank_weight, is_active, the match window, and
    excluded_values. Weights are tuned against the eval baseline and that tuning is the
    only calibration the ranker has, so the seed must never overwrite it.

Scope is the T0 tracer's pilot keys (jayson-odoo/sorento-crm#73). The remaining keys
measured present in the catalog (trap_type, wc_form, rimless, seat_material, ...) land
in T1, and `bowl_count` ships inactive there because nothing in the catalog carries it.

Coverage figures below are measurements taken against the live catalog copy over
11,584 distinct active codes. They are recorded on the row so a later reviewer can see
why a key is weighted the way it is without redoing the work.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product_spec import ProductSpecRegistry, ProductSpecSearchPolicy

# Fields the seed owns. Anything not listed here is left alone once a row exists.
_SEED_OWNED = (
    "label",
    "data_type",
    "unit",
    "allowed_values",
    "synonyms",
    "measured_coverage",
)
# `applies_when` used to be seed-owned. It is CALIBRATION, not vocabulary: which
# classes may carry a key is a merchandising judgement ("bowl count is not only for
# kitchen sinks"), and the n8n parser is not held to it the way it is held to the value
# list. Seed-owned, an edit here was reverted on the next deploy without saying so.
#
# `applies_to_classes` is gone entirely. It was never seeded, never read by anything,
# and never held a value in any row - a column that existed only to be rendered in a
# table header. The scope people were reading in that column was always `applies_when`.

# How close a numeric value must be to count, defaulted from the key's UNIT.
# `(tolerance, decay)`; decay 0 means exact-or-nothing.
#
# The bug this replaces: one module-level `+/- 5` was a millimetre intuition applied to
# every numeric key, so `bowl_count` 1 vs 2 (distance 1) scored a PERFECT match and a
# single-bowl sink outranked real double-bowl sinks for "double bowl kitchen sink".
#
# A count is exact-or-nothing. Millimetres keep the old constants, so dimensions behave
# exactly as before. Add a row here rather than special-casing a key.
_MATCH_DEFAULTS_BY_UNIT: dict[str | None, tuple[float, float]] = {
    "mm": (5.0, 150.0),
    None: (0.0, 0.0),
}


# The ranker's scoring knobs, seeded with the constants they replaced so behaviour on
# day one is unchanged. `discontinued_penalty` is the one genuinely new number: 4,969
# active-but-discontinued products used to rank as if they were live. It is set below
# CLASS_BOOST on purpose - a discontinued product that answers the question still beats
# a live one that does not, it just answers second.
SEARCH_POLICY_SEED: list[dict] = [
    {
        "policy_key": "class_boost",
        "label": "A matching product class is worth",
        "value": 5.0,
        "help_text": "The strongest signal there is - every product has a class.",
    },
    {
        "policy_key": "free_term_boost",
        "label": "Each matching word is worth",
        "value": 1.2,
        "help_text": "Words matched against the product's spec sentence, not its raw description.",
    },
    {
        "policy_key": "numeric_boost",
        "label": "A matching measurement is worth",
        "value": 2.0,
        "help_text": "Scaled by how close it is - see each key's own tolerance.",
    },
    {
        "policy_key": "mismatch_penalty",
        "label": "Contradicting what was asked costs",
        "value": 2.5,
        "help_text": (
            "A floor-standing WC when the customer said wall hung. Smaller than the match "
            "it opposes: this demotes the product, it never removes it."
        ),
    },
    {
        "policy_key": "discontinued_penalty",
        "label": "Being discontinued costs",
        "value": 2.0,
        "help_text": (
            "4,969 discontinued products are still active and still sellable, so this "
            "ranks them below a live equivalent rather than hiding them."
        ),
    },
    {
        "policy_key": "flyer_source_boost",
        "label": "A spec read from the flyer counts extra",
        "value": 1.5,
        "help_text": (
            "A multiplier on the match, not a score of its own. The flyer is the better "
            "source and often the only one: 14 cards say FRAMELESS where 2 descriptions "
            "do, and 9 say MASSAGE JET where none do. Above 1, a product whose flyer "
            "card states the spec beats one whose description merely mentions the word. "
            "Set it to 1 to treat both sources alike."
        ),
    },
    {
        "policy_key": "relevance_floor",
        "label": "Show nothing below a score of",
        "value": 1.5,
        "help_text": (
            "Below this the best match is one weak word hit. The chatbot asks for a code "
            "or a photo instead of offering a guess."
        ),
    },
    {
        "policy_key": "max_candidates",
        "label": "Offer at most this many products",
        "value": 5.0,
        "help_text": "Variants of one model collapse onto the model, so five means five models.",
    },
]


def _rules_from_shipped_tables() -> dict[str, list[dict]]:
    """Today's hardcoded token tables, as rule rows.

    Built FROM the tables rather than retyped, so the seeded rules cannot drift from
    what the engine used to do - a transcription error here would be a silent
    catalog-wide derivation change, and the whole point of this seed is that the first
    run derives identically.

    Imported inside the function: `product_spec_derivation` imports this module.
    """
    from app.services import product_spec_derivation as d

    def contains(table) -> list[dict]:
        return [{"match": "contains", "pattern": token, "value": value} for token, value in table]

    rules: dict[str, list[dict]] = {
        "material": contains(d.MATERIAL_TOKENS),
        "mounting": contains(d.MOUNTING_TOKENS),
        "control_type": contains(d.CONTROL_TOKENS),
        "product_type": contains(d.PRODUCT_TYPE_TOKENS),
        "water_supply": contains(d.WATER_SUPPLY_TOKENS),
        "steel_grade": contains(d.STEEL_GRADE_TOKENS),
        "furniture_type": contains(d.FURNITURE_TOKENS),
        "capacity_litre": [
            {"match": "regex", "pattern": d.CAPACITY_RE.pattern, "capture": 1, "unit": "L"}
        ],
        "power_hp": [
            {"match": "regex", "pattern": d.POWER_HP_RE.pattern, "capture": 1, "unit": "hp"}
        ],
        "is_thermostatic": [
            {"match": "present", "pattern": d.THERMOSTATIC_RE.pattern, "value": True}
        ],
        "has_sliding_rail": [
            {"match": "present", "pattern": d.SLIDING_RAIL_RE.pattern, "value": True}
        ],
        "is_high_basin": [{"match": "present", "pattern": d.HIGH_BASIN_RE.pattern, "value": True}],
        "has_filter": [{"match": "present", "pattern": d.FILTER_TAP_RE.pattern, "value": True}],
        "has_pull_out_shower": [
            {"match": "present", "pattern": d.PULL_OUT_SHOWER_RE.pattern, "value": True}
        ],
        "has_chopping_board": [
            {"match": "present", "pattern": d.CHOPPING_BOARD_RE.pattern, "value": True}
        ],
        "has_dish_rack": [{"match": "present", "pattern": d.DISH_RACK_RE.pattern, "value": True}],
        "no_overflow": [{"match": "present", "pattern": d.NO_OVERFLOW_RE.pattern, "value": True}],
        "has_shower_union": [
            {"match": "present", "pattern": d.SHOWER_UNION_RE.pattern, "value": True}
        ],
        "spray_functions": [
            {"match": "regex", "pattern": d.FUNCTION_COUNT_RE.pattern, "capture": 1}
        ],
        "hose_length": [
            # Captured in metres off the card ("c/w 1.2m"), stored in millimetres like
            # every other length, because that is the unit the ranker compares in.
            {
                "match": "regex",
                "pattern": d.HOSE_LENGTH_RE.pattern,
                "capture": 1,
                "scale": 1000,
                "unit": "mm",
            }
        ],
        "is_frameless": [{"match": "present", "pattern": d.FRAMELESS_RE.pattern, "value": True}],
        "has_led": [{"match": "present", "pattern": d.LED_RE.pattern, "value": True}],
        "is_honeycomb": [{"match": "present", "pattern": d.HONEYCOMB_RE.pattern, "value": True}],
        "is_soft_close": [{"match": "present", "pattern": d.SOFT_CLOSE_RE.pattern, "value": True}],
        "has_diverter": [{"match": "present", "pattern": d.DIVERTER_RE.pattern, "value": True}],
        "is_rimless": [{"match": "present", "pattern": d.RIMLESS_RE.pattern, "value": True}],
        "bar_count": [
            {"match": "contains", "pattern": token, "value": count}
            for token, count in d.BAR_COUNT_TOKENS
        ],
        "spout_type": contains(d.SPOUT_TOKENS),
        "trap_type": contains(d.TRAP_TOKENS),
        "flush_type": contains(d.FLUSH_TOKENS),
        "shape": contains(d.SHAPE_TOKENS),
        "class": [
            {"match": "ends_with", "pattern": token, "value": value}
            for token, value in d.CLASS_TAIL_TOKENS
        ],
        # Finish was code-suffix ONLY, which meant a product whose code carries no
        # suffix had no finish at all. The flyer prints it in words on 500+ cards
        # ("Matt Black" 152, "Gunmetal" 103, "Chrome" 98, "Golden Yellow" 73), so the
        # words go first and the suffix stays as the fallback. Longest first: "MATT
        # BLACK" and "FULL ROSE GOLD" must beat "BLACK" and "GOLD".
        "finish": [
            {"match": "contains", "pattern": token, "value": value}
            for token, value in d.FINISH_WORDS
        ] + [
            {"match": "code_suffix", "pattern": suffix, "value": value}
            for suffix, value in d.FINISH_SUFFIXES.items()
        ],
        "trap_length": [
            {"match": "regex", "pattern": d._TRAP_LENGTH_RE.pattern, "capture": 1, "unit": "mm"}
        ],
        # Was the one key with no rules at all: a hardcoded reader ran it, so the screen
        # said "no rules yet, nothing will ever fill this in" beside 74 products that
        # carried it, and there was no way to change how it was read. Word forms first,
        # then the digit form, which is the order the hardcoded reader used.
        "bowl_count": [
            {"match": "regex", "pattern": rf"\b{word}\s+BOWLS?\b", "value": count}
            for word, count in d.BOWL_WORDS.items()
        ] + [{"match": "regex", "pattern": d._BOWL_DIGIT_RE.pattern, "capture": 1}],
        "is_smart": [{"match": "present", "pattern": d._SMART_WC_RE.pattern, "value": True}],
        # The flyer prints a labelled size the description does not carry:
        # "D: L680xW375xH770mm". 177 of 756 cards state one, and 96 products have no
        # dimension in their own description at all - so without these the size a
        # customer asks for exists on paper and nowhere the ranker can see.
        #
        # Scoped to the flyer because the description's own size is parsed by the
        # measurement block, which also cross-checks the stored columns and flags a
        # round product whose length is really a diameter. These fill the gap; they do
        # not compete with it.
        "dim_length": [
            {"match": "regex", "pattern": r"L\s*(\d+(?:\.\d+)?)\s*[xX*]", "capture": 1,
             "source": "flyer"}
        ],
        "dim_width": [
            {"match": "regex", "pattern": r"W\s*(\d+(?:\.\d+)?)\s*[xX*]", "capture": 1,
             "source": "flyer"}
        ],
        "dim_height": [
            {"match": "regex", "pattern": r"H\s*(\d+(?:\.\d+)?)\s*(?:MM|mm)?", "capture": 1,
             "source": "flyer"}
        ],
        # What the seat cover is made of. Only the flyer says it ("*PP Seat Cover"),
        # and it is a real buying decision: PP is the cheap one, UF the heavy one.
        "seat_material": [
            {"match": "regex", "pattern": r"\bPP\b[^.]*SEAT", "value": "pp", "source": "flyer"},
            {"match": "regex", "pattern": r"\bUF\b[^.]*SEAT", "value": "uf", "source": "flyer"},
            {"match": "regex", "pattern": r"UREA[^.]*SEAT", "value": "uf"},
            {"match": "regex", "pattern": r"DUROPLAST", "value": "duroplast"},
        ],
        "has_drainer": [{"match": "present", "pattern": "DRAINER", "value": True}],
        "has_overflow": [{"match": "present", "pattern": r"OVER\s*FLOW", "value": True}],
        "has_fixing_screw": [
            {"match": "present", "pattern": d._FIXING_SCREW_NOUN, "value": True}
        ],
    }
    return rules


def seed_derivation_rules(db: Session, *, commit: bool = False) -> dict:
    """Give each key its shipped rules, ONCE. An edited row is never overwritten.

    Same ownership split as everything else calibratable here: the seed puts the
    starting point in, and from then on it belongs to whoever tunes it. A re-seed that
    reinstated the shipped list would delete a rule someone added, on deploy, silently.
    """
    shipped = _rules_from_shipped_tables()
    written = 0
    for row in db.query(ProductSpecRegistry).all():
        if row.derivation_rules:
            continue
        rules = shipped.get(row.spec_key)
        if not rules:
            continue
        row.derivation_rules = rules
        written += 1
    db.flush()
    if commit:
        db.commit()
    return {"keys_seeded": written}


def seed_search_policy(db: Session, *, commit: bool = False) -> dict:
    """Create missing policy rows. An existing row is NEVER overwritten - it is tuning."""
    existing = {row.policy_key for row in db.query(ProductSpecSearchPolicy).all()}
    created = 0
    for entry in SEARCH_POLICY_SEED:
        if entry["policy_key"] in existing:
            continue
        db.add(ProductSpecSearchPolicy(**entry))
        created += 1
    db.flush()
    if commit:
        db.commit()
    return {"created": created}


def search_policy(db: Session) -> dict[str, float]:
    """Every scoring knob as a plain dict. Missing rows fall back to the seed."""
    stored = {row.policy_key: float(row.value) for row in db.query(ProductSpecSearchPolicy).all()}
    return {entry["policy_key"]: stored.get(entry["policy_key"], float(entry["value"]))
            for entry in SEARCH_POLICY_SEED}


def default_match_window(unit: str | None) -> tuple[float, float]:
    """(tolerance, decay) for a unit. Unknown units are exact-or-nothing, never guessed."""
    return _MATCH_DEFAULTS_BY_UNIT.get(unit, (0.0, 0.0))

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
        # OTHERS (1,956 products) and NO LOGO (651) are how the catalog records the
        # ABSENCE of a brand. They are real values on real rows, so they cannot be
        # deleted, but they are not something a customer asks for - and offered to the
        # understanding model as options they became its bucket for any word it could
        # not place ("interlignet wc" -> brand OTHERS). Not offered, not accepted.
        "excluded_values": ["OTHERS", "NO LOGO"],
        "measured_coverage": 11584,
        # Rankable, never a filter: every brand in the master is Sorento-sellable.
        "rank_weight": 1.5,
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
        "synonyms": {"_self": ["diameter", "dia", "across"]},
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
        "synonyms": {"_self": ["length", "long"]},
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
        "synonyms": {"_self": ["width", "wide"]},
        "unit": "mm",
        "measured_coverage": 3390,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "dim_height",
        "label": "Height",
        "data_type": "numeric",
        "synonyms": {"_self": ["height", "tall", "high"]},
        "unit": "mm",
        "measured_coverage": 3390,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "depth",
        "label": "Depth",
        "data_type": "numeric",
        "synonyms": {"_self": ["depth", "deep"]},
        "unit": "mm",
        "measured_coverage": 365,
        "rank_weight": 1.0,
    },
    {
        "spec_key": "thickness",
        "label": "Thickness",
        "data_type": "numeric",
        "synonyms": {"_self": ["thickness", "thick", "gauge"]},
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
        "allowed_values": ["stainless_steel", "ceramic", "glass", "pvc", "brass", "acrylic", "abs", "nanograin", "granite"],
        "synonyms": {
            "stainless_steel": ["stainless", "stainless steel", "s/steel", "steel", "inox"],
            "ceramic": ["ceramic", "porcelain"],
            "glass": ["glass", "tempered glass"],
            "pvc": ["pvc", "plastic"],
            "abs": ["abs", "abs plastic"],
            "nanograin": ["nanograin", "nano grain", "nano"],
            "granite": ["granite", "granite stone", "quartz"],
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
            "concealed",
            "counter_top",
            "semi_recessed",
            "exposed",
        ],
        "synonyms": {
            "wall_hung": ["wall hung", "wall mounted", "wall mount", "hang on wall"],
            "floor_standing": ["floor standing", "floor mounted", "free standing"],
            "pedestal": ["pedestal", "with pedestal"],
            "concealed": ["concealed", "hidden", "in wall"],
            "counter_top": ["counter top", "countertop", "above counter", "on counter", "top mount", "table top", "tabletop"],
            "under_counter": ["under counter", "undermount", "under mount", "below counter"],
            # 383 taps say PILLAR MOUNTED and 220 more just say PILLAR. In this catalog
            # the word always describes where the tap is fixed, which is why it moved
            # out of control_type.
            "semi_recessed": ["semi recessed", "semi-recessed", "half recessed"],
            "exposed": ["exposed", "exposed shower", "surface mounted"],
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
            # 73 flyer cards. Distinct from french_gold in Sorento's own range, and
            # nothing else mapped to it, so a customer asking for it got nothing.
            "golden_yellow",
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
            "golden_yellow": ["golden yellow", "gold yellow", "yellow gold"],
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
            # The flyer's own aisles. Each of these was already in the catalog under a
            # class so broad it could not answer for them: "double towel bar" and
            # "paper holder" were both simply Bathroom Accessory.
            "pop_up_waste",
            "towel_bar",
            "towel_shelf",
            "hook_bar",
            "robe_hook",
            "corner_basket",
            "paper_holder",
            "grab_bar",
            "soap_dispenser",
            "flexible_hose",
            "flush_valve",
            "floor_trap",
            "floor_grating",
            "cistern",
            "tumbler",
            "mirror",
            "bidet",
            # Nouns the flyer sells by name that derived to nothing at all.
            "toilet_seat",
            "urinal",
            "toilet_brush",
            "squatting_pan",
            "towel_ring",
            "dustbin",
            "bottle_trap",
            "water_pump",
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
            "pop_up_waste": ["pop up waste", "popup waste", "pop-up waste", "waste cover"],
            "towel_bar": ["towel bar", "towel rack", "towel rail", "penyangkut tuala"],
            "towel_shelf": ["towel shelf", "shelf"],
            "hook_bar": ["hook bar", "hanger bar"],
            "robe_hook": ["robe hook", "hook", "coat hook"],
            "corner_basket": ["corner basket", "corner rack", "corner shelf"],
            "paper_holder": ["paper holder", "toilet roll holder", "tissue holder"],
            "grab_bar": ["grab bar", "handrail", "safety bar"],
            "soap_dispenser": ["soap dispenser", "soap holder", "soap dish"],
            "flexible_hose": ["flexible hose", "flexi hose", "connector hose", "hose"],
            "flush_valve": ["flush valve", "flushing valve"],
            "floor_trap": ["floor trap", "floor waste"],
            "floor_grating": ["floor grating", "grating", "floor drain"],
            "cistern": ["cistern", "flush tank", "water tank"],
            "tumbler": ["tumbler", "toothbrush holder"],
            "mirror": ["mirror", "led mirror", "bathroom mirror"],
            "bidet": ["bidet", "hand bidet", "bidet spray", "shattaf", "jet spray"],
            "toilet_seat": ["toilet seat", "seat cover", "wc seat", "seat and cover"],
            "urinal": ["urinal", "urinal bowl"],
            "toilet_brush": ["toilet brush", "brush holder", "wc brush"],
            "squatting_pan": ["squatting pan", "squat pan", "jamban cangkung"],
            "towel_ring": ["towel ring", "ring towel holder"],
            "dustbin": ["dustbin", "waste bin", "rubbish bin", "tong sampah"],
            "bottle_trap": ["bottle trap", "basin trap"],
            "water_pump": ["water pump", "pressure pump", "booster pump", "pam air"],
        },
        "measured_coverage": 5075,
        "rank_weight": 3.0,
    },
    {
        "spec_key": "water_supply",
        "label": "Water supply",
        "data_type": "enum",
        # Cold-only or hot-and-cold. The first question a salesperson asks about a tap
        # and the commonest phrase on the flyer (878 descriptions say COLD TAP), yet
        # nothing in the registry could express it: a cold tap and a mixer both derived
        # to product_type=basin_tap and scored identically for "basin mixer tap".
        "allowed_values": ["cold_only", "mixer"],
        "synonyms": {
            "cold_only": ["cold tap", "cold only", "single cold", "cold water tap"],
            "mixer": ["mixer", "mixer tap", "hot and cold", "hot cold", "mixer type"],
        },
        "measured_coverage": 1226,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "is_rimless",
        "label": "Rimless",
        "data_type": "boolean",
        # Printed on the flyer as its own selling point and asked for by name. Scoped to
        # the pan classes: "rimless" said of a tap is not a fact about the tap.
        "applies_when": {"class": ["Water Closet", "Urinal", "Squatting Pan"]},
        "synonyms": {"true": ["rimless", "rim less", "no rim"]},
        "measured_coverage": 337,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "bar_count",
        "label": "Number of bars",
        "data_type": "numeric",
        # Single or double towel bar. The same shape as bowl_count, and for the same
        # reason: the flyer prints them as separate products and the customer says the
        # number, so without it "double towel bar" scored a single bar just as highly.
        "synonyms": {
            "_self": ["bar", "bars"],
            "1": ["single towel bar", "single bar", "one bar"],
            "2": ["double towel bar", "double bar", "two bar", "twin bar"],
        },
        "measured_coverage": 264,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "furniture_type",
        "label": "Furniture type",
        "data_type": "enum",
        # 990 cabinets all derived to class "Bathroom Furniture" and nothing else, so a
        # basin cabinet and a mirror cabinet were the same product to the ranker. The
        # flyer names them apart on every card.
        # No mirror_cabinet here: product_type already answers for it, and holding one
        # fact in two keys lets a mirror cabinet score the same thing twice.
        "allowed_values": ["basin_cabinet", "side_cabinet", "tall_cabinet"],
        "synonyms": {
            "basin_cabinet": ["basin cabinet", "vanity", "vanity cabinet", "under basin cabinet"],
            "side_cabinet": ["side cabinet", "storage cabinet"],
            "tall_cabinet": ["tall cabinet", "tall unit", "column cabinet"],
        },
        "measured_coverage": 595,
        "rank_weight": 3.0,
    },
    {
        "spec_key": "is_thermostatic",
        "label": "Thermostatic",
        "data_type": "boolean",
        "synonyms": {"true": ["thermostatic", "temperature control", "constant temperature"]},
        "measured_coverage": 44,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "has_sliding_rail",
        "label": "Sliding rail",
        "data_type": "boolean",
        # "Sliding" in this catalogue always means a height-adjustable shower rail.
        "synonyms": {"true": ["sliding", "sliding bar", "sliding rail", "adjustable rail"]},
        "measured_coverage": 148,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "is_high_basin",
        "label": "High basin",
        "data_type": "boolean",
        "synonyms": {"true": ["high basin", "tall basin", "vessel height", "high rise"]},
        "measured_coverage": 100,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "has_filter",
        "label": "Water filter",
        "data_type": "boolean",
        "synonyms": {"true": ["filter tap", "filter", "with filter", "water filter"]},
        "measured_coverage": 64,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "has_pull_out_shower",
        "label": "Pull-out shower",
        "data_type": "boolean",
        "synonyms": {"true": ["pull out shower", "pull-out shower", "pull out spray"]},
        "measured_coverage": 40,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "has_chopping_board",
        "label": "Chopping board",
        "data_type": "boolean",
        # What the flyer sells the multifunction sinks on.
        "synonyms": {"true": ["chopping board", "cutting board", "with board"]},
        "measured_coverage": 36,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "has_dish_rack",
        "label": "Dish rack",
        "data_type": "boolean",
        "synonyms": {"true": ["dish rack", "drying rack", "with rack"]},
        "measured_coverage": 38,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "no_overflow",
        "label": "Without overflow",
        "data_type": "boolean",
        # The opposite of has_overflow, and stated on its own: a basin sold WITHOUT one
        # is a different product, not a product missing a fact.
        "synonyms": {"true": ["without overflow", "no overflow", "w/o overflow"]},
        "measured_coverage": 40,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "has_shower_union",
        "label": "Shower union",
        "data_type": "boolean",
        "synonyms": {"true": ["shower union", "union", "wall union"]},
        "measured_coverage": 54,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "steel_grade",
        "label": "Steel grade",
        "data_type": "enum",
        # 304 vs 201 is the first thing a kitchen-sink buyer asks and the biggest price
        # difference on the page. 705 descriptions say 304, 137 say 201, and the flyer
        # prints "S/Steel 304" 218 times - it was simply not askable before.
        "allowed_values": ["304", "201"],
        "synonyms": {
            "304": ["304", "sus304", "grade 304", "s/steel 304", "stainless steel 304"],
            "201": ["201", "sus201", "grade 201", "s/steel 201"],
        },
        "measured_coverage": 842,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "spray_functions",
        "label": "Spray functions",
        "data_type": "numeric",
        # "3 function shower" is how the flyer sells it (36 cards) and how a customer
        # asks. A count, so exact-or-nothing - a 2-function head does not nearly satisfy
        # someone who asked for 3.
        "synonyms": {
            "_self": ["function", "functions", "spray", "mode", "modes", "setting"],
            "1": ["single function", "1 function", "one function"],
            "2": ["2 function", "two function", "double function"],
            "3": ["3 function", "three function", "triple function"],
            "5": ["5 function", "five function"],
        },
        "measured_coverage": 349,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "hose_length",
        "label": "Hose length",
        "data_type": "numeric",
        "unit": "mm",
        # The hand-bidet hose the flyer prints as "c/w 1.2m" on 41 cards. Customers ask
        # because it decides whether the spray reaches, and 189 descriptions carry it.
        "synonyms": {"_self": ["hose", "hose length", "pipe", "tube"]},
        "measured_coverage": 237,
        "rank_weight": 2.0,
        # Millimetres, but a hose is not a cabinet: 100mm either side is what "about
        # 1.2m" means to a customer, and nothing beyond half a metre is the same hose.
        "match_tolerance": 100.0,
        "match_decay": 500.0,
    },
    {
        "spec_key": "capacity_litre",
        "label": "Capacity",
        "data_type": "numeric",
        "unit": "L",
        # The flyer's page 16 sells dustbins as 8 litre and 12 litre and nothing read it.
        "synonyms": {"_self": ["litre", "liter", "capacity", "volume", "size in litre"]},
        "measured_coverage": 74,
        "rank_weight": 2.5,
        # A litre either side is the same bin to a customer; five litres is not.
        "match_tolerance": 1.0,
        "match_decay": 5.0,
    },
    {
        "spec_key": "power_hp",
        "label": "Power",
        "data_type": "numeric",
        "unit": "hp",
        "synonyms": {"_self": ["horsepower", "hp", "power", "motor"]},
        "measured_coverage": 48,
        "rank_weight": 2.5,
        "match_tolerance": 0.1,
        "match_decay": 0.5,
    },
    {
        "spec_key": "is_frameless",
        "label": "Frameless",
        "data_type": "boolean",
        # The clearest case for reading the flyer over the description: 14 flyer cards
        # say FRAMELESS and only 2 descriptions do.
        "synonyms": {"true": ["frameless", "frame less", "no frame", "borderless"]},
        "measured_coverage": 16,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "has_led",
        "label": "LED light",
        "data_type": "boolean",
        "synonyms": {"true": ["led", "led light", "lighted", "illuminated", "with light"]},
        # 84, NOT the 1,148 a `LIKE '%LED%'` first reported: that substring also matches
        # CONCEALED and CLOSE-COUPLED. Every count in this file is a word-boundary match.
        "measured_coverage": 84,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "is_honeycomb",
        "label": "Honeycomb structure",
        "data_type": "boolean",
        # The flyer gives page 7's bathroom furniture its own name and sells on it; 154
        # descriptions carry it.
        "synonyms": {"true": ["honeycomb", "honey comb", "honeycomb structure"]},
        "measured_coverage": 154,
        "rank_weight": 2.5,
    },
    {
        "spec_key": "is_soft_close",
        "label": "Soft close",
        "data_type": "boolean",
        "synonyms": {"true": ["soft close", "soft closing", "slow close", "damper"]},
        "measured_coverage": 8,
        "rank_weight": 2.0,
    },
    {
        "spec_key": "has_diverter",
        "label": "Diverter",
        "data_type": "boolean",
        "synonyms": {"true": ["diverter", "with diverter", "divertor"]},
        "measured_coverage": 37,
        "rank_weight": 1.5,
    },
    {
        "spec_key": "spout_type",
        "label": "Spout",
        "data_type": "enum",
        "allowed_values": ["flexible", "double_flexible", "pull_out", "swivel", "gooseneck", "waterfall"],
        "synonyms": {
            "flexible": ["flexible", "flexible head", "flexi", "bendable", "hose spout"],
            "double_flexible": ["double flexible", "double spout"],
            "pull_out": ["pull out", "pull-out", "extendable", "pull down"],
            "swivel": ["swivel", "rotating", "turnable"],
            "gooseneck": ["gooseneck", "goose neck", "high arc"],
            "waterfall": ["waterfall", "water fall", "cascade"],
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
        "synonyms": {"_self": ["trap"]},
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
            "_self": ["bowl", "bowls"],
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
        "spec_key": "seat_material",
        "label": "Seat cover material",
        "data_type": "enum",
        "allowed_values": ["pp", "uf", "duroplast"],
        # Only the flyer states it, on 25 cards (PP 13, UF 12). Low coverage, high
        # decisiveness: someone asking for a UF seat is refusing a PP one, so where the
        # catalog says it, it settles the answer.
        "synonyms": {
            "pp": ["pp", "pp seat", "pp seat cover", "polypropylene", "plastic seat"],
            "uf": ["uf", "uf seat", "uf seat cover", "urea", "urea formaldehyde"],
            "duroplast": ["duroplast", "duroplast seat", "soft close seat"],
        },
        "applies_when": {"class": ["Water Closet"]},
        "measured_coverage": 25,
        "rank_weight": 2.5,
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
            # Calibration is set ONCE, at creation, then belongs to whoever tunes it.
            # An explicit value in the seed entry wins over the unit default, so a key
            # that needs an unusual window can say so without inventing a new unit.
            tolerance, decay = default_match_window(entry.get("unit"))
            db.add(
                ProductSpecRegistry(
                    spec_key=key,
                    rank_weight=entry.get("rank_weight", 1.0),
                    excluded_values=entry.get("excluded_values", []),
                    is_active=entry.get("is_active", True),
                    match_tolerance=entry.get("match_tolerance", tolerance),
                    match_decay=entry.get("match_decay", decay),
                    **values,
                )
            )
            created += 1
            continue

        # A row a human took ownership of is never repaired. The anti-drift guarantee
        # only applies to vocabulary this file shipped; overwriting someone's edit on
        # every deploy would make the UI a lie.
        if (row.source or "seed") != "seed":
            continue

        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True

        # New SHIPPED rules are appended; existing rules are never touched or reordered.
        #
        # Without this, shipped vocabulary could never reach an install again. Migration
        # 311i materialised every key's rules into the column, and `configured_rules`
        # prefers the column over the shipped table — so adding 17 product types to the
        # table moved the value list and changed nothing about what gets derived. The
        # symptom is the worst kind: the screen lists `bidet` as a value, the catalogue
        # has 715 bidets, and not one of them carries it.
        #
        # Appending is safe for first-match-wins because a new token is by definition
        # not matched by the existing rules; anything needing to sit ABOVE an existing
        # rule (a longer phrase beating a shorter one) has to be ordered by hand, which
        # is what the rule editor is for.
        shipped_for_key = _rules_from_shipped_tables().get(key) or []
        if shipped_for_key:
            stored_rules = list(row.derivation_rules or [])
            seen = {
                (str(r.get("match")), str(r.get("pattern")), str(r.get("value")))
                for r in stored_rules
            }
            missing = [
                r
                for r in shipped_for_key
                if (str(r.get("match")), str(r.get("pattern")), str(r.get("value"))) not in seen
            ]
            if missing and stored_rules:
                row.derivation_rules = stored_rules + missing
                changed = True

        if changed:
            updated += 1

    db.flush()
    if commit:
        db.commit()

    return {"created": created, "updated": updated}


def merged_allowed_values(row: ProductSpecRegistry) -> list:
    """The shipped values plus the ones staff added, minus the ones they took away.

    Suppression is applied LAST and matches on the exact stored value, so taking a
    shipped value away and adding one back under the same name both work, in either
    order — the same bargain `merged_synonyms` strikes for words.
    """
    merged = list(row.allowed_values or [])
    for value in row.user_values or []:
        if value not in merged:
            merged.append(value)
    dropped = {str(v).strip() for v in (row.suppressed_values or [])}
    return [v for v in merged if str(v).strip() not in dropped]


def merged_synonyms(row: ProductSpecRegistry) -> dict:
    """Seed synonyms with the staff-added ones folded in, per value.

    Additions are additive: a word added here can never remove one the n8n parser is
    relying on. Removals are explicit and separate — `suppressed_synonyms` says "this
    business does not use that word for that value", which is what "matte black" needed:
    it ships as a word for `black`, and while it is bound there it cannot mean a colour
    of its own however many values you add.

    Suppression is applied LAST, so suppressing a word the seed ships and adding it back
    under another value both work, in either order.
    """
    merged = {value: list(words) for value, words in (row.synonyms or {}).items()}
    for value, words in (row.user_synonyms or {}).items():
        existing = merged.setdefault(value, [])
        for word in words:
            if word not in existing:
                existing.append(word)
    for value, words in (row.suppressed_synonyms or {}).items():
        if value not in merged:
            continue
        dropped = {str(w).strip().lower() for w in words}
        merged[value] = [w for w in merged[value] if str(w).strip().lower() not in dropped]
    return merged


def shipped_scopes() -> dict[str, dict]:
    """`applies_when` as the seed declares it, for a caller with no database."""
    return {
        entry["spec_key"]: entry["applies_when"]
        for entry in SPEC_REGISTRY_SEED
        if entry.get("applies_when")
    }


def configured_scopes(db: Session) -> dict[str, dict]:
    """Which products each key applies to, as configured.

    Reads EVERY row for the same reason `configured_rules` does: `is_active` says
    whether the key is searched, not which products may legitimately carry it.
    """
    scopes = shipped_scopes()
    for row in db.query(ProductSpecRegistry).all():
        # An explicit empty gate is a real answer - "this applies to everything" - so it
        # overwrites the seed's rather than falling through to it.
        scopes[row.spec_key] = row.applies_when or {}
    return {key: gate for key, gate in scopes.items() if gate}


def active_registry(db: Session) -> list[ProductSpecRegistry]:
    """Active keys only, ordered stably so a cached render is byte-comparable.

    Returns live ORM rows, deliberately unmodified: callers that need the customer
    vocabulary must go through `merged_synonyms(row)`. Folding the merge in here would
    mean mutating a tracked object on a read path, where a single stray autoflush would
    write the merged result back over the seed-owned column and quietly destroy the
    distinction this table just gained.
    """
    return (
        db.query(ProductSpecRegistry)
        .filter(ProductSpecRegistry.is_active.is_(True))
        .order_by(ProductSpecRegistry.spec_key)
        .all()
    )
