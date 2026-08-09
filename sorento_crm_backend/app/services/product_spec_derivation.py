"""Read specs out of the catalog. Deterministically, or not at all.

There is no inference in this module and that is deliberate. Two mechanisms that
needed it were measured and rejected: curating specs out of the description (bowl count
appears in 110 of 22,366 descriptions), and inducing dimensions from code conventions
(best rule 25.3% against 387 labelled rows, where 99% was required). What is left is
what can be read directly, so every value here is defensible by pointing at the
substring it came from.

Precedence, highest first:

  1. a `source='human'` value already stored   - a reviewer settled it, never touch it
  2. the products table's own columns          - curated data outranks parsed text
  3. literal tokens in the description         - shape-gated, see below
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
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.models.product import Product, ProductCategory
from app.models.product_spec import (
    ProductFlyerText,
    ProductSpecException,
    ProductSpecifications,
)
from app.services.product_spec_rendering import render_spec_sentence

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
# sentence ("(SIPHONIC) WASH DOWN WC") — real plumbing marketing copy is not always
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
# a squatting pan. Only a token at the END counts — an earlier one is a modifier saying
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

# "S-TRAP 300MM" / "S-TRAP:250MM" / "( S- TRAP 250MM )" — the catalog is inconsistent
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
MAX_PLAUSIBLE_MM = 5000

# 2 to 4 numbers separated by x / X / *, with optional spaces and an optional unit.
_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[xX*]\s*(\d+(?:\.\d+)?)"
    r"(?:\s*[xX*]\s*(\d+(?:\.\d+)?))?"
    r"(?:\s*[xX*]\s*(\d+(?:\.\d+)?))?",
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
    """
    match = _SINGLE_DIM_RE.search(description or "")
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
# the list is its priority. Five kinds, which is what the shipped tables between them
# needed and no more:
#
#   contains     the pattern appears as whole words       "S/STEEL 304" -> stainless_steel
#   ends_with    the pattern is the TRAILING noun        "SQUATTING PAN" -> Squatting Pan
#   present      a regex matches; the value is a flag    "OVER\s*FLOW" -> true
#   regex        a regex matches; capture a number       "(\d+)MM S-TRAP" -> 150
#   code_suffix  the product code's last segment         "-BL" -> black
#
# `source` limits a rule to one text: "description", "flyer", or "any" (the default).
# A rule that should only ever fire on marketing copy can say so.
_WORD_BOUNDED = {"present"}


def _rule_matches(
    rule: dict, texts: dict[str, str], code: str, default_scope: str = "any", only_text: str | None = None
):
    """(value, evidence) for the first rule that fires, or None.

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
        return rule.get("value"), f"-{pattern.upper()}"
    # The code is the only place some facts are written down. `SRTSC` names a seat cover
    # in every code that carries it, while the descriptions say "SEAT COVER", "COVER",
    # or nothing recognisable — and there was no way to say so. `code_suffix` reads the
    # finish after the last dash; nothing read the body of the code.
    #
    # Unbounded on purpose, unlike `contains` on prose: a product code is a dense string
    # with no word breaks, so a letter boundary would never match.
    if kind in {"code_contains", "code_starts_with"}:
        needle = pattern.upper()
        hit = code.startswith(needle) if kind == "code_starts_with" else needle in code
        return (rule.get("value"), needle) if hit else None

    # ONE text per call. The caller runs every rule against the description before it
    # runs any rule against the flyer, so a low-priority rule matching marketing copy
    # cannot beat a high-priority rule matching the product master.
    if only_text is not None:
        # A rule that names its own text only ever runs against that text.
        if scope in texts and scope != only_text:
            return None
        haystacks = [texts.get(only_text, "")]
    else:
        haystacks = (
            [texts.get(scope, "")] if scope in texts else [texts["description"], texts["flyer"]]
        )
    for haystack in haystacks:
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
                    return rule.get("value"), pattern.upper()
            elif kind == "ends_with":
                token = pattern.upper()
                if haystack == token or haystack.endswith(" " + token):
                    return rule.get("value"), token
            elif kind == "present":
                match = re.search(rf"(?<![A-Z]){pattern}(?![A-Z])", haystack)
                if match:
                    return rule.get("value", True), match.group(0)
            elif kind == "regex":
                match = re.search(pattern, haystack)
                if match:
                    group = int(rule.get("capture") or 0)
                    raw = match.group(group) if group else match.group(0)
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
                    return value, match.group(0)
        except re.error:
            continue
    return None


# Which text a key's rules read when the rule does not say. Everything reads the
# description and the flyer; CLASS reads the cleaned tail, because a class rule is
# answering "what IS this" and the raw description also lists what it comes with.
_DEFAULT_SCOPE_BY_KEY = {"class": "class_tail"}


def apply_rules(rules_by_key: dict[str, list[dict]], texts: dict[str, str], code: str) -> dict:
    """{spec_key: (value, evidence, which_text)} for every key whose rules fire.

    SOURCE-MAJOR, RULE-MINOR: description, then flyer, then the code. Every rule is
    tried against one source before any rule is tried against the next, so the rule
    list is a priority list only WITHIN a source. Two things were wrong without it.

    Rule order beat source order. `SRTWC7614-RL` says "S-TRAP:250MM" in its own
    description and "P-Trap: Horizontal Outlet" on its flyer card; the P-TRAP rule sits
    above the S-TRAP rule, so it matched the flyer first and the product was stored as
    a P-trap, contradicting its own description.

    And the CODE beat both. A code suffix is a convention, not a statement: `-GY` is
    mapped to grey, but the flyer for `SRTWB1516-GY` says "Golden Yellow" in words.
    Words a human wrote outrank a letter pair, which is what the shipped `finish` rules
    always intended - "the words go first and the suffix stays as the fallback" - and
    could not express while one loop ran them together.
    """
    code_kinds = {"code_suffix", "code_contains", "code_starts_with"}
    # Keys a product may legitimately hold more than one of. SRTWT9605-RG is "Rose Gold
    # + Matt Black" - both true, and a customer asking for either is right. First-match
    # -wins had to discard one of them, and which one it discarded depended on rule
    # order, so the answer was arbitrary rather than merely incomplete.
    multi = MULTI_VALUE_KEYS
    found: dict[str, tuple] = {}
    for key, rules in (rules_by_key or {}).items():
        default_scope = _DEFAULT_SCOPE_BY_KEY.get(key, "any")
        # The key's own primary text, the flyer as gap-filler, the code as last resort.
        primary = default_scope if default_scope in texts else "description"
        for source in (primary, "flyer", "code"):
            if key in found:
                break
            collected: list = []
            evidences: list[str] = []
            for rule in rules or []:
                is_code_rule = str(rule.get("match")) in code_kinds
                if is_code_rule != (source == "code"):
                    continue
                hit = _rule_matches(
                    rule, texts, code, default_scope, only_text=None if is_code_rule else source
                )
                if hit is None:
                    continue
                value, evidence = hit
                if value is None:
                    continue
                if key in multi:
                    # Keep every distinct tone this source states, then stop: a later
                    # source must not add to what a better one already answered.
                    if value not in collected:
                        collected.append(value)
                        evidences.append(evidence)
                    continue
                found[key] = (value, evidence, "flyer" if source == "flyer" else source)
                break
            if collected:
                found[key] = (
                    collected[0] if len(collected) == 1 else collected,
                    " + ".join(evidences),
                    "flyer" if source == "flyer" else source,
                )
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

# Keys the DESCRIPTION owns. A rule may fill one in, but only where the description had
# nothing to say - the product master is the business's own record and the flyer is a
# leaflet, which is the same precedence every other key already follows. Without this a
# flyer's rounded "L680xW375xH770" would overwrite an exact size the master states.
_DESCRIPTION_FIRST_KEYS = {
    "dim_length",
    "dim_width",
    "dim_height",
    "diameter",
    "depth",
    "thickness",
}

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


def derive(
    product: Product,
    category: ProductCategory | None,
    *,
    rules_by_key: dict[str, list[dict]] | None = None,
    scopes_by_key: dict[str, dict] | None = None,
    flyer_text: str = "",
) -> _Derivation:
    """Everything readable about one product. Pure: no session, no writes.

    `rules_by_key` is the registry's configured derivation rules. Omitted (tests, and
    any caller that has not loaded them), the shipped tables in this module are used, so
    the module still derives standalone exactly as it always did.

    `scopes_by_key` is each key's `applies_when`: which products may carry it at all.
    Same fallback, same reason.

    `flyer_text` is what the printed flyer says about this code. It is a GAP-FILLER: a
    rule is tried against the description first and only falls through to the flyer,
    because the master is the business's own record and marketing copy is a leaflet.
    Where a value does come from the flyer, its provenance says `flyer` so nobody has to
    guess which of the two they are looking at.
    """
    out = _Derivation()
    description = (product.description or "").upper()
    code = (product.product_code or "").upper()
    texts = {
        "description": description,
        "flyer": (flyer_text or "").upper(),
        # What the product IS, with the code, dimensions, parentheticals and
        # accompaniments removed. Only class rules read this by default.
        "class_tail": class_text(product.description or "", code),
    }

    if rules_by_key is None:
        rules_by_key = shipped_rules()
    if scopes_by_key is None:
        scopes_by_key = shipped_scopes()
    applies_when = scopes_by_key
    fired = apply_rules(rules_by_key, texts, code)

    # 1. class off the category; brand off the PRODUCT'S OWN brand field.
    #
    # The category prefix (`SRT-KS` -> Sorento) is a decode of a code, and the product
    # carries the real answer in `brand_id`: 22,771 of 22,805 products have one, across
    # 12 brands. Trusting the prefix got 1,934 rows wrong — every INFINITY (532), OTHERS
    # (403) and NO LOGO (601) product was relabelled as Sorento or Cabana, and four
    # brands the prefix cannot express at all were unreachable. Curated data outranks a
    # decoded code, exactly as it does for dimensions below.
    #
    # The prefix is NOT kept as a fallback for the 34 products carrying no brand. It is
    # the same wrong mechanism at smaller scale, and it spells the brand its own way
    # ("Sorento" vs the brands table's "SORENTO"), which would put both spellings into
    # an open vocabulary and split the ranker's evidence between them. Rule 5 applies:
    # no brand is a better answer than a guessed one.
    # Class precedence: a configured rule, then the trailing noun, then the category.
    #
    # The configured rule used to be computed and then dropped on the floor - `fired`
    # held it and the loop below skipped the key - so every class rule anyone wrote in
    # the registry did nothing. "Product code contains SRTSC -> Seat Cover" saved,
    # re-read the catalogue, and changed no product, with no way to tell why.
    #
    # A rule someone wrote is an explicit statement and outranks a heuristic reading of
    # the last word, which is why it goes first. The trailing noun stays underneath it:
    # it reads a CLEANED tail (code, dimensions, parentheticals and everything the
    # product comes WITH removed), which is work the raw-text rule engine does not do.
    class_rule = fired.get("class")
    if class_rule is not None and class_rule[0] is not None:
        out.set("class", class_rule[0], class_rule[1])
    else:
        named = _class_from_description(product.description or "", code)
        if named is not None:
            out.set("class", named[0], named[1])
        elif category is not None and category.class_label:
            # Marked `category`, not `derived`. It is the weakest class signal in the
            # module - a decode of a filing code, not a reading of the product - and
            # `_apply_scope` refuses to delete a spec on the strength of it.
            out.set("class", category.class_label, category.category_code, source="category")

    brand_name = (getattr(product.brand, "brand_name", None) or "").strip()
    if brand_name:
        out.set("brand", brand_name, f"brand={brand_name}")


    # 3. shape. Never defaulted: "unstated" and "rectangular" are different, and the
    #    dimension rules below turn on which one it is.
    #
    #    Read from the CONFIGURED rules, like every other key. It used to read the
    #    hardcoded token table here and the configured rules separately below, so the
    #    two could disagree: editing the shape rules changed the stored value but not
    #    the gate that decides whether 407 is a diameter or a length.
    shape = None
    fired_shape = fired.get("shape")
    if fired_shape is not None and fired_shape[0] is not None:
        shape = str(fired_shape[0])
        out.set("shape", shape, fired_shape[1])

    # 4. dimensions, gated on shape
    parsed = _dimensions(description)
    stored = {
        "dim_length": product.dimensions_length,
        "dim_width": product.dimensions_width,
        "dim_height": product.dimensions_height,
    }
    has_stored = any(v is not None for v in stored.values())

    if shape in ("round", "square"):
        # The stored columns are mis-keyed for these: 407 is a diameter, not a length.
        if parsed:
            numbers, evidence = parsed
            out.set("diameter", numbers[0], evidence, unit="mm")
            if len(numbers) > 1:
                out.set("depth", numbers[1], evidence, unit="mm")
            if len(numbers) > 2:
                out.set("thickness", numbers[2], evidence, unit="mm")
        if has_stored:
            out.flag(
                "diameter",
                "shape_mismatch",
                proposed={"shape": shape},
                stored={k: float(v) for k, v in stored.items() if v is not None},
            )
    else:
        described: dict[str, float | int] = {}
        evidence = ""
        if parsed:
            numbers, evidence = parsed
            for key, number in zip(("dim_length", "dim_width", "dim_height"), numbers):
                if number > MAX_PLAUSIBLE_MM:
                    out.flag(key, "implausible_dimension", proposed={"value": number, "evidence": evidence})
                    continue
                described[key] = number
            if len(numbers) > 3:
                out.set("thickness", numbers[3], evidence, unit="mm")
        else:
            lone = _single_dimension(description)
            if lone and lone[0] <= MAX_PLAUSIBLE_MM:
                described["dim_length"], evidence = lone

        for key, column_value in stored.items():
            if column_value is not None:
                # Curated data outranks parsed text.
                out.set(key, _number(str(column_value)), f"{key}={column_value}", unit="mm")
                if key in described and described[key] != _number(str(column_value)):
                    out.flag(
                        key,
                        "column_conflict",
                        proposed={"value": described[key], "evidence": evidence},
                        stored={"value": float(column_value)},
                    )
            elif key in described:
                out.set(key, described[key], evidence, unit="mm")

        # length == width is the fingerprint of a round or square product forced into
        # rectangular columns, even when the description never says so.
        length, width = stored["dim_length"], stored["dim_width"]
        if length is not None and width is not None and length == width:
            out.flag(
                "shape",
                "shape_mismatch",
                proposed={"shape": "round_or_square"},
                stored={"dim_length": float(length), "dim_width": float(width)},
            )

    # 5. everything the CONFIGURED RULES produce: material, mounting, finish, the
    #    feature flags, the trailing-noun class, every key someone adds later.
    #
    #    A drainer, an overflow or a fixing screw is asserted only where the text says
    #    so. Absence of the word is never evidence of absence.
    for key, (value, evidence, origin) in fired.items():
        if key == "class":
            continue  # handled above, where the category fallback lives
        if key in _DESCRIPTION_FIRST_KEYS and key in out.values:
            continue  # the description already said it; a rule only fills the gap
        unit = "mm" if key in _MM_KEYS else None
        out.set(key, value, evidence, unit=unit, source="flyer" if origin == "flyer" else "derived")

    # 6. drop anything the key does not apply to.
    #
    # `applies_when` was a hint to the understanding model and nothing else: it shaped
    # what the model was allowed to EXTRACT from a customer sentence, but nothing
    # stopped derivation writing the key onto a product of any class. So a jacuzzi
    # whose flyer says DRAINER was stored as having a drainer board, and `has_drainer`
    # ended up on 74 products outside Kitchen Sink against 32 inside it - the majority
    # of the key's own data contradicting the scope printed next to it on screen.
    _apply_scope(out, applies_when)

    return out


def _apply_scope(out: "DerivedSpec", applies_when: dict[str, dict]) -> None:
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


# Bump whenever the RULES above change: new key, new token, changed precedence.
#
# `derived_hash` skips a re-derive when nothing about the product changed, which is what
# makes a catalog-wide run cheap. But the product is only half the input - the rules are
# the other half. Without this, adding `bowl_count` re-derived every tap (their category
# gained a class, so their hash moved) and silently skipped all 1,148 kitchen sinks,
# which kept their old values and reported a successful run. The failure is invisible:
# the job says "skipped", which is exactly what it says when there is genuinely nothing
# to do.
DERIVATION_VERSION = "24"


def _input_hash(
    product: Product,
    category: ProductCategory | None,
    rules_fingerprint: str = "",
    flyer_text: str = "",
) -> str:
    parts = [
        DERIVATION_VERSION,
        # The RULES are half the input now, and they are edited without a deploy - so
        # DERIVATION_VERSION alone can no longer say "nothing changed". Without this,
        # editing a rule in the UI would report a successful run that skipped every row.
        rules_fingerprint,
        flyer_text,
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
    flyer_text: str | None = None,
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
    if flyer_text is None:
        flyer = db.query(ProductFlyerText).filter_by(product_code=product_code).first()
        flyer_text = flyer.text if flyer else ""

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
        _rules_fingerprint({"rules": rules_by_key, "scopes": scopes_by_key}),
        flyer_text or "",
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

    result = derive(product, category, rules_by_key=rules_by_key, flyer_text=flyer_text)

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

    written = 0
    for row_product, _ in rows:
        spec = existing.get(row_product.id)
        if spec is None:
            spec = ProductSpecifications(product_id=row_product.id)
            db.add(spec)

        # A reviewer-confirmed value outranks anything derivable.
        kept_values, kept_provenance = {}, {}
        for key, entry in (spec.provenance or {}).items():
            if entry.get("source") == "human":
                kept_provenance[key] = entry
                if key in (spec.values or {}):
                    kept_values[key] = spec.values[key]

        spec.values = {**result.values, **kept_values}
        spec.provenance = {**result.provenance, **kept_provenance}
        # The only text spec search may match. Rendered here so it can never drift
        # from the values it describes.
        spec.rendered_text = render_spec_sentence(spec.values)
        spec.derived_hash = fingerprint
        spec.status = "needs_review" if result.exceptions else "derived"
        written += 1

    # Rebuild this code's open exceptions rather than appending, so a fixed input
    # clears its flag instead of accumulating a duplicate every run.
    db.query(ProductSpecException).filter(
        ProductSpecException.product_code == product_code,
        ProductSpecException.resolved_at.is_(None),
    ).delete(synchronize_session=False)
    for flagged in result.exceptions:
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

    db.flush()
    if commit:
        db.commit()

    return {"written": written, "skipped": 0, "exceptions": len(result.exceptions)}


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
    flyer_by_code = {row.product_code: row.text for row in db.query(ProductFlyerText).all()}

    totals = {"codes": 0, "written": 0, "skipped": 0, "exceptions": 0}
    for index in range(0, len(codes), chunk_size):
        for code in codes[index : index + chunk_size]:
            result = derive_for_code(
                db,
                code,
                rules_by_key=rules_by_key,
                scopes_by_key=scopes_by_key,
                flyer_text=flyer_by_code.get(code, ""),
            )
            totals["codes"] += 1
            for key in ("written", "skipped", "exceptions"):
                totals[key] += result[key]
        if commit:
            db.commit()

    return totals
