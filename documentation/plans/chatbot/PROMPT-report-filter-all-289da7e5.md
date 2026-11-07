# Parser prompt change: explicit ALL for report filters (REPORT-FILTER-ALL)

- Base: production v72, md5 `d29c19830b22aa47403a88ddcb8e817d`. This is the v202 text the owner published, less two v71
  lines; the exact file is `prompt-prod-v72-d29c1983.txt`.
- Result: md5 `289da7e56130a489ecb624031996acc2` (round 5, edits 1-11); the exact file is `prompt-report-filter-all.txt`.
  Round 4 was md5 `d51a084c46ea5afee1a6775ced30f607` (edits 1-10, crew v78, re-check 6 Nov). Round 3 was md5 `5a58739ad208e2a2bc4d081c9087816c` (edits 1-9, crew v77, targeted re-check 6 Nov). Round 2 was md5 `e9421dede66c100a5f75db1db7c6a1e2` (edits 1-7) and round 1 was md5
  `698e137b692ff61ce48bf1c1e4aa7571` (edits 1-4); crew gated both (below).
  `tests/chatbot/test_report_filter_all.py::test_p1_*` pins both md5s.
- Not published: only the owner moves the production label.
- Owner rule kept: these are slot rules only, with no gold-message examples and no word lists.
- The two v71 lines that v72 lacks are not restored here (crew, 5 Nov: only if the gate shows they matter).

Code that keys on this text: `parser.REPORT_ALL_WORD` (`["ALL"]`) turns on `"ALL"` in
`ParserConfig.report_ask_defined`. With it:
- The schema's report_ask channel enum offers "ALL".
- The engine passes `all_value=True` to `report_ask.from_object`, so an empty slot is "not said" and only ALL clears.
- The legacy `broaden_axis` / `broaden_to` / `scope_intent` / `entity_op` fields are not read for reports.

v72 (no `["ALL"]`) keeps the temporary adapter `report_ask._legacy_all`.

## Edits (all in `== REPORT_ASK ==`, apply by anchor)

1. Object shape line: `"channel": "dealer|project|null", "company": "string|null"` becomes
   `"channel": "dealer|project|ALL|null", "company": "string|ALL|null"`.
2. Slot bullet. The sentence `A message that widens a slot to every value ("all" of it) empties that list.` becomes:
   `A message that widens a slot to every value, or clears or removes its filter, writes ALL in that slot: company "ALL", channel "ALL", a list ["ALL"].`
3. A new bullet before `  - An answer to the open question fills the asked slot and keeps the rest:`:
   `  - ALL is the only way to clear a filter: a slot left [] or null is a slot this message did not touch, and the held value stays. Removing one name from a list writes the list without it; removing its last name writes ["ALL"]. Clearing every filter at once writes ALL in company, channel, sales_agents, account_types, brands, categories, customers and products, and keeps basis, date_from, date_to, frame, group_by and top_n as held. A Held report slot that is empty is already every value: copy it empty, never as ALL.`
4. One-name bullet. `the word company -> company only (brands stays without it);` becomes
   `the word company -> company only (brands stays without it, ["ALL"] when it was the only brand);`

5. (round 2, crew gate: BM / mixed "clear all" kept the company or brand, fa-03 / fa-12 moved the axis) The ALL
   bullet's clear-every-filter sentence becomes: `A message that asks for the report with no filter at all, in any language or wording, clears every filter at once: it writes ALL in company, channel, sales_agents, account_types, brands, categories, customers and products, the company and the brands included even when an earlier turn named them, and keeps basis, date_from, date_to, frame, group_by and top_n as held. Writing ALL never changes frame, group_by or top_n.`
6. (round 2, crew gate step 1: "show dealer and project" gave one total with channel ALL) In the frame bullet,
   `... is a breakdown on that slot's group_by.` becomes
   `... is a breakdown on that slot's group_by (frame breakdown), even beside a word for total; that slot itself stays as held, never ALL.`
7. (round 2, crew gate tf-16: company "Mocha, Sorento" for "both") Before `The lists and company hold NAMES ...`:
   `company holds ONE company name, or ALL for every company the user holds (never two names joined).`

8. (round 3, crew gate 6 Nov: fa-13/14/16/18/20/30/32 kept company and channel on a clear-all) Before the copy-first
   bullet's `Every slot the message does not touch stays exactly as held: ...`:
   `A message that asks for no filter touches every filter slot: the company and the channel are filters exactly like the lists, so they become ALL too although the Held report holds them (only slots the Held report already holds empty stay empty).`
9. (round 3, crew gate step 16: "brand" to the company-or-brand question kept Company Sorento) In the one-name bullet,
   `the word brand -> brands only (company stays as held);` becomes
   `the word brand -> brands only (company stays as held; a reply that picks brand for a name the assistant asked about never writes that name in company);`

10. (round 4, crew re-check steps 8 / 14: "Sorento company, Sorento brand" ran the brand only) On the entity line,
    `"said_as": what said_as_text says: "company", "brand", "both" (both words); null whenever said_as_text is null }` gains
    `; a name this message calls a company in one place and a brand in another is ONE entity whose said_as_text holds both words and whose said_as is "both" }`.
    The code reads a name's slot from said_as, never from the object's company slot alone ("brand only" parses also write
    the company: ON-2, F2, tf-29), and since round 4 of the code it merges two entities of one name (company + brand = both).

11. (round 5, crew re-check on v78: step 1 came back frame total with NO group_by) In the frame bullet,
    `A message that asks for a total sets frame total with group_by and top_n null, whatever the Held report had.` becomes
    `A message that asks for a total, and asks to see no slot's values one by one, sets frame total with group_by and top_n null, whatever the Held report had; a message that also asks to see a slot's values (side by side, each one, split) is a breakdown on that slot, its words for a total notwithstanding, and the top-level group_by names that slot too.`
    Code backs it (round 6): a total whose object names no axis takes the top-level group_by under the K1 guards (K1b).

## Gate (crew runs it on the Mac; this sandbox has no Gemini key and no prod-copy DB)

- Gold: `scripts/chatbot_eval/gold/parser_report_filter_all.jsonl`, 28 rows. 16 of them are EN / BM / ZH mixes in the owner's style (clear every filter with no keyword, one slot to ALL). The other 12: clear brand, all brands, any agent, clear
  company, all companies, clear all, remove one of two brands, all customers, all channels, two forgotten-echo
  controls, and "all brands" with nothing held.
- Regression controls: re-run `parser_report_totals_filters.jsonl` and `parser_report_semantic_carry.jsonl` on the
  candidate. Their clear rows (written for `[]`) now expect ALL for the cleared slot.
- Spend cap: USD 0.70 total on the ORG key, ledgered by crew.

| Run | Text | Set | Pass | Note |
|---|---|---|---|---|
| crew 5 Nov, x1, gemini-3.5-flash-lite | 698e137b | filter_all fa-01..28 | 21/28 raw (base 4/28) | fails fa-14/16/18/20 (clear all kept company + channel), fa-15, fa-03/fa-12 (axis moved) |
| crew 5 Nov | 698e137b | totals_filters tf-01..34 | 16/34 raw, 25/34 effective (base 26/34) | most raw fails: ALL where the old gold wanted []; tf-27, tf-16 |
| crew 5 Nov | 698e137b | semantic_carry sc-01..16 | 13/16 | |

| crew 6 Nov, x1, gemini-3.5-flash-lite | e9421ded | filter_all fa-01..37 | 26/37 raw, 28/37 effective (base 5/37 raw, 20/37 effective) | fa-30, fa-32 write company Sorento; fa-13/14/16/18/20 keep channel + company; fa-34, fa-11/12, fa-36 |
| crew 6 Nov | e9421ded | totals_filters tf-01..34 (ALL gold) | 23/34 raw, 26/34 effective | tf-03/04/08 channel ALL, tf-13/16/27/28, tf-25/26 |
| crew 6 Nov | e9421ded | semantic_carry sc-01..16 | 13/16 | sc-01, sc-15, sc-16 |

Crew spend 6 Nov: gate 0.336 + replays 0.207 + console pass 0.091 = USD 0.633 of 0.70, ledgered by crew.

| crew 6 Nov targeted re-check, v77 | 5a58739a | fa-13/14/18/30/32, steps 9-11, 14 clears, 15, EN clear-all, T5-T9 smoke | PASS | FAIL: steps 8, 14, 16 (company with the word Sorento), 17 (from 16); fa-16 / fa-20 keep channel dealer; fa-36 / step 1 no split on the first turn |

| crew 6 Nov re-check, v78 | d51a084c | steps 8, 16, 17, BM + EN clear all | PASS | FAIL: step 1 (frame total, no group_by); step 14a (company + brand parsed, brand only shown: code, the CP-5 branch) |

Gold corrections for round 3 (no live run from this sandbox):
- fa-06, fa-13..20 and fa-29..34 expected ALL in slots the Held report holds EMPTY. The prompt says such a slot is copied
  empty, never ALL, so those expectations were wrong and are now `[]` / null. Part of the 6 Nov fa-13/14/16/18/20/34 fails
  was this gold error; the rest is the parser keeping company and channel (edit 8).
- +3 rows: fa-38 (step 8, "Sorento company, brands Sorento and Cabana": both), fa-39 (step 14, "Sorento company,
  Sorento brand": both), fa-40 (step 16, "brand" to the open company-or-brand question: brands only, company null).

Crew spend 5 Nov: gate 0.367 + replays 0.117 + console pass 0.075 = USD 0.558 of 0.70, ledgered by crew.

Gold changes for round 2 (to re-gate on e9421ded; no live run from this sandbox, the ORG key is near its daily cap):
- `parser_report_filter_all.jsonl` +9 rows (fa-29..37): the crew's exact failing clear-all phrasings over the hand-test
  report (EN, BM, ZH, mixed), T5's shape (company + brand + category held), T8 "all brand all category", step 1's
  fresh "show dealer and project" (a breakdown, never ALL) and "both companies" (ALL).
- `parser_report_totals_filters.jsonl`: tf-17, tf-18, tf-19, tf-20 (clears) and tf-28 (the only brand moved to the
  company) now expect `["ALL"]` where they expected `[]`: the new semantics, where `[]` means "not touched".
