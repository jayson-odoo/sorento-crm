# PLAN: chatbot totals vs top-N, company vs brand, clearing a held filter, combined turn (4 Nov 2026)

Status: merged (main 2adb19b7, 5 Nov 2026, owner hand test PASS); shipped in release 30bbcc6a7c with parser text v202
md5 d29c1983 on the production label (prod v72). Follow-up for the owner's prod transcript on v72 (widen and re-ask):
PLAN-chatbot-report-widen-reask-7nov.md.

## Journey

A staff user asks the sales chatbot (Chatbot Console, staff contact) for sales totals and then refines them over
several turns: narrow to a company, split by channel, drop a filter. Owner test, 4 Nov ~09:20 MYT, prod console,
contact Mr Loo, parser prompt v70.

Failures reported (owner's words in the lane brief):
- F1 a TOTAL ask was treated as a RANKING ask ("How many? For example top 5" / "By quantity or by amount?").
- F2 "sorento company only" held BOTH Company: Sorento and Brand: SORENTO.
- F3 the held brand could not be cleared ("all brands", "brand is all brand"); "clear the brand filter" dropped
  everything and re-asked basis + period.
- F4 "sorento company only, show dealer and project" applied the filter but not the breakdown.
- F5 a fresh full question kept Company + Brand from earlier turns (brand should never have been added, F2).

## Replay (baseline, origin/main 240d6e8679; prod runs 24189427cb, same chatbot code)

Copy :8102 on sorento_prod_1020, parser pinned to version id 2247a9af (md5 57d7d412 = prod v70 per crew record),
contact Mr Loo with the agent switch off for the run (prod console replies were bot-path). Raw traces:
`crew/state/files/chatbot-trace-4nov/replay/baseline.jsonl` (crew state only; real names stay out of the repo).

Findings so far (x1, gemini-3.5-flash-lite):
- F2 reproduced: C4 "sorento company only, show dealer and project" -> Company: Sorento AND Brand: SORENTO.
- F4 reproduced: C4 kept the held channel split but added the brand; the split itself survived here.
- Carry loss not in the owner's list: B3 / E3 ("break down project and retail", "top 10 products") dropped the held
  period and basis and re-asked them; C3 (same text, same state as B3) kept them. Parser variance on one input.
- F1 not reproduced x1 on a clean thread (A1, E4 gave a total). The ranking asks fire when the verdict carries a
  ranking frame; root cause is in which field decides that (see root-cause note).

## Two carry paths (decides where the fix goes)

#2105 (merged 3 Nov, deployed 24189427cb) added a NEW report-ask path behind the prompt marker
`parser.REPORT_ASK_LINE` (`head/parser.py:963`, `:1198`): the parser writes the whole report ask each turn and
`report_ask.from_object` (`lanes/business/report_ask.py:3273-3407`, called at `engine.py:6308`) applies it.
Production serves v70 (md5 57d7d412 + one trailing newline; sorento_dev_1028 v70 = 0e52eb27 differs by that newline
only), which has no marker, so production runs the OLD coded carry. PR B deletes the old carry (~950 lines) after
the owner moves the parser label to the candidate text e4aa6d43.

Second replay on the new path (copy on sorento_prod_1020, the e4aa6d43 text saved unlabelled as v196 id dfd08dcf,
`replay/newpath-e4aa6d43.jsonl`):
- F3 fixed there: B5 "brand is all brand", B6 "all brands", B7 "clear the brand filter" each dropped the brand and
  kept company, channel split, period and basis.
- F4 fine there: C4 applied the company and kept the split.
- F2 still there: B4 / C4 "sorento company only" -> Company: Sorento AND Brand: SORENTO.
- F1's exact asks appear there: C5 "show delaer and project" -> "1. How many? For example top 5. 2. By quantity or
  by amount?".
- New-path-only defects: A1-A3 asked the basis three times although "deliver" was typed; E4 carried the dealer
  customer from the earlier thread into "Total sale deliver ... Sorento brand".

## Root-cause note (file:line, `:N` = `lanes/business/report_ask.py`)

- F1 total read as ranking [both paths]. The asks are `TOP_N_QUESTION` :36 and `METRIC_LINE`
  (`ranking_ask.py:10`); they fire whenever `args.group_by` is set (not month/year) and `top_n` / measure are
  missing (`_given_top_n` :1936-1946, `_given_choices` :1949-1960). The parser has no field that says "total, not a
  ranking" or "breakdown, not a ranking" (`head/parser.py:318-414`); `report_breakdown` is engine-only (:476,
  :619-644). Old path: a null `group_by` on a reply means "no change" (`_reply_fills` :1967-1996, `_swap_axis`
  :915-923), so a held axis can never be dropped by "i want total sales"; `from_top_selling` :481-508 forces
  `group_by` product. New path: a total needs `group_by` null (:3359-3360); a typed split without the engine flag
  gets both asks (C5).
- F2 one word, two filters [both paths]. Company comes from the parser scalar `sales_company` (`_company_said`
  :2490-2495, set :2429-2433); brand from an entity hint `brand` (`take_words` :746-788 -> `_word_filters`
  :1481-1588 -> `brand_ids`). Nothing checks that the brand word is the company just named. #2105's overlap ask
  (`_account_plan` :1601-1689) covers brand vs account type only (:1628-1633).
- F3 clearing one filter [old path]. `_widened` :2513-2520 widens channel / product / customer / company only;
  "all brands" is ignored (:2546). The clear-brand op empties `focus.brands` (`turn/chat_state.py:449-450`), not the
  frame's `brand_ids`. "clear the brand filter" took the reset path (`engine.py:5014-5048`, `:5083-5096`,
  `turn/apply.py:84` keeps only tier + brands). New path: `_carry` :3410-3431 skips a widened kind
  (`turn/decide.py:446-456`).
- F4 combined turn [old path]. `_refine` never sets `group_by` (:2269, :2544), so a turn read as a refine drops the
  typed breakdown.
- F5 carry [both]. Follows from F2 (the brand should not exist); whether a complete new question keeps held filters
  is the owner's call (card).
- #2105 follow-up: `with_customer_groups` :2862-2871 queries a uuid column with any truthy id -> DataError on a
  non-UUID; same unguarded `in_` in `arg_names` :3025 and `_group_names` :3060. Guard as `_gate_ids` :1413-1422
  (`fetch.is_uuid`, `fetch.py:357`).
- Rate limit "Too many reports in the last 10 minutes": per user, System Settings `report_ask_rate_limit` /
  `report_ask_rate_window_minutes` (`api/v1/order_management/report_ask.py:49-51`, `:514-516`), default 10 / 10.

## Behaviour card

`crew/state/files/chatbot-trace-4nov/card-totals-filters.md` (real examples stay in crew state). Answers above.

## Architecture

Layer: backend chatbot only. Parser report-ask object (`head/parser.py`, marker path), the parser prompt text (a DB row;
the edits are recorded in `PROMPT-chatbot-totals-filters-d29c1983.md`), and `report_ask.from_object`
(`lanes/business/report_ask.py:3409-3590` at c1a5da1ee4; :3273-3407 on main before this lane). No FE, no migration, no old-path code (PR B deletes it).

- M1 ask frame. The report-ask object gets `frame`: `total` | `breakdown` | `ranking` | null. `from_object` acts on it:
  - total: axis None (status `sales_report`), the held axis and top N are not carried.
  - breakdown: the object's axis (else the held one), `report_breakdown` set, so no count or measure ask. Stray message-level
    `rank_direction` / `top_n` / `rank_by` do not turn it into a ranking.
  - ranking: today's path; count and measure are asked only when missing.
  - A frame with an axis counts as typed for the held-axis rule (`:3337-3346`), so the object's axis wins over a held one.
  - null or absent: today's inference, byte for byte (texts without the field).
- M2 one name, one filter (owner Q2 (c)). In `from_object`, a name said in THIS message that is both a brand and a company the
  contact can see (found from data: the brand catalogue and the contact's companies, no name list) is resolved by its
  entity's `kind_said`: company -> company only; brand -> brand only; both kinds -> both filters; null -> ONE kind
  question (the #2105 kind ask, `_kind_ask` `:1721-1727` / `_kind_options` `:410`, with company, brand and both), whose
  answer fills the slot(s) and keeps the rest. A contact who sees one company gets the brand, no question. A name held
  from an earlier turn and not said now is untouched (Q3). Parser fields consumed, nothing read from the user's text.
- M3 clear one filter. No new mechanism: the new path's widen (`turn/decide.py:446-456` `widened_kinds`, `_carry`
  `:3410-3431`). Tests lock every filter kind; a kind that fails gets the same widen handling.
- M4 basis. Prompt only: the message's own basis field is filled when the message says it. The V1 never-default guard
  (`:3313-3315`) stays.
- M5 DataError. `with_customer_groups` (`:2862-2871`), `arg_names` (`:3025`), `_group_names` (`:3060`) skip non-UUID
  ids (`fetch.is_uuid`, as `_gate_ids` `:1413-1422`).
- Prompt. New text = e4aa6d43 + three anchored edits (frame, one name one slot + `kind_said`, message basis), md5 pinned.
  Gates on gemini-3.5-flash-lite x1 (crew OK USD 0.80): parser-gold TRAIN no-op control both arms + gold rows from the
  UAC written as whole objects.

## Tickets

- T1 tester: red tests for the UAC rows not marked PENDING (engine level, stubbed parser objects, no LLM), new file
  `tests/chatbot/test_report_totals_filters.py`; `test(red):` commit alone.
- T2 coder: M1, M2, M5 (+ M3 gaps the tests show) until T1 is green; touched suites green.
- T3 coder: prompt text edits + parser schema key, no live calls; lead reviews the text.
- T4 lead: gates (gold + TRAIN control), md5 pin, ledger lines.
- T5 reviewer (opus), kill-proof per mechanism.
- T6 console pass on the copy pinned to the new text; hand test script; owner moves the label after his pass.
- T7 user guide: the sales chatbot page under `documentation/user-guides/` (frame, clearing a filter).

Test DB: throwaway `chatbot_totals_filters_ci` (template of an idle throwaway, migrated to head, owner sorento_crm),
`SORENTO_ENV_FILE=.env.ci-tests`; baseline `tests/chatbot/test_report_semantic_carry.py` 73 passed.
