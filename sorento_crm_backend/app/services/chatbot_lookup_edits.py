"""The list-free parser prompt (CHAT-SLIM-INDEX S5): exact-text edits that take every list out of the
production parser text and add the `== LOOKUP LISTS ==` line.

Each anchor is text of the production-labelled version (v63, md5 0f3b48e6) that must appear exactly
once; any anchor missing or doubled leaves the text untouched (`apply` returns None). The lists these
spans carried reach the parser per turn instead, as the candidate blocks of `head/lookup_lists.py`
(row texts and `PROMPT_SYNONYMS` there hold the words that used to live here). Rule text that named a
removed per-turn line now names its block. Pure and stdlib-only, outside `app/services/chatbot/` on
purpose: a migration imports it, and the chatbot package pulls the engine (and a second DB connection).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

MARKER = "== LOOKUP LISTS =="

logger = logging.getLogger("alembic.runtime.migration")


@dataclass(frozen=True)
class Edit:
    op: str  # "replace" | "delete" (anchor = exact text) | "replace_line" (anchor = sha256 of one whole line)
    anchor: str
    payload: str  # one line; "" for a delete (or a replace_line that removes the line)


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
        'a name from the Brand candidates block (see the BRAND CANDIDATES rule below); never a fixed list',
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
    # The warehouse code list under the short-token rule: locations are the Location candidates block now.
    Edit(
        "replace",
        '== IN AN ORDER OR OUTSTANDING ASK, A SHORT TOKEN IS A LOCATION ==\nUnder domain_hint "order" (a DO / SO / outstanding question), a SHORT token that is not a\nproduct code and that follows "for", "at", "in", or stands alone beside the product, is a\nWAREHOUSE word. Emit it as an entity with hint "warehouse" - NEVER "customer".\nSHORT means one of exactly two shapes, and nothing else counts:\n  (a) at most 4 characters, letters or letters with one digit: "IB", "BB", "IR", "ACTS",\n      "SMC", "NTC", "RSV", "DFCT", "BILL", "BRW", "MWH", "RSW", "DC1", "WH3"\n  (b) a hyphenated site code of at most 10 characters: "BRW-IB", "MWH-IB", "BRW-ACTS"',
        '== IN AN ORDER OR OUTSTANDING ASK, A SHORT TOKEN IS A LOCATION == Under domain_hint "order" (a DO / SO / outstanding question), a SHORT token that is not a product code and that follows "for", "at", "in", or stands alone beside the product, is a WAREHOUSE word. Emit it as an entity with hint "warehouse" - NEVER "customer". SHORT means one of exactly two shapes, and nothing else counts: (a) at most 4 characters, letters or letters with one digit, as the Location candidates block spells a location; (b) a hyphenated site code of at most 10 characters, as that block spells it.',
    ),
    # The company code mapping line and the company list in SALES_COMPANY.
    Edit("delete", 'Company codes: Sorento = SRT, Mocha = MCH, Cabana = CBN (case-insensitive; "srt team" = Sorento).\n', ""),
    Edit(
        "replace",
        '== SALES_COMPANY: the company named, or null ==\n"Sorento" / "Mocha" (or the company\'s own name as typed) when the message names the\ncompany whose sales are asked about; null when none is named. Never a customer.',
        '== SALES_COMPANY: the company named, or null == The company whose sales are asked about, as the message names it (the company\'s own name as typed); null when none is named. Never a customer.',
    ),
    # The empty KNOWN BRANDS banner: its rule is the BRAND CANDIDATES rule below.
    Edit("delete", '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nKNOWN BRANDS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n', ""),
    # The file type list on the attachment_type entity line.
    Edit("replace", 'the KIND of document wanted: photo, image, technical drawing/spec, 3D model, certificate, installation guide.', 'the KIND of document wanted (the File type candidates block names the kinds).'),
    Edit("replace", '(photo | technical drawing | 3D model | certificate | installation guide)', '(the kind the File type candidates block names)'),
    # Lines that quoted a real customer or supplier name, anchored by the hash of the whole line and
    # replaced by the same line with a placeholder (a real name never enters the repository).
    Edit("replace_line", "9f2bc4a0db54f2b15a091e0d6141b0446bb085c1400ee38b5bf6fb35b6557dd8", '  - "for <customer name> only"               -> false (a customer)'),
    Edit("replace_line", "197740b14f87dfdaf43dfaab61dd0bd44d0761f8fbc921fdbcc49fac352f8fed", '                    question \u2014 "any delivery to <customer name> for srtwc286", "delivery status", "got'),
    Edit("replace_line", "f34581a224b8301912d8b89bf47098ed515b6ac35451cd08edd58e12e24374bf", '"request_for_help": the USER explicitly asks for a human, agent, or staff member to help. This fires on the user\'s own request. It takes priority over business_query, clarification, and casual \u2014 if the user asks for human help, classify as request_for_help even if they also mention a product or order. Merely asking you to share/send/provide DATA (a list, report, order status) is NOT a human-help request \u2014 that is business_query. request_for_help is ONLY a request for a HUMAN. A message that names a customer or product next to a delivery / order / DO word ("delivery to <customer name>", "hantar ke <customer name>", "any DO for X") is business_query, intent_hint check_order, domain_hint order, entity = that name with current_message true, is_escalation_confirmation false, even when an escalate offer is open.'),
    Edit("replace_line", "fb11a9da45644fb997c0047b59de5089124fd6cffa7b3ef820202cb2238a784e", '    phrase that names ONE thing ("water closet", "<customer name>"), or a part'),
    Edit("replace_line", "a2dabcfb7ebef30b9a8ef08d5c3cb9970e7ddb2a9e2bc40bfa261b28c758d4d6", '    without guessing. Example: "one <customer name> srtkt72ss" = quantity + a customer-ish name +'),
    Edit("replace_line", "20f9aee5f2d1abb6d7fdbcfcf9f9e1c83df23ff142cde723d10d2e20c79c0517", '    "customer one <customer name>, product srtkt72ss"'),
    Edit("replace_line", "0b196ff87efb918aef7cb106dedb684f82c6311aac0d85f1301858964b2e2125", '      → { "raw":"one <customer name>",  "hint":"customer", "confident":true }'),
    Edit("replace_line", "2ba13c26007da67ac27cacee72555159b819b3fa9b53911890a15771a4805404", 'WORKED EXAMPLES, over a question already scoped to SRTWC286-SH for <customer name>:'),
    Edit("replace_line", "7bb00c5588e1f887043c8b240cbbb3f5c801ec9cdaedb01bc5e2a930b55e9d03", '    <customer name>" gets'),
    Edit("replace_line", "e62f772e9b5eb35314602c0ff7a86b268981128c6c6afad7431cff95ab541335", '  - options "1. <customer name>, 2. <customer name>, 3. <customer name>, 4. <customer name>"'),
    Edit("replace_line", "9a6fdee87d94f2ab057aadd7e3f9a0be94fcb67e5a87fb0fe0fc524bee20cd7e", '  - options "1. Sales order list, 2. Delivery order list" + "delivery to <customer name>" ->'),
    Edit("replace_line", "4d7e57a00bb66a72667b62c62e3d7cd52d23bb38d859fb56d9f216806f047fbe", '    entities [<customer name> as customer], reference_positions []'),
    Edit("replace_line", "45f4c5b881759a7d262f904e887a0fd89a98b0055e4a9bd1c1d42a1b711106ff", 'request_for_help is ONLY a request for a HUMAN. A message that names a customer or product next to a delivery / order / DO word ("delivery to <customer name>", "hantar ke <customer name>", "any DO for X") is business_query, intent_hint check_order, domain_hint order, entity = that name with current_message true, is_escalation_confirmation false, even when an escalate offer is open.'),
    Edit("replace_line", "dabaa5c485590457a6e2105dae3d744a90464278d14bcaf5807e55dc2ed47bab", '  - suppliers: a supplier, vendor or factory NAME to filter by ("from <supplier name>",'),
    Edit("replace_line", "4c77fb0133916eee4489c419eacb6093fd4a5e170c2050525609c733998d23ea", '    "<supplier name> only", "pembekal X", "供应商 X"), as written. The word "supplier" or "vendor"'),
    Edit("replace_line", "79bf888615056f9e77c7309272b039c1da4e21869ba7c48915a8c1a391af7c13", '  - "low stock report water closet <supplier name>" -> categories ["water closet"], suppliers'),
    Edit("replace_line", "00869cda747163abfdabe4e8212102f4351c3ea7c178b9e0b5c71c26ef64eb72", '    ["<supplier name>"]'),
    Edit("replace_line", "dfa291df92829a771a444f45c651b3340678d8f6eb850865b6c63272bef13cf9", 'message that only names a filter or a grouping ("<supplier name> only", "by supplier", "sorento'),
    Edit("replace_line", "56052b9fc81fe5b8725b2a372d30b63fe8ed6496b6cd3b556ef327fe513dec25", 'field at all there. "outstanding dealer quantity for <customer name>" keeps order_status'),
    Edit("replace_line", "ab415facc673a56df333468f014a10b93fe166306222e67c36ee14ea98755f52", '  - "dealer sales report for <customer name>" -> sales_channel "dealer", entity {raw: "<customer name>", hint:'),
    Edit("replace_line", "3a8870ea44734c2f4a38d8268914d480f737d042499e03c02614dfff6953fbe0", 'was: top_n on that list ("last 3 DO for <customer name>" is an order list with top_n 3, never'),
    Edit("replace_line", "98d0540a354f47d5c627cda15ea7e1fb1670206f16fa13734d71550ad58cdb32", '  - CUSTOMER, a company that bought: "for <customer name>", "for <customer name> only" -> entity {raw:'),
    Edit("replace_line", "ecf5acb82626138af6256abaa753ab93417922ac5cc36d8e1f5520fcb3fb5eb7", '    "<customer name>", hint: "customer"}, exactly as anywhere else.'),
    Edit("replace_line", "e4da542d5e7b7b0764b42abaa205bb4fa949ebc298fa148b623d4f613a5dc2a2", 'false when the message names another party ("outstanding for <customer name>") or no one ("list'),
    Edit("replace_line", "b2205ea7092741e89652ffb61a14ce834da344b377bc7f5a80dfafc6cf44a541", 'the person to answer later. "PO for SRTWC8517", "delivery to <customer name>", "price of'),
    Edit("replace_line", "bc6fb7bc1622d6a81de4978e6ce80e6664a68c91e80c2efc05c7e232dc390909", 'orders records found for customer <customer name>. Would you like me'),
    Edit("replace_line", "957046097dd2b880236ec5af196ab49b5d93d6195928e56f19ecce360b3c673d", 'Anything LONGER than that is a CUSTOMER name, however it is capitalised: "<customer name>",'),
    Edit("replace_line", "d644222dcffdf3d88d3598b3c16f6d862bd2767ef8d393ae877f957bd8e271a4", '"<customer name>", "<customer name>", "<customer name>" are customer entities, never'),
    Edit("replace_line", "c6b4f273cc08bccaf3009af57374abbeeb0672921d9df6af21cfde3bf24045bd", '  - "how much did <customer name> sell this year" -> domain_hint "order", intent_hint'),
    Edit("replace_line", "d0c30a54da47092cafa56701870eb534001099f413a16b4ce8a90b0825ce19c6", '    "check_order", order_status "sales_report", entities [<customer name> as customer]'),
    Edit("replace_line", "c737ef98a91b9d3fed2cbc7d147b901fcd0c7b5fe8367cc77a43360485afb57b", '  - "dealer sales report for <customer name> March" -> sales_channel "dealer", entity {raw:'),
    Edit("replace_line", "65774d7c713ff3ad023ce6d1431b812c7538a16e9383297b60c6b6ac7d44d525", '    "<customer name>", hint: "customer"}, date_filter_start "2026-03-01", date_filter_end'),
    # Warehouse code examples in the rule text: the codes are Location candidates now, so the examples use a placeholder.
    Edit("replace", '  - "SRTWT7443 sales order outstanding for IB" -> SRTWT7443 is the product, "IB" is a\n    warehouse entity\n  - "any DO for SRTWT7445 at BRW", "outstanding in BRW-IB", "o/s at MWH", "backlog BB"\n    -> "BRW", "BRW-IB", "MWH", "BB" are warehouse entities', '  - "SRTWT7443 sales order outstanding for <warehouse code>" -> SRTWT7443 is the product, "<warehouse code>" is a warehouse entity; "any DO for SRTWT7445 at <warehouse code>", "outstanding in <warehouse code>", "backlog <warehouse code>" -> each <warehouse code> is a warehouse entity'),
    Edit("replace", '"at BRW"                        -> false (a place)', '"at <warehouse code>"                        -> false (a place)'),
    Edit("replace", 'outstanding how many at BRW?" -> document ["DO"]', 'outstanding how many at <warehouse code>?" -> document ["DO"]'),
    Edit("replace", 'outstanding how many at BRW?" ->\n    "do_outstanding" (product SRTWC8518-SH, warehouse BRW)', 'outstanding how many at <warehouse code>?" -> "do_outstanding" (product SRTWC8518-SH, warehouse <warehouse code>)'),
    Edit("replace", 'outstanding for IB" -> document ["SO"]', 'outstanding for <warehouse code>" -> document ["SO"]'),
    Edit("replace", 'outstanding for IB" -> "so_outstanding" (product\n    SRTWT7443, warehouse IB)', 'outstanding for <warehouse code>" -> "so_outstanding" (product SRTWT7443, warehouse <warehouse code>)'),
    Edit("replace", 'outstanding both at BRW-IB" -> document ["SO", "DO"]', 'outstanding both at <warehouse code>" -> document ["SO", "DO"]'),
    Edit("replace", 'outstanding both at BRW-IB" -> "outstanding_both"', 'outstanding both at <warehouse code>" -> "outstanding_both"'),
    Edit("replace", 'outstanding for SRTWT7445 at BRW" -> document [] (no paper named)', 'outstanding for SRTWT7445 at <warehouse code>" -> document [] (no paper named)'),
    Edit("replace", 'outstanding for SRTWT7445 at BRW" -> bare "outstanding" (no document', 'outstanding for SRTWT7445 at <warehouse code>" -> bare "outstanding" (no document'),
)


def _sha(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def apply(text: str) -> str | None:
    """`text` with every edit applied and the marker line appended as the last line, or None (with the
    reason logged) when any anchor is missing or found more than once, or the marker is already there.
    A `replace_line` anchor is the sha256 of one whole line, so a line that quotes a real name is never
    quoted here."""
    if any(ln.strip() == MARKER for ln in text.splitlines()):
        logger.info("lookup lists: the text already carries %s", MARKER)
        return None
    hashes: dict[str, int] = {}
    for ln in text.split("\n"):
        hashes[_sha(ln)] = hashes.get(_sha(ln), 0) + 1
    for edit in EDITS:
        found = hashes.get(edit.anchor, 0) if edit.op == "replace_line" else text.count(edit.anchor)
        if found != 1:
            logger.warning("lookup lists: anchor %r found %d times, nothing published", edit.anchor[:70], found)
            return None
    for edit in EDITS:
        if edit.op != "replace_line":
            text = text.replace(edit.anchor, edit.payload, 1)
    line_edits = {e.anchor: e.payload for e in EDITS if e.op == "replace_line"}
    if line_edits:
        kept: list[str] = []
        for ln in text.split("\n"):
            payload = line_edits.get(_sha(ln))
            if payload is None:
                kept.append(ln)
            elif payload:
                kept.append(payload)
        text = "\n".join(kept)
    return text.rstrip("\n") + "\n" + MARKER + "\n"
