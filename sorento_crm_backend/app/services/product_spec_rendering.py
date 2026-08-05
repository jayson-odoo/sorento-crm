"""Render spec values as the one sentence spec search is allowed to match.

Product resolution is code-only by design (`entity_resolver.py:2945`): a description
cross-reference like "USED FOR SRTWC6015-RL-UF" must not resolve that row for token
SRTWC6015. Spec search does not loosen that rule, it routes around it. The searchable
text is built from spec VALUES and never from `products.description`, so a foreign code
cannot enter the index in the first place.

The code stripper below is the last line of defence rather than the first. Derivation
should never emit a code as a value, but a renderer that depends on that holding is one
bad mapping away from reintroducing the exact bug the code-only rule exists to prevent.

Reads as language, not as a key dump, because it is embedded: "Sorento kitchen sink.
Stainless steel. Wall mounted." sits in the same space as a customer saying "stainless
steel kitchen sink, wall mounted", where "class=Kitchen Sink|material=stainless_steel"
does not.
"""
from __future__ import annotations

import re

# Shapes a Sorento product code takes. Anchored on a letter-then-digits run so a bare
# measurement ("1000", "1.2") is never mistaken for a code and stripped out of a
# dimension phrase.
CODE_SHAPES: tuple[str, ...] = (
    r"\b[A-Z]{2,}[0-9]{3,}[A-Z0-9-]*\b",   # SRTKS4028B, CKS1050-BL, BRC2112UWP-S
    r"\bACC-[A-Z0-9-]+\b",                 # ACC-CB8002-HN
    r"\b[0-9]+MM-[A-Z]+\b",                # 40MM-TAIL
)

# value -> the words a person would use. Keys absent here fall back to a de-underscored
# form, so a new registry value degrades to readable text rather than disappearing.
_PHRASES: dict[str, dict[str, str]] = {
    "material": {
        "stainless_steel": "Stainless steel",
        "ceramic": "Ceramic",
        "glass": "Glass",
        "pvc": "PVC",
        "brass": "Brass",
        "acrylic": "Acrylic",
    },
    "mounting": {
        "wall_hung": "Wall mounted",
        "floor_standing": "Floor standing",
        "pedestal": "With pedestal",
        "concealed": "Concealed",
        "counter_top": "Counter top",
        "under_counter": "Under counter",
        "pillar_mounted": "Pillar mounted",
    },
    "control_type": {
        "single_lever": "Single lever",
        "two_way": "Two way",
        "self_closing": "Self closing",
        "sensor": "Sensor operated",
    },
    "product_type": {
        "angle_valve": "Angle valve",
        "bib_tap": "Bib tap",
        "basin_tap": "Basin tap",
        "kitchen_tap": "Kitchen tap",
        "shower_tap": "Shower tap",
        "mixer_tap": "Mixer tap",
        "hand_shower": "Hand shower",
        "rain_shower": "Rain shower",
        "shower_set": "Shower set",
        "shower_head": "Shower head",
        "close_coupled": "Close coupled",
        "one_piece": "One piece",
        "art_basin": "Art basin",
        "mirror_cabinet": "Mirror cabinet",
    },
    "spout_type": {
        "flexible": "Flexible spout",
        "double_flexible": "Double flexible spout",
        "pull_out": "Pull out spout",
        "swivel": "Swivel spout",
        "gooseneck": "Gooseneck spout",
    },
    "trap_type": {
        "s_trap": "S-trap, floor outlet",
        "p_trap": "P-trap, wall outlet",
    },
    "flush_type": {
        "washdown": "Washdown flush",
        "siphonic": "Siphonic flush",
        "twister": "Twister flush",
    },
    "shape": {
        "round": "Round",
        "square": "Square",
        "rectangular": "Rectangular",
        "oval": "Oval",
    },
    "finish": {
        "black": "Black finish",
        "gunmetal": "Gunmetal finish",
        "nickel": "Nickel finish",
        "grey": "Grey finish",
        "rose_gold": "Rose gold finish",
        "chrome": "Chrome finish",
        "french_gold": "French gold finish",
        "white": "White finish",
        "satin_chrome": "Satin chrome finish",
    },
}


def strip_codes(text: str) -> str:
    """Remove anything code-shaped, then tidy the whitespace it leaves behind."""
    for pattern in CODE_SHAPES:
        text = re.sub(pattern, " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _plain(value) -> str:
    return str(value).replace("_", " ").strip()


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _phrase(key: str, value) -> str:
    table = _PHRASES.get(key, {})
    return table.get(str(value), _plain(value).capitalize())


def render_spec_sentence(values: dict) -> str | None:
    """The embeddable sentence for one product, or None when there is nothing to say.

    Returning None matters: an empty sentence embeds to a vector that sits near
    everything, so a product with no specs would surface for every query.
    """
    if not values:
        return None

    def read(key):
        entry = values.get(key)
        return entry.get("value") if isinstance(entry, dict) else None

    parts: list[str] = []

    # Lead with what the customer leads with: the brand and the thing itself.
    brand, class_label = read("brand"), read("class")
    if class_label:
        head = f"{brand} {str(class_label).lower()}" if brand else str(class_label)
        parts.append(head)
    elif brand:
        parts.append(str(brand))

    # The bowl count and "intelligent" lead the features: both are decisive, rejecting
    # ones a customer states first rather than a nice-to-have they'd compromise on.
    bowls = read("bowl_count")
    if bowls is not None:
        word = {1: "Single bowl", 2: "Double bowl", 3: "Triple bowl"}.get(int(bowls))
        parts.append(word or f"{_number(bowls)} bowls")

    if read("is_smart") is True:
        parts.append("Intelligent toilet")

    for key in ("product_type", "material", "shape", "mounting", "spout_type",
                "control_type", "trap_type", "flush_type", "finish"):
        value = read(key)
        if value is not None:
            parts.append(_phrase(key, value))

    trap_length = read("trap_length")
    if trap_length is not None:
        parts.append(f"{_number(trap_length)} mm trap")

    if read("has_drainer") is True:
        parts.append("With drainer board")
    if read("has_overflow") is True:
        parts.append("With overflow")
    if read("has_fixing_screw") is True:
        parts.append("With fixing screw")

    # Dimensions, shape-aware. A round product has a diameter, and rendering it as
    # "407 x 120" would put a diameter in the width slot of the index.
    diameter = read("diameter")
    if diameter is not None:
        parts.append(f"{_number(diameter)} mm diameter")
        depth = read("depth")
        if depth is not None:
            parts.append(f"{_number(depth)} mm deep")
    else:
        triple = [read(k) for k in ("dim_length", "dim_width", "dim_height")]
        present = [_number(v) for v in triple if v is not None]
        if len(present) >= 2:
            parts.append(f"{' x '.join(present)} mm")

    thickness = read("thickness")
    if thickness is not None:
        parts.append(f"{_number(thickness)} mm thick")

    if read("is_accessory") is True:
        parts.append("Accessory or spare part")

    if not parts:
        return None

    sentence = ". ".join(part.strip().rstrip(".") for part in parts if part) + "."
    sentence = strip_codes(sentence)
    # Stripping can leave an empty shell ("..") if every part was code-shaped.
    if not re.search(r"[A-Za-z0-9]", sentence):
        return None
    return re.sub(r"\s+\.", ".", re.sub(r"\.{2,}", ".", sentence)).strip()
