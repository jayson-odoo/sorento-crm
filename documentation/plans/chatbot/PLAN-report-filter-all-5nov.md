# PLAN: report filters - explicit ALL, parser object final

Status: Build done, Review next (lane REPORT-FILTER-ALL, PR #2209; standard track: no migration, no auth change).
Started 5 Nov 2026. UAC: `report-filter-all-acceptance-criteria.md`. Prompt: `PROMPT-report-filter-all-698e137b.md`.

## Owner pain

In the sales / outstanding report chatbot, follow-ups like "clear brand", "clear company", "all brands", "any agent" and
"clear all" failed or behaved randomly after weeks of tuning. The owner wants a fix at the root, not another patch.

## Root cause (re-verified on main 4c529e1e)

- The parser already writes the whole report each turn (`report_ask`, `head/parser.py:1019-1093`) and sees the held one
  (the `Held report:` line). For "clear brand" it writes `brands: []`.
- `report_ask.from_object` then put the held value back:
  - `_carry` treated an empty list or a null company as "not mentioned" unless the legacy `broaden_axis` +
    `broaden_to: "all"` also named that kind (`turn/decide.widened_kinds`). That was one axis per turn, and the signal
    was easy to miss.
- The company was a single nullable string, so "all companies", null and "not said" could not be told apart.
- Correction to the crew diagnosis: the `held_filters` refill (`report_ask.py:2433-2442`, `:2479`) never runs on an
  object turn. `:2246` drops `sales_ranking_frame` and `report_held` (`_OBJECT_DROPS`) first. It serves only the old
  hold path, which still runs on the marker prompt whenever the model leaves `report_ask` null on a report ask. There it
  locks owner ruling B / S6b (23 Oct: a new axis after a ranking keeps the filter on screen;
  `test_one_ranking_r2::test_r2_2`, `test_sales_account_type_lane::test_at34_a_new_axis_keeps_the_held_account_filter`,
  which fail when it is deleted and pass on main). So it stays here, and PR B deletes it with the rest of the old path
  (crew-ask on #2209).

## Design

1. The parser's `report_ask` object is final. Every filter slot has an explicit ALL:
   - company `"ALL"`, channel `"ALL"`
   - sales_agents, account_types, brands, categories, customers and products `["ALL"]`

   A prompt text that writes `["ALL"]` defines it (`parser.REPORT_ALL_WORD`; `report_ask_defined_in` then holds
   "ALL", and the channel enum offers it).
2. `report_ask._read_all`: a slot written ALL becomes no filter (ALL anywhere in a list is the whole list). The report
   then runs without it, so the held state, and the next `Held report:` line, has that slot empty.
3. `report_ask._keep_held` is the ONE safety rule. A slot the object left empty, over a held value, without ALL, forgot
   to echo it, so the held value stays. It has two guards, both read from the object itself:
   - Not the breakdown's own axis slot: it would collapse to one row (C6-2).
   - Not a held name the object now holds in a slot the held report did not hold it in: it moved, for example a name
     the message calls the company.
4. `report_ask._held_spelling`: a company that is none of the contact's own (by name or code) but a close spelling of
   the held one (ratio >= 0.8) is the held one. An exact own company always wins.
5. Temporary: `report_ask._legacy_all`. On a prompt without ALL (production v72 today), the legacy widen signal
   (`widened_kinds`) reads as ALL for the empty slots it names. TODO(REPORT-FILTER-ALL): delete it, `_LEGACY_WIDEN_SLOTS`
   and the `all_value` switch once the owner publishes the ALL prompt (crew Q2 ruling).
6. "clear all" (owner 5 Nov, crew Q4) writes ALL in every filter slot, company and channel included. The basis, the
   period, frame, group_by and top_n stay.

## Deleted rules, the case each covered, and what covers it now

| Deleted | Case it covered | Covered now by |
|---|---|---|
| `_carry` (`report_ask.py:3684-3710` on main) | CP-1 / C6-2: the object drops a held filter the message did not touch | `_keep_held` (empty + held + no ALL keeps), FA-1 |
| `_carry`'s `widened_kinds` read | B5-B7 "all brands" / "clear the brand filter" clear despite `brands: []` | ALL (`_read_all`), FA-1 / FA-2; legacy prompt: `_legacy_all`, CL-1..6 |
| `_carry`'s `named & hints` skip (a kind this message names is never carried) | "sorento company only" over a held SORENTO brand (TF-28, HT1-2) | the moved-name guard in `_keep_held`, plus said_as (`_word_kinds`), U4 |
| `_carry`'s brand + account type as ONE kind (`_CARRY_KINDS`) | a word moved between brands and account_types | the moved-name guard, U4 |
| `_carry`'s `answering` channel rule (CP-1: the channel carried only while a question is open) | the held channel kept on a reply | `_keep_held` for every turn (owner 3 Nov: a full new ask keeps the channel), FA-6, SC-8 updated |
| HT1-18 echo rule (`report_ask.py:3589-3605` on main, keyed on top-level `sales_company`) | v202 "Sorenth" echo over a held Sorento | `_held_spelling`, FA-5c (now also with `sales_company` null, which the old rule refused) |

Keyword rules (owner 5 Nov: "clear all" is never hard-coded; the parser reads the meaning, code applies the object).
`report_ask.py` reads no message text: no regex, and `take_words` takes its text argument for the seam's shape only. One
keyword rule did reach report turns: `order_list.clears_the_brand` ("all brands", "clear the brand", "no brand") and the
raw-text `brand_word_alone` switch. Both ran at `engine.py:6895`, after `from_object`, whenever an order or outstanding
list was open, so an outstanding report turn could be read by its words. Both now stand down on any turn whose parse
carries a report object (`order_list.py:164`, K1). They stay for the plain order list, another lane's feature (K1 lock).

`broaden_axis`, `scope_intent` and `entity_op: "clear"` are no longer read for reports on an ALL prompt (FA-2).
`widened_kinds` stays for the which-one customer pick. `topic_reset` still means "no held report" (CL-7).

Code size: `report_ask.py` loses `_carry`, `_CARRY_KINDS`, the HT1-18 block, the CP-1 rule and the refill. It gains
`_read_all`, `_keep_held` and `_held_spelling`, and the temporary `_legacy_all` adds about 20 lines until the publish.
The new rule names no case: it has no per-kind table and reads no message-level parser field (no `sales_company`, no
`entities`, no open question).

## Tests

`tests/chatbot/test_report_filter_all.py` (no LLM; recorded-shape objects through the real engine and lane):
- FA-1..FA-6: ALL per slot, the forgotten echo, clear all, one of two brands, the company slot, the channel slot.
- U1..U5: the parser flag, `_read_all`, `_keep_held`, `_held_spelling`.
- P1 / P2: the md5 pins and the gold loader.

The suites test_report_totals_filters, test_report_totals_filters_ht1 and test_report_semantic_carry stay green. SC-8 is
updated to the 3 Nov ruling.

## Prompt and gold

Prompt candidate 698e137b, on the v72 base d29c1983: `PROMPT-report-filter-all-698e137b.md`. The gold rows are in
`scripts/chatbot_eval/gold/parser_report_filter_all.jsonl` (28 rows, 16 of them EN / BM / ZH mixes of clear all and of one slot). Crew runs the eval gate (cap USD 0.70, ORG key,
ledgered) and the #2156 replays on the Mac (crew Q5). Never published by the lane; only the owner moves the label.
