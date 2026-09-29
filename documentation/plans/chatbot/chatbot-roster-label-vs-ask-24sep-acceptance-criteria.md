# UAC: a message naming its own domain is an ask, not a roster pick by label (24 Sep 2026)

Plan: `PLAN-chatbot-roster-label-vs-ask-24sep.md`. Track: small fix.

- AC-1860 Over an open `product_pick` roster that offers SRT446-RG, the message "Photo
  srt446-RG" (parser: `domain_hint: product_attachment`, `domain_in_message: true`,
  `reference_positions: []`) is read as NEW_ASK, plans `product_attachment`, never fires
  `label_match` or `domain_locked_by_pick`, and leaves the roster open unchanged.
- AC-1861 Over the same roster, "Srt446-RG list price" (parser: `domain_hint:
  master_products`, `domain_in_message: true`, `requested_attributes: ["price"]`) plans
  `master_products`.
- AC-1862 Over the same roster, the bare code "SRT446-RG" (parser: entity only,
  `domain_in_message: false`, `reference_positions: []`) is still read as ANSWER via
  `label_match`, locks the roster's `purchase_cost`, and records position 1 answered.
- AC-1863 Over the same roster, a bare "2" (`reference_positions: [2]`) is still read as
  ANSWER via `positions`, settles option 2, locks `purchase_cost`.
- AC-1864 Over the same roster, "purchase cost SRT446-RG" (same domain as the roster,
  `domain_in_message: true`) is read as NEW_ASK, plans `purchase_cost`, and the roster
  stays open.
- AC-1865 The rule is kind-agnostic: over an open `tier_pick` (Office / Dealer / End
  user), "Dealer promo SRT446" (`domain_in_message: true`) is NEW_ASK with the tier
  carried as an entity, while a bare "Dealer" (`domain_in_message: false`) still picks
  position 2.
- AC-1866 Live, end of lane: one console chain (typo roster, then bare "SRT446-RG",
  then "Photo srt446-RG", then "Srt446-RG list price") on a lane backend with the real
  parser plans `purchase_cost`, `product_attachment` and `master_products` in that
  order. Observed 24 Sep 2026: satisfied; the parser resolved the bare code to
  `reference_positions: [1]` itself with `domain_in_message: true`, so the `label_match`
  arm was not exercised live (unit-covered by AC-1862). Details in the plan.
- AC-1867 `tests/chatbot/test_turn_replay.py` corpus stays green with no DIVERGENCES
  entry added; `turn/apply.py`, `chatbot_parser_prompt.py` and roster retention
  (`pending.is_roster`, `with_answered_positions`) are not modified.
