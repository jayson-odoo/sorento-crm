"""Read specs out of the catalog. Deterministically, or not at all.

There is no inference in this module and that is deliberate. Two mechanisms that
needed it were measured and rejected: curating specs out of the description (bowl count
appears in 110 of 22,366 descriptions), and inducing dimensions from code conventions
(best rule 25.3% against 387 labelled rows, where 99% was required). What is left is
what can be read directly, so every value here is defensible by pointing at the
substring it came from.

Precedence, highest first:

  1. a value a person already set            - a reviewer settled it, never touch it
                                                 (`AUTHORED_SOURCES`, product_spec_write)
  2. the products table's own columns        - curated data outranks parsed text
  3. literal tokens in the description       - shape-gated, see below
  4. a closed code lookup (the finish suffix)
  5. nothing

Rule 5 is not a failure mode. A NULL spec leaves the row to the other ranking legs,
where a guessed one would actively boost a wrong candidate.

SHAPE GATING is the subtle part. `products` has only length/width/height, so a round
basin's diameter has been forced into `length` across the catalog:

    CONCRETE ROUND BASIN (407X120X10MM)  ->  length=407 width=120 height=10
                                              ^ diameter ^ depth  ^ thickness

For a round or square product the stored columns are therefore mis-keyed, not merely
different, so they are NOT trusted for length/width and the row is flagged for a human.
231 codes catalog-wide have length = width, which is the same defect showing up without
the description saying so.

Ticket: jayson-odoo/sorento-crm#74.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.product import Product, ProductCategory
from app.models.product_spec import (
    ProductSpecException,
    ProductSpecifications,
)
from app.services.product_spec_write import (
    authored_keys,
    lock_product_code,
    merge_authored_over,
    write_spec_row,
)

# --------------------------------------------------------------------------- #
# vocabulary, mirroring the Spec Registry's allowed_values
# --------------------------------------------------------------------------- #

# Longest first: "STAINLESS STEEL" must win before "STEEL" matches.
MATERIAL_TOKENS: list[tuple[str, str]] = [
    ("STAINLESS STEEL", "stainless_steel"),
    ("S/STEEL", "stainless_steel"),
    ("STAINLESS", "stainless_steel"),
    ("TEMPERED GLASS", "glass"),
    ("CERAMIC", "ceramic"),
    ("PORCELAIN", "ceramic"),
    ("ACRYLIC", "acrylic"),
    ("GLASS", "glass"),
    ("BRASS", "brass"),
    ("PVC", "pvc"),
    ("ABS", "abs"),  # 291 - the flyer prints it on every hand bidet and paper holder
    ("NANOGRAIN", "nanograin"),  # 96 - a named sink surface, not a generic composite
    ("GRANITE", "granite"),  # 40
    ("MARBLE", "marble"),
]

# Measured on the live catalog: WALL MOUNT* 513 taps, PILLAR MOUNT* 383, bare PILLAR a
# further 220, UNDER COUNTER 47 basins, UNDERMOUNT 14 sinks. "PILLAR" was previously a
# control type, which was wrong twice over: in this catalog it always describes where
# the tap is fixed, and holding it in two tables let one product score the same fact on
# two legs of the ranker.
MOUNTING_TOKENS: list[tuple[str, str]] = [
    ("TABLE TOP", "counter_top"),  # 40 - the flyer's own name for a counter-top basin
    ("TABLETOP", "counter_top"),
    ("WALL HUNG", "wall_hung"),
    ("WALL MOUNTED", "wall_hung"),
    ("WALL MOUNT", "wall_hung"),
    ("FLOOR STANDING", "floor_standing"),
    ("FLOOR MOUNTED", "floor_standing"),
    ("FREE STANDING", "floor_standing"),
    ("UNDER COUNTER", "under_counter"),
    ("UNDERMOUNT", "under_counter"),
    ("UNDER MOUNT", "under_counter"),
    ("COUNTER TOP", "counter_top"),
    ("COUNTERTOP", "counter_top"),
    ("ABOVE COUNTER", "counter_top"),
    ("TOP MOUNT", "counter_top"),
    ("PILLAR MOUNTED", "pillar_mounted"),
    ("PILLAR MOUNT", "pillar_mounted"),
    ("PILLAR", "pillar_mounted"),
    ("SEMI RECESSED", "semi_recessed"),  # 66
    ("SEMI-RECESSED", "semi_recessed"),
    ("CONCEALED", "concealed"),
    # The counterpart of concealed, and stated as its own selling point on 118 rows.
    ("EXPOSED", "exposed"),
    ("PEDESTAL", "pedestal"),
]

# How the water is controlled. Deliberately NOT the product noun: "mixer" and "bib"
# moved to `product_type`, which is what a customer actually says.
CONTROL_TOKENS: list[tuple[str, str]] = [
    ("SINGLE LEVER", "single_lever"),
    ("SINGLE HANDLE", "single_lever"),
    ("SELF CLOSING", "self_closing"),
    ("SELF-CLOSING", "self_closing"),
    ("SENSOR", "sensor"),
    ("TWO WAY", "two_way"),
    ("2 WAY", "two_way"),
]

# The noun the customer uses inside a class. Longest first: "BIB TAP" must beat "TAP",
# and "HAND SHOWER" must beat "SHOWER". Counts are live measurements.
PRODUCT_TYPE_TOKENS: list[tuple[str, str]] = [
    ("ANGLE VALVE", "angle_valve"),  # 338
    ("HOSE BIB TAP", "bib_tap"),
    ("BIB TAP", "bib_tap"),  # 476
    ("BASIN TAP", "basin_tap"),  # 220
    ("SINK TAP", "kitchen_tap"),  # part of 1,101 with KITCHEN TAP
    ("KITCHEN TAP", "kitchen_tap"),
    ("SHOWER TAP", "shower_tap"),
    ("MIXER TAP", "mixer_tap"),
    ("MIXER", "mixer_tap"),  # 1,770
    ("HAND SHOWER", "hand_shower"),  # 487
    ("RAIN SHOWER", "rain_shower"),  # 12
    ("SHOWER SET", "shower_set"),  # 550
    ("SHOWER HEAD", "shower_head"),  # 616
    ("CLOSE-COUPLED", "close_coupled"),  # 342 with CLOSE COUPLED
    ("CLOSE COUPLED", "close_coupled"),
    ("ONE PIECE", "one_piece"),  # 745
    ("ONE-PIECE", "one_piece"),
    ("ART BASIN", "art_basin"),  # 294
    ("MIRROR CABINET", "mirror_cabinet"),
    # --- the flyer's own aisles -------------------------------------------------
    # Everything below was sold on the 2025-2026 flyer and landed in the catalog as
    # class "Tap" (650) or "Bathroom Accessory" (384) - true, and useless to a
    # salesperson asked for a double towel bar. Counts are LIKE matches over active
    # descriptions, measured before the token was added rather than guessed.
    ("POP UP WASTE", "pop_up_waste"),  # 142
    ("POP-UP WASTE", "pop_up_waste"),  # 12
    ("POPUP WASTE", "pop_up_waste"),
    ("TOWEL SHELF", "towel_shelf"),  # 210
    ("TOWEL BAR", "towel_bar"),  # 439 (single/double split by bar_count)
    ("TOWEL RACK", "towel_bar"),  # 13
    ("HOOK BAR", "hook_bar"),  # 200
    ("ROBE HOOK", "robe_hook"),  # 159
    ("CORNER BASKET", "corner_basket"),
    ("CORNER RACK", "corner_basket"),  # 4
    ("PAPER HOLDER", "paper_holder"),  # 388
    ("GRAB BAR", "grab_bar"),  # 106
    ("SOAP DISPENSER", "soap_dispenser"),  # 126
    ("FLEXIBLE HOSE", "flexible_hose"),  # 456
    ("FLUSH VALVE", "flush_valve"),  # 111
    ("FLOOR GRATING", "floor_grating"),  # 224
    ("FLOOR TRAP", "floor_trap"),  # 96
    ("CISTERN", "cistern"),  # 227
    ("TUMBLER", "tumbler"),  # 69
    # AFTER mirror_cabinet, which is the more specific reading of the same word.
    ("MIRROR", "mirror"),  # 1,107
    ("BIDET", "bidet"),  # 715
]

# The nouns a salesperson says out loud that had no derivation at all. Counts are
# word-boundary matches on the live description column.
EXTRA_TYPE_TOKENS: list[tuple[str, str]] = [
    ("SEAT COVER", "toilet_seat"),  # 291
    ("TOILET SEAT", "toilet_seat"),
    ("URINAL", "urinal"),  # 158
    ("TOILET BRUSH", "toilet_brush"),  # 172 BRUSH, nearly all of them toilet brushes
    ("SQUATTING PAN", "squatting_pan"),  # 30
    ("SQUAT PAN", "squatting_pan"),
    ("TOWEL RING", "towel_ring"),  # 74
    ("DUSTBIN", "dustbin"),  # the flyer's page 16, by litre
    ("WASTE BIN", "dustbin"),
    # Before BOTTLE TRAP: "300MM DRAIN PIPE FOR 32MM BOTTLE TRAP" is a pipe that FITS
    # one, and reading it as the trap itself answered the wrong question.
    # "BASIN COLD TAP" is a basin tap; only the adjacent "BASIN TAP" form was read, so
    # this row derived a water supply and no type at all.
    ("BASIN COLD TAP", "basin_tap"),
    ("BASIN HOT TAP", "basin_tap"),
    ("DRAIN PIPE", "drain_pipe"),
    ("STOP COCK", "stop_cock"),
    ("STOPCOCK", "stop_cock"),
    ("SHOWER SEAT", "shower_seat"),
    ("HANDRAIL", "handrail"),
    ("HAND RAIL", "handrail"),
    ("BOTTLE TRAP", "bottle_trap"),
    ("CABINET HINGES", "hinge"),
    ("HINGES", "hinge"),
    ("HINGE", "hinge"),
    ("PRESSURE PUMP", "water_pump"),
    ("BOOSTER PUMP", "water_pump"),
    ("WATER PUMP", "water_pump"),
    # These read as new nouns but the catalogue already has a type for them; deriving
    # them to a second value would split one aisle across two answers.
    ("STOP VALVE", "angle_valve"),  # 44
    ("SOAP HOLDER", "soap_dispenser"),
    ("SOAP DISH", "soap_dispenser"),
    ("FLOOR DRAIN", "floor_grating"),
    ("CORNER SHELF", "corner_basket"),
    ("TOWEL RACK", "towel_bar"),
    ("GLASS SHELF", "towel_shelf"),
]

# Specific readings run before the generic nouns below them, so "TOILET SEAT" is never
# answered by a bare "TOILET".
PRODUCT_TYPE_TOKENS = EXTRA_TYPE_TOKENS + PRODUCT_TYPE_TOKENS

# Furniture is the weakest page in the flyer test and this is why: a basin cabinet, a
# mirror cabinet and a side cabinet all derived to class "Bathroom Furniture" and nothing
# else, so 990 cabinets were mutually indistinguishable. The flyer names them separately
# on every card.
FURNITURE_TOKENS: list[tuple[str, str]] = [
    ("BASIN CABINET", "basin_cabinet"),  # 232
    ("SIDE CABINET", "side_cabinet"),
    ("TALL CABINET", "tall_cabinet"),
]

# "2 IN 1", "3 IN 1", "4 IN 1" - how many pieces the furniture set has, and the only
# thing separating SRTBF31513 from SRTBF11614 once both quote the same 580x460x400.
PIECE_COUNT_RE = re.compile(r"\b(\d)\s*IN\s*1\b")

# What a bin, a cistern or a tumbler holds. The flyer's page 16 sells dustbins as
# "8 litre" and "12 litre" and nothing in the catalogue read it.
# The bare "12L" form is where the real data is - 6L cisterns, 12L and 20L bins - but
# the same letters end a product code (SRTKS1008L, CB F-809L). Requiring that no letter
# or digit precede the number keeps the bins and drops the codes.
CAPACITY_RE = re.compile(
    r"(?<![A-Z0-9])(?<![A-Z]-)(\d+(?:\.\d+)?)\s*(?:LITRES?|LITERS?|LTR|L)\b"
)
# The imperial twin of capacity_litre: the flyer's drinkware is sold in ounces.
CAPACITY_OZ_RE = re.compile(r"(?<![A-Z0-9])(\d+(?:\.\d+)?)\s*OZ\b", re.IGNORECASE)

# Pumps are quoted in horsepower on 48 rows and kilowatts on 14; customers say HP.
POWER_HP_RE = re.compile(r"(\d+(?:\.\d+)?)\s*HP\b")

# "2-Ways", "3 WAYS": how many outlets the diverter feeds. NOT the same fact as
# spray_functions - SRTWT9605-RG is a 2-way set with a 3-function hand shower, and
# folding them together would answer "2 ways" with 3-function sets.
WAY_COUNT_RE = re.compile(r"\b(\d)\s*-?\s*WAYS?\b")

# A shower with a temperature valve - asked for by name, and 44 rows say so.
THERMOSTATIC_RE = re.compile(r"\bTHERMOSTATIC\b")
# A shower set on a height-adjustable rail, which is what "sliding" means here.
SLIDING_RAIL_RE = re.compile(r"\bSLIDING\b")

# A tall basin tap, sold as its own thing on 31 flyer cards and asked for by name.
HIGH_BASIN_RE = re.compile(r"\bHIGH\s+BASIN\b")
# Water filter built into the tap.
FILTER_TAP_RE = re.compile(r"\bFILTER\s+TAP\b")
# A kitchen tap whose head pulls out as a spray.
PULL_OUT_SHOWER_RE = re.compile(r"\bPULL[\s-]?OUT\s+SHOWER\b")
# The sink accessories the flyer sells the multifunction sinks on.
CHOPPING_BOARD_RE = re.compile(r"\bCHOPPING\s+BOARD\b")
DISH_RACK_RE = re.compile(r"\bDISH\s+RACK\b")
# Stated on 40 cards as a selling point, and the opposite of has_overflow - a basin
# sold WITHOUT one is a different product, not a missing fact.
NO_OVERFLOW_RE = re.compile(r"\bW/?O\s+OVERFLOW\b|\bWITHOUT\s+OVERFLOW\b")
SHOWER_UNION_RE = re.compile(r"\bSHOWER\s+UNION\b")

# The steel a sink is made of. 304 vs 201 is the first question a kitchen-sink buyer
# asks and the biggest price difference on the page: 705 descriptions say 304, 137 say
# 201, and the flyer prints "S/Steel 304" 218 times.
STEEL_GRADE_TOKENS: list[tuple[str, str]] = [
    ("S/STEEL 304", "304"),
    ("SUS304", "304"),  # 216
    ("SUS 304", "304"),
    ("STAINLESS STEEL 304", "304"),
    ("304", "304"),  # 705
    ("SUS201", "201"),
    ("S/STEEL 201", "201"),
    ("201", "201"),  # 137
]

# How many spray patterns a shower or bidet head offers. The flyer prints "3 Functions"
# on 36 cards and a salesperson quotes it by number.
FUNCTION_COUNT_RE = re.compile(r"\b(\d)\s*-?\s*FUNCTIONS?\b")

# The hose that comes with a hand bidet or shower. Printed as "c/w 1.2m" on 41 cards;
# customers ask for the length because it decides whether it reaches.
HOSE_LENGTH_RE = re.compile(r"\b(\d(?:\.\d)?)\s*M\b(?=[^A-Z]|$)")

# Mirror and furniture features the flyer sells on, each its own line on the card.
FRAMELESS_RE = re.compile(r"\bFRAMELESS\b")
LED_RE = re.compile(r"\bLED\b")
HONEYCOMB_RE = re.compile(r"\bHONEYCOMB\b")
SOFT_CLOSE_RE = re.compile(r"\bSOFT[\s-]?CLOS(?:E|ING)\b")
DIVERTER_RE = re.compile(r"\bDIVERTER\b")

# Cold-only or hot-and-cold. The single most common distinction on the flyer (878
# descriptions say COLD TAP, 348 say MIXER) and the first thing a salesperson
# establishes, yet nothing in the registry could express it: both landed on
# product_type=basin_tap and ranked identically for "basin mixer".
WATER_SUPPLY_TOKENS: list[tuple[str, str]] = [
    ("COLD TAP", "cold_only"),  # 878
    ("MIXER TAP", "mixer"),  # 348
    ("MIXER", "mixer"),
]

# A rim to clean or not. Printed on the flyer as its own selling point ("Washdown With
# Rimless") and asked for by name.
RIMLESS_RE = re.compile(r"\bRIMLESS\b")

# Single or double towel bar - the flyer prints them as separate products and customers
# ask for them by number, exactly as they do with sink bowls.
BAR_COUNT_TOKENS: list[tuple[str, int]] = [
    ("DOUBLE TOWEL", 2),  # 170
    ("SINGLE TOWEL", 1),  # 94
]

# The waste-outlet rule the user named: `-P` is a P-trap and the bare twin is an S-trap.
# Only the LITERAL statement is read here. The code-suffix pairing is a separate rule
# with its own gating (`CB5105-P` is a bib tap, not a trap), and is not in this release.
TRAP_TOKENS: list[tuple[str, str]] = [
    ("P-TRAP", "p_trap"),  # 291
    ("P TRAP", "p_trap"),
    ("S-TRAP", "s_trap"),  # 736
    ("S TRAP", "s_trap"),
]

# How the spout behaves. `FLEXIBLE` alone is the catalog's own phrasing for a flexible
# hose spout: 518 taps carry it, which is why "flexible kitchen tap" was a reasonable
# thing for a customer to type and get nothing back.
SPOUT_TOKENS: list[tuple[str, str]] = [
    ("WATERFALL", "waterfall"),  # 38 - the flyer gives it a section of its own
    ("DOUBLE FLEXIBLE SPOUT", "double_flexible"),
    ("FLEXIBLE HEAD", "flexible"),
    ("FLEXIBLE HOSE", "flexible"),
    ("FLEXIBLE", "flexible"),  # 518
    ("PULL OUT", "pull_out"),  # 123 incl. PULL-OUT
    ("PULL-OUT", "pull_out"),
    ("SWIVEL", "swivel"),
    ("GOOSENECK", "gooseneck"),
]

# How a water closet flushes. Order is precedence: SIPHONIC first because it is the
# rarer, more specific term (14 rows) and 6 of those also say WASH DOWN in the same
# sentence ("(SIPHONIC) WASH DOWN WC") - real plumbing marketing copy is not always
# a clean taxonomy, so the more specific word wins. TWISTER is a branded flush name
# (188 rows, "TWISTER FLUSH WC") checked before the generic WASHDOWN family (498).
FLUSH_TOKENS: list[tuple[str, str]] = [
    ("SIPHONIC", "siphonic"),
    ("SYPHONIC", "siphonic"),
    ("TWISTER FLUSHING", "twister"),
    ("TWISTER FLUSH", "twister"),
    ("TWISTER", "twister"),
    ("WASH-DOWN", "washdown"),
    ("WASH DOWN", "washdown"),
    ("WASHDOWN", "washdown"),
]

# Spelled-out bowl counts. `<digit> BOWL` is handled separately by regex.
BOWL_WORDS: dict[str, int] = {
    "SINGLE": 1,
    "DOUBLE": 2,
    "TRIPLE": 3,
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
}

SHAPE_TOKENS: list[tuple[str, str]] = [
    ("RECTANGULAR", "rectangular"),
    ("ROUND", "round"),
    ("SQUARE", "square"),
    ("OVAL", "oval"),
    ("ELLIPSE", "oval"),
    ("SQ", "square"),
]

# --------------------------------------------------------------------------- #
# class, from the description's TRAILING noun
# --------------------------------------------------------------------------- #
#
# The category code decodes to a class (`SRT-WC` -> Water Closet) and for 6,140 codes
# that is the only signal there is. But it is the business's filing, not a description
# of the product, and it is wrong in both directions: 11 squatting pans and 6 urinals
# are filed under Water Closet, 120 flexible hoses and 10 shower sets under Tap, 12
# cloth hangers under Bathroom Accessory. `SORENTO SQUATTING PAN` came back as a water
# closet, which is what a customer asking for a water closet then got offered.
#
# English puts the head noun LAST in a compound, so the description already carries the
# answer: `BASIN MIXER` is a mixer, `URINAL FLUSH VALVE` is a valve, `SQUATTING PAN` is
# a squatting pan. Only a token at the END counts - an earlier one is a modifier saying
# what the product is FOR. Measured across 11,670 codes: 4,138 agree with the category,
# 205 disagree, and reading the disagreements the description is right nearly every time.
#
# Longest first: `KITCHEN SINK` must beat `SINK`, `MIRROR CABINET` must beat neither
# alone (bare CABINET and MIRROR are deliberately absent - whether a mirror is furniture
# or an accessory is the business's call, not a derivation's, and guessing moved 135
# rows on nothing but this module's opinion).
CLASS_TAIL_TOKENS: list[tuple[str, str]] = [
    ("SQUATTING PAN", "Squatting Pan"),  # 11 - filed under Water Closet
    ("SQUATING PAN", "Squatting Pan"),  # the catalog's own misspelling
    ("WATER CLOSET", "Water Closet"),
    ("WC", "Water Closet"),
    # The catalog says TOILET as often as it says WC, and it was not in this list, so
    # an "AUTO INDUCTION TOILET" fell through to its category and any key gated on
    # `class = Water Closet` was then dropped from it.
    ("TOILET", "Water Closet"),
    ("KITCHEN SINK", "Kitchen Sink"),
    ("GRANITE SINK", "Kitchen Sink"),
    ("WASH BASIN", "Wash Basin"),
    ("ART BASIN", "Wash Basin"),
    ("BASIN", "Wash Basin"),
    ("URINAL", "Urinal"),  # 6 - filed under Water Closet
    # Split apart. One class conflated two products a customer chooses between: asking
    # for a bathtub returned jacuzzis, and no amount of ranking fixes a class that says
    # they are the same thing. Safe to separate because the words never co-occur -
    # measured, 373 descriptions say JACUZZI, 240 say BATHTUB, and ZERO say both.
    # A product whose description says neither keeps the category's own broader label,
    # which is the honest answer when the only evidence is a filing code.
    ("BATHTUB", "Bathtub"),
    ("BATH TUB", "Bathtub"),
    ("JACUZZI", "Jacuzzi"),
    ("FLEXIBLE HOSE", "Flexible Hose"),  # 120 - filed under Tap
    ("MIRROR CABINET", "Bathroom Furniture"),
    ("VANITY CABINET", "Bathroom Furniture"),
    ("CLOTH HANGER", "Cloth Hanger"),  # 12 - filed under Bathroom Accessory
    ("CLOTHES HANGER", "Cloth Hanger"),
    ("BIB TAP", "Tap"),
    ("BASIN TAP", "Tap"),
    ("KITCHEN TAP", "Tap"),
    ("MIXER TAP", "Tap"),
    ("MIXER", "Tap"),
    ("TAP", "Tap"),
    ("FAUCET", "Tap"),
    ("HAND SHOWER", "Shower"),
    ("RAIN SHOWER", "Shower"),
    ("SHOWER SET", "Shower"),
    ("SHOWER HEAD", "Shower"),
    ("SHOWER", "Shower"),
]
CLASS_TAIL_TOKENS.sort(key=lambda pair: -len(pair[0]))

# "(CABINET ONLY)" names the product; every other parenthetical is a colour, a
# dimension or an aside, and keeping them buries the head noun.
_CLASS_PARENS_RE = re.compile(r"\((?![^)]*\bONLY\b)[^)]*\)")
# Everything after these words is what the product COMES WITH or is FOR, never what it
# is: `MIXER TAP WITH PULL OUT SHOWER` is a tap, `CISTERN FOR WALL HUNG WC` is a
# cistern. Without this cut, 61 taps were reclassified by their accessories.
_CLASS_ACCOMPANIMENT_RE = re.compile(r"\s(?:WITH|C/W|FOR|W/)\s.*$|\s\+.*$")
_CLASS_DIMENSIONS_RE = re.compile(r"[\d.]+\s*X\s*[\d.]+.*$")


def class_text(description: str, code: str) -> str:
    """The description with everything that is not WHAT THIS IS stripped out.

    The code, the dimensions, the parenthetical, and everything the product comes WITH
    or is FOR. `BRAVAT WC ONE PIECE (C/W SEAT COVER & FITTING) C21101W-3` reduces to
    `BRAVAT WC ONE PIECE`, which is the difference between a water closet and a seat
    cover.

    Public, and the text every CLASS rule is matched against, because a rule written in
    the registry needs the same protection the trailing-noun read has always had: a
    plain `contains SEAT COVER` on the raw description reclassified 147 water closets
    that merely ship with one.
    """
    text = (description or "").upper()
    text = _CLASS_PARENS_RE.sub(" ", text)
    text = _CLASS_ACCOMPANIMENT_RE.sub(" ", text)
    text = text.replace((code or "").upper(), " ")
    text = _CLASS_DIMENSIONS_RE.sub(" ", text)
    text = re.sub(r"[^A-Z ]+", " ", text)
    text = re.sub(r"\bONLY\b", " ", text)
    return " ".join(text.split())


def _class_from_description(description: str, code: str) -> tuple[str, str] | None:
    """(class, the words it was read from) when the description names its own class."""
    text = class_text(description, code)
    for token, label in CLASS_TAIL_TOKENS:
        if text == token or text.endswith(" " + token):
            return label, token
    return None


# Finish stated in WORDS. Counts are cards on the 2025-2026 A3 flyer, which is where
# most of these appear - the product master states a finish only in the code suffix, and
# only when the code has one. Longest first, so "MATT BLACK" wins before "BLACK" and
# "FULL ROSE GOLD" before "ROSE GOLD" and "GOLD".
FINISH_WORDS: list[tuple[str, str]] = [
    ("FULL ROSE GOLD", "rose_gold"),  # 50
    ("ROSE GOLD", "rose_gold"),
    ("GOLDEN YELLOW", "golden_yellow"),  # 73
    ("MATT BLACK", "black"),  # 152 - the registry already calls this black
    ("GUN METAL", "gunmetal"),
    ("GUNMETAL", "gunmetal"),  # 103
    ("BRUSHED NICKEL", "nickel"),
    ("CHROME", "chrome"),  # 98
    ("NICKEL", "nickel"),
    ("BLACK", "black"),  # 41
    ("WHITE", "white"),
    ("GREY", "grey"),
    ("SATIN", "satin_chrome"),  # 20 flyer cards, and the only finish word on some
]

# Trailing code segment -> finish. Everything absent here yields nothing: DIY is
# packaging, ENG is the -P-ENG collision family, bare digits are variant numbering.
FINISH_SUFFIXES: dict[str, str] = {
    # Matt black, on 52 codes. Its absence is why SRTWB890-MBL carried no finish at all
    # and could not be told apart from SRTWB890, the same basin in white.
    "MBL": "black",
    "BL": "black",
    "GM": "gunmetal",
    "NL": "nickel",
    "NK": "nickel",
    "GY": "grey",
    "RG": "rose_gold",
    "CR": "chrome",
    "FRG": "french_gold",
    "WH": "white",
    "SC": "satin_chrome",
}

# Nouns that mean "a part of a product", not a product. Matched as the HEAD of the
# phrase, never as a feature: a sink with a drainer board is still a sink.
#

# A basin sold "C/W BASIN SCREW" has a fixing screw; "WALL HUNG BASIN SCREW (10 X 140)"
# IS the screw set. This key only
# fires for the former, mirroring how has_drainer excludes a drainer sold as itself.
_FIXING_SCREW_NOUN = "SCREW"
# ...and "**W/O SCREW" says the opposite, which the bare noun read as a yes. That put
# SRTWB890-MBL and SRTWB890 - the same basin, one with the screw and one without - on
# identical spec profiles.
FIXING_SCREW_RE = re.compile(r"(?<!W/O )(?<!WITHOUT )SCREW")

# "S-TRAP 300MM" / "S-TRAP:250MM" / "( S- TRAP 250MM )" - the catalog is inconsistent
# about the separator, so all three are matched. Independent of TRAP_TOKENS: a customer
# who says "150mm S-trap" wants a specific pan, not just any S-trap.
_TRAP_LENGTH_RE = re.compile(r"[SP]\s*-?\s*TRAP\s*[:,]?\s*(\d+(?:\.\d+)?)\s*MM")

# All three phrasings describe the same thing: an automated, sensor/app-driven toilet.
# "AUTO INDUCTION" appears without the word INTELLIGENT on 6 rows, so it is checked on
# its own rather than folded into the INTELLIGENT-only case.
_SMART_WC_RE = re.compile(r"INTELLIGENT|AUTO\s*INDUCTION|SMART\s*(?:TOILET|WC)")

# No sanitaryware product is five metres in any direction. Real catalog data carries
# separator typos ("540X440180MM" parses as 540 x 440180), and a dimension that absurd
# would otherwise be indexed and ranked on. Out-of-range values are dropped and flagged
# rather than silently stored.
#
# It is `product_spec_registry.max_value` now, per key and editable (AC-A.5), seeded
# 5000 on every millimetre key. One module constant said the same thing about a
# thickness and a bath, and could not be looked at, let alone changed. The number
# itself lives with the seed that plants it:
# `product_spec_registry.DEFAULT_MM_MAX_VALUE`.

# 2 to 4 numbers separated by x / X / *, with optional spaces and an optional unit.
# Each number may be LABELLED and may carry its own unit, because the flyer writes
# "L750 x W165 x H247mm" and "D L255xW125xH255mm" while the product master writes
# "1500x750x630MM". 188 flyer cards use the labelled form and not one of them parsed, so
# a grab bar printed its exact size on the card and still could not be found by it.
_DIM_PART = r"(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?"
_DIM_RE = re.compile(
    rf"{_DIM_PART}\s*[xX*]\s*{_DIM_PART}"
    rf"(?:\s*[xX*]\s*{_DIM_PART})?"
    rf"(?:\s*[xX*]\s*{_DIM_PART})?",
)

# "1 BOWL", "2BOWL", and the spelled-out "SINGLE BOWL" / "DOUBLE BOWL (...)". Only a
# count immediately preceding the word is read; nothing is inferred from a length.
_BOWL_DIGIT_RE = re.compile(r"(?<!\d)(\d)\s*BOWLS?\b")
_BOWL_WORD_RE = re.compile(rf"\b({'|'.join(BOWL_WORDS)})\s+BOWLS?\b")


def _find_token(haystack: str, table: list[tuple[str, str]]) -> tuple[str, str] | None:
    """First (value, evidence) whose token appears literally. Order is precedence."""
    for token, value in table:
        if re.search(rf"(?<![A-Z]){re.escape(token)}(?![A-Z])", haystack):
            return value, token
    return None




def _bowl_count(description: str) -> tuple[int, str] | None:
    """(count, evidence) when the description states a bowl count, else None.

    Both forms occur in the catalog and neither is dominant: `SINGLE BOWL` 42 rows,
    `DOUBLE BOWL` 64, `<digit> BOWL` 8, out of 1,148 kitchen sinks. The other ~90% say
    nothing about bowls at all. Returning None for those is the whole point - a double
    bowl is not derivable from a 1000 mm length, and guessing it would put wrong
    products in front of a customer who asked for a specific one.
    """
    match = _BOWL_WORD_RE.search(description)
    if match:
        return BOWL_WORDS[match.group(1)], match.group(0)
    match = _BOWL_DIGIT_RE.search(description)
    if match:
        return int(match.group(1)), match.group(0)
    return None


def _number(raw: str) -> float | int:
    value = float(raw)
    return int(value) if value.is_integer() else value


# A single stated size, for the rows that quote one number instead of LxWxH:
# "MARBLE TOP BASIN (800MM)". Read as the length, which is the dimension people quote.
_SINGLE_DIM_RE = re.compile(r"(?<![A-Z0-9X])(\d{2,4})\s*MM\b")


def _dimensions(description: str) -> tuple[list[float | int], str] | None:
    match = _DIM_RE.search(description or "")
    if not match:
        return None
    numbers = [_number(g) for g in match.groups() if g is not None]
    if len(numbers) < 2:
        return None
    return numbers, match.group(0)


def _single_dimension(description: str) -> tuple[float | int, str] | None:
    """The one size a row states when it does not state three.

    Only consulted when the LxWxH form found nothing, so a compound size is never
    reduced to its first number.

    A trap length is not a size. "ONE PIECE TWISTER FLUSH WC (P-TRAP 180MM)" states the
    trap outlet and nothing else, and reading its 180 as the length put a wrong Length on
    889 water closets (843 spec rows carried 180 / 250 / 300 from this span) and made
    every hand-entered length on them read as a conflict. The trap span is blanked
    before the lone size is looked for; ``trap_length`` reads it separately.
    """
    match = _SINGLE_DIM_RE.search(_TRAP_LENGTH_RE.sub(" ", description or ""))
    if not match:
        return None
    return _number(match.group(1)), match.group(0)


class _Derivation:
    """Accumulates values, provenance and exceptions for one product code."""

    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.provenance: dict[str, dict] = {}
        self.exceptions: list[dict] = []

    def set(self, key: str, value, evidence: str, *, unit: str | None = None, source: str = "derived") -> None:
        if value is None:
            return
        entry: dict = {"value": value}
        if unit:
            entry["unit"] = unit
        self.values[key] = entry
        self.provenance[key] = {"source": source, "confidence": 1.0, "evidence": evidence}

    def flag(self, spec_key: str, reason: str, proposed=None, stored=None) -> None:
        self.exceptions.append(
            {"spec_key": spec_key, "reason": reason, "proposed": proposed, "stored": stored}
        )


# --------------------------------------------------------------------------- #
# the rule engine: HOW a key is read, as data
# --------------------------------------------------------------------------- #
#
# The token tables above are now the SEED for `product_spec_registry.derivation_rules`,
# not the thing the engine reads. They stay here because they are the shipped starting
# point and the seed is built from them, which is what guarantees the first run after
# this change derives identically. Everything after that is edited in the UI.
#
# A rule is `{match, pattern, value}` and the first one to match wins, so the order of
# the list is its priority. The kinds, which is what the readers between them need and
# no more:
#
#   contains     the pattern appears as whole words       "S/STEEL 304" -> stainless_steel
#   ends_with    the pattern is the TRAILING noun        "SQUATTING PAN" -> Squatting Pan
#   present      a regex matches; the value is a flag    "OVER\s*FLOW" -> true
#   regex        a regex matches; capture a number       "(\d+)MM S-TRAP" -> 150
#   code_suffix  the product code's last segment         "-BL" -> black
#   from_field   the PRODUCT ROW, not its text           "column:dimensions_length" -> 800
#   name_head    what the product name says it IS        "MIXER TAP WITH ..." -> Tap
#
# The last two are the readers that used to run before any rule did (#425). They read
# the product record rather than a string, which is why they are kinds of their own
# rather than patterns - and they are ordinary rows in the same ordered list, so the
# screen that lists "how this is read" is now the whole truth about it.
#
# `source` limits a rule to one text: "description", "flyer", "size_text",
# "class_tail", or "any" (the default). A rule that should only ever fire on marketing
# copy can say so.
_WORD_BOUNDED = {"present"}

# Rules that read the product row itself. They take no text and never fire on pasted
# marketing copy, where there is no product to read.
_RECORD_KINDS = {"from_field", "name_head"}

# A CODE rule belongs at the BOTTOM of a key's list - a code suffix is a convention, not
# a statement, and a card saying "Golden Yellow" outranks `-GY` mapping to grey - but
# that is the list's own order now rather than a phase behind it, and migration 450
# moved the rows that sat above their text rules down to where they always ran.


def _rule_matches(
    rule: dict, texts: dict[str, str], code: str, default_scope: str = "any"
):
    """(value, evidence, which_text) for a rule that fires, or None.

    Never raises on a bad rule. These are edited by hand in a form, and one malformed
    regex must not stop the catalog deriving - it is skipped and the next rule is tried.
    """
    kind = str(rule.get("match") or "contains").lower()
    pattern = str(rule.get("pattern") or "")
    if not pattern:
        return None

    scope = str(rule.get("source") or default_scope).lower()
    if kind == "code_suffix":
        if "-" not in code:
            return None
        if code.rsplit("-", 1)[1] != pattern.upper():
            return None
        return rule.get("value"), f"-{pattern.upper()}", "code"
    # The code is the only place some facts are written down. `SRTSC` names a seat cover
    # in every code that carries it, while the descriptions say "SEAT COVER", "COVER",
    # or nothing recognisable - and there was no way to say so. `code_suffix` reads the
    # finish after the last dash; nothing read the body of the code.
    #
    # Unbounded on purpose, unlike `contains` on prose: a product code is a dense string
    # with no word breaks, so a letter boundary would never match.
    if kind in {"code_contains", "code_starts_with"}:
        needle = pattern.upper()
        hit = code.startswith(needle) if kind == "code_starts_with" else needle in code
        return (rule.get("value"), needle, "code") if hit else None

    # Each rule reads ITS OWN text: the one it names, or the description and the flyer
    # when it names none. Only one of those two ever holds anything - derivation reads a
    # product and `propose_from_text` reads pasted copy - so a rule cannot silently
    # answer from the wrong document, and the list stays a plain priority list.
    names = [scope] if scope in texts else ["description", "flyer"]
    for name in names:
        haystack = texts.get(name, "")
        if not haystack:
            continue
        try:
            if kind == "contains":
                # Bounded by letters, NOT a bare substring search. `SQ` -> square would
                # otherwise fire on SQUATTING PAN, and `MIXER` on SHOWERMIXER: checked
                # against the live catalog, plain `find()` changed 42 of 11,415 codes,
                # some of them into nonsense. This is the shipped `_find_token`
                # behaviour, and derivation must not change because its rules moved
                # into a table.
                if re.search(rf"(?<![A-Z]){re.escape(pattern.upper())}(?![A-Z])", haystack):
                    return rule.get("value"), pattern.upper(), name
            elif kind == "ends_with":
                token = pattern.upper()
                if haystack == token or haystack.endswith(" " + token):
                    return rule.get("value"), token, name
            elif kind == "present":
                match = re.search(rf"(?<![A-Z]){pattern}(?![A-Z])", haystack)
                if match:
                    return rule.get("value", True), match.group(0), name
            elif kind == "regex":
                match = re.search(pattern, haystack)
                if match:
                    group = int(rule.get("capture") or 0)
                    raw = match.group(group) if group else match.group(0)
                    # An OPTIONAL group that did not participate is not a reading. The
                    # size triple's third and fourth numbers are optional - a two-number
                    # size has no height - and taking the group anyway asked `float`
                    # to read None.
                    if group and raw is None:
                        continue
                    value = _number(raw) if group else rule.get("value", True)
                    # `scale` converts the captured number into the unit the catalog
                    # stores. The flyer prints a hose as "1.2m" while every length here
                    # is millimetres, and the ranker normalises a customer's "1.2m" to
                    # 1200 - so storing 1.2 meant the stored value and the query could
                    # never meet, and the mismatch scored a PENALTY against the very
                    # product the customer asked for.
                    scale = rule.get("scale")
                    if scale and isinstance(value, (int, float)):
                        value = value * float(scale)
                        if float(value).is_integer():
                            value = int(value)
                    return value, match.group(0), name
        except re.error:
            continue
    return None


def _record_read(rule: dict, product, category, spec_key: str):
    """(value, evidence, origin) for a rule that reads the PRODUCT, not a string.

    These are the readers `derive()` used to run before it looked at any rule, and each
    one is a row now (#425, AC-A.1):

      * `from_field` `category` - the class the category is filed under. The weakest
        class signal there is (a decode of a filing code), so it is marked `category`
        rather than `derived`, and `_apply_scope` refuses to delete a spec on its say-so.
      * `from_field` `brand` - the product's own brand row. 22,771 of 22,805 products
        carry one, and reading the brand off the category prefix instead got 1,934 wrong.
      * `from_field` `column:<column>` - a number in the product master. Curated data,
        which is why the shipped lists put it above the text.
      * `name_head` - what the product NAME says it is: the description with the code,
        the dimensions, the parenthetical and everything the product comes WITH removed,
        read for its trailing noun. `MIXER TAP WITH PULL OUT SHOWER` is a tap.

    `None` whenever there is no product to read - the pasted-text pass has none, and a
    rule that reads the record must simply not fire there.
    """
    if product is None:
        return None
    kind = str(rule.get("match") or "").lower()
    pattern = str(rule.get("pattern") or "")

    if kind == "name_head":
        named = _class_from_description(
            product.description or "", (product.product_code or "").upper()
        )
        return (named[0], named[1], "field") if named else None

    if pattern == "category":
        label = getattr(category, "class_label", None) if category is not None else None
        if not label:
            return None
        return label, (getattr(category, "category_code", "") or ""), "category"

    if pattern == "brand":
        name = (getattr(getattr(product, "brand", None), "brand_name", None) or "").strip()
        return (name, f"brand={name}", "field") if name else None

    if pattern.startswith("column:"):
        # Named on the rule, so the row reads as the sentence it is ("from the product's
        # `dimensions_length` column") and a key can be pointed at a different column
        # without a deploy. Anything the products table does not have reads as nothing.
        raw = getattr(product, pattern.split(":", 1)[1], None)
        if raw is None:
            return None
        return _number(str(raw)), f"{spec_key}={raw}", "field"

    return None


# Which text a key's rules read when the rule does not say. Everything reads the
# description and the flyer; CLASS reads the cleaned tail, because a class rule is
# answering "what IS this" and the raw description also lists what it comes with.
_DEFAULT_SCOPE_BY_KEY = {"class": "class_tail"}


def _gate_passes(rule: dict, held: dict) -> bool:
    """Whether this rule applies to a product the derivation has read this far.

    `applies_when` and its negative `unless`, both `{spec_key: [values]}`, compared
    against what the SAME derivation has already produced. This is the round/square gate
    (#425, AC-A.1): a round basin's stored columns are mis-keyed, so 407 is a diameter
    and not a length, and the rows that read a length say `unless shape is round or
    square` while the diameter row says `applies when` it is.

    A gate the derivation cannot answer - no shape read at all, which is most of the
    catalogue - leaves `unless` satisfied and `applies_when` unmet, which is exactly how
    the hardcoded `if shape in ("round", "square")` behaved.
    """
    for field, wanted in (("applies_when", True), ("unless", False)):
        gate = rule.get(field)
        if not gate:
            continue
        for gate_key, permitted in gate.items():
            value = held.get(gate_key)
            allowed = {str(v).strip().lower() for v in (permitted or [])}
            hit = value is not None and str(value).strip().lower() in allowed
            if hit is not wanted:
                return False
    return True


def _gate_keys(rules_by_key: dict[str, list[dict]]) -> set[str]:
    """Keys some rule's gate reads, so they are derived before the rules that need them."""
    keys: set[str] = set()
    for rules in (rules_by_key or {}).values():
        for rule in rules or []:
            keys |= set(rule.get("applies_when") or {})
            keys |= set(rule.get("unless") or {})
    return keys


def apply_rules(
    rules_by_key: dict[str, list[dict]],
    texts: dict[str, str],
    code: str,
    *,
    product=None,
    category=None,
    max_values: dict | None = None,
    explain_key: str | None = None,
) -> dict:
    """What each key reads, and what else its own list had to say about it.

    `explain_key`, when given, makes the found entry for THAT ONE key carry
    `explain` - one `{index, value, evidence}` per row of its list, in order (index
    0-based, aligned to `rules[index]`), with `value`/`evidence` null where the row
    does not fire - and `explain_winner_index`, the row that actually won. Try-it
    (AC-B.1) is this and nothing else: the
    same loop below, run once with a draft list substituted for one key, reading every
    row instead of stopping at the first match. It changes nothing for a caller that
    does not pass it - every added branch below is `and not is_explain`, so a normal
    derive/derive_all run takes the same first-match path it always has.

    `{spec_key: {value, evidence, origin, column, text, flags}}`. `column` and `text` are
    the readings a `from_field column:` row and the first text row made, kept whether or
    not they won: a disagreement between the two is the `column_conflict` exception, and
    it has to be raised whichever of them is on top (AC-A.4).

    ORDER IS PRIORITY, across every kind, with no phase behind it. The engine used to
    run every text rule before any code rule wherever the rows sat, so a list could not
    be read as what it does: `class` held "code contains SRTSC -> Seat Cover" on top of
    32 rules that all outranked it. That order is real - a code suffix is a convention,
    not a statement, and `-GY` maps to grey while a card says "Golden Yellow" in words -
    so migration 450 MOVES those rows to where they ran instead of keeping the phase
    that made the screen wrong.

    A number above the key's `max_value` is dropped and flagged rather than stored, and
    it stops the key: "540X440180MM" is a separator typo, and reading the next rule
    instead would answer a question the typo already answered wrongly. The cap judges
    TEXT only - a number a person typed into the product master is data, and four live
    products legitimately carry a column above it.
    """
    max_values = max_values or {}
    found: dict[str, dict] = {}
    values: dict[str, object] = {}

    # A gate reads another key's value, so that key is derived first. `shape` decides
    # whether 407 is a diameter or a length, and reading the dimensions before it would
    # answer with whichever the dict happened to hold.
    gates = _gate_keys(rules_by_key)
    ordered = [key for key in (rules_by_key or {}) if key in gates]
    ordered += [key for key in (rules_by_key or {}) if key not in gates]

    for key in ordered:
        rules = rules_by_key.get(key) or []
        default_scope = _DEFAULT_SCOPE_BY_KEY.get(key, "any")
        is_explain = explain_key is not None and key == explain_key
        read: dict = {
            "value": None,
            "evidence": "",
            "origin": "description",
            "column": None,
            "text": None,
            "flags": [],
        }
        # Only a key with a column row can disagree with its column, and only that case
        # needs the whole list read after a winner is found. Everything else stops at
        # the first match, as it always has. Try-it (`is_explain`) is the other case
        # that needs every row read, and it needs it for every rule kind.
        wants_conflict = any(
            str(rule.get("match")) == "from_field"
            and str(rule.get("pattern") or "").startswith("column:")
            for rule in rules
        )
        # Keys a product may legitimately hold more than one of. SRTWT9605-RG is "Rose
        # Gold + Matt Black" - both true, and a customer asking for either is right.
        collected: list = []
        evidences: list[str] = []
        explain_rows: list[dict] = []
        explain_winner_index: int | None = None

        # 0-based: this `index` aligns to `rules[index]`, which is how the frontend's
        # `SpecRuleEditor` maps a read back onto its row (`reads[index]`). Unrelated to
        # `_validate_rules`'s 1-based "Rule N" wording, which names a row in an error
        # sentence rather than indexing into an array.
        for index, rule in enumerate(rules):
            explain_row = None
            if is_explain:
                explain_row = {"index": index, "value": None, "evidence": None}
                explain_rows.append(explain_row)

            kind = str(rule.get("match") or "contains").lower()
            if not _gate_passes(rule, values):
                continue

            is_column = kind == "from_field" and str(
                rule.get("pattern") or ""
            ).startswith("column:")
            if kind in _RECORD_KINDS:
                hit = _record_read(rule, product, category, key)
            else:
                hit = _rule_matches(rule, texts, code, default_scope)
            if hit is None or hit[0] is None:
                continue
            value, evidence, origin = hit
            if explain_row is not None:
                explain_row["value"] = value
                explain_row["evidence"] = evidence

            cap = max_values.get(key)
            if (
                cap is not None
                and not is_column
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > cap
            ):
                read["flags"].append(
                    {
                        "spec_key": key,
                        "reason": "implausible_dimension",
                        "proposed": {"value": value, "evidence": evidence},
                        "stored": None,
                    }
                )
                if not is_explain:
                    break
                continue

            if is_column:
                if read["column"] is None:
                    read["column"] = (value, evidence)
            elif read["text"] is None:
                read["text"] = (value, evidence)

            if key in MULTI_VALUE_KEYS:
                # Every tone THIS source states, and then no more: a two-tone tap is
                # "Rose Gold + Matt Black" and a customer asking for either is right,
                # but a code suffix must not add a third to what the words already
                # answered.
                if collected and origin != read["origin"]:
                    if not is_explain:
                        break
                    continue
                if value not in collected:
                    if not collected:
                        read["origin"] = origin
                        if is_explain:
                            explain_winner_index = index
                    collected.append(value)
                    evidences.append(evidence)
                continue
            if read["value"] is None:
                read["value"] = value
                read["evidence"] = evidence
                read["origin"] = origin
                if is_explain:
                    explain_winner_index = index
                if not wants_conflict and not is_explain:
                    break

        if collected:
            read["value"] = collected[0] if len(collected) == 1 else collected
            read["evidence"] = " + ".join(evidences)
        if is_explain:
            read["explain"] = explain_rows
            read["explain_winner_index"] = explain_winner_index
        if read["value"] is not None or read["flags"] or is_explain:
            found[key] = read
            if read["value"] is not None:
                values[key] = read["value"]
    return found


# Keys a product may hold more than one of at once. Two-tone taps and shower sets are
# printed that way on 23 flyer cards ("Rose Gold + Matt Black").
MULTI_VALUE_KEYS = {"finish"}

# Keys measured in millimetres, so the stored value carries its unit.
_MM_KEYS = {
    "trap_length",
    "dim_length",
    "dim_width",
    "dim_height",
    "diameter",
    "depth",
    "thickness",
    "hose_length",
}

# Texts that are the PRODUCT'S OWN account of itself. A rule reading one of these has
# read the business's own record; a rule reading the flyer has read a leaflet.
_OWN_TEXTS = {"description", "class_tail", "size_text"}


def description_first_keys(rules_by_key: dict[str, list[dict]] | None = None) -> frozenset[str]:
    """Keys the product itself already answers, so a flyer only ever fills the gap.

    This was a hand-written list of six keys. It is computed now, because the readers it
    was describing are rules: a key is description-first when something in its list reads
    the product's own record or its own description, so removing that row removes the
    precedence with it rather than leaving a constant asserting a reader that no longer
    runs. Same meaning, one place, and it moves when the rules move.

    Class and brand join the six sizes, and that is the correction the list was hiding:
    both are read off the product record, so a flyer that disagrees is a conflict for a
    person to settle, not a value to apply silently.
    """
    if rules_by_key is None:
        # Cached: `classify_spec_proposal` asks this per proposal, and a flyer batch is
        # hundreds of them against every rule in the registry.
        global _SHIPPED_DESCRIPTION_FIRST
        if _SHIPPED_DESCRIPTION_FIRST is None:
            _SHIPPED_DESCRIPTION_FIRST = description_first_keys(shipped_rules())
        return _SHIPPED_DESCRIPTION_FIRST
    return frozenset(
        key
        for key, rules in (rules_by_key or {}).items()
        if any(
            str(rule.get("match")) in _RECORD_KINDS
            or str(rule.get("source") or "") in _OWN_TEXTS
            for rule in rules or []
        )
    )


_SHIPPED_DESCRIPTION_FIRST: frozenset[str] | None = None


# The shipped rules, used when a caller has not loaded the configured ones. Built lazily
# from the seed so there is exactly one definition of "what ships".
_SHIPPED_RULES: dict[str, list[dict]] = {}


def shipped_rules() -> dict[str, list[dict]]:
    global _SHIPPED_RULES
    if not _SHIPPED_RULES:
        from app.services.product_spec_registry import _rules_from_shipped_tables

        _SHIPPED_RULES = _rules_from_shipped_tables()
    return _SHIPPED_RULES


def shipped_scopes() -> dict[str, dict]:
    from app.services.product_spec_registry import shipped_scopes as _scopes

    return _scopes()


def configured_scopes(db: Session) -> dict[str, dict]:
    from app.services.product_spec_registry import configured_scopes as _scopes

    return _scopes(db)


def shipped_max_values() -> dict[str, float]:
    from app.services.product_spec_registry import shipped_max_values as _caps

    return _caps()


def configured_max_values(db: Session) -> dict[str, float]:
    from app.services.product_spec_registry import configured_max_values as _caps

    return _caps(db)


def derive(
    product: Product,
    category: ProductCategory | None,
    *,
    rules_by_key: dict[str, list[dict]] | None = None,
    scopes_by_key: dict[str, dict] | None = None,
    max_values: dict[str, float] | None = None,
) -> _Derivation:
    """Everything readable about one product. Pure: no session, no writes.

    `rules_by_key` is the registry's configured derivation rules. Omitted (tests, and
    any caller that has not loaded them), the shipped tables in this module are used, so
    the module still derives standalone exactly as it always did.

    `scopes_by_key` is each key's `applies_when`: which products may carry it at all.
    Same fallback, same reason.

    `max_values` is each key's `max_value`: the number above which a reading is a typo
    rather than a measurement. Same fallback again.

    THE FLYER IS NO LONGER AN INPUT (AC-B.18). It used to arrive as `flyer_text` and act
    as a gap-filler under the description; a flyer now reaches specs only as reviewed
    proposals, through `propose_from_text` below. The `flyer` text stays in the table,
    empty, because a rule may still name it as its scope: reading it as "" is what makes
    such a rule fire on a proposal and never on a derivation.
    """
    out = _Derivation()
    description = (product.description or "").upper()
    code = (product.product_code or "").upper()
    texts = {
        "description": description,
        "flyer": "",
        # What the product IS, with the code, dimensions, parentheticals and
        # accompaniments removed. Only class rules read this by default.
        "class_tail": class_text(product.description or "", code),
        # The description with the trap span blanked out. A trap outlet is not a size:
        # "ONE PIECE TWISTER FLUSH WC (P-TRAP 180MM)" states where the waste leaves and
        # nothing else, and reading its 180 as the length put a wrong Length on 889
        # water closets. The lone-size row reads this text; `trap_length` reads the span
        # itself from the description, where it still is.
        "size_text": _TRAP_LENGTH_RE.sub(" ", description),
    }

    if rules_by_key is None:
        rules_by_key = shipped_rules()
    if scopes_by_key is None:
        scopes_by_key = shipped_scopes()
    if max_values is None:
        max_values = shipped_max_values()

    # ONE ordered list per key, and nothing outside it. The class off the category, the
    # brand off the product's own field, the `L x W x H` block and the plausibility cap
    # were four readers that ran BEFORE any rule and appeared on no screen, so
    # `SRTWC8354-SH-P` showed "the rules now read 180 mm" beside a rule list that could
    # not have read it. They are rows now (#425, AC-A.1), in the order they always ran:
    # the column, then the size in the text, then the lone size, then whatever anybody
    # adds; the name head and the category UNDER a human's own class rules.
    fired = apply_rules(
        rules_by_key,
        texts,
        code,
        product=product,
        category=category,
        max_values=max_values,
    )

    for key, read in fired.items():
        for flagged in read["flags"]:
            out.flag(
                flagged["spec_key"], flagged["reason"], flagged["proposed"], flagged["stored"]
            )
        if read["value"] is None:
            continue
        origin = read["origin"]
        out.set(
            key,
            read["value"],
            read["evidence"],
            unit="mm" if key in _MM_KEYS else None,
            # A class inherited from the CATEGORY is marked as such and not as derived:
            # it is a decode of a filing code rather than a reading of the product, and
            # `_apply_scope` refuses to delete a spec on the strength of it.
            source=(
                "category"
                if origin == "category"
                else "flyer"
                if origin == "flyer"
                else "derived"
            ),
        )

    # Curated data is never SILENTLY outranked. Where a key holds both a column reading
    # and a text reading and the two disagree, the disagreement is flagged whichever of
    # them is on top - the column above the text (its shipped order) or a text row a
    # merchandiser moved above it (AC-A.4).
    for key, read in fired.items():
        column, from_text = read["column"], read["text"]
        if column and from_text and column[0] != from_text[0]:
            out.flag(
                key,
                "column_conflict",
                proposed={"value": from_text[0], "evidence": from_text[1]},
                stored={"value": float(column[0])},
            )

    # SHAPE GATING's other half, which is not a reading and so is not a rule: a round or
    # square product whose columns hold anything at all has them MIS-KEYED (407 is a
    # diameter, not a length), and a rectangular one whose length equals its width is
    # the same defect showing up without the description saying so. Both are questions
    # for a person, and neither produces a value.
    stored = {
        "dim_length": product.dimensions_length,
        "dim_width": product.dimensions_width,
        "dim_height": product.dimensions_height,
    }
    shape = (out.values.get("shape") or {}).get("value")
    if shape in ("round", "square"):
        if any(value is not None for value in stored.values()):
            out.flag(
                "diameter",
                "shape_mismatch",
                proposed={"shape": shape},
                stored={k: float(v) for k, v in stored.items() if v is not None},
            )
    else:
        length, width = stored["dim_length"], stored["dim_width"]
        if length is not None and width is not None and length == width:
            out.flag(
                "shape",
                "shape_mismatch",
                proposed={"shape": "round_or_square"},
                stored={"dim_length": float(length), "dim_width": float(width)},
            )

    # Drop anything the key does not apply to.
    #
    # `applies_when` was a hint to the understanding model and nothing else: it shaped
    # what the model was allowed to EXTRACT from a customer sentence, but nothing
    # stopped derivation writing the key onto a product of any class. So a jacuzzi
    # whose flyer says DRAINER was stored as having a drainer board, and `has_drainer`
    # ended up on 74 products outside Kitchen Sink against 32 inside it - the majority
    # of the key's own data contradicting the scope printed next to it on screen.
    _apply_scope(out, scopes_by_key)

    return out


def try_read(
    spec_key: str,
    rules: list[dict],
    *,
    product: Product | None = None,
    category: ProductCategory | None = None,
    text: str | None = None,
    rules_by_key: dict[str, list[dict]] | None = None,
    scopes_by_key: dict[str, dict] | None = None,
    max_values: dict[str, float] | None = None,
) -> dict:
    """What a DRAFT rule list (unsaved) would read for one key, row by row (AC-B.1).

    The one thing `derive()` and `propose_from_text()` do not offer: they report the
    winner, not every row that was tried. This calls the same `apply_rules` they call,
    with `rules_by_key[spec_key]` swapped for the draft and `explain_key=spec_key`, so
    every other key still reads with its OWN configured rules - a size row gated on
    `shape` still needs `shape` derived first, draft or not.

    Exactly one of `product`/`text` is expected: a product reads its own description,
    code and fields; pasted text has none of those, so a `from_field` or `name_head`
    row reads nothing from it - it plays the same role a flyer card does in
    `propose_from_text`, not the product's own description.

    Returns `{"reads": [{"index", "value", "evidence"}, ...], "winner_index": int | None}`.
    """
    if rules_by_key is None:
        rules_by_key = dict(shipped_rules())
    else:
        rules_by_key = dict(rules_by_key)
    rules_by_key[spec_key] = rules
    if scopes_by_key is None:
        scopes_by_key = shipped_scopes()
    if max_values is None:
        max_values = shipped_max_values()

    if product is not None:
        description = (product.description or "").upper()
        code = (product.product_code or "").upper()
        texts = {
            "description": description,
            "flyer": "",
            "class_tail": class_text(product.description or "", code),
            "size_text": _TRAP_LENGTH_RE.sub(" ", description),
        }
    else:
        code = ""
        texts = {"description": "", "flyer": (text or "").upper(), "class_tail": "", "size_text": ""}

    fired = apply_rules(
        rules_by_key,
        texts,
        code,
        product=product,
        category=category,
        max_values=max_values,
        explain_key=spec_key,
    )
    read = fired.get(spec_key) or {}
    return {
        "reads": read.get("explain") or [],
        "winner_index": read.get("explain_winner_index"),
    }


def _apply_scope(out: "_Derivation", applies_when: dict[str, dict]) -> None:
    """Remove derived keys whose `applies_when` the product does not satisfy.

    Gate values are compared case-insensitively against what THIS derivation produced,
    so a gate can name another derived key (`diameter` only applies to a round or
    square product) as well as the class.

    A key is removed only when the gate's own key has a value that CONTRADICTS it. An
    unclassed product keeps everything, because this module's standing rule is that
    absence of a word is never evidence of absence - and the strict reading deleted
    `flush_type` from every WC whose description ends in "FLUSHING" rather than in a
    class noun, which is the data the key exists for.

    A class INHERITED FROM THE CATEGORY never gates either. It is a decode of a filing
    code and it is wrong often enough to matter: an AUTO INDUCTION TOILET filed under a
    kitchen-sink category would have had `is_smart` deleted on the category's say-so,
    while the description says the word in full. Evidence read from the product cannot
    be overruled by a guess about the product.
    """
    for key, gate in applies_when.items():
        if not gate or key not in out.values:
            continue
        for gate_key, permitted in gate.items():
            held = (out.values.get(gate_key) or {}).get("value")
            allowed = {str(v).strip().lower() for v in (permitted or [])}
            if not allowed or held is None:
                continue
            if (out.provenance.get(gate_key) or {}).get("source") == "category":
                continue
            if str(held).strip().lower() not in allowed:
                out.values.pop(key, None)
                out.provenance.pop(key, None)
                break


# --------------------------------------------------------------------------- #
# the flyer pass, lifted out of derivation (AC-B.18)
# --------------------------------------------------------------------------- #
def propose_from_text(
    text: str,
    code: str,
    *,
    rules_by_key: dict[str, list[dict]] | None = None,
    scopes_by_key: dict[str, dict] | None = None,
    max_values: dict[str, float] | None = None,
) -> list[dict]:
    """What a piece of marketing copy SAYS about one code. Proposals, never writes.

    This is the flyer text pass that used to run inside `derive()`, lifted whole
    (captain, 2026-08-14): the rule order, the `source: "flyer"` rule scope, the
    millimetre units and the `applies_when` gate all behave exactly as they did,
    because the knowledge in them was tuned against the real flyer document and is
    the thing the bulk flyer-ingestion slice inherits.

    What is gone is the merge. The pass no longer competes with a description, so the
    one piece of precedence it owed - the description owns a size - survives as the
    `description_first` flag on each proposal, for the caller to render as a conflict
    the reviewer unticks rather than as a rule applied silently.

    Pure on purpose: no session, no product row, no writes. `code` is here because the
    code passes (`code_suffix` and friends) are part of the same pass; pass "" when
    there is no code to read.
    """
    if rules_by_key is None:
        rules_by_key = shipped_rules()
    if scopes_by_key is None:
        scopes_by_key = shipped_scopes()
    if max_values is None:
        max_values = shipped_max_values()

    code = (code or "").upper()
    texts = {
        # There is no description here, and that is the point: a rule scoped to the
        # product master must not fire on a leaflet somebody pasted. The same goes for
        # the two texts derived FROM a description - a class tail and a trap-blanked
        # size text - which is what keeps the size readers off a pasted card.
        "description": "",
        "flyer": (text or "").upper(),
        "class_tail": "",
        "size_text": "",
    }
    # No product row, so the rules that read one (`from_field`, `name_head`) do not
    # fire here at all: a leaflet says nothing about the product master's own columns.
    fired = apply_rules(rules_by_key, texts, code, max_values=max_values)

    # Accumulated into the same shape `derive()` builds, so the SAME `_apply_scope`
    # runs over it - a second copy of the gate rules would drift the first time
    # somebody edited `applies_when`.
    out = _Derivation()
    origins: dict[str, str] = {}
    for key, read in fired.items():
        if read["value"] is None:
            continue
        unit = "mm" if key in _MM_KEYS else None
        out.set(key, read["value"], read["evidence"], unit=unit, source="derived")
        origins[key] = "flyer" if read["origin"] == "flyer" else "code"
    _apply_scope(out, scopes_by_key)

    owned = description_first_keys(rules_by_key)
    return [
        {
            "spec_key": key,
            "value": entry.get("value"),
            "unit": entry.get("unit"),
            "evidence": (out.provenance.get(key) or {}).get("evidence") or "",
            "origin": origins.get(key, "flyer"),
            # The one piece of precedence the pass owes the description: where the
            # product's own record already answers this key, a card that disagrees is a
            # conflict for a person to settle. Computed from the rules rather than a
            # hand-written list, so removing the row removes the precedence with it.
            "description_first": key in owned,
        }
        for key, entry in out.values.items()
    ]


# Bump whenever the RULES above change: new key, new token, changed precedence.
#
# `derived_hash` skips a re-derive when nothing about the product changed, which is what
# makes a catalog-wide run cheap. But the product is only half the input - the rules are
# the other half. Without this, adding `bowl_count` re-derived every tap (their category
# gained a class, so their hash moved) and silently skipped all 1,148 kitchen sinks,
# which kept their old values and reported a successful run. The failure is invisible:
# the job says "skipped", which is exactly what it says when there is genuinely nothing
# to do.
# 27: the flyer left the input entirely (AC-B.13), so every code's fingerprint moves
# and the next catalogue run rewrites every row. That is the point - a flyer-only value
# must not survive as a derived one - and it is why the runbook schedules a full
# re-derive as its own step rather than leaving it to the nightly job.
DERIVATION_VERSION = "27"


def _input_hash(
    product: Product,
    category: ProductCategory | None,
    rules_fingerprint: str = "",
) -> str:
    parts = [
        DERIVATION_VERSION,
        # The RULES are half the input now, and they are edited without a deploy - so
        # DERIVATION_VERSION alone can no longer say "nothing changed". Without this,
        # editing a rule in the UI would report a successful run that skipped every row.
        rules_fingerprint,
        product.product_code or "",
        product.description or "",
        # `brand` is read off this column now, so a re-brand has to move the hash.
        (getattr(product.brand, "brand_name", None) or ""),
        (category.category_code if category else "") or "",
        (category.class_label if category else "") or "",
        str(product.dimensions_length),
        str(product.dimensions_width),
        str(product.dimensions_height),
    ]
    return hashlib.sha256("||".join(parts).encode()).hexdigest()


def _rules_fingerprint(rules_by_key: dict[str, list[dict]] | None) -> str:
    """A hash of the configured rules, so editing one re-derives what it affects."""
    return hashlib.sha256(
        json.dumps(rules_by_key or {}, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def configured_rules(db: Session) -> dict[str, list[dict]]:
    """Every key's rules, as configured. Falls back to the shipped tables.

    A key with no rules configured yet gets the shipped ones, so seeding is a
    convenience rather than a prerequisite - an unseeded database still derives.

    EVERY key, not only active ones. `is_active` governs whether the parser extracts
    the key and whether the ranker weights it; it is not a statement about the catalog.
    Deriving only active keys means flipping a key on shows an empty column until
    somebody re-runs the catalog job, and flipping it off silently discards data that
    was expensive to produce.
    """
    from app.models.product_spec import ProductSpecRegistry

    shipped = shipped_rules()
    rules: dict[str, list[dict]] = dict(shipped)
    for row in db.query(ProductSpecRegistry).all():
        configured = row.derivation_rules or []
        if configured:
            rules[row.spec_key] = configured
        # A value this business has taken away must stop being PRODUCED, not merely
        # stop being offered - otherwise suppression is cosmetic and the catalog keeps
        # filling in a value the business says it does not use. The stored rule is left
        # alone, so putting the value back brings its rules back with it.
        dropped = {str(v).strip() for v in (row.suppressed_values or [])}
        if dropped and rules.get(row.spec_key):
            rules[row.spec_key] = [
                rule
                for rule in rules[row.spec_key]
                if str(rule.get("value", "")).strip() not in dropped
            ]
    return rules


def derive_for_code(
    db: Session,
    product_code: str,
    *,
    commit: bool = False,
    rules_by_key: dict[str, list[dict]] | None = None,
    scopes_by_key: dict[str, dict] | None = None,
    max_values: dict[str, float] | None = None,
) -> dict:
    """Derive one code and fan the result out to every row that shares it.

    COMPANY SCOPE MATTERS HERE. A product code exists once per company, so the fan-out
    only reaches every copy when the session scope is all-companies (``None``). This
    function deliberately does NOT force that: a request-time re-derive must stay
    inside its caller's isolation. The catalog-wide batch job is the thing that runs
    unscoped, and `derive_all` documents it.
    """
    if rules_by_key is None:
        rules_by_key = configured_rules(db)
    if scopes_by_key is None:
        scopes_by_key = configured_scopes(db)
    if max_values is None:
        max_values = configured_max_values(db)

    # The same lock the authored write and the verify guard take, before anything is
    # read: a code with no spec row yet has no row to lock FOR UPDATE, so two writers
    # racing to create the first one would otherwise both pass their reads. Locking the
    # code's product rows covers that, and taking them first keeps the lock order the
    # same everywhere. Released by the caller's commit, which for `derive_all` is its
    # per-chunk one.
    lock_product_code(db, product_code)

    rows = (
        db.query(Product, ProductCategory)
        # Brand is read per product now, so eager-load it: lazily this is an extra
        # query per row across 11,415 codes. `populate_existing` because a Product
        # already in the session keeps the relationship it was first loaded with - a
        # re-brand inside one session would otherwise derive the old brand AND hash to
        # the old fingerprint, so the row would look up to date while being wrong.
        .options(joinedload(Product.brand))
        .populate_existing()
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.product_code == product_code)
        .order_by(Product.company_id, Product.id)
        .all()
    )
    if not rows:
        return {"written": 0, "skipped": 0, "exceptions": 0}

    # One derivation is written to every copy, so WHICH copy it reads from matters.
    # The company copies of a model can sit in different categories, and only some of
    # those categories are classified. Taking whichever row the database happened to
    # return first silently dropped class and brand for 40 of 594 pilot codes, and
    # made the result depend on row order. Prefer a classified category, then fall
    # back, and order the query so the fallback is at least deterministic.
    product, category = next(
        (pair for pair in rows if pair[1] is not None and pair[1].class_label),
        rows[0],
    )
    fingerprint = _input_hash(
        product,
        category,
        # Scopes are half of what a rule produces, so an `applies_when` edit has to
        # move the hash exactly as a rule edit does. Without it, narrowing a key
        # reports "skipped" for every product and leaves the old values in place.
        # The cap is half of what a rule produces too: raising `max_value` on a key
        # must re-read the products it was dropping, or the run reports "skipped" and
        # leaves them empty.
        _rules_fingerprint(
            {"rules": rules_by_key, "scopes": scopes_by_key, "max_values": max_values}
        ),
    )

    existing = {
        spec.product_id: spec
        for spec in db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id.in_([p.id for p, _ in rows]))
        .all()
    }

    if existing and len(existing) == len(rows) and all(
        spec.derived_hash == fingerprint for spec in existing.values()
    ):
        return {"written": 0, "skipped": len(rows), "exceptions": 0}

    # Scopes as well as rules: they are already in hand for the fingerprint above,
    # and without them one code's re-derive gated on the SHIPPED `applies_when`
    # while the catalogue run gated on the configured one - the same product read
    # two ways depending on which button produced it. Extraction already passes
    # both (`product_spec_extract`), so this is derivation catching up with it.
    result = derive(
        product,
        category,
        rules_by_key=rules_by_key,
        scopes_by_key=scopes_by_key,
        max_values=max_values,
    )

    # Brand is the one spec that lives on the ROW while derivation is keyed on the CODE.
    # Where two company copies of a model carry different brands (6 rows catalog-wide),
    # one derivation cannot be right for both, so both get the chosen one and a human is
    # told. Silence here would publish a wrong brand, which is the failure that made this
    # column authoritative in the first place.
    brands = {
        (getattr(p.brand, "brand_name", None) or "").strip() for p, _ in rows
    } - {""}
    if len(brands) > 1:
        result.flag(
            "brand",
            "company_copies_disagree",
            proposed=result.values.get("brand", {}).get("value"),
            stored=", ".join(sorted(brands)),
        )

    # Two passes, because `status` depends on the exception set and the exception set
    # now depends on the merged provenance. A reviewer-confirmed value outranks
    # anything derivable, and the merge rule for that lives in one place.
    merged: list[tuple[ProductSpecifications, dict, dict]] = []
    answered: set[str] = set()
    conflicts: list[dict] = []
    for row_product, _ in rows:
        spec = existing.get(row_product.id)
        if spec is None:
            spec = ProductSpecifications(product_id=row_product.id)
            db.add(spec)

        values, provenance, row_conflicts = merge_authored_over(
            result.values, result.provenance, spec.values, spec.provenance
        )
        merged.append((spec, values, provenance))
        answered |= authored_keys(provenance)
        conflicts.extend(row_conflicts)

    # A question a person has answered does not re-ask itself. `flag()` appends
    # unconditionally and knows nothing about what is stored, so without this filter
    # setting `shape` by hand sees `round_or_square` come back on the very next run and
    # the 258 flagged codes can never be cleared.
    exceptions = [f for f in result.exceptions if f["spec_key"] not in answered]

    # A NEW disagreement still gets asked, once. Exceptions are keyed on the code with
    # no product_id, and every company copy produces the same conflict.
    seen: set[tuple[str, str]] = set()
    for conflict in conflicts:
        identity = (conflict["spec_key"], conflict["reason"])
        if identity in seen:
            continue
        seen.add(identity)
        exceptions.append(conflict)

    written = 0
    # One before/after pair speaks for the whole code, and it must come from the copy
    # the verify hash is defined on - `current_values_hash` reads the lowest product id
    # that HAS a spec row - not from whichever copy iterates first: a fresh no-spec
    # copy that sorts first would hand back an empty "before" and withdraw a stamp over
    # canonical values that never changed. Read BEFORE `write_spec_row` replaces the
    # column: a verification stamp has to be withdrawn against what it was actually
    # made against. The skip-if-unchanged return above never reaches here, which is the
    # point - a re-run that changes nothing must not withdraw anything (AC-D.3).
    before_values: dict = (
        dict(existing[min(existing)].values or {}) if existing else {}
    )
    # After the writes every copy holds a spec row, so the canonical copy is the lowest
    # product id outright - the same row `current_values_hash` reads back afterwards.
    canonical_after_id = min(spec.product_id for spec, _, _ in merged)
    after_values: dict = {}
    for spec, values, provenance in merged:
        write_spec_row(
            spec,
            values=values,
            provenance=provenance,
            has_exceptions=bool(exceptions),
            derived_hash=fingerprint,
        )
        if spec.product_id == canonical_after_id:
            after_values = values
        written += 1

    # Rebuild this code's open exceptions rather than appending, so a fixed input
    # clears its flag instead of accumulating a duplicate every run.
    db.query(ProductSpecException).filter(
        ProductSpecException.product_code == product_code,
        ProductSpecException.resolved_at.is_(None),
    ).delete(synchronize_session=False)
    for flagged in exceptions:
        db.add(
            ProductSpecException(
                id=str(uuid.uuid4()),
                product_code=product_code,
                spec_key=flagged["spec_key"],
                reason=flagged["reason"],
                proposed=flagged["proposed"],
                stored=flagged["stored"],
            )
        )

    # Imported at call time: this module is imported by the write service, and this is
    # the edge that would close the cycle.
    from app.services.product_spec_verification import invalidate_on_values_change

    invalidate_on_values_change(
        db,
        product_code,
        before_values=before_values,
        after_values=after_values,
    )

    db.flush()
    if commit:
        db.commit()

    return {"written": written, "skipped": 0, "exceptions": len(exceptions)}


def derive_all(
    db: Session,
    *,
    codes: list[str] | None = None,
    chunk_size: int = 500,
    commit: bool = False,
) -> dict:
    """Derive a batch of codes. Resumable by passing the codes still outstanding.

    Run this with the all-companies scope (``company_scope(db, None)``) so one
    derivation lands on every copy of a model. Under a single-company scope it will
    quietly cover half the catalog and the two copies will drift, which is the exact
    failure the code-keyed fan-out exists to prevent.
    """
    if codes is None:
        codes = [c for (c,) in db.query(Product.product_code).distinct().all()]

    # Loaded ONCE: 11,415 codes each re-reading the registry is 11,415 queries for an
    # answer that cannot change mid-run.
    rules_by_key = configured_rules(db)
    scopes_by_key = configured_scopes(db)
    max_values = configured_max_values(db)

    totals = {"codes": 0, "written": 0, "skipped": 0, "exceptions": 0}
    for index in range(0, len(codes), chunk_size):
        for code in codes[index : index + chunk_size]:
            result = derive_for_code(
                db,
                code,
                rules_by_key=rules_by_key,
                scopes_by_key=scopes_by_key,
                max_values=max_values,
            )
            totals["codes"] += 1
            for key in ("written", "skipped", "exceptions"):
                totals[key] += result[key]
        if commit:
            db.commit()

    return totals
