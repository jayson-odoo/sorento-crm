# UAC: PROMPT-RULES-DIET (plan PLAN-prompt-rules-diet-26oct.md)

- AC-1 Size: the published diet version is under 90,000 chars (start 129,651, list-free text md5 3f1e2d27).
- AC-2 No worse: on every accepted round, arm B (round text) majority >= arm A (previous accepted text) on R5 62 end-to-end
  and TRAIN 118; wrong-category messages on the category set at most A + 1.
- AC-3 Hard rows majority-right in every round: "dealer only" keeps sales_channel dealer; "srt a3 flyer" gives promotion_kind
  a3_flyer. Ranking follow-ups ("only project", "dealer only", "yang 3 tu sahaja") reported per round.
- AC-4 Same parser switches: every gate `parser.resolve_config` reads off the raw template is identical before and after
  (lookup lists, closed lists, code lookup, chat state, template marker, compare_to, by_words, sales channels line, tokens).
- AC-5 Every `== ... ==` heading and every OUTPUT key survives; no new instruction section is added.
- AC-6 SALES-TARGET-CHAT still applies: the `== SALES REPORT: order_status "sales_report", domain_hint "order" ==` anchor
  stays exactly once, and the SALES TARGET insert applies to the diet text.
- AC-7 Anchored edits only: every anchor found exactly once on the list-free text, else nothing is published; a second
  apply publishes nothing. Migration publishes ONE unlabelled version, idempotent, label unmoved; downgrade drops only it.
- AC-8 No customer data in the repo (placeholders; a line naming a real party is anchored by sha256).
- AC-9 Spend logged per run (LEDGER), dev key only, cap USD 5 per round and USD 30 total.
