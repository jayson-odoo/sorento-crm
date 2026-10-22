# PLAN: owner console turns 22 Oct, fix round on #1816 (lane REPORT-SMART-L, round S2)

Status: S5 reviewer READY at e7332aeec0; round S6 (owner ruling 23 Oct: after a ranking = (B), run across all) in progress. Track: L (prompt candidate, resolver/state guards).
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

## Round S3 (crew go 23 Oct: replay turns 2, 7, 8, 9 + year; delivery prompt r2)

Evidence: replay `crew/state/eval/report-smart-v92/replay/after.md` (v96 12eb406f, code 1ed44f3e59, Index x2 + Block),
delivery A/B `crew/state/eval/report-smart-v92/delivery/results.md` (v96 vs v97 94eb6108). Causes read from the stored
turns (chatbot.turns on the crew copy).

### ARCHITECTURE

- Layer: the head honours the parser's verdict. No keyword list, no token rule, no new match tier, no post-parser
  domain override. Every code item reads a parser field.
- Shared mechanism (S3-2, S3-3): a word the parser already put in a NON-entity field of the same verdict
  (`sales_channel`; the period) is that field, never an entity. One seam: where verdict entities enter the report
  words and the resolver (engine.py:5989-6005 filter, report_ask.py:605-606 `_word_filters`). Extends the S2 guard
  (a sales_agent word equal to `sales_channel`) to every entity hint, and to the period.
- S3-1 uses the existing required-ask contract (`answered_by_parser`, required_fields.py:135), as the other asks do.
- Classes fixed: (1) a report ask whose open question the parser never sees, so its held values are dropped on the
  answer; (2) a channel word read as an entity of any kind; (3) a year read as a product next to the same year read
  as the period.
- Not in S3: the drill rule (report_ask.py:821-826, owner question filed); C2 resolver shield (deferred, S1).

### Items

- S3-1 PERIOD (CODE). `SALES_RANKING_ASK` (report_ask.py:259-276) is registered without `answered_by_parser`, so
  `of_required_ask` (turn/question.py:107) returns None, the State says "open question: none" (chat_state.py:297),
  `reply_verdict` drops the slot on the shape path (required_fields.py:381, :423) and the held period goes with it
  (turn 2: "Which period?" after "in 2026"). Fix: the ranking ask is answered by the parser; the Open question states
  the owed fields and the held values; the `scope` slot gets a FieldSpec so it is stated too (question.py:110-112).
- S3-2 CHANNEL WORD (CODE). Guards cover a hint that is a parser field (engine.py:5989-6005) and a sales_agent word
  equal to `sales_channel` (report_ask.py:605-606); 'Project' hinted brand / category passes and reads "I don't know
  'Project' as a brand." Fix: an entity whose raw equals the verdict's own `sales_channel` (casefold; values from
  reports/ask.SALES_CHANNELS) is that channel, whatever its hint: dropped before the report words, the resolver and a
  kind pick.
- S3-3 YEAR (CODE, crew (a) 23 Oct). The parser takes the index candidate '2026' (MGB5020-26) next to period 2026;
  grounding refuses the canonical (grounding.py:866-873) and the resolver's substring tier (entity_resolver.py:2070-2091)
  fans '2026' out to 9 codes. The substring tier stays untouched (deliberate for mid-code partials,
  tests/test_product_code_resolution.py:267). Fix: a product entity whose raw equals the year the parser set as the
  period (date_filter_start / date_filter_end) is dropped at the S3-2 seam; no period set, or another year: kept.
- S3-P PROMPT v98 (= v96 + r2, NON-production): delivery DO-list text phrased without the extra field names and the
  v96 WHEN wording kept (v97 left `status` null on 12/24 WHEN asks, apply.py:1306/1320 read `status` only, and
  regressed the channel class 21/24 -> 13/24); the year rule on the Candidates rule (a candidate line for the
  message's own period word is no pick); `group_by` channel only when the channels themselves are ranked (a channel
  value alone under a held ranking is a refine). v92 needs the delivery edit at the same lines 107, 233, 261.

- S3-4 STATUS READERS (CODE, crew (a) 23 Oct). The parser fills the delivery status in `status` or in `order_status`
  (v97 / v100 left `status` null on 9-12 of 24 WHEN asks, `order_status` outstanding on all). Readers disagree:
  decide.py:683, chat_state.py:503, apply.py:1652/1661/1717 read `status or order_status`; apply.py:1306/1320/1324 and
  `lane_parse_output` (turn_runtime.py:2043-2049) read `status` only, so focus.status drops outstanding (a follow-up
  cannot repeat it) and a named DO never becomes do_outstanding. Fix as built (81d890adf7): the delivery-status writers
  (the focus write, `lane_parse_output`) read one helper, `delivery_status` (turn/apply.py): `status`, else
  `order_status` when it is outstanding or delivered. The readers that must also see report kinds (decide.py:683,
  chat_state.py:503, apply.py:1652/1661/1719) keep reading `status or order_status` directly.
- Prompt candidate after S3-P: v100 (699cb49d, NON-production) = v97 + v99's channel `group_by` line and Candidates
  year line (v98 0ee024ce and v99 412ed671 measured and set aside; numbers in crew state).

- Review round (reviewer NOT READY on dd535e7c81): the field-word drop must run before `names_its_own_ask`
  (engine.py:5341 reads the entities first, so a stray year or channel entity on the answer turn drops the open slot);
  tests guard the `delivery_status` narrowing, `lane_parse_output` directly, and the year rule's both-ends condition.
  Noted: the chat_state.py:1614 change also lets low stock (the only other `about` ask) take a declared fill with a
  KEEP or switch_domain op on the state path, as LOWSTOCK-SEMANTIC and the off-state path already do.

- Round S4 (EVAL-BENCH v100 measure on 911fa7d96c, causes in crew/state/eval/report-smart-v92/explore1023-diagnosis.md):
  S4-1 'compare with last year' under the open basis question: the shape path takes the reply as the answer
  (required_fields.py:391, :414-428), `settle` (report_ask.py:822-838) reads only period / count / measure / basis, so
  `collect` uses the whole message as the basis word (required_fields.py:309-321, miss line :200). Fix: a reply that
  sets one of the ask's own args (the parser's `compare_to`) and fills no owed field adds that arg and re-asks the
  owed fields, no "I don't know" line, no miss; `of_required_ask` states the held args (turn/question.py:127-130).
  S4-2 the promotion access level question names the parser's `promotion_kind` (label built from entity raws only,
  answer.py:327-334), from the same source as the Promotion kinds line (turn/context.py:132-142).
  Parser items (23 'For product <code>' refine, 42 'top N dealers selling X') go to a prompt candidate after the
  owner's test.

- Round S5 (causes: crew/state/eval/report-smart-v92/explore1023b-rootcause.md). The S2-S4 lines rendered on every live
  row (v100, render sha 05cdc9c968); the misses are parser readings driven by the history it is given.
  S5-1 CONSOLE HISTORY. The console Reset (useChatbotConsole.ts:190-195, console_service.py:218-221) clears State only;
  `recent_exchanges` (turn_runtime.py:376-419), `previous_reply_text` (:307-345) and the Recent conversations frames
  (engine.py:4080-4093; frames close only on a topic switch, :6485-6495) still carry the talk from before the Reset,
  against console_service.py:197-201 ("this contact remembers nothing"). Fix: on a console turn, the three history
  readers take only turns of the current test run. Real contacts unchanged.
  S5-2 RANKING FRAME. A sales ranking envelope has figures [] so has_result is False (turn_runtime.py:6062), miss = the
  codes (:6096), missed ['sales'] (engine.py:7812), and the digest writes "Asked about sales for X, but nothing was found"
  (episode_digest.py:225-227, :466) also when the ranking answered. Fix: a ranking that returned ranked rows has a
  result.
  Parser lines (template 53 'for product X' refine, 297 'top N dealers selling X', 310 a flyer ask is a promotion ask)
  go to a v101 candidate with gold rows after the owner's test.

- Round S6 (OWNER RULING 23 Oct, the drill question filed in round S3): after a ranking, a message that changes what is
  ranked or adds a filter without "of these" / "across all" runs ACROSS ALL and the header says so ("Across all sales
  agents"); "their customers" / "of these agents" / "only those 5" narrow to the list on screen.
  ARCHITECTURE: report lane, honours the parser's `ranking_drill` (scoped | global | unsure | null, head/parser.py:323).
  Today `settle` reads a new axis after a shown ranking with drill null or unsure as "unsure" and asks the scope
  question (report_ask.py:862-867, `_unsure_line` :986, `_drill` :996-1080). Fix: only `scoped` narrows (today's scoped
  branch); global, unsure and null run the global branch, and the answer carries one header line naming the population
  of the ranking that was on screen ("Across all <its group_by noun>"). No scope question is asked any more; a scope
  slot already held by a session is still answered. Not changed: a refine of the ranking on screen (same axis,
  ranking_refine true), a fresh ask with no ranking shown. Prompt: "only those N" as a scoped example goes into the
  v101 candidate (template line 300 lists "these", "their", "above").

### Gates (S3)

Red-first per item (tester writes from the UAC, coder makes green, kill test per fix), touched suites `-n 2`,
reviewer. Re-measure, cap USD 0.6: v98 on the delivery gold, parser_when_deliver, the channel class x2 and the 13-turn
replay (Index), plus report slice half 1 if the cap holds; table to crew.
