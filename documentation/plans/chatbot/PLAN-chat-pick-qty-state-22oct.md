# PLAN: CHAT-PICK-QTY-STATE - the state path keeps the old path's pick / quantity / clear safeguards (parity)

**Status:** Review (22 Oct 2026). #1825 is the chat RE-RELEASE branch (crew decision 22 Oct): main d400da75db +
re-applied #1823 (9e23244cc6, the base of crew/explore-1022) + this lane's fixes; both prompt paths are gates (v63 old
path, v92 state path). The prod-only focus_diff fix ships separately as #1827 off plain main. Track: SMALL FIX. Red-first,
kill-proof per slice, one reviewer. Backups: crew/chat-pick-qty-state-pre1826 (on #1823), -reverted-base (on main).
**UAC:** `chat-pick-qty-state-acceptance-criteria.md` (alongside). Evidence (local only, never committed): crew incident
file `prod-chat-1022-pick-qty.md` (owner's prod turn table, 22 Oct 00:00 MYT).

## Goal
With the `## Conversation state and state_changes` heading in the parser template (prod v64 = `lean-index/parser-v92.txt`),
the chatbot gives the SAME result the old decide() path (prod v63, no state heading) gives today for 2 and 3; 1 is a
defect on BOTH paths (owner retest on v63, 22 Oct 01:13 MYT: `1` on a did-you-mean resumed the open one-slot task left
by the earlier v92 loop):
1. a pick answer (`1`, a code, a quoted pick) to an open did-you-mean: answers the picked product, never resumes an
   older (open or parked) task. Fix in task.run: when the parser returns an open_question_answer for the stored open
   question, that answer wins and the resume rule (task.py:677-696, from #1247 bc0e6e2601) does not fire. No new rule,
   no keyword check: the override is removed;
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

## Measured (22 Oct, lane DB copy of sorento_explore1020, dry run, egress blocked, dev key)
- Replay, dealer contact, 8 turns x 3 arms (A v63 composer off Block; B v92 composer on Index; C v92 composer off
  Block). The parse of `1` (did-you-mean pick) and of `2` (after "How many units of CL8109A?") is the same on v63 and
  v92: open_question_answer pick [n], reference_positions [n]. So bugs 1 and 2 are code after the parser.
  "Clear all": v63 topic_reset true + mode cancel; v92 topic_reset true in C, false in B.
- Old path given parse B (topic_reset false, mode null) also clears nothing: parser variance, not a parity gap.
- Parser gold set `scripts/chatbot_eval/gold/parser_pick_qty.jsonl` (16 rows), x1: picks by number, code, Malay,
  Chinese and a continuously numbered roster pass on both prompts. A bare `2` over the quantity question: v63 gives no
  position, v92 gives position 2 even with no last list, so on v92 the shared code safeguard holds it. Reset phrasings:
  topic_reset true 6 of 7 on both; "padam semua" false on both.
- Case 2 (owner Console, staff): a multi-product answer numbers items 1..11 and its did-you-mean 12-14
  (turn/compose.py:479-492, product_pick :535-540); answer_bridge.py:287-288 `apply_crossdomain_hit` then replaces that
  roster with the zero-stock escalate offer (or None), so `13` finds no option on either path. Ruling (crew-relayed): the
  numbered question wins; keep the roster, render the rung without the offer sentence. No escalation-audience change
  (owner ruling 22 Oct: as today, availability-only contacts get no offer per HT26, dealer-tier contacts keep it per
  s11 26 Sep). Fact for a later lane, not changed here: the HT26 strip runs only on inventory/incoming turns
  (engine.py:7828-7833; tests/chatbot/test_stock_ask_ht26_dealer_no_escalation.py:216 pins a promotion turn unstripped).

## Slices (re-release base, head after 2c98063e07)
1. task.run resume arm: the parser's answer, applied to the stored question (decide() ANSWER: a fitting pick or a yes),
   wins over the resume rule (red 56b383324d + 3ba6639897, fix e423c9481b + e407a181dc). Both paths.
2. One bare-number predicate for both paths, `chat_state.bare_position_quantity`, called by the old path and by the
   state-path pick loop only while the quantities question is open (red 1a3ab4b58e + 0a28eaa5ad, fix 144f39068e +
   3a6cdba69e). The #1823 quoted-list rule is kept.
3. A topic reset on the state path drops the stored list (red e47f774f29, fix 69281935f6); focus_diff diffs the union of
   keys (red d7420debfe, fix 5864e17f0e; prod copy #1827).
4. A numbered did-you-mean keeps its roster over the zero-stock offer, answer_bridge.py `apply_crossdomain_hit` (red
   c0655a9a59, fix 0091b1f24f).
5. The parser's item quantities answer the quantity question in pick mode too, apply.py `_open_question_answer` (red
   fe70fe1a08, fix 1d2e6c6554).
6. Overnight (EVAL-BENCH class battery, 22 Oct): the small-talk recap's "Last time" reads closed episodes only (red
   8b63d41bf3, fix dd6827c43f); a declared cancel / decline of the stored question blocks resume and keeps its decline
   arm on the state path (red b57ee374fd, fix a8f483fd82; R1 35638c9ff3: only with a stored question); a declined
   did-you-mean drops its unresolved token (red f084f1a4bd, fix 83adba6fa9; R2 1dcdadee2a); a topic reset wins over the
   pending-answer early returns: no stored pending survives it (red 11f22ea3bd, fix 4b448ea9d5).
   Parser gold set widened to 68 rows in 8 classes (3e91d6ebe6); x1: v63 67/68, v92 65/68.
   Old-path gaps NOT changed: v63 stores no numbered data list (tail.py ~188, state path only), so a row number over a
   multi-product answer cannot pick on v63; v63's file-kind question has no numbered kinds without closed lists
   (engine.py ~7744).

## Coordination
REPORT-SMART-L (#1816) and CHAT-CLOSED-LISTS-L (#1755) touch turn/apply.py, chat_state.py, task.py; keep the diff to
the seams above, rebase often.
