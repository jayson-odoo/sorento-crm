# PLAN: PROMPT-V109, v63 feature edits one at a time

Status: in progress (25 Oct 2026). Track: prompt-only lane, no repo code change; eval gates on a crew copy.
Owner OK 25 Oct ~15:20: dev-key budget about USD 11 (key ..bG4A), stop and report at USD 9.

## Goal

Bring the v103-only behaviours into the production parser prompt v63 (md5 0f3b48e6, 140,897 chars) by EDITING
v63's own sections, one feature per candidate, each gated against v63 on current main 537a9df3d3. Do not revive
v103 or its dormant paths (conversation state, closed lists, template, live lists).

Why edits, not bullets: PROMPT-V107 round 2 (v108 = v63 + 3 added bullets) moved none of its targets; the added
lines lose to v63's own SALES_CHANNEL / ranking sections (crew/state/eval/v107/SUMMARY.md).

## Features (in order)

1. SALES_CHANNEL rewrite: "Top 10 dealer selling X" ranks customers (dealer = the customer axis), it is not the
   Dealer channel filter; "Dealer sales only" (#1844) still sets the channel.
2. Count / compare: "how many customers/orders/products", "vs last year", "vs previous period". The compare
   text also switches the schema on (head/parser.py compare_to); confirm the code path is live once the field
   appears.
3. "by salesppl" / "by customer" after a total: axis only (group_by), never an entity.
4. Malay / Chinese refines keep the product ("untuk produk BS3301 sahaja", "jualan tertinggi BS3301 ... ikut
   jurujual").

## Gate per feature

- Arm A = v63 md5 0f3b48e6 (copy row version 74, id 44e007d0 on sorento_explore1020), run once on this main.
- Arm B = candidate (unlabelled prompt version on the copy, pinned by id + md5).
- Sets: TRAIN 118 (engine-built parser gold), R5 ranking 62, EXPLORE-1023C console x2.
- Probe first: the feature's target rows x1 (cents). Full gate only when the probe fixes the target.
- Pass = target rows fixed in both runs, no slice down 3 points or more, no EXPLORE row worse in both runs.
- Final passing candidate: held-out 113 + dealer battery, once per arm.
- Expectations are never relabelled without owner OK.

## Money

Ledger: crew/state/eval/v109/LEDGER.md (same columns as v107). Hard cap USD 11, stop and report at USD 9.

## Output

Crew report per feature with numbers. Passing candidate: crew report --ask with diff path, numbers and publish
steps (Prompts page, save as a new chatbot_semantic_parser version, OWNER moves the production label; rollback =
label back to v63). Crew never publishes.
