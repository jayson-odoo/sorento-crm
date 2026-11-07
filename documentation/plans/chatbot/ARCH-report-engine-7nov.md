# ARCH: can the chatbot report engine scale? (REPORT-ASK-ARCH, 7 Nov 2026)

Status: proposal (scout, docs only, no app code changed). Track: architecture plan; each wave below is its own lane
with its own PLAN + UAC when the owner picks it up.

Owner, 7 Nov ~16:00, after REPORT-FILTER-ALL (#2209) took 8 rounds: "you see, ~480 branches, can we really scale for
more future features?"

Short answer: **not on the current shape.** The query layer and the renderer already scale (table driven, one
executor). What does not scale is the layer between the parser and the query: a full-state parser object whose
EMPTY slot is ambiguous (unchanged, cleared, or forgotten), resolved by ~30 named keep/clear/widen rules, then
flattened back into the old verdict fields and run through the 2016-style `_settle` path. Every rule is a guess about
what an empty slot meant, and every new phrasing moves the guess. The fix is to make the parser say what it means
per axis (an op), merge with one table, and validate once.

Measured on `origin/main` 61e9d217 and on #2209's head 89f14f49. Every number below was produced in this sandbox
(`radon` 6, Python `ast`), commands at the bottom.

---

## 1. Measurements

### 1.1 Size and branching

| File | main lines | #2209 lines | main `if` stmts | #2209 `if` | radon sum(cc-1) main / #2209 | worst function (cc) |
|---|---|---|---|---|---|---|
| `app/services/chatbot/lanes/business/report_ask.py` | 3781 | 3931 | **464** | **478** | 1702 / 1767 | `_settle` 199 (`report_ask.py:2198`, #2209 `:2201`) |
| `app/api/v1/order_management/report_ask.py` (route) | 1013 | 1013 | - | - | 400 | `report_ask` 263 (`:229-790`) |
| `app/services/reports/ask.py` (executor) | 737 | 737 | - | - | 150 | `run_ask` 35 (`:306`) |
| `app/services/chatbot/lanes/business/chat_report.py` | 462 | 462 | - | - | 132 | `_args` 46 |
| `sorento_crm_mcp/sorento_crm_mcp/presenters.py` (report part) | ~600 of 4118 | same | - | - | 238 (30 fns) | `_report_ask` 58 (`:3650-3764`) |

The "~480 branches" of the 5 Nov diagnosis are the `if` statements of `report_ask.py`: 464 on main, 478 on #2209.
Counting every decision point (radon: `if`, `elif`, `and`/`or`, comprehension filters, ternaries) it is 1702 / 1767.
`report_ask.py` on main: 122 top-level functions (135 with closures), 21 of them above cc 20. #2209: 144 with closures.

Functions above cc 40 in `report_ask.py` (main): `_settle` 199 (:2198), `from_object` 140 (:3456; #2209 158 at
:3496), `_fresh_args` 85 (:1877), `_word_kinds` 60 (:3365), `_account_plan` 59 (:1626), `_refine` 58 (:2628),
`as_kind_answer` 53 (:1022), `_word_filters` 50 (:1506), `as_basis_answer` 46 (:963), `kind_edits` 46 (:1098),
`by_capability` 45 (:596), `_drill` 44 (:2780), `with_held` 42 (:1288), `arg_names` 41 (:3114).

### 1.2 Which part does what (`report_ask.py`, every top-level function classified by its docstring)

| Part | main fns / lines / `if` | #2209 fns / lines / `if` | Where |
|---|---|---|---|
| (a) understanding the sentence: re-reading parser fields, seams before resolution | 27 / 478 / 70 | 29 / 515 / 71 | `by_capability` :596, `take_words` :761, `hold_words` :729, `drop_field_words` :692, `status_as_basis` :526, `from_top_selling` :496, `_word_kinds` :3365, `_open_pick` :3354, `_rows_on_screen` :3335; #2209 adds `_read_all`, `_legacy_all` |
| (b) merging with the held report (follow-up state) | 51 / 1339 / 185 | 54 / 1426 / 198 | `from_object` :3456, `_carry` :3684, `with_held` :1288, `as_held_refine` :1195, `_refine` :2628, `_drill` :2780, `kind_edits` :1098, `as_kind_answer` :1022, `as_basis_answer` :963, `names_its_own_ask` :821, `_held_object` :3271, `_customer_stays` :2603, `_widened` :2618; #2209 adds `_keep_held`, `_keep_held_report`, `_held_spelling` |
| (b)+(c) `_settle`: held refill, required fields and clarify in one body | 1 / 378 / 72 | 1 / 380 / 72 | `report_ask.py:2198-2575` |
| clarify questions (text) | 5 / 29 / 4 | same | `_kind_question` :425, `_basis_question` :345 |
| (c) building the query: words to ids, route params | 32 / 763 / 119 | 32 / 767 / 119 | `_fresh_args` :1877, `_word_filters` :1506, `_account_plan` :1626, `_company_or_brand` :1756, `route_args` :2920, `with_customer_groups` :2961 |
| (d) rendering / names | 6 / 109 / 14 | same | `arg_names` :3114, `error_line` :3045; the reply itself is `presenters._report_ask` (MCP) |

**(b) is 55% of the file's function lines (1717 of 3096 on main, with `_settle`) and 257 of its 464 `if`s.** Every
one of the 8 rounds of #2209 changed (b). (c) and (d) did not move.

Outside the file, the engine calls `report_ask` at 14 seams in a fixed order, each a separate rewrite of the verdict:
`engine.py:6367-6371` (`from_object`, `status_as_basis`), `:6555-6560` (`without_pick_axis`, `by_capability`,
`hold_words`), `:6773` (`drop_field_words`), `:6818-6850` (`as_basis_answer`, `as_kind_answer`, `names_its_own_ask`,
`as_held_refine`, `with_held`), `:6875` (`take_words`), `:7406` (`dealer_location_words`), `:3637` (`held_report`).
#2209 adds 140 lines to `engine.py` and touches `order_list.py:164` and `turn/decide.py`.

### 1.3 The keep/clear/widen rules (main), each a guess about an empty or noisy slot

1. `_carry` C6-2: per kind, a kind the message names nothing of keeps the held value (`report_ask.py:3684`).
2. CP-1: the held channel carries while a clarification is open (`:3709`).
3. HT1-18: an object company the message did not type is an echo of the held company (`:3589-3605`).
4. HT1-8: a ranking on the held breakdown's axis with no count stays a breakdown (`:3550`).
5. A reply to the open question keeps the held axis unless it types one (`:3570`).
6. C6-2 (turn 23d6cb50): an axis over a slot filtered to one value keeps the held axis (`:3577`).
7. CP-2 / CP-6: a ranking's measure is the object's, else the held one, else amount (`:3584`).
8. M1: a total drops the held axis and count (`:3538`).
9. M1: a breakdown with no axis takes the held axis (`:3540`).
10. AF-7: a counted breakdown is a ranking (`:3547`).
11. V1: a basis counts only when said or already held (`:3504`).
12. HT1: `said_as` decides company / brand / both for a company name (`:3630`, `_word_kinds` :3365).
13. ON-2 / CP-5: a brand slot over a same-name company puts the held company back (`:3637`).
14. Owner ruling B + S6b: a new axis after a ranking refills the held brand, category, agent, account type (`:2400-2441`).
15. S6c: the measure, basis and count on screen stay (`:2482`, `:2502`).
16. The held company carries unless widened (`:2459`).
17. `_customer_stays` CHATBOT-FOLLOWUP-CARRY (`:2603`).
18. `_widened` R-P3-09, `broaden_axis` = all drops one held axis (`:2618`, reader `turn/decide.py:446`).
19. `_refine`: only the keys the verdict changed re-run (`:2628`).
20. `as_held_refine` S3: a refine of the report on screen whatever type the parser named (`:1195`).
21. `with_held` R8: a ranking reply to a held total keeps period, product, measure, basis (`:1288`).
22. `_reply_wins` / `_swap_axis` S6c: a reply that swaps the axis drops that axis's filter (`:908`, `:935`).
23. `kind_edits`: a word-question answer also edits period, measure, basis, channel (`:1098`).
24. `names_its_own_ask` S2c: a sales verdict under an open question is a new ask (`:821`).
25. `restates_the_ask`: `ranking_refine` + `new_subject` is the whole ask again (`:1178`).
26. `_drill`: a drill drops the target axis's own held filter (`_AXIS_FILTERS` `:132`, `:2831`).
27. `_without_carried_products` P4: a product named now replaces a carried one (`:1856`).
28. `order_list.clears_the_brand` / `brand_word_alone` K1: raw-text keyword clears (`order_list.py:68`, `:81`, `:163`).

**28 on main.** #2209 deletes 3 (`_carry`, CP-1, the `sales_company` form of HT1-18) and K1 on report turns, and adds
5 (`_read_all` :3756, `_legacy_all` :3776, `_keep_held_report` :3786, `_keep_held` + `_MOVES` :3809, `_held_spelling`
fuzzy ratio 0.8 :3842), so **29 on #2209 head**. Rule tags cited in the file: 41 distinct on main, 40 on #2209.
Lines that say carry / keep / stays / clear / widen / drop: 221 on main, 235 on #2209.

### 1.4 Tests

- 169 backend test files reference `report_ask`; together they hold **3317** test functions on main, **3368** on
  #2209 (+45 in `tests/chatbot/test_report_filter_all.py`, plus edits). 114 files in `tests/chatbot/` carry report,
  sales, ranking, carry, outstanding or totals in their name.
- Most are rule tests: they pin one rule's output for one phrasing (for example
  `test_one_ranking_r2::test_r2_2`, `test_at34_a_new_axis_keeps_the_held_account_filter`). A rule test survives only as
  long as its rule; a corpus test (message + held state -> expected report) survives any rewrite. Section 3 moves the
  weight to the second kind.
- Parser gold already exists: `scripts/chatbot_eval/gold/parser_report_{semantic_carry,totals_filters,v92}.jsonl`,
  and #2209 adds `parser_report_filter_all.jsonl` (28 rows). L1 replay of recorded parses without any LLM exists:
  `scripts/chatbot_eval/replay.py`.

### 1.5 What the 156 recorded live turns on #2209 show

The two `crew-note` recordings (7 Nov 07:51, rec_part_aa / ab) are 6 runs x 26 steps: heads 2a8e6f7c and 4c1b310a,
3 runs each, prompt v79 289da7e5 (step 18 on v74), Gemini flash-lite. Each row: text, `report_ask`, `open_question`.

- **The parser emits full state, and an empty slot is ambiguous.** Step 18.2 "clear brand" (no-ALL prompt) leaves
  `brands` out in 6 of 6 runs, exactly like a turn that did not mention brands. No code can tell those apart; that is
  what rules 1, 2, 14, 16 and `_keep_held` each try to guess. With ALL (step 2) the same message writes
  `brands: ["ALL"]` in 6 of 6 runs: once the parser states the op, nothing has to be guessed.
- **Ops come out reliably; re-echoed state does not.** "remove cabana" (step 9) gives `brands: ["SORENTO"]` 6/6, but
  steps that only need the held state echoed vary: 8 of 26 steps differ across the 3 runs on 2a8e6f7c, 12 of 26 on
  4c1b310a (step 0 holds a `brands: ["SORENTO"]` its message does not name in 4 of 6 runs; step 10 "sales agent ACT" flips frame total
  / breakdown; step 20 company Sorento / ALL). A full-state contract makes the model re-copy every held slot every
  turn; each copy is a chance to drop or invent one.
- **The engine feeds the parser.** Step 11 "buang semua filter" writes company ALL in 3/3 runs on 2a8e6f7c and company
  Sorento in 3/3 runs on 4c1b310a, same prompt. The difference is the `Held report:` line the engine printed into the
  parse, so an engine change moves the parse. The corpus must record that line (the recording does not; Q4).
- Step 17 "break down project and retail" (dealer vs project split) already parses as `group_by: channel` 6/6:
  that "new report type" needs no code at all.

---

## 2. Target design

One sentence: **the parser says, per axis, what this message does to the held report; one table applies it; one
validator decides run or ask; one function turns the spec into the route's params; the route and the agent share it.**

```
parser  ->  ReportDelta  --merge(table)-->  ReportSpec  --validate-->  Clarify | RunnableSpec
                 ^ held spec printed as the Held report line             |
                 +---------------- answer to a Clarify is a delta -------+
RunnableSpec --resolve(axis table)--> ResolvedSpec --to_params--> crm_report_ask route --> reports.ask.run_ask
agent tool crm_report_ask(spec)  ------------------------------------------^ (same validate + resolve + run)
```

### 2.1 Types (new `app/services/reports/spec.py`, ~250 lines)

```python
AXES = {  # the ONE table: every filter axis, its kind, its route param, its resolver, its header label
    "company":      Axis(scalar=True,  param="company",          resolver="company",  label="Company"),
    "channel":      Axis(scalar=True,  param="channel",          resolver="enum",     label="Channel", values=("dealer", "project")),
    "brand":        Axis(scalar=False, param="brand_ids",        resolver="brand",    label="Brand"),
    "category":     Axis(scalar=False, param="category_ids",     resolver="category", label="Category"),
    "sales_agent":  Axis(scalar=False, param="sales_agent_ids",  resolver="agent",    label="Sales agent"),
    "customer":     Axis(scalar=False, param="customer_ids",     resolver="customer", label="Customer"),
    "product":      Axis(scalar=False, param="product_ids",      resolver="product",  label="Product"),
    "account_type": Axis(scalar=False, param="account_types",    resolver="account",  label="Account type"),
    "location":     Axis(scalar=False, param="warehouse_codes",  resolver="location", label="Location"),
}
class ReportSpec(BaseModel):          # the whole report: what the Held report line prints, what the agent sends
    kind: Literal["sales", "outstanding"]
    basis: Basis | None
    period: Period | None             # one slot: from + to
    frame: Literal["total", "breakdown", "ranking"]
    group_by: AxisName | Literal["month", "year"] | None
    top_n: int | None; sort: Literal["desc", "asc"] = "desc"; measure: Measure | None
    filters: dict[AxisName, list[str] | ALL]   # names as shown; ids ride beside them (`names` today)
class AxisOp(BaseModel):
    op: Literal["keep", "set", "add", "remove", "all"]; values: list[str] = []
class ReportDelta(BaseModel):         # what the parser emits; an ABSENT key is keep, by contract
    new_report: bool = False          # a fresh ask: merge starts from an empty spec, not the held one
    kind / basis / period / frame / group_by / top_n / measure: ScalarOp | None
    filters: dict[AxisName, AxisOp]
```

### 2.2 Merge: one table, no phrase rules (new `app/services/reports/merge.py`, ~80 lines)

| op | list axis (brand, agent, ...) | scalar (company, channel, period, basis, frame, group_by, top_n, measure) |
|---|---|---|
| absent / `keep` | held | held |
| `set` | values | value |
| `add` | held + values (dedupe, case-folded) | = set |
| `remove` | held - values | none if value == held, else held |
| `all` | ALL (no filter) | none (no filter / unset) |

Plus `new_report: true` (or a different `kind`): start from the empty spec. That is the whole merge. Three structural
invariants are derived from the spec, not from the message, and are table rows too:

- I1 `frame == total` -> `group_by = top_n = None` (today's M1, rule 8).
- I2 a breakdown/ranking ranks ACROSS its axis: the axis's own filter is not applied while it is the axis
  (`_AXIS_FILTERS` today, rule 26), but stays in the spec so "back to the total" gets it back.
- I3 a breakdown over an axis whose filter holds one value is one row: run as a total of that value (rule 6,
  without reading `rank_by` noise).

Everything else in 1.3 disappears: rules 1, 2, 3, 13, 14, 16, 17, 18, 22, 27 are `keep` / `set` / `remove` / `all` on
one axis; 4, 5, 7, 9, 10, 15, 19, 20, 21 are `keep` on a scalar; 23, 24, 25 are "the answer is a delta" (2.3);
11 and 12 move to validation (2.3); 28 is gone (no text read). The fuzzy company echo (`_held_spelling`) becomes the
company resolver's job: an unknown company name resolves against the contact's own companies or is refused, as
every other axis value already is.

`drill` ("top 5 customers of these agents") is `set` with `values` taken from the rows on screen: the position or
"these" reference is turned into that op by one converter (today's `_drill` keeps its row-reading part, ~40 lines,
loses its merge part).

### 2.3 Validation and ONE clarify policy (new `reports/validate.py`, ~200 lines)

`validate(spec, ctx) -> Run | Ask(field, question, options)` checks a fixed, ordered list; the first failure is the
one question:

1. kind / grant (`grant_key`, `not_enabled_line`: refusal, not a question)
2. period missing (`PERIOD_QUESTION`)
3. basis missing (V1: never defaulted; the outstanding kind question for an outstanding ask)
4. a name the resolver finds in two axes (brand vs account type vs company: today's `_account_plan`,
   `_company_or_brand`, `_kind_question`)
5. a name the resolver finds nothing or several of (today's `_word_filters` lines)
6. a ranking with no count (`TOP_N_QUESTION`; month/year trends never ask)

The open question is held as `(spec_so_far, field)`. **The answer is parsed like any message: a delta.** "delivered"
under the basis question is `basis: set delivered`; "brand" under the brand-or-account-type question is
`filters.brand: add [Cabana]`; a numbered pick is converted to the same op by `rf.picked_option` (exists). So
`as_basis_answer`, `as_kind_answer`, `kind_edits`, `names_its_own_ask`, `restates_the_ask`, `_reply_fills`,
`_resolve_period/_top_n/_metric/_basis` (~600 lines) are replaced by "merge the answer's delta, validate again". A
message that is a new ask under an open question says `new_report: true`; no code decides it.

### 2.4 Query and render

- `resolve(spec)` walks `AXES` and calls one resolver per axis (today's `_word_filters`, `_account_plan`,
  `_product_args`, `_customer_in`, `_in_company` become resolver entries, unchanged inside). Held names reuse held
  ids (today's `names` map) so a held customer is never looked up again.
- `to_params(resolved)` is a loop over `AXES[...].param` (today's `route_args` + parts of `_fresh_args`).
- The route keeps every gate (grant, audience, company, location policy) and calls `reports.ask.run_ask`, the one
  executor over `CATALOGUE` (`reports/ask.py:54`), which is already table driven. Its 263-cc param validator
  (`report_ask.py:229-790`) gains a `ReportSpec` body path and shares `validate` with the chatbot.
- Render stays `presenters._report_ask`; the header lines ("Company:", "Brand:") read `AXES[...].label` from the spec,
  so a new axis is shown without presenter code.

### 2.5 One engine for chatbot and agent

The agent already calls the SAME route (`crm_report_ask`, `agent/tools.py:111`, guards at `:1252-1272`) with flat
params, and it has no held-state problem: it sends a full spec each call. Give `crm_report_ask` the `ReportSpec` JSON
schema as its tool schema, and run `validate` + `resolve` for both callers. `crm_query` (`agent/query_tools.py`,
`assistant_registry/query.py`) is a row/group read over registry entities with no basis, period or reveal semantics,
so the recommendation is NOT to fold sales into it (Q2).

### 2.6 How a new feature lands (end state)

| Feature | Files | ~Lines | Tests |
|---|---|---|---|
| New filter axis (e.g. region) | `reports/spec.py` AXES row (5), `reports/ask.py` CATALOGUE filter + dataset column (10-20), resolver entry (10-30), prompt: one schema key + one bullet (new md5) | 40-80 | merge-table tests are parametrized over `AXES` (free); 1 resolver test; 4 corpus turns (set / add / remove / all) |
| Dealer vs project split | none: `group_by: channel` exists and parses 6/6 (step 17) | 0 | 2 corpus turns |
| Supplier outstanding | new dataset `reports/datasets/purchase_order_lines_open.py` (~150, like `unpaid_documents.py`), CATALOGUE entry (20), `kind: supplier_outstanding` + its allowed axes (supplier, product, brand, location) (10), `supplier` AXES row + resolver (30), presenter header (20), prompt kind value | ~250 | dataset test vs seeded POs, 1 validate test (axis not allowed for the kind), 6 corpus turns |
| Sales leaderboard (agents vs target) | `measure: achievement` row on the invoiced definition joining `sales/achievement_service.py` (60-100), presenter column (20), prompt measure value | ~120 | executor test, 3 corpus turns |

No feature touches `merge.py` or `validate.py`'s order. Today the same "new axis" touches `_AXIS_FILTERS`,
`_CARRY_KINDS`, `_FILTER_SLOTS`, `_MOVES`, `REPORT_ASK_KEYS`, `_object_of`, `from_object`, `_fresh_args`,
`_settle`'s refill and `_widened`, and each needs its own keep/clear decision.

---

## 3. Migration path

**Golden corpus (built in W0, kept green by every wave):**

- L1 engine corpus, no LLM: `tests/chatbot/golden/report_turns.jsonl`, one row per turn: `held_spec`, the recorded
  parser object (or delta), `open_question`, expected `{route_params | ask_field | refusal}`. Sources: the 156
  recorded turns on #2209 (6 runs x 26 steps, distinct objects deduplicated), the owner's Expected list from the
  7 Nov 04:41 `crew-handtest` (steps 1-20), the 5 Nov / 5 Nov 23:32 crew gate notes (2a8e6f7c, ee34327b, d15853fa
  findings), and the existing gold files in 1.4. Run as one parametrized pytest through the real engine with
  `replay.py`'s recorded-parse mode.
- L0 parser corpus, live, budgeted: same messages + the `Held report:` line -> expected delta, graded by
  `scripts/chatbot_eval/parser_gold.py`. Every prompt is pinned by md5 (as `test_report_filter_all.py:382-390` pins
  698e137b / d29c1983 today); a prompt edit is a new md5, a new candidate file and a re-grade, never an edit in place.
- Pass bar per wave: L1 100% (the corpus is the spec); L0 per-step pass rate n/3 not below the previous published
  prompt's on the same step.

| Wave | What | App change | Delete | Size | Time | Risk |
|---|---|---|---|---|---|---|
| W0 | Corpus + harness (above); re-record the 26 steps with the `Held report:` line (Q4) | none (tests + data) | nothing | ~300 test lines + data | 0.5-1 day | low |
| W1 | `spec.py`, `merge.py`, `validate.py`, `to_params` as pure functions; **shadow**: on every object turn, convert the full-state object to a delta (absent = keep, ALL = all, a changed list = set) and log new-path params vs legacy params into `turn_trace` | additive only | nothing | ~600 + ~400 tests | 2 days | low (no behaviour change) |
| W2 | Delta prompt: the parser emits per-axis ops; the engine takes the new path when the prompt text carries a `report_delta` marker (as `ParserConfig.report_ask` gates today), old prompts keep the old path | engine seam at `engine.py:6367`, new prompt candidate (md5 pinned), gold rewritten to deltas | nothing yet | ~300 + prompt + 40 gold rows | 2-3 days | medium: model reliability on ops (the corpus says ops are the stable part) |
| W3 | Clarify as delta: the open question's answer merges like any message | `turn/` open-ask plumbing for this ask | `as_basis_answer`, `as_kind_answer`, `kind_edits`, `names_its_own_ask`, `restates_the_ask`, `_reply_fills`, `_resolve_*`, the 6 engine seams at `:6818-6850` (~ -900) | net ~ -700 | 2 days | medium |
| W4 | Delete the legacy follow-up path once the delta prompt is published in production and W1's shadow log shows no unexplained diffs for a week (Q5) | report_ask.py, `order_list.py:163-170`, `turn/decide.widened_kinds` report use | `with_held`, `as_held_refine`, `_refine`, `_settle`'s refill (`:2400-2510`), `from_object`'s rules, `_keep_held*`, `_held_spelling`, `_legacy_all`, `_customer_stays`, `_widened`, `_carry` leftovers; rule-only tests rewritten as corpus rows (~ -1800 app lines, a few hundred rule tests) | net ~ -1600 | 2-3 days | high, mitigated by W0 corpus + W1 shadow |
| W5 | Agent shares the spec: `crm_report_ask` schema = `ReportSpec`, route body path, one `validate` | `agent/tools.py`, route | the agent's own arg guards that `validate` covers | ~200 | 1 day | low |
| W6 | Resolution as the AXES resolver table; `_settle` / `_fresh_args` split | report_ask.py | `_settle` (cc 199), `_fresh_args` (cc 85) as monoliths | net ~ -400 | 2 days | medium |

Total ~12-14 working days of lanes, sequential (W1 before W2; W3 and W5 can run in parallel after W2). End state
estimate: `report_ask.py` 3931 lines / 478 `if`s becomes ~1200 lines across `spec.py` (~250), `merge.py` (~80),
`validate.py` (~200), resolvers (~500), lane glue (~150), with ~120 `if`s, almost all in resolvers that do not change
when a phrasing changes.

What this does NOT fix: parser variance. 8-12 of 26 steps already vary across 3 runs of the same text. Ops shrink how
much the model has to copy each turn (only what the message changes), which is the part that varies most, but a
misread op is still a misread; the corpus measures it per step instead of a patch chasing it.

### 3.1 While the waves run

- No new keep/clear rule in `report_ask.py`. A failing phrasing becomes a corpus row (red, marked expected-fail) and
  waits for W2.
- #2209 is the bridge, not wasted work: its ALL value is exactly the `all` op, and its prompt edits are the first
  half of the delta prompt.

---

## 4. Questions (max 5, each with a recommendation)

1. **Parser contract: per-axis ops (delta, absent = keep) or full-state object (today)?** Recommendation: ops,
   because the ~29 rules exist only to guess what an empty full-state slot meant, and the corpus shows the explicit
   op is the stable output ("clear brand" with ALL 6/6, without 0/6 distinguishable).
2. **Agent sharing: `crm_report_ask` with the `ReportSpec` schema, or sales as a `crm_query` entity?**
   Recommendation: `crm_report_ask` + `ReportSpec`, one route and one executor; `crm_query` has no basis, period or
   reveal semantics and would be a second sales engine.
3. **#2209: merge it as the bridge and freeze rules, or park it for W2?** Recommendation: merge once its hand test
   passes, then freeze: no new rule patches, failures become corpus rows.
4. **Corpus: may crew re-record the 26 steps with the `Held report:` line, and is the 7 Nov hand-test Expected list
   the expectation per turn?** Recommendation: yes to both; without the held line a parser row is not replayable
   (step 11 shows the held line moves the parse).
5. **Shadow logging (W1) in production for a week before W4 deletes the old path?** Recommendation: yes, trace only,
   no behaviour change; it turns "did we break a phrasing" into a diff count.

---

## Appendix: how the numbers were produced

```bash
pip install radon
git worktree add ../pr2209 89f14f49          # #2209 head; main = 61e9d217
# radon cc sum, functions, max cc: radon.complexity.cc_visit over each file (closures included)
# if statements: ast.walk count of ast.If per file / per function
# classification: every top-level def of report_ask.py assigned to (a)/(b)/(c)/(d) by its docstring
# tests: grep -l report_ask -r tests | xargs grep -c '^\s*def test_'
# corpus: the two crew-note jsonl blocks of #2209 (7 Nov 07:51), 156 rows, grouped by (head, step)
```
