# Parser prompt change: explicit ALL for report filters (REPORT-FILTER-ALL)

- Base: production v72, md5 `d29c19830b22aa47403a88ddcb8e817d`. This is the v202 text the owner published, less two v71
  lines; the exact file is `prompt-prod-v72-d29c1983.txt`.
- Result: md5 `698e137b692ff61ce48bf1c1e4aa7571`, 115,587 bytes; the exact file is `prompt-report-filter-all.txt`.
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

## Gate (crew runs it on the Mac; this sandbox has no Gemini key and no prod-copy DB)

- Gold: `scripts/chatbot_eval/gold/parser_report_filter_all.jsonl`, 12 rows: clear brand, all brands, any agent, clear
  company, all companies, clear all, remove one of two brands, all customers, all channels, two forgotten-echo
  controls, and "all brands" with nothing held.
- Regression controls: re-run `parser_report_totals_filters.jsonl` and `parser_report_semantic_carry.jsonl` on the
  candidate. Their clear rows (written for `[]`) now expect ALL for the cleared slot.
- Spend cap: USD 0.70 total on the ORG key, ledgered by crew.

| Run | Rows | Pass | USD | Ledger |
|---|---|---|---|---|
| (crew) | | | | |
