# PLAN: a status-filtered order miss names EVERY resolved order, not the first one

Status: in progress. Track: small fix. Owner ask 23 Sep 2026 ("the user asks 3 but it
only answers 1, why ah" / "yes").
UAC: `chatbot-order-status-all-orders-23sep-acceptance-criteria.md`.

## Evidence (prod, 23 Sep 2026 08:58, contact 482766833, turn 48)

- Message "STATUS DELIVERY / PS202609-0374 / PS202609-0398 / PS202609-0410". Parser:
  `domain_hint: order`, `order_status: delivered`, three `hint: order` entities.
- Gate resolved all three (`compatible_entities` has three `customer_order` rows, each
  match carries `display.status = "New Order"` and `display.customer_name`).
- `crm_order_management_orders_list` ran with the three numbers AND status=delivered;
  all three are `New Order`, so it returned "No matching results found".
- Reply: "Order PS202609-0374 (MATRIX EXCELCON SDN BHD (PROJECT)) hasn't been delivered
  yet - current status: New Order. Would you like me to escalate ...". PS202609-0398 and
  PS202609-0410 were dropped without a word.

## Cause (one seam)

`app/services/chatbot/lanes/business/answer.py::not_found_error_message`, the
"status-filter-aware" branch (~line 3579): `order_match = jsc.find(all_matches, ...)`
takes the FIRST order match in `compat_uuids` and renders one line. The branch was
written for one specific order; a multi-order ask hits it with N resolved orders.

## Fix

Same function, same branch. Collect every match in `all_matches` whose uuid is in
`compat_uuids` and whose `entity_type` is in `_ORDER_TYPES`, deduped by uuid
(`all_matches` is built from `intersection` + `by_entity_type` + `resolutions`, so a
uuid appears up to three times), in `gate.compatible_entities` order (that is the
order the customer typed). Render one line per order with the EXISTING wording,
unchanged per line, joined by `\n`, then the one escalate question:

```
Order PS202609-0374 (MATRIX EXCELCON SDN BHD (PROJECT)) hasn't been delivered yet - current status: New Order.
Order PS202609-0398 (MATRIX EXCELCON SDN BHD (PROJECT)) hasn't been delivered yet - current status: New Order.
Order PS202609-0410 (COMMERCE HOUSE SDN BHD (PROJECT)) hasn't been delivered yet - current status: New Order.
Would you like me to escalate to Sorento customer service team?
```

Both arms (`delivered` and `outstanding`) get the loop. One order = byte-identical
output to today (existing test `test_s6c_answer_lane.py` "hasn't been delivered yet"
stays green unchanged). No new string, no helper table, no parser change.

Not in scope: whether the parser should read "STATUS DELIVERY" as a delivered FILTER
rather than a plain status ask. Today's path already tells the customer the status per
order, so that is a wording ruling for the owner, not this fix.

## Tests (pytest, `tests/chatbot/test_s6c_answer_lane.py`, `not_found_error_message` direct)

1. Three resolved orders, `order_status: delivered`, none delivered: three lines in
   compatible_entities order, each with code + customer + "current status: X", one
   escalate question at the end.
2. Same with `order_status: outstanding`: three "has no outstanding items" lines.
3. Duplicate matches (same uuid in `intersection`, `by_entity_type` and `resolutions`)
   still render once per order.
4. One resolved order: output unchanged from before the fix (existing test).
5. `tests/chatbot/test_turn_replay.py` stays green.

## Fix 2: the CS member picker sends no quick replies

Owner ruling 23 Sep 2026: the numbered text list ("Please choose who to route to
(reply with the number): 1. Maryam Ariffin ...") is enough - the same names must not
ALSO go out as WhatsApp quick-reply buttons (a wall of up to a dozen taps). Scope:
`member_offer` ONLY - `team_pick`, `company_pick`, every roster kind keep their quick
replies exactly as today. `result_set` stays populated (a numbered reply still resolves
through it); only `quick_replies` is withheld.

Two seams, one shared predicate:

- `app/services/chatbot/turn/pending.py::quick_replies_suppressed(kind)` - `kind ==
  "member_offer"` directly (one kind does not need a table), next to
  `ESCALATION_OFFER_KINDS`.
- `app/services/chatbot/engine.py::_quick_replies_of(answer)` (the miss arm's own
  `answer.question` -> reply seam, `_run_answer`'s caller) - returns `None` when the
  question's kind is suppressed, before joining option labels.
- `app/services/chatbot/turn/compose.py::compose_question(pending, ...)` (a PENDING
  RE-ASK - the same open question printed again on a later turn) - same predicate,
  same result.

Checked and NOT touched: `tail/reply_ladder.compose_reply`'s own `quick_reply` never
carried member names in the first place (only `access-level-choice-message` and
`build-suggest-offer`'s `suggest_quick_reply` feed it) - the member names only ever
reached `quick_replies` through `answer.question.options` at the two seams above.
`tail/compose.py::crossdomain_compose`'s own `quick_reply` edit is the unrelated
"Yes escalate / No it's okay" cross-domain buttons. `lanes/escalation.py::
_clarify_actions` is the team clarify's own quick replies, a different kind.

Tests: `tests/chatbot/test_rearch_r4_miss_engine.py::TestAC1866MemberOfferSendsNoQuickReplies`
(engine-level: the real `answer_bridge.answer_for` mints the `member_offer` Pending
with a stubbed CS roster, `engine._quick_replies_of` - the exact function `_run_answer`
calls - is asserted `None` while `result_set` still lists the members) and
`TestAC1867OtherPendingKindsKeepTheirQuickReplies` (regression guard: `team_pick` /
`product_pick` still yield the comma-joined string, at both the `_quick_replies_of` and
`compose_question` re-ask seams).
