# PLAN: CHAT-STATE round 7 - the referent of a bare number: the quote first, then today's rule (LAST-REFERENT v2)

**Status:** Build v2 complete, reviewer READY + security PASS + L1 gate clean, pushing to #1772; approved: owner 20 Oct ~07:55 ("oh ok yeah correct") on crew's three rules; crew un-HOLD. v1
(recency: the newest of list / question / task wins) is withdrawn (owner 20 Oct ~07:40 "how many outranks a newer
list"). Lands on #1772 (`crew/chat-state-r2`). Track: inside the L lane, LEAD pattern (tester red -> coder -> lead
kill-proof -> reviewer + security-reviewer (MCP presenter + fetch ids) -> L1 gate -> ONE push).
**UAC:** `chat-state-last-referent-r7-acceptance-criteria.md` (alongside). **Source:** owner r40 case-12 ruling (a
QUOTED reply follows the quoted message's context); owner 20 Oct ~07:40; crew review F5 (CHAT-ARCH-REVIEW-20oct.md:104-107).

## Goal
1. A quoted reply's referent wins: "1" quoting the flyer list picks flyer 1; "1" quoting the how-many is the quantity.
2. Without a quote, today's rule stays: an open how-many beats a newer list (`turn/apply.py:2613-2639`).
3. Promo, file and order rows of a shown list are pickable by number only when no question is open, and a pick fetches
   exactly that row.

## Today (measured 20 Oct, head a77e5d8b9d)
- Quote: respond.io `replyTo.id` (engine.py:1186-1190) resolves to the quoted ChatbotTurn by message id, text match as
  fallback (quoted.py:64-132; `QuotedTurn.turn_no` quoted.py:39). `_quoted_context` (engine.py:1213-1286, called ~4370)
  swaps `state_in.focus` + `pending` for the quoted turn's; the live ones ride `State.quoted_live` (turn/state.py:324)
  and are written back by `carry_live_state` (turn/tail.py:20-65).
- Gap 1: the quoted turn's focus still carries the owed stock task, so `_bare_position_is_the_quantity` turns a "1"
  quoting the flyer list into the quantity. Nothing says the list was THAT message's content: `Focus.last_list` has no
  stamp (turn/state.py:209; writer turn/tail.py:103-125).
- Gap 2: promo rows carry no key: `_promotions` calls `b.item` without `entity_id` (sorento_crm_mcp presenters.py:
  1051-1064) though `_Builder.item` supports it (presenters.py:287, :329, top-level "id", never printed); `_row_item`
  keeps only "Product Code" (tail.py:89-100); `_pickable` is product-only (turn/chat_state.py:809-812).
- Gap 3: a promo pick has no fetch path: `promo_filter` (turn_runtime.py:568-606) takes promotion ids only from the
  resolver, which matches Promotion.description exactly (entity_resolver.py:~2412). The id param exists:
  `TYPE_TO_PARAM["promotion"] = "promotion_ids"` (lanes/business/fetch.py:320).
- Gap 4: file rows are not in `last_list` at all (Section.files is separate from figures, turn/compose.py:49-54) and
  `attach()` emits no attachment id (presenters.py:352-363).

## ARCHITECTURE
1. Layer: State (tail writer, chat_state pick) + the quoted-turn swap, plus one presenter field (row ids). No new text
   rewriter; the prompt is not touched (the base prompt's bare-number rule already matches "how many outranks").
2. Shared mechanism: `last_list` carries the turn that showed it (`shown_at_turn`) and each row's kind + id. A quote
   resolves to a turn (existing); when that turn showed the list (`shown_at_turn == QuotedTurn.turn_no`), the list is
   the referent and the owed stock task does not take the number. One `_pickable(row, open_question)` rule: product
   rows as today; a keyed promotion / file / order row only when no question is open. A picked row enters as an entity of its
   kind with its id, so the existing id params fetch it (promotion_ids; attachment_ids for files; the order's id).
3. Also fixes: every quoted pick over an older owed task (stock, count, clarify); every promo / file list pick when
   nothing is open; promo picks no longer depend on an exact description match.
4. Removes: the product-only `_pickable`; the "Product Code"-only row key. Kept on purpose: the how-many-outranks rule
   (owner 20 Oct) and the base prompt lines (chatbot_parser_prompt.py:414-416, 464-465); P1-P3 sent to crew 20 Oct are
   WITHDRAWN.

## Slices (each: tester red -> coder -> lead kill-proof -> reviewer; L1 gate at round end)
- R7-1 keys: presenter promo rows carry `entity_id`; file rows carry the attachment id; the tail writes promo and file
  rows into `last_list` with kind + id and stamps `shown_at_turn` (a question's options keep its `asked_at_turn`, per
  the v1 coder's seam finding: test_chat_state_seam.py same-input same-focus).
- R7-2 quote: a quote of the turn that showed the list makes the list the referent (the owed task does not take the
  number); a quote of the how-many turn keeps the quantity.
- R7-3 pick: `_pickable` per rule 3; the pick enters as an entity of its kind with its id; the fetch sends that row.

## Before any push
The v1 red commit a77e5d8b9d encodes the withdrawn recency rule: its rewritten pins (test_chat_state_apply.py:488,
test_stock_ask_ht26_r5_picker_not_sticky.py:101) go back to today's rule and test_chat_state_r7_last_referent.py is
rewritten to v2 by the tester (new `test(red):` commit). The v1 coder WIP patch (scratchpad r7-coder-wip.patch) is
reused only for the writer stamp + row kind/key; its `open_referent` recency is dropped.

## Measurement
L1 replay gate (base 7f299b4cc8); state-path effect rides the paired TRAIN x1 (cap 0.3 USD).

## Round log
- Review round 1 (20 Oct): security-reviewer PASS (picked ids scoped server-side by the live contact on every fetch;
  quote lookup confined to the same contact + is_test, quoted.py:86-131; no id printed). Reviewer NOT READY: B1 quoting
  the live roster counted as quoting a list (options stamped asked_at_turn), B2 apply.py early return unpinned; should-fix
  listed-first unpinned, one file replaced a numbered list, fetched-by-id unproven. Tests 26c11f7b44 (B1 + single-file
  red; B2 / listed-first / 2+ files / fetched-by-id x2 at the promotions tool call / unlinked-contact guards) -> fix
  3b1b2e1427 (quotes_the_list false when the quoted turn's own question is open; files become the list only when 2+,
  lead-accepted: one file with no earlier list is still recorded; logged next view drops quoted_turn_no); kill-proof
  2 fail / restored 37/37. Re-check READY (kills K1 K6 K8 K9 each caught). L1 gate vs 7f299b4cc8: grounding 0/1506,
  turn 0/585 (two earlier runs flagged 2 turns each: the same fallback reply swapped between arms, 13 per arm every run,
  harness ordering noise; re-runs 0/585).
- v2 build: reds b117944fe5 (10 backend + 3 MCP) -> fix 10ef73a84e (tail rows keyed by id + shown_at_turn; State.quoted_turn_no
  set in engine._quoted_context; quote of the list turn picks from it; promo / file / order rows pickable only with
  nothing open; MCP presenters carry promo / attachment / order ids); kill-proof: fix files reverted -> 10 + 3 fail,
  restored 25/25. Live-shape red 6bc744bb61 (parser input under a quote of the list turn) -> fix 4ee31faff6 (view hides
  the held how-many, one predicate `quotes_the_list`); kill-proof 1 fail / restored 29/29. The post-parser demand_qty
  red was dropped (40427e6b5b): fix at the parser input only. Deviation: a files-only section records its files as the
  list (replaces an earlier list). Open for review: an id row's uuid reaches the fetch without re-resolution (scoping
  rests on the scoped MCP tools); clarify / company-pick variants of AC-R7-5 untested (shapes unverified).
- v2 approved by the owner 20 Oct ~07:55; crew un-HOLD. Prompt: only chat_state_prompt.py:34 changes (sent to crew).
- v1 (recency) planned + reds a77e5d8b9d + coder WIP (all reds green) 20 Oct; HELD by crew, withdrawn by owner ruling
  20 Oct ~07:40. v1 finding kept: the promo pick could not fetch the file (gap 3).
