# PLAN: CHAT-STATE round 7 - one open referent: the last list or question the bot showed (LAST-REFERENT)

**Status:** Plan, approved by crew a51605376 (a) (20 Oct): lands on #1772 (`crew/chat-state-r2`). Track: inside the L
lane, LEAD pattern (tester red -> coder -> lead kill-proof -> reviewer + security-reviewer -> L1 gate -> ONE push).
**UAC:** `chat-state-last-referent-r7-acceptance-criteria.md` (alongside). **Source:** owner rule 20 Oct 07:04 on the
bench pass audit row 6 ("I thought the list supposed to stay open? So whatever the last open question should be the
reference for the picker?"); crew review F5 (CHAT-ARCH-REVIEW-20oct.md:104-107, "a shown list mints a State `last
list`", owned by CHAT-STATE).

## Goal
A list the bot showed stays open. A bare number or a pick refers to the NEWEST of: the last list, the pending question,
the open stock task. One referent, chosen by recency, never by type. Every row kind of a list is pickable.

## Today (measured 20 Oct, head 7f299b4cc8)
- `Focus.last_list` exists (turn/state.py:209), one writer `turn/tail.py:103-125` (`last_list_after`), state path only.
  A newer list replaces it; a turn that shows nothing keeps it. It carries no turn stamp.
- Precedence is by type: `turn/question.py:129-141` picks required_ask, then pending, then the stock task; a data list
  is never the question. `turn/apply.py:2613-2639` `_bare_position_is_the_quantity` turns a lone position into
  `demand_qty` whenever a stock task is owed a number. Audit row 6: "1" after a two-file promo list, with the older
  MKS9505-GM-HC how-many still open, answered "MKS9505-GM-HC x 1".
- Only product rows with a code are pickable (`turn/chat_state.py:809-812`; `_row_item` keeps only "Product Code",
  tail.py:89-100); a promo / file / order row is shown but never pickable.
- Stamps that exist: `Pending.asked_at_turn` (turn/pending.py:82), `Task.touched_at_turn` (turn/task.py:91),
  `State.turn_no` (turn/state.py:313).

## ARCHITECTURE
1. Layer: State (the tail writer + the chat_state view / applier). No new text rewriter. The prompt lines are
   CHAT-CODE-LOOKUP's template (P1-P3 sent through crew 20 Oct).
2. Shared mechanism: `last_list` rows carry their kind + key (product id/code, attachment id, promotion id, order id)
   and the list carries `shown_at_turn`. One function in turn/chat_state.py, `open_referent(state)`, returns the newest
   of {last list (shown_at_turn), pending (asked_at_turn), stock task owed a value (touched_at_turn)}. The view prints
   only that one as open (an older stock task prints as a held task, not as the open question); the pick and a bare
   number resolve against it.
3. Also fixes: picks on file, promotion and order lists; the 26 Sep picker-not-sticky ruling still holds by recency
   (the how-many asked after the list is the newest); a pending roster vs a newer list.
4. Removes on the state path: the type rule in `_bare_position_is_the_quantity` (apply.py:2613-2639; it reads
   `open_referent` or stands down under the state gate), the product-only `_pickable` rule (chat_state.py:809-812),
   the "Product Code"-only row key in `_row_item`. Off the state path nothing is recorded (decide.py:237-302) and the
   legacy rule stays until the state flag retires (state-off byte-identical, lane invariant).

## Slices (each: tester red -> coder -> lead kill-proof -> reviewer; L1 gate at round end)
- R7-1 writer: `last_list_after` stamps `shown_at_turn` and keeps each row's kind + key for every row kind.
- R7-2 referent: `open_referent` + the view prints one open referent; the stock task under a newer list is held.
- R7-3 readers: the pick resolves against the referent for every row kind into the right Subject axis; the bare-number
  rule reads the referent. The 2 code pins of the old rule change with an owner-rule cite: test_chat_state_apply.py:488,
  test_stock_ask_ht26_r5_picker_not_sticky.py:101 (its prompt-text pin :127 moves with CHAT-CODE-LOOKUP's P1).

## Measurement
L1 replay gate (base 7f299b4cc8) for first asks / state-off; the state-path effect rides the paired TRAIN x1 that
already waits for the DEV key (cap 0.3 USD).

## Round log
