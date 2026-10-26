# UAC: PROMPT-RULES-DIET (plan PLAN-prompt-rules-diet-26oct.md)

- AC-1 Size: the published diet version is under 103,000 chars (start 129,651, list-free text md5 3f1e2d27). Was 90,000;
  owner ruling 26 Oct (crew relay): "90k is no longer the bar", ship candidate = the gated s1c text, 102,402 chars.
- AC-2 No worse: arm B majority >= arm A on R5 62 end-to-end and TRAIN 118; wrong-category messages on the category set at
  most A + 1. From crew a83045112 (26 Oct) A = v185 fixed (not the previous round). Shipped s1c: R5 22 = 22, hard rows
  3/3, wrong-category 21 vs 22, TRAIN 95 vs 96 (one item, G014, root-caused to one edit; per-run means equal); owner
  ruling (b) accepted s1c with that TRAIN result.
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
