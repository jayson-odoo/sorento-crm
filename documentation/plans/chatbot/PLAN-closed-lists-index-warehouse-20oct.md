# PLAN: CLOSED-LISTS-INDEX-MODE round 2 - warehouse and finish short forms join the index

Status: Build (explore branch crew/closed-lists-index-explore1020 only; not #1755 / main). Track: full (LEAD pattern).
Source: owner 20 Oct ~22:35 MYT "i thought warehouse should be indexed also just like spec?" + crew brief (the "frg" bug).

## Root cause (code check on 4cd6d4d930)

- parser_template.py:170 tells the parser that a short token (at most 4 letters, or letters with one digit) after
  "for / at / in" or beside the product is a warehouse, so "frg" is hinted `warehouse`.
- Grounding never checks a warehouse hint (head/grounding.py:772-779 touches class / spec / attachment / product hints
  only), so turn/apply.py:1085-1110 writes "frg" onto focus.warehouse and it rides every later turn.
- "-FRG" is the registry's own finish code suffix (product_spec_registry.py:301-305 derivation rule, texts ["-FRG"],
  value french_gold; product_spec_derivation.py:469), which index mode never shows the parser.

## ARCHITECTURE (owner 20 Oct: layer, shared mechanism, other classes fixed, special cases removed)

Layers DATA -> candidates (index) and GROUNDING. One mechanism: index mode's per-turn closed list
(head/closed_lists_index.py, message-word match by code / name / alias, exact or near spelling at the candidates.py
thresholds; near spelling adds lines only and never binds) gains two sources read from data, never word lists:
- W1 warehouses: the `warehouses` table, matched on code, name, and the code's last `-` segment (the same reading
  as resolve_warehouse_token, lanes/business/services.py:497-533). Listed under the candidates header for this turn.
- W3 finish short forms: the registry's own derivation code-suffix texts (kind "code", code_match ends_with):
  a typed "frg" lists "finish = french_gold" for this turn only.
- W2 grounding: in index mode a warehouse hint the registry does not resolve is dropped, through the same path as
  the attachment-type drop (grounding.py:966-999 -> verdict dropped_kinds -> turn/apply.py:1111-1115 clears the axis).
Removes, in index mode only: the "<= 4 letters is a warehouse" shape rule. The rendered prompt replaces that rule
with "a warehouse is one the index lists" (fixed text, so the system prompt stays byte-equal across turns; the
template file is not edited: prompt freeze, crew a29691875). Block mode byte-identical (tests pin it).

## Acceptance (red first)

- IW-1 index mode, message "frg" (no warehouse FRG exists): the index lists `finish = french_gold`, no warehouse
  line; a warehouse hint "frg" is dropped by grounding and focus.warehouse is not written (an earlier held
  warehouse is cleared, as dropped_kinds does for file types).
- IW-2 a real warehouse code (e.g. "BRW") and a suffix ("IB" -> BRW-IB, MWH-IB): listed; the hint is kept and
  resolves as today.
- IW-3 a 3-4 letter non-warehouse word ("stok", "ada"): no warehouse line; a warehouse hint on it is dropped.
- IW-4 the WH collision: "wh3" (a warehouse code in the seeded world) lists the warehouse; "wh" alone lists
  finish white and any warehouse whose code or suffix is WH; neither binds by itself.
- IW-5 block mode: prompt and grounding byte-identical to 4cd6d4d930 (the I-series guards stay green).
- IW-6 the index-mode system prompt is byte-equal across turns (I8 pattern) with the rule replaced.

## Gate

Opus reviewer READY; tests/chatbot/test_closed_lists_index_mode.py + the new file + touched suites green; parser
gold on TRAIN location / warehouse + spec items in index mode, x1 with early stop, cap USD 1.0 total.

## Round 2b (Opus review NOT READY on 9bce884b56)

Built: red 61d77c5cc1, fix 58d4f909d5, seed shape 9bce884b56 (lead sign-off), harness 51bf7b8f96 / 6f71442ba8
(parser_gold renders the engine's fresh turn, `--closed-lists-mode`, `warehouse` expect key).
Review findings taken: (1) no test keeps a suffix hint; (2) the index listed a warehouse by NAME that grounding and
the lane cannot resolve (HQ "HEADQUARTER"), so the hint dropped and the held axis cleared; (3) the replacement
sentence said "short token" but no longer defined short, so a word code (PROJECT, SAMPLE, SHOWROOM, PENANG on the
real DB) could become a warehouse in index mode; (4) IW-4 "binds nothing" could not fail, no -WH warehouse seeded;
(5) nothing pinned the fail-loud ParserError.

ARCHITECTURE: one warehouse reading everywhere. The index lists, for a message word, exactly what
resolve_warehouse_token resolves (exact code wins, else the last-"-" suffix; no name, no near spelling), so the
index never offers what grounding and the lane cannot keep. The index-mode sentence keeps the original short-token
shape definition and adds one condition ("and only when the index lists it"), so index mode can only REMOVE a
warehouse hint relative to block, never add one. Removes: name matching and near spelling for warehouses.

- IW-7 a warehouse hint "IB" keeps BRW-IB and MWH-IB; no clears-axis rule fires.
- IW-8 "stock at headquarter" (HQ named HEADQUARTER) lists no warehouse line.
- IW-9 "hq" lists HQ only (not MKTG-HQ / SD-HQ); "at wh3" lists WH3 only (not WH3-AM).
- IW-10 "wh" lists finish white AND the -WH warehouses (MOCHA-WH seeded); a warehouse hint "wh" keeps them.
- IW-11 system_prompt on a template version without the sentence raises ParserError; a legacy version is unchanged.
- IW-6 amended (lead sign-off, design change above): the index system prompt keeps the shape definition and adds
  the "index lists" condition; byte-equal across turns.
Gold (index arms only, block unchanged): word codes "for project only", "sample", "showroom", "penang" never become
warehouses; the 6 order rows and 7 location rows stay 6/6 and 7/7.

## Round 2c: option B (crew a11138672, measured)

Parser gold (crew/state cap USD 1.0; rows: 10 TRAIN finish short forms beside codes, 7 synthetic location, 6 synthetic
order-shaped, 5 synthetic word-code; explore DB codes): W1 listing made the parser hint word codes as warehouses
("outstanding SO for project SRTWC286" -> PROJECT on v81-index and v88-index, "penang ..." on v81-index; block 5/5
clean), and on the copy's legacy prompt family (v81 ~ v77) W1 added 0 passes. The frg / RG fixes come from W3 and W2.

ARCHITECTURE: the warehouse closed list lives at the GROUNDING layer, not in the parser prompt. Kept: W3 (finish
short-form lines from the registry's code-suffix rules), the one-reading helper services.warehouse_codes_for
(lanes + grounding). Removed: W1 Warehouse lines and the index-mode replacement sentence (the warehouse rule of the
template is unchanged in index mode). W2 narrowed after the Opus review (AC-38, grounding.py:891-895: an unknown
filter word is said back, never dropped to answer unfiltered): in index mode a warehouse hint warehouse_codes_for
cannot resolve is dropped ONLY when its word is a registry finish short form (W3's data), and that drop does not
clear the held warehouse (the customer named a finish, not a warehouse). A resolvable code always wins ("wh" ->
MOCHA-WH / NEW-WH). Any other unknown warehouse word is kept and said back, as in block mode.
