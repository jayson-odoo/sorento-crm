"""The list-free parser prompt (CHAT-SLIM-INDEX S5): exact-text edits that take every list out of the
production parser text and add the `== LOOKUP LISTS ==` line.

Each anchor is text of the production-labelled version (v63, md5 0f3b48e6) that must appear exactly
once; any anchor missing or doubled leaves the text untouched (`apply` returns None). The lists these
spans carried reach the parser per turn instead, as the candidate blocks of `head/lookup_lists.py`
(row texts and `PROMPT_SYNONYMS` there hold the words that used to live here). Rule text that named a
removed per-turn line now names its block. Pure: no database, no I/O.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.chatbot.head.lookup_lists import MARKER

logger = logging.getLogger("alembic.runtime.migration")


@dataclass(frozen=True)
class Edit:
    op: str  # "replace" | "delete"
    anchor: str
    payload: str  # one line; "" for a delete


EDITS: tuple[Edit, ...] = (
    # Every Specification line (word and number keys) and the Product types line: now the Spec and Category candidate blocks.
    Edit(
        'delete',
        "\n".join((
        'Specification bar_count ("Number of bars"): a number. Words: bar, bars. Said in words: 1 (single towel bar, single bar, one bar); 2 (double towel bar, double bar, two bar, twin bar).',
        'Specification board_thickness ("Drainer board / countertop thickness"): a number in mm. Words: board thickness, drainer board thickness, countertop thickness, panel thickness, 面板.',
        'Specification bowl_count ("Number of bowls"): a number. Words: bowl, bowls. Said in words: 1 (single bowl, one bowl, 1 bowl, single sink); 2 (double bowl, two bowl, 2 bowl, twin bowl, double sink); 3 (triple bowl, three bowl, 3 bowl).',
        'Specification capacity_litre ("Capacity"): a number in L. Words: litre, liter, capacity, volume, size in litre.',
        'Specification capacity_oz ("Capacity (oz)"): a number in oz. Words: oz, ounce, ounces.',
        'Specification control_type ("Control type"): choices Single lever = single_lever (single lever, single handle, one lever); Two way = two_way (two way, 2 way, dual); Self closing = self_closing (self closing, self-closing, push, delay action); Sensor = sensor (sensor, automatic, auto, touchless).',
        'Specification depth ("Depth"): a number in mm. Words: depth, deep.',
        'Specification diameter ("Diameter"): a number in mm. Words: diameter, dia, across.',
        'Specification dim_height ("Height"): a number in mm. Words: height, tall, high.',
        'Specification dim_length ("Length"): a number in mm. Words: length, long.',
        'Specification dim_width ("Width"): a number in mm. Words: width, wide.',
        'Specification finish ("Finish or colour"): choices Black = black (black, matt black, matte black); Gunmetal = gunmetal (gunmetal, gun metal); Nickel = nickel (nickel, brushed nickel); Grey = grey (grey, gray); Rose gold = rose_gold (rose gold, rosegold); Chrome = chrome (chrome, polished chrome); French gold = french_gold (french gold, gold); White = white (white); Satin chrome = satin_chrome (satin chrome, satin); Golden yellow = golden_yellow (golden yellow, gold yellow, yellow gold).',
        'Specification flush_type ("Flush type"): choices Washdown = washdown (washdown, wash down, wash-down); Siphonic = siphonic (siphonic, syphonic); Twister = twister (twister flush, twister flushing, twister).',
        'Specification furniture_type ("Furniture type"): choices Basin cabinet = basin_cabinet (basin cabinet, vanity, vanity cabinet, under basin cabinet); Side cabinet = side_cabinet (side cabinet, storage cabinet); Tall cabinet = tall_cabinet (tall cabinet, tall unit, column cabinet).',
        'Specification has_chopping_board ("Chopping board"): yes or no. Words: chopping board, cutting board, with board.',
        'Specification has_dish_rack ("Dish rack"): yes or no. Words: dish rack, drying rack, with rack.',
        'Specification has_diverter ("Diverter"): yes or no. Words: diverter, with diverter, divertor.',
        'Specification has_drainer ("Has a drainer board"): yes or no. Words: drainer, with drainer, drainer board, drain board.',
        'Specification has_filter ("Water filter"): yes or no. Words: filter tap, filter, with filter, water filter.',
        'Specification has_fixing_screw ("Comes with a fixing screw"): yes or no. Words: basin screw, fixing screw, c/w screw, with screw.',
        'Specification has_led ("LED light"): yes or no. Words: led, led light, lighted, illuminated, with light.',
        'Specification has_overflow ("Has an overflow"): yes or no. Words: overflow, with overflow, c/w overflow, overflow hole.',
        'Specification has_pull_out_shower ("Pull-out shower"): yes or no. Words: pull out shower, pull-out shower, pull out spray.',
        'Specification has_shower_union ("Shower union"): yes or no. Words: shower union, union, wall union.',
        'Specification has_sliding_rail ("Sliding rail"): yes or no. Words: sliding, sliding bar, sliding rail, adjustable rail.',
        'Specification hose_length ("Hose length"): a number in mm. Words: hose, hose length, pipe, tube.',
        'Specification is_frameless ("Frameless"): yes or no. Words: frameless, frame less, no frame, borderless.',
        'Specification is_high_basin ("High basin"): yes or no. Words: high basin, tall basin, vessel height, high rise.',
        'Specification is_honeycomb ("Honeycomb structure"): yes or no. Words: honeycomb, honey comb, honeycomb structure.',
        'Specification is_rimless ("Rimless"): yes or no. Words: rimless, rim less, no rim.',
        'Specification is_smart ("Intelligent / smart toilet"): yes or no. Words: intelligent toilet, intelligent, smart toilet, smart wc, auto induction.',
        'Specification is_soft_close ("Soft close"): yes or no. Words: soft close, soft closing, slow close, damper.',
        'Specification is_thermostatic ("Thermostatic"): yes or no. Words: thermostatic, temperature control, constant temperature.',
        'Specification material ("Material"): choices Stainless steel = stainless_steel (stainless, stainless steel, s/steel, steel, inox); Ceramic = ceramic (ceramic, porcelain); Glass = glass (glass, tempered glass); PVC = pvc (pvc, plastic); Brass = brass (brass); Acrylic = acrylic (acrylic); ABS = abs (abs, abs plastic); Nanograin = nanograin (nanograin, nano grain, nano); Granite = granite (granite, granite stone, quartz); Marble = marble (marble, marble top, marmar).',
        'Specification mounting ("Mounting"): choices Wall hung = wall_hung (wall hung, wall mounted, wall mount, hang on wall); Pedestal = pedestal (pedestal, with pedestal); Concealed = concealed (concealed, hidden, in wall); Counter top = counter_top (counter top, countertop, above counter, on counter, top mount, table top, tabletop); Under counter = under_counter (under counter, undermount, under mount, below counter); Pillar mounted = pillar_mounted (pillar mounted, pillar mount, pillar tap, pillar); Semi recessed = semi_recessed (semi recessed, semi-recessed, half recessed); Exposed = exposed (exposed, exposed shower, surface mounted); Free standing = free_standing (free_standing, floor standing, floor mounted).',
        'Specification no_overflow ("Without overflow"): yes or no. Words: without overflow, no overflow, w/o overflow.',
        'Specification piece_count ("Pieces in the set"): a number. Words: in 1, piece set, pieces, set of.',
        'Specification power_hp ("Power"): a number in hp. Words: horsepower, hp, power, motor.',
        'Specification seat_cover ("Seat Cover"): choices SRTSCBD319-UF = srtscbd319-uf (srtscbd319-uf); SRTSCBD330-UF = srtscbd330-uf (srtscbd330-uf); SRTSCBD331-UF = srtscbd331-uf (srtscbd331-uf); SRTSCBD332-UF = srtscbd332-uf (srtscbd332-uf); SRTSCBD289-UF = srtscbd289-uf (srtscbd289-uf); SRTSCBD333-UF = srtscbd333-uf (srtscbd333-uf); SRTSCBD403 = srtscbd403 (srtscbd403); SRTSCBD324 = srtscbd324 (srtscbd324); SRTSCBD323 = srtscbd323 (srtscbd323); SRTSCBD320 = srtscbd320 (srtscbd320); SRTSCBD407 = srtscbd407 (srtscbd407); SRTSCBD401 = srtscbd401 (srtscbd401); SRTSCBD329 = srtscbd329 (srtscbd329); SRTSCBD315 = srtscbd315 (srtscbd315); SRTSCBD313 = srtscbd313 (srtscbd313); SRTSCBD325 = srtscbd325 (srtscbd325); SRTSCBD326 = srtscbd326 (srtscbd326); SRTSCBD327 = srtscbd327 (srtscbd327); SRTSCBD823-MBL = srtscbd823-mbl (srtscbd823-mbl); SRTSCBD824-BL = srtscbd824-bl (srtscbd824-bl); SRTSCBD834-MBL = srtscbd834-mbl (srtscbd834-mbl); SRTSCBD833-BL = srtscbd833-bl (srtscbd833-bl); SRTSCBD825-GY = srtscbd825-gy (srtscbd825-gy); SRTSCBD826-RG = srtscbd826-rg (srtscbd826-rg); SRTSCBD835-GY = srtscbd835-gy (srtscbd835-gy); SRTSCBD841-BL = srtscbd841-bl (srtscbd841-bl); SRTSCBD842-MBL = srtscbd842-mbl (srtscbd842-mbl); SRTSCBD843-GY = srtscbd843-gy (srtscbd843-gy); SRTSCBD844-RG = srtscbd844-rg (srtscbd844-rg).',
        'Specification seat_material ("Seat cover material"): choices PP = pp (pp, pp seat, pp seat cover, polypropylene, plastic seat); Uf = uf (uf, uf seat, uf seat cover, urea, urea formaldehyde); Duroplast = duroplast (duroplast, duroplast seat, soft close seat).',
        'Specification shape ("Shape"): choices Round = round (round, circular); Square = square (square); Rectangular = rectangular (rectangular, rectangle); Oval = oval (oval, ellipse).',
        'Specification spout_type ("Spout"): choices Flexible = flexible (flexible, flexible head, flexi, bendable, hose spout); Double flexible = double_flexible (double flexible, double spout); Pull out = pull_out (pull out, pull-out, extendable, pull down); Swivel = swivel (swivel, rotating, turnable); Gooseneck = gooseneck (gooseneck, goose neck, high arc); Waterfall = waterfall (waterfall, water fall, cascade).',
        'Specification spray_functions ("Spray functions"): a number. Words: function, functions, spray, mode, modes, setting. Said in words: 1 (single function, 1 function, one function); 2 (2 function, two function, double function); 3 (3 function, three function, triple function); 5 (5 function, five function).',
        'Specification steel_grade ("Steel grade"): choices 304 = 304 (304, sus304, grade 304, s/steel 304, stainless steel 304); 201 = 201 (201, sus201, grade 201, s/steel 201).',
        'Specification surface_texture ("Surface texture"): choices Normal = normal (normal finish, normal surface); Honeycomb = honeycomb (honeycomb, honey comb, hc); Nano Volcano = nano_volcano (nano volcano, volcano); Nano Grain = nano_grain (nano grain, nanograin, grain); Andria Series = andria_series (andria, andria series).',
        'Specification thickness ("Thickness"): a number in mm. Words: thickness, thick, gauge.',
        'Specification trap_length ("Trap outlet length"): a number in mm. Words: trap.',
        'Specification trap_type ("Trap"): choices S trap = s_trap (s trap, s-trap, floor outlet, floor waste); P trap = p_trap (p trap, p-trap, wall outlet, wall waste).',
        'Specification water_supply ("Water supply"): choices Cold only = cold_only (cold tap, cold only, single cold, cold water tap); Mixer = mixer (mixer, mixer tap, hot and cold, hot cold, mixer type).',
        'Specification way_count ("Ways (diverter outlets)"): a number. Words: way, ways, outlet, outlets, diverter way.',
        'Product types (the category entity keeps these, never a specification): Angle valve, Bib tap, Basin tap, Kitchen tap, Shower tap, Mixer tap, Hand shower, Rain shower, Shower set, Shower head, Close coupled, One piece, Art basin, Mirror cabinet, Pop up waste, Towel bar, Towel shelf, Hook bar, Robe hook, Corner basket, Paper holder, Grab bar, Soap dispenser, Flexible hose, Flush valve, Floor trap, Floor grating, Cistern, Tumbler, Mirror, Bidet, Toilet seat, Urinal, Toilet brush, Squatting pan, Towel ring, Dustbin, Bottle trap, Water pump, Hinge, Shower seat, Handrail, Drain pipe, Stop cock.',
    )) + "\n",
        '',
    ),
    # The category examples and the translations (now PROMPT_SYNONYMS data and the Category candidates block); the rule clauses stay.
    Edit(
        'replace',
        'each KIND of product named ("water tap", "tap", "water closet", "basin\n    mixer", "kitchen sink", "shower", or a category code like "SRT-FT"), in English, without\n    the brand and without "only", "for", "category". Translate: "paip air", "kepala paip",\n    "水龙头" -> "water tap"; "tandas", "mangkuk tandas", "马桶" -> "water closet"; "sinki dapur",\n    "厨房水槽" -> "kitchen sink". A number inside a category name keeps it a category.',
        'each KIND of product named, in English, without the brand and without "only", "for", "category". A number inside a category name keeps it a category.',
    ),
    # Brand example list.
    Edit(
        'replace',
        'brands: brand words ("sorento", "mocha", "cabana", or one from Known brands), as written.',
        'brands: brand words from the Brand candidates block, as written.',
    ),
    # Entity hint table.
    Edit(
        'replace',
        'a name from the Known brands: line (see KNOWN BRANDS below); never a fixed list',
        'a name from the Brand candidates block (see KNOWN BRANDS below); never a fixed list',
    ),
    # The KNOWN BRANDS rule: the per-turn Known brands line is now the Brand candidates block; the Sorento / Mocha example pair is dropped.
    Edit(
        'replace',
        "\n".join((
        '== KNOWN BRANDS: entities[].hint "brand" ==',
        'The user block carries a "Known brands:" line, built fresh every turn from the live',
        'catalogue - the ONLY valid brand names are the ones it lists THIS turn, never a name',
        'from earlier training and never carried over from an earlier turn. A token matching',
        'one of those names, or the code in parentheses beside it, is a brand entity: "raw" is',
        'the word the customer typed, "canonical_code" is the brand name exactly AS LISTED on',
        "the Known brands line - never the parenthesised code, never the customer's own",
        'spelling or case.',
        '  - Known brands: Sorento (SRT), Mocha (MCH) - "brand Sorento" -> entity {raw:',
        '    "Sorento", hint: "brand", canonical_code: "Sorento"}',
        '  - Same line, "MCH stock" -> entity {raw: "MCH", hint: "brand", canonical_code:',
        '    "Mocha"}',
        'A word that is NOT on the Known brands line is never hinted "brand" - read it as',
        'whatever it would otherwise be (a product code, a customer name, a description).',
        'No "Known brands:" line at all this turn (nothing active) means no brand entity can',
        'be named at all - fall back to whatever other hint the word would otherwise carry.',
    )),
        '== BRAND CANDIDATES: entities[].hint "brand" == The user block carries a "Brand candidates" block, built fresh every turn from the live catalogue - the ONLY valid brand names are the ones it lists THIS turn, never a name from earlier training and never carried over from an earlier turn. A token matching one of those names, or the code in parentheses beside it, is a brand entity: "raw" is the word the customer typed, "canonical_code" is the brand name exactly AS LISTED in the block - never the parenthesised code, never the customer\'s own spelling or case. A word that is NOT in the block is never hinted "brand" - read it as whatever it would otherwise be (a product code, a customer name, a description). No Brand candidates block this turn means no brand entity can be named at all - fall back to whatever other hint the word would otherwise carry.',
    ),
    # Brand example list in the follow-up rules.
    Edit(
        'replace',
        'a name from "Known brands" or "Sorento", "Mocha", "Cabana":',
        'a name from the Brand candidates block:',
    ),
    # spec_key source.
    Edit(
        'replace',
        'a key from the Specification lines of the policy block, or null',
        'the key in the "(key: value)" bracket of a Spec candidates line of the user message, or null',
    ),
    # spec_value source.
    Edit(
        'replace',
        'one of that key\'s choices (the value after "="), a number for a',
        'the value in that same bracket of the Spec candidates line, a number for a',
    ),
    # The attachment type word maps (now PROMPT_SYNONYMS data and the File type candidates block).
    Edit(
        'replace',
        "\n".join((
        '  - "photo","actual photo","image","picture", "how does it look","what does it look like",',
        '    "looks like","appearance","show me","see it"  → attachment_type "photo"',
        '  - "videos","actual video"  → attachment_type "video"',
        '  - "drawing","technical drawing","spec","CAD","blueprint" → attachment_type "technical drawing"',
        '  - "installation guide", "installation manual" → attachment_type "installation_guide"',
        '  - "cert","certificate","Ikram"                          → attachment_type "certificate"',
        'attachment_type canonical_code is always the taxonomy value (photo, video, technical drawing, 3D model, certificate, installation guide), never the customer\'s own word: "image", "picture", "gambar" are all photo.',
    )),
        'attachment_type canonical_code is always the taxonomy value of the kind the message means, never the customer\'s own word; a look-and-feel request ("how does it look", "looks like", "show me", "see it") implies a photo.',
    ),
    # The file type translation map.
    Edit(
        'replace',
        'translating ANY language or synonym (gambar/foto→photo; imej→image; lukisan teknikal/spec→technical drawing; model 3D→3D model; sijil/cert→certificate)',
        'translating ANY language or synonym',
    ),

    # The specification entity's vocabulary: the Specification lines are now the Spec candidates block.
    Edit(
        'replace',
        'ONLY a key\n      that has a "Specification <key>" line in the policy block below; the choices and\n      the words listed on that line are the whole vocabulary, in any language.',
        'ONLY a key that a Spec candidates line of the user message names in its "(key: value)" bracket (spec_key and spec_value come from that bracket); the lines of that block are the whole vocabulary, in any language.',
    ),
)


def apply(text: str) -> str | None:
    """`text` with every edit applied and the marker line appended as the last line, or None (with the
    reason logged) when any anchor is missing or found more than once, or the marker is already there."""
    if any(ln.strip() == MARKER for ln in text.splitlines()):
        logger.info("lookup lists: the text already carries %s", MARKER)
        return None
    for edit in EDITS:
        found = text.count(edit.anchor)
        if found != 1:
            logger.warning("lookup lists: anchor %r found %d times, nothing published", edit.anchor[:70], found)
            return None
    for edit in EDITS:
        text = text.replace(edit.anchor, edit.payload, 1)
    return text.rstrip("\n") + "\n" + MARKER + "\n"
