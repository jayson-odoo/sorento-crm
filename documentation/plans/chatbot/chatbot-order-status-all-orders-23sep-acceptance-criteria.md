# UAC: status-filtered order miss names every resolved order (23 Sep 2026)

Plan: `PLAN-chatbot-order-status-all-orders-23sep.md`. Track: small fix.

- AC-1860 When N orders resolve (`gate.compatible_entities` has N order rows), the
  status-filtered tool returns nothing, and `order_status` is `delivered`, the miss
  reply carries one "Order <code> (<customer>) hasn't been delivered yet - current
  status: <status>." line per order, in `compatible_entities` order, then ONE
  "Would you like me to escalate to <team> team?" question.
- AC-1861 Same for `order_status: outstanding` with the "has no outstanding items"
  line per order.
- AC-1862 An order whose uuid appears in more than one of `intersection`,
  `by_entity_type`, `resolutions` renders once.
- AC-1863 One resolved order produces the same text as before this fix (existing
  test in `tests/chatbot/test_s6c_answer_lane.py` unchanged and green).
- AC-1864 The live turn (contact 482766833, turn 48: PS202609-0374, PS202609-0398,
  PS202609-0410, all `New Order`) satisfies AC-1860 with all three named.
- AC-1865 `tests/chatbot/test_turn_replay.py` stays green with no DIVERGENCES entry.

## Fix 2: the CS member picker sends no quick replies (owner ruling 23 Sep 2026)

- AC-1866 When a `member_offer` pending is the open question (the CS member picker,
  "Please choose who to route to (reply with the number): 1. ... 2. ..."), the reply's
  `quick_replies` is `None` - the numbered text list is the whole offer, not also a row
  of WhatsApp tap buttons. `result_set` stays populated with the member rows
  (`entity_type: "member"`, one per roster row) so a numbered reply still resolves
  against them.
- AC-1867 Every other pending kind (`team_pick`, `company_pick`, `product_pick` and
  every other roster kind) is unaffected: `quick_replies` is still the comma-joined
  option-label string exactly as before this fix.
