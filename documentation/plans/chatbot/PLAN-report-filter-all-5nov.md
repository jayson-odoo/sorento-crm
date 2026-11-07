# PLAN: report filters - explicit ALL, parser object final

Status: Build round 6 (crew re-check on v78) done, crew re-check next (lane REPORT-FILTER-ALL, PR #2209; standard track: no migration, no auth change).
Started 5 Nov 2026. UAC: `report-filter-all-acceptance-criteria.md`. Prompt: `PROMPT-report-filter-all-289da7e5.md`.

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
   - Not a held brand or account type name that the object newly puts in the other of those two lists, or in the
     company (`_MOVES`). Examples: the brand-or-account-type answer, or a name the message calls the company. The
     company itself is never un-held by a move: "<name> brand only" keeps the held company (review B1, R1). No other
     slot pair moves: a new customer "Tan" never blocks a held agent "Tan" (U4b).
4. `report_ask._held_spelling`: a company that is none of the contact's own (by name or code), that no entity of this
   message types, and that is a close spelling of the held one (ratio >= 0.8) is the held one. An own company always
   wins. A company the user typed stays as written and is refused when not held (review B2: "Sorento SG", R2).
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
| `_carry`'s `named & hints` skip (a kind this message names is never carried) | "sorento company only" over a held SORENTO brand (TF-28, HT1-2) | said_as (`_word_kinds`) drops the brand when the message calls the name the company (R3, TF-28, HT1-2); the `_MOVES` guard keeps a moved name from refilling, U4. Since round 6 said_as brand no longer drops an object company (the object is final) |
| `_carry`'s brand + account type as ONE kind (`_CARRY_KINDS`) | a word moved between brands and account_types | the `_MOVES` guard (brands with account_types), U4 |
| `_carry`'s `answering` channel rule (CP-1: the channel carried only while a question is open) | the held channel kept on a reply | `_keep_held` for every turn (owner 3 Nov: a full new ask keeps the channel), FA-6, SC-8 updated |
| HT1-18 echo rule (`report_ask.py:3589-3605` on main, keyed on top-level `sales_company`) | v202 "Sorenth" echo over a held Sorento | `_held_spelling`, FA-5c (now also with `sales_company` null, which the old rule refused). The old rule's entity guard is kept (a company this message types is never an echo, R2 / U5b); its `sales_company` guard is replaced by "none of the contact's own" |

Keyword rules (owner 5 Nov: "clear all" is never hard-coded; the parser reads the meaning, code applies the object).
`report_ask.py` reads no message text: no regex, and `take_words` takes its text argument for the seam's shape only. One
keyword rule did reach report turns: `order_list.clears_the_brand` ("all brands", "clear the brand", "no brand") and the
raw-text `brand_word_alone` switch. Both ran at `engine.py:6895`, after `from_object`, whenever an order or outstanding
list was open, so an outstanding report turn could be read by its words. Both now stand down on any turn whose parse
carries a report object (`order_list.py:164`, K1). They stay for the plain order list, another lane's feature (K1 lock).

`broaden_axis`, `scope_intent` and `entity_op: "clear"` are no longer read for reports on an ALL prompt (FA-2).
`widened_kinds` stays for the which-one customer pick. `topic_reset` still means "no held report" (CL-7).

Code size: `report_ask.py` loses `_carry`, `_CARRY_KINDS`, the HT1-18 block and the CP-1 rule. The `held_filters` refill
stays until PR B (crew ruling Q3, TODO in `_fresh_args`). It gains
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

Prompt candidate 289da7e5 (round 5; earlier d51a084c, 5a58739a, e9421ded, 698e137b), on the v72 base d29c1983: `PROMPT-report-filter-all-289da7e5.md`. The gold rows are in
`scripts/chatbot_eval/gold/parser_report_filter_all.jsonl` (28 rows, 16 of them EN / BM / ZH mixes of clear all and of one slot). Crew runs the eval gate (cap USD 0.70, ORG key,
ledgered) and the #2156 replays on the Mac (crew Q5). Never published by the lane; only the owner moves the label.

## Crew gate round (5 Nov evening, gate on 698e137b / ee34327b)

| # | Gate finding | Cause | Fix |
|---|---|---|---|
| 1 | "clear all" lost the period and basis and asked again (T5, X EN) | the keep rule covered filter slots only; the parser left date_from / date_to / basis null | `_keep_held_report`: the same rule over every slot of the held report (period, basis, measure, frame, axis, count). Null keeps, a value replaces, ALL clears; an explicit total still drops the axis (G1, G1b) |
| 2 | BM / mixed "clear all" kept the brand or company | parser miss | prompt edit 5 (clear every filter in any language or wording, the company and brands included), gold fa-29..34 |
| 3 | ZH 清除所有筛选 parsed all ALL, replied chit-chat | the parse had no report status, so `from_object` set the object aside | on the ALL prompt an object of the held report's kind is that report's follow-up (`follow_up`, G3) |
| 4 | step 1: no Dealer / Project rows | parser miss (frame total, channel ALL) | prompt edit 6 (side-by-side values are a breakdown, even beside "total"; never ALL), gold fa-36 |
| 5 | steps 8 / 12: "couldn't find a supplier called Sorento" | the span supplier rewrite (`engine._with_span_suppliers`) and the supplier scope (`_supplier_scope`, fed by the span model's `supplier_typed`) ran on report turns | both stand down on a kept report object (G5). Bare Sorento keeps its one company-or-brand question (ON-3, HT1-5) |
| 6 | steps 13-15 asked the basis | the script gave none | the hand test now says "delivered" |

Also in this round: tf-16 "both" as company "Mocha, Sorento" (prompt edit 7: company holds one name or ALL, gold
fa-37). The totals-filters gold now expects `["ALL"]` where it expected `[]` for a clear (tf-17..20) and for the only brand
moved to the company (tf-28).

Not fixed here (found by the crew gate, outside this lane's rules): B2 / R2 "delivered" after "Sorento company ..." asks
"SORENTO: brand, account type or company?" because the 1104 copy has a SORENTO account type (the existing ON-6 rule
asks a word in both tables).

## Crew gate round 2 (6 Nov, gate on e9421ded / d15853fa)

| # | Gate finding | Code or parser | Fix |
|---|---|---|---|
| 1 | Company sticks: fa-30 `buang semua filter`, fa-32 `全部 la, 不要 filter`; steps 16-17 show Company Sorento for a brand answer | Parser. The object path writes the company only from the object's own company slot, the company / both pick of an open question (`kind_company`), the said_as company slot, or the held company when the object leaves it null (`_keep_held`). Replayed in the harness: a brand answer whose object leaves company null runs with no company on both the old three-way question and the new one (H15). The Held report line for the open question shows company null. So the stray company is written by the parser: it copies the held company on a clear-all, and it wrote Sorento into company on the 1104 three-way question's brand answer | prompt edit 8 (company and channel are filters like the lists), edit 9 (a brand answer never writes the company); the three-way question no longer exists for a company's name (item 5) |
| 2 | Step 8: "Sorento company, brands Sorento and Cabana" kept CABANA only | Code: `_word_kinds` kept the FIRST entity per word (`named.setdefault`), so the word's company entity hid its brand entity | `said_as_of`: the word's said_as over every entity of this message; company and brand together are both (H8) |
| 3 | Step 14: "Sorento company, Sorento brand" kept only the brand | same as 2 (the other entity order) | same (H8 brand-first) |
| 4 | fa-13 `clear all filter`, fa-14 `buang semua filter`, fa-16 `tak payah filter apa2, semua`, fa-18 `全部 la, 不要 filter`, fa-20 `start over without any filter, same month` | Each: (a) the parser kept the held channel dealer and company Sorento (it cleared only the lists), and (b) a gold error of mine: those rows expected ALL in account_types and products, which the Held report holds empty and the prompt says to copy empty | (a) prompt edit 8; (b) gold corrected (also fa-06, fa-29..34) |
| 5 | ON-6 "SORENTO: brand, account type or company?" (R2, step 15) | Code + data. Account types are the customers' stored `autocount_debtor_type` (AutoCount data, `parser.py:1487`, `ask_params.account_type_options`), not a seed. 1104 is a production copy, so production almost certainly stores the same SORENTO type (not verified: no prod access) | `_account_plan`: a brand word that is one of the contact's own companies (2+ companies, from data) is that company or its brand, never asked as an account type; `_company_or_brand` asks company or brand once (owner rule). "Sorento account type" (said) still reads the type. Tests C6-1(a), S2, C6-2(b), R1-b, R5-1, R5-1c updated (they set up the old three-way question; the last four only needed some kind question and now use a brand-and-type word that is no company) |

## Crew targeted re-check (6 Nov, v77 = 5a58739a, head 6ffc293e)

No recorded parse objects reached the sandbox; each fix below is pinned by a replay test of the parse shape it assumes.

| Finding | Which is right / cause | Fix |
|---|---|---|
| Step 8: the parser wrote company Sorento, the report shows no Company line | The code is following the design: a name that is both a company and a brand takes its slot from the entity's `said_as`, never from the object's company slot alone, because "Sorento brand only" parses also write company Sorento (ON-2, F2, tf-29, the R3 equivalence). The object's company plus a one-entity `said_as` brand is that shape. The message meant both, so the parser's `said_as` was wrong (or one of two entities lacked its typed word). A second field, top-level `sales_company`, was tried as a tie-breaker and rejected: R3's "brand only" parse carries it too | prompt edit 10 (one entity, `said_as` both); two entities of one name already merge (round 4, H8). K8 pins both directions |
| Step 14: "Sorento company, Sorento brand" shows the brand only | same | same |
| Step 16: "brand" after the company-or-brand question shows Company Sorento + Brand SORENTO | Code. The open question's held ask (`_held_object`) carried the first turn's company Sorento, which is the very reading the question asks about, and `_keep_held` put it back on the answer. An object echoing that company beside a declared "brand" pick was also applied | the open company-or-brand question no longer holds the asked name as the company, and a declared brand pick drops an object company of that name (K16, both variants; the owner's "a brand answer replaces the company reading") |
| Step 17 | inherits 16 | as 16 |
| fa-36 / step 1: no Dealer / Project split on the first turn | Parser frame total. When the parse also carries the axis, code now runs it: a total frame beside an axis this message names itself (not the held one) whose slot is not one value is that breakdown (K1). A one-value slot (AF-1's noisy "brand") or a copied held axis stays a total. A parse with no axis at all stays the parser's | `from_object` frame rule |
| fa-16 / fa-20 keep channel dealer | Parser (edit 8 already says company and channel are filters like the lists) | none new; watch in the re-gate |

## Crew re-check on v78 (6 Nov, d51a084c, head dcd1fd81): round 6

| Finding | Cause (file:line on dcd1fd81) | Fix (red first: 652e81bf) |
|---|---|---|
| Step 14a: "Sorento company, Sorento brand" parsed company Sorento + brand SORENTO, report showed the brand only | Code. Probed through the engine across seven entity shapes after a real clear-all: only one Sorento entity with `said_as` brand loses the company. `report_ask.py:3681` (`elif slot == "brand" and same: ask["company"] = held_company`, the CP-5 branch) replaced the object's company with the held one, none after the clear-all | branch deleted: the object's company is applied as written (K8, both said_as variants). Flips four tests that locked the override for "brand only" parses that also wrote the company (tf-29, F2, R3-2, R3-4): "brand only" is brand only when the parse leaves the company null (HT1-3, the one-name bullet) |
| Step 1: frame total with no group_by | Parser dropped the axis from the object, so the K1 rule had nothing to read | prompt edit 11; code: a total whose object names no axis takes the parse's top-level `group_by` (this message's own reading) under the K1 guards (K1b); with no axis anywhere it stays one figure (K1c) |
| fa-16 / fa-20 / fa-36 | not run by crew; replayed here as recorded objects | the gold clear-all object clears company + channel and keeps period / basis / axis; the recorded miss (channel dealer in the object) keeps dealer because the object kept it (a parser miss, no code drop); fa-36's gold object is the Dealer / Project breakdown |
