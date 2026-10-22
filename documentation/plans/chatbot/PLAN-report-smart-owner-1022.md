# PLAN: owner console turns 22 Oct, fix round on #1816 (lane REPORT-SMART-L, round S2)

Status: built D, E, B, C, A'', F'' (cc3ccfd1a5), review round 1 fixes in progress; replay waits the v96 id. Track: L (prompt candidate, resolver/state guards). Branch
`claude/report-smart-1021-r2xexf` (on `crew/chat-release-1022`), base head afd7f70605. Diagnosis (13 turns, prompt v94,
code 65c2025c05): `crew/state/eval/report-smart-v92/owner-1022-diagnosis.md` (crew-only). UAC:
`report-smart-owner-1022-acceptance-criteria.md`.

## Items (crew order, 22 Oct)

ARCHITECTURE. Layers: the sales report lane's product reading (D, E), the resolver / State seams that turn parser
entities into picks and held rows (A guard, B), the lane's drill reading (C), the promotions subject (F), and one
candidate prompt (v95, non-production) for the parser halves (A, year, F). Shared mechanism per item named below; no
regex over message words; parser fields only.

- D (turns 1, 2, 4). `fetch.py:2607 sales_report_product_code` returns codes[0] when the codes share no prefix, so a
  mixed code set (a word that fanned out) froze the ranking on an unrelated product. A mixed set goes to the report-ask
  route as `product_ids` (the route takes them, `_AXIS_FILTERS`), never codes[0]; a set too large for the route asks
  which product.
- E (turn 3). A product named on a refine of a held ranking replaces the held product (`_refine`, report_ask.py:845
  reads brand and category only today); the prompt half (v95: a refine may carry a product entity) rides the candidate.
- A (turns 7, 8). The channel word is never an entity on a report ask (v95 line); code guard: an entity whose hint is
  not an entity kind (e.g. `sales_channel`) never reaches the resolver or a kind_pick (turn/reconcile.py:89-177,
  turn/apply.py:1895-1908); a sales report verdict carrying `sales_channel` never also refuses the same word as a sales
  agent (report_ask.py:641-648).
- B (turns 9, 10). A pick that binds no row (uuid None, reconcile.py:165) is dropped, never held; a sales ranking's
  customer narrowing reads current-message customers only (the lane's own rule, report_ask.py:655-656), so a carried
  customer is not re-resolved by `must_narrow_one` (turn/narrow.py:483) before the lane.
- C (turn 9). The lane drills only on the parser's `ranking_drill`; a changed axis alone after a failed fresh ask never
  scopes to the old frame (report_ask.py:792-801).
- Year (turns 1, 4). PROMPT line in v95: a year is a period, never a product. No token guard in code (crew ruling).
- F (turns 11-13). `promotion_kind` from the Promotion kinds line (v95); the brand-subject check counts only products
  typed THIS message (held_family output, head/held_family.py:193, is not typed; turn_runtime.py:616-658); Sorento's SRT
  short code on the Known brands line (built from the live brand list, turn_runtime.py:512; data or code, measured).

## A'' / F'' as shipped (owner ruling 22 Oct 23:20: ALWAYS-ON full lines in both closed-list modes)

Index matching is spelling only (closed_lists_index.py:218-237), so the channel and brand values are always-on lines in
Block and Index mode, never index-matched; the 23:05 index design is superseded.

- A''. A "Sales channels" line in the parser's user turn (turn/context.py, beside Known brands and Promotion kinds)
  from one source, `reports/ask.SALES_CHANNELS` (dealer, project), which also feeds the parser schema's `sales_channel`
  enum and the report route's channel labels (the SCM demand classes are a different vocabulary). The template's
  sales_channel rule names the line. Guard: an entity whose hint is a parser output field (not an entity kind) never
  reaches the resolver or a kind pick. Code half of AC-A1: a stray word equal to the channel the same verdict set is
  never refused as a sales agent (review round 1).
- F''. Brand short forms as data: the alias lookup-set reader takes the set key; a `brand_alias` set (option value =
  brand_code, keywords = short forms) prints on the Known brands line as "Name (code, alias...)" ("SORENTO (SRT)";
  no alias: "Name (code)" as before) and every brand lookup takes an alias (`resolve_brand_token`, the flyer brand
  filter's `exact_brand_rows`). No migration; release data step: the set + SORENTO -> SRT row (System > Lookup Sets).
- F code halves: codes held_family re-emits are not typed products, so a brand + kind flyer ask sends the kind and the
  brand, not the held products.
- Named: B1's no-row pick guard was dropped (kind-pick answers hold the raw value by contract,
  test_samantha_26sep_s8_kind_pick_siblings t4); B2 (no pre-lane customer narrowing for a sales ranking with no
  current-message customer) removes the poisoning. D also covers the per-product sales report (asks which product).

## Prompt candidate v96

v95 (registered, non-production) carried hand-written A / F lines and is superseded by v96:
`crew/state/eval/report-smart-v92/candidate_v96.txt` = v94 + the E line, the year line and one sales_channel sentence
naming the Sales channels line (+277 chars). Non-production; the owner publishes.

## Gates

Red-first per item (`test(red):` commits), kill test per fix, touched suites `-n 2`, reviewer (+ security-reviewer
if a seam touches access), then the owner's 13 turns replayed on v95 + this head (paid, cap USD 1), before / after
table to crew (crew-only path, no contact names or ids).
