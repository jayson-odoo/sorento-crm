# PLAN: the parser writes the whole report ask each turn (semantic carry, 2 Nov 2026)

**Status:** Review (PR A: red 194174a4f4 + 2a6e449d22 + 847771fcd2 + 6da25eadf6 + b021ccc367 + 3677a20646, green 819f45105e + ac6116db6d + 523bda322c + 9b6fee096f + 0538e65004; re-review next; split ruled by crew 2 Nov). Track: full (L-ish: parser prompt + schema + the lane's report path; no migration, no route change,
no auth change). Branch `crew/sales-account-type-semantic` from origin/main 46de2f6d77. Lane SALES-ACCOUNT-TYPE,
follow-up of #2067 / #2074. Supersedes `PLAN-report-multiturn-carry-2nov.md` (PR #2092, coded carry rules, closed
unmerged). UAC: `report-semantic-carry-acceptance-criteria.md`.

## Why

Owner, #2074 hand test on the crew copy, 2 Nov: "it can get the answer I want but it kind of cannot survive multi
turn" (14 turns, turns 6 to 14 drop slots set earlier or ask for them again). Owner direction 2 Nov 21:10: "the model
should be able to understand". Crew answered card a25806750: direction 2 (below), spend approved, srt102-rg expected
set by crew.

Investigation (crew/state/files/sales-check-1nov/agentic-vs-chat-2nov.md, file:line on origin/main 46de2f6d77):

1. The parser is asked what THIS message says (`entity_op`, `ranking_refine`, `by_words`; head/parser.py:170-806).
   There is no output for "the report the user wants now".
2. The held report reaches the parser only as one State line with every id stripped (turn/chat_state.py:68,
   :93-102, `_pairs` :128-138, `_subject` :158-164): the held sales agent, brand, category, customer and company are
   invisible, so the model cannot carry them even when it reads the follow-up right.
3. Code then guesses the carry from noisy flags (lanes/business/report_ask.py `names_its_own_ask` :800-856,
   `_follows_up` :1238-1253, `with_held` :1262-1330, `_settle` :2008-2372, `_refine` :2435-2558; engine.py:6102-6153).
   Its own comment says the flags flip run to run (report_ask.py:1240-1243). #2092 added ~180 more lines of such rules.
4. Agent mode carries because the model sees its own previous `crm_report_ask` args (agent/memory.py:90-142) and
   rewrites the whole arg set each turn. Routing staff reports to the agent costs ~10x and drops the fixed report
   template the owner asked to keep (16 Oct), so it is the yardstick, not the route.

## Rules (crew answers, 2 Nov)

- R1 Each report turn the parser receives the held report (the last report that ran, or the open question's ask so
  far) as WORDS, by name, and returns the FULL report ask after this message as one `report_ask` object: kind, basis,
  period, breakdown, count, measure, channel, company, sales agents, account types, brands, categories, customers,
  products, and the words it could not tell brand from account type. Starting from the held report and changing only
  what the message changes is the model's job; there is no code rule for it.
- R2 Code passes the object to the existing route arg builder and keeps ONLY value checks, never language rules:
  - V1 basis is never defaulted (owner 27 Oct): the object's basis counts only when this message says it (the
    parse's own `basis` / `sales_basis`) or it is the basis the held report or the open ask already has (the user
    chose it earlier in the conversation). Else the basis question.
  - V2 company is one of the contact's own (`_company_said` report_ask.py:2388-2393, else COMPANY_FORBIDDEN_LINE);
    two or more companies and nothing in the ask that says which -> the company question (`_owes_company` :2396-2400,
    unchanged).
  - V3 dealer refusal over the final args (`_dealer_outside` :1408-1429 and the route's own refusal).
  - V4 data questions stay: a word in both the brand and the account type tables -> "brand or account type?"
    (`_account_plan` :1542-1633) when the object left it in `brand_or_account_type`, or this message has an entity
    for it with `kind_said` null (the model's own reading of whether the user said which); a word carried from the
    held report with no entity this turn never asks. While that question is open, the parse's declared pick of an
    offered option answers it (the list-pick class, V5), whatever list the object put the word in. Refined 2 Nov from
    the prototype: flash-lite never fills `brand_or_account_type` (4 of 4 runs); an agent name matching
    several -> the agent pick; no period -> PERIOD; a ranking with no count -> TOP_N (`rf.collect`).
  - V5 rows on screen stay as they are: drill (`_drill` :2591-2682), list picks (`_detail_outcome` :1918-1937,
    `so_list_outcome` :1952, `more_outcome` :1969), scope answers.
- R3 "srt102-rg sales 2026" after "srt102-rg dealer sales may 2026" runs over ALL channels and the reply header
  names the channel (a restated ask drops what it does not name, owner pass 6, 17 Sep). Crew-set expectation; the
  owner can change it.
- R4 The coded carry logic is deleted (list in "Deletion" below), in the PR that ships after the label moves.

## ARCHITECTURE

1. **Layer.** Parser contract (head/parser.py schema + a DB prompt version) and the lane's report path
   (lanes/business/report_ask.py), with one engine seam (engine.py report block ~6050-6175). No route, MCP or
   reports-service change: the object ends in the same `crm_report_ask` args `route_args` builds today
   (report_ask.py:2731-2756).
2. **Shared mechanism.** ONE held report, ONE rendering, ONE object. The held report = `focus.sales_ranking_frame`
   (written engine.py:8465-8480 from `route_args`), or, while a field question is open, `focus.required_ask`'s ask.
   It is rendered once as a `Held report:` line in words: each id the frame holds is shown by its NAME, and the frame
   keeps an id->name map beside the ids so a name the object carries maps back to the same id with no re-resolve. The
   object goes through the existing word->id resolution (`_word_filters` :1454-1529, `_fresh_args` :1722-1839) and
   the existing rails. Same "schema follows the prompt" pattern as `with_opportunity` (parser.py:931-952): a marker
   line in the prompt text sets `ParserConfig.report_ask` (parser.py:93-167, `resolve_config` :1104-1122) and adds
   the object to the schema (`_base_schema` :1409-1417).
3. **Classes fixed.** Every slot, not one shape: agent, account type, brand, category, customer, product, period,
   company, basis, breakdown, count, measure, channel; every follow-up kind (refine, re-typed ask, answer to an open
   question, slot replaced, new topic) is the same operation for the model: edit the shown object.
4. **Removes.** When the flag is on, the lane never reads `entity_op` / `ranking_refine` / `state_changes` to decide
   carry; the seams `names_its_own_ask`, `as_basis_answer`, `as_kind_answer`, `as_held_refine`, `with_held`, the
   company-pick flags and `_settle`'s answering-slot and frame-hold branches are skipped. With the flag off (every
   production text today) the old path runs unchanged until the label moves; then PR B deletes it.
5. **Not built.** No word list, no regex, no new question type, no new table, no agent routing change, no change to
   the reply template.

## Slices

Size: add ~250 lines (schema ~30, held line ~50, object -> args ~80, rails ~60, engine branch ~30) + one prompt
section + tests; delete ~950 (report_ask.py ~900 + engine seams) after promotion.

**PR A (this branch).**
- A1 Schema: `REPORT_ASK_LINE` marker, `_REPORT_ASK_SCHEMA`, `with_report_ask(schema)`, `ParserConfig.report_ask`.
  The marker is the section heading line of the candidate text, exactly:
  `== REPORT_ASK: the whole sales or outstanding report after this message, one object ==`.
- A2 Held report line: rendered from the frame / open ask in words; frame stores id->name; printed in the user block
  only when `ParserConfig.report_ask` (context.py `ContextLayers` :254-310, L2 render :454 / :542; engine call
  :5416-5455). Format (fixed, so the gold rows and the renderer agree): `Held report: ` + compact JSON of the SAME
  shape as `report_ask` (same keys, same order, names never ids, nulls and empty lists kept so the model copies and
  edits one object, the agent's "last call args" mechanism). While a field question is open:
  `Held report (open question: <basis|period|count|company|brand or account type|sales agent>): ` + the ask so far.
- A3 Lane: when the verdict carries `report_ask`, build the ask from it (kind, words -> ids, period, basis, axis,
  count, channel, company), apply V1-V5, run. Old seams skipped for that turn.
- A4 Candidate prompt: the copy's v71 lineage (production lineage, md5-pinned) + one anchored section with the marker
  line and the instruction "the whole report the user wants after this message: start from Held report, change only
  what this message changes; another topic starts empty". UNLABELLED; crew publishes it on the copy; the label is
  the owner's.
- A5 Eval: parser gold rows for the 14 turns + the srt pair, each row carrying its held report line
  (scripts/chatbot_eval/gold, parser_gold.py with a held-line field); no-op control (the candidate without the
  marker vs the base text) on parser-gold TRAIN rows, since schema / user-block additions flip unrelated rows.

**PR B (after the owner moves the label to the candidate).** Delete the old carry path and its tests (list below);
the flag stays only if another lane still serves a text without the marker.

Split reason: production serves an unmarked text until the owner moves the label; deleting the old carry with PR A
would leave production with no carry at all between the release and the label move. Crew ruled the split (a), 2 Nov
(ask a26467083): PR A first, PR B only after the owner moves the parser label in production.

## Prototype results (2 Nov, crew-approved spend, ledger lines 22:12 and 22:24)

Prompt text: `PROMPT-report-semantic-carry-e4aa6d43.md` (one anchored section on 99b5fc65, no gold-message examples, no
word lists). 16 gold rows x1 on gemini-3.5-flash-lite: round 1 D 11 of 16, round 2 D3 13 of 16; table in the prompt doc.
Graded on the FULL object (every slot, bacfd008cb), D3 is 12 of 16: sc-01 (an invented agent code no candidate list
names, read as a customer; the both-table word is V4 in code), sc-03 (V4: the declared pick answers in production; the
gold harness shows no options line), sc-12 (question path, crew ruling below), sc-16 (known limit). No-op control
(ledger 2 Nov 22:3x / 22:57, USD 0.688): parser-gold TRAIN, 113 lane ids both arms completed x1, whole parse BASE
99b5fc65 90 vs D3 e4aa6d43 91, 4 wins / 5 losses, p=1.00 (score_bakeoff): the section and schema flip no unrelated row
beyond run-to-run noise.

## Known limits (PR A)

- sc-16, crew ruling 2 Nov: "<code> sales 2026" after "<code> dealer sales may 2026" keeps channel dealer (the model
  reads it as a period change, 2 of 2 runs). The reply header names the channel, so the user sees it and can say
  "all channels". Crew-set expectation (all channels) marked FAIL / known limit.
- Not object slots, so they stay this message's own and do not carry: sort direction, compare_to, mine, locations,
  specs.
- Owner turn 12, crew ruling 2 Nov: a bare both-table word with nothing open ("sorento" with company Sorento held)
  may be read as a brand; the code then asks "Sorento: brand or account type?" (owner 1 Nov ambiguity rule), never a
  wrong figure.
- Review round 2 Nov: a held name maps back to its held id only inside the ask's company (else it is resolved in the
  named company; a subject not there goes on the "Not applied:" line); the declared pick of an offered basis / kind
  option answers V1; a ranking is marked by this message's own rank_direction / top_n, never by a carried measure.
- Review round 2, 3 Nov: agents, brands and categories carry as words and resolve fresh in the ask's company (no held
  id map; codes are unique per company); only customers keep a held id map, inside the ask's company. One open
  question rule: the declared pick of an offered option fills the slot the object left null (basis, outstanding kind,
  company, brand or account type). A month or year axis takes only this message's own count. The object counts on a
  report parse, or on any reply while a report question is open (the engine reads such a reply as its answer, flag
  off too).
- Review rounds 3 and 4, 3 Nov: the measure question stays a free question (no offered options; the model fills
  measure; the ask-all numbered reply is unchanged). A held customer is looked up again in a switched company by
  its exact name, behind the customers permission, and for a dealer only among its linked customers. A carried name
  missing in the named company gets the same reply as the same name typed there.
- A held brand whose code equals another brand's name is asked "matches several brands" on the next turn (fails
  safe, never a wrong figure).

## Deletion (PR B; origin/main line numbers)

report_ask.py: `names_its_own_ask` 800-856, `_new_subject` 859-862, `_swappable` 865-870, `_other_axis` 873-884,
`_reply_wins` 887-904, `_echoes_axis` 907-911, `_swap_axis` 914-922, `_carries_answer_op` 925-930, `_binds_subject`
933-939, `as_basis_answer` 942-998, `as_kind_answer` 1001-1070, `kind_edits` 1073-1151, `restates_the_ask`
1154-1163, `as_held_refine` 1171-1208, `_settled_by_its_axis` 1211-1217, HELD keys 1222-1231, `_follows_up`
1238-1253, `_holds_a_customer` 1256-1259, `with_held` 1262-1330, `typed_group_by` 790-797, `_reply_fills`
1877-1906, `_customer_stays` 2411-2423, `_widened` 2426-2432, `_refine` 2435-2558; `_settle`'s answering-slot
(2047-2163) and frame-hold (2167-2297) branches. engine.py: 6102-6123, 6136-6153, `held_domains` 5703-5705.

## Spend (crew approved 2 Nov, x1, ORG key, ledger lines before and after in
crew/state/eval/gemini-org-key-ledger.md, key last4 only)

- Parser prototype: 15 gold rows + no-op control x1, about USD 0.05 (flash-lite).
- Agentic yardstick: the same 14 turns + srt pair on the copy with `force_agent` each turn, up to USD 0.65.
- Runners stop on any 429 or two busy replies.

## Tests (red first, LEAD pattern: tester red, coder green on Opus, reviewer)

1. Parser unit: the marker sets `ParserConfig.report_ask` and adds `report_ask` (required, nullable, strict) to the
   schema; an unmarked text's schema is byte-identical to today's.
2. Context: with the flag, the user block carries `Held report:` naming the agent, account type, brand, category,
   customer, company BY NAME, plus basis, period, breakdown, count, channel; without the flag it is unchanged.
3. Lane / engine (real `engine.run_turn`, Postgres, fake parser returning the object): the 14 owner turns and the srt
   pair as conversations; each turn asserts the args that RAN (or the question asked). Rewritten from #2092's
   tests/chatbot/test_report_multiturn_carry.py (MC-1..MC-13): same expected route args, new fake parser shape.
4. Rails: object basis not said and not held -> basis question; object company foreign -> forbidden line; dealer ->
   refusal; word in both tables left unsure -> brand or account type question; two agents matching -> pick.
5. Flag off: the #2070 / #2074 / channel suites stay green unchanged.
Global guards not needed (no table, no list endpoint).

## Owner rulings checked

Basis never defaulted (27 Oct): V1. Outstanding summary, no company question on outstanding (29 Oct): kept (the
outstanding branch of `_settle` 2324 unchanged). Structured replies, no free-form (16 Oct): kept, same template.
Semantic, no word lists (1 Nov brief): the model edits the object; code checks values only. Restated ask drops what it
does not name (17 Sep pass 6): R3.
