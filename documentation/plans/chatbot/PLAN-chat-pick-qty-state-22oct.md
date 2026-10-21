# PLAN: CHAT-PICK-QTY-STATE - the state path keeps the old path's pick / quantity / clear safeguards (parity)

**Status:** Plan (22 Oct 2026). Track: SMALL FIX (crew rescope 22 Oct ~00:35: parity, not new behaviour; no behaviour
card, no owner questions). Red-first, kill-proof, one reviewer, parser gold set >= 8, LLM spend x1 per gate.
**UAC:** `chat-pick-qty-state-acceptance-criteria.md` (alongside). Evidence (local only, never committed): crew incident
file `prod-chat-1022-pick-qty.md` (owner's prod turn table, 22 Oct 00:00 MYT).

## Goal
With the `## Conversation state and state_changes` heading in the parser template (prod v64 = `lean-index/parser-v92.txt`),
the chatbot gives the SAME result the old decide() path (prod v63, no state heading) gives today for:
1. a pick answer (`1`, a code, a quoted pick) to an open did-you-mean: answers the picked product, never resumes a
   parked task;
2. a bare number answering "How many units of X?": it is the quantity, not a pick on an older list;
3. "clear all": whatever the old path does today.
Out of scope: discontinued candidates in did-you-mean (bug 5 of the incident), the "Last time" recap wording.

## Today (head f8e73e16e8, paths under sorento_crm_backend/app/services/chatbot)
- State heading gates (crew lookup): head/chat_state_prompt.py:66 -> ParserConfig.state_block (head/parser.py:899) turns
  on the State block (engine.py:4743), the state_changes schema (parser.py:1199/904), state_path (engine.py:4959) and
  chat_state.apply_changes (engine.py:4999). NOT gated: task_mod.run incl. its resume arm and `_open_pick_answer`.
- Pick answer: `_open_pick_answer` (turn/apply.py:2993) writes only reference_positions (:3069). `task_mod.run`
  (apply.py:3520-3534) runs before `_answer_pending` (:3563). The resume arm (turn/task.py:677-696) needs only
  `task.domain == domain_hint` and `_only_task_slots` (task.py:143, True on no entities :156-158); it ignores task status
  and the `positions` / `pending` it is handed (apply.py:3523-3525, unused per task.py:541-543). apply.py:3634-3659 then
  returns the task question with fetch=[].
- Bare number: the qty ask is an open question of kind quantities with `items` and no `options` (turn/question.py:130-141,
  task.py:1245-1273). On the state path, position 2 misses `options` (chat_state.py:1343-1345), falls to the stale
  last_list row branch (:1358; `_pickable` :863-871 lets product rows through) and :1565-1574 turns it into a product
  entity and clears reference_positions. The old safeguard `_bare_position_is_the_quantity` (apply.py:2647-2681, called
  :3419) runs later (engine.py:5537/6168/6220) and no longer sees a lone position. Card R4 (:1580-1586) then drops the
  owed task. last_list never retires (tail.py:190-191 keeps previous).
- Clear all: the state ops have no reset (chat_state.py:24-26, `_clear_axis` :401-433); new_subject keeps tasks and
  last_list (:1400). The prompt's `entity_op` "clear" (head/parser_template.py:346, 359) is read by no state-path code.
  Old path: own entity_op "clear" handling (crew lookup, to be measured by the replay).

## Method
1. Replay the owner's turn shape on v63 AND v92 (console `--say` dry run, scripts/chatbot_console_check.py, a lane DB
   copy, egress blocked, no sends). The v63 reply/trace per turn is the expected result. Table in the PR (codes only,
   no contact data).
2. `test(red):` per bug per path (state heading on AND off), tests/chatbot/, synthetic contacts.
3. Fix at the seam where the state path skips the old safeguard: one shared predicate, called by both paths.
4. Kill-proof, reviewer, parser gold set (scripts/chatbot_eval/gold/parser_pick_qty.jsonl, >= 8 varied messages, x1
   on v92 and v63).

## ARCHITECTURE
1. Layer: code after the parser (State applier + the task runner). The parser verdict is trusted as is; no text rules.
2. Shared mechanism: "an open question owns the turn's positions". The old path's own predicates
   (`_bare_position_is_the_quantity` / `_stock_task_owed_a_number` / `_lone_position`, and the pick-answer guard) become
   the single source both paths call, so the state path cannot drift from them again.
3. Also fixes (UNVERIFIED until measured): any open-question answer (attachment kind pick, company pick) arriving
   while a parked task shares its domain; any later list question shown over an older last_list.
4. Removes: the state path's private "lone position -> last_list pick" conversion while a quantities question is open.

## Coordination
REPORT-SMART-L (#1816) and CHAT-CLOSED-LISTS-L (#1755) touch turn/apply.py, chat_state.py, task.py; keep the diff to
the seams above, rebase often.
