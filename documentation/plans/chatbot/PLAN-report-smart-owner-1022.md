# PLAN: owner console turns 22 Oct, fix round on #1816 (lane REPORT-SMART-L, round S2)

Status: plan; red-first per item in the order below. Track: L (prompt candidate, resolver/state guards). Branch
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

## A' / F' (owner direction 23:05, design via crew 22 Oct): values from the closed-list index, not prompt lines

The v95 A and F prompt lines are paused. Facts: the index covers specs, file types and certificates
(closed_lists_index.py:248-276, :418; engine.py:1171-1181); Known brands is a full line in both modes
(turn/context.py:100-116, "Name (brand_code)"); no brand alias exists (Sorento's brand_code on the copy is SORENTO);
the one alias set is `attachment_type_alias` (chatbot_prompt_vars.py:341-357); `sales_channel` is a parser enum.

- A'. A "Sales channels" closed list from the code's channel source (scm/demand_class.py DEMAND_CLASSES, with
  PROJECT_SEGMENTS as its match words): Block mode prints the full line, Index mode prints the matched channel line
  through the same match path as file types (+ a SYSTEM_BLANKS pointer). The template rule names the list. The guard
  stays: a channel value, or any entity whose hint is not an entity kind, never reaches the resolver or a kind pick.
- F'. Brand aliases as data: the alias lookup-set reader generalised to a `brand_alias` set (option value = brand_code,
  keywords = short forms). The Known brands line shows the alias in both modes, Index also prints the matched alias
  line, and `resolve_brand_token` (lanes/business/services.py:798-811) takes an alias as an exact match. No migration:
  the set and its SRT row are data (System > Lookup Sets); idempotent SQL for the copy DB goes to crew.
- F code halves stay: the brand-subject check counts only products typed THIS message; the promotion kind and brand
  reach the tool even when products are held.

## Prompt candidate v95

`crew/state/eval/report-smart-v92/candidate_v95.txt` = v94 (id 99f70258, exported `base_v94.txt`) + the E and year lines
(the A and F lines are paused: see A' / F'), additive, few. Non-production; the owner publishes.

## Gates

Red-first per item (`test(red):` commits), kill test per fix, touched suites `-n 2`, reviewer (+ security-reviewer
if a seam touches access), then the owner's 13 turns replayed on v95 + this head (paid, cap USD 1), before / after
table to crew (crew-only path, no contact names or ids).
