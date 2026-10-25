# PLAN: parser prompt v107 and its publish gate (PROMPT-V107)

Status: in progress (small fix track: prompt text + eval gate, no product code, no migration).
Owner approval: 25 Oct 2026 ~12:30, budget about USD 9-10 on the OpenAI DEV key.
UAC: `prompt-v107-gate-25oct-acceptance-criteria.md` (alongside).

## Problem

#1816 (REPORT-SMART-L) left three parser misses that are prompt-level, not code
(crew/state/reports/REPORT-SMART-L.md, "Prompt misses" and row 16 of gate 4):

1. "Top 10 dealer selling X" / "which dealer sold X" sets `sales_channel` dealer. A dealer is the
   customer axis (we sell to dealers), never the channel.
2. "Project sales top 10 srt102-rg" after a held ranking parses as a sales report with `top_n` 10 and
   no `group_by`, so #1844's filter rule (group_by channel + one sales_channel after a held ranking
   = filter the held ranking) never fires and the user gets "No sales found".
3. "seat cover for <WC code>" can come back with no product entity: the WC code must stay the product
   entity and the relation goes to `find` (`app/services/product_find.py:331` FIND_RULE).

## Approach

v107 = v103 (id aa7b25a3, md5 f808cb72 on the copy DBs) plus exactly three rules, one per miss, placed
on the lines that already own each field (the `sales_channel` line, the sales_ranking line, the
product-code line). Nothing else changes. v104-v106 (by_words) are not used.

Arm A is the real production v63 text, pinned by md5 0f3b48e6 (stored on the copy DBs as version 74,
id 44e007d0; the copies' own "version 63" is a different text, md5 a561be6e). Every result prints
the md5 of the text it ran.

## Gate (arm A vs arm B, same code, same config)

Config: code = main 47881ef118 (contains fe9477165b), closed lists Block, composer OFF,
gpt-5.4-mini, reasoning off, DEV key only. Copy DBs only (sorento_explore1020); no new DB copies;
writes inside BEGIN/ROLLBACK or restored by script.

1. Parser gold x1: train 118 + held-out 113 + 62 R5 ranking rows, engine-built turns for both arms.
   Pass: B >= A paired; no slice down 3 points or more.
2. R4 replay: R3 owner script x 3 audiences + 30 real prod_1020 sessions x 3 turns, x2 runs per arm.
   Pass: no row worse in both runs.
3. Dealer battery, 229 turns per arm. Pass: B no worse than A.
4. EXPLORE-1023C, 23 rows per arm. Pass: B no worse than A, rows 13 and 16 fixed.

Spend: ledger at crew/state/eval/v107/LEDGER.md, one line per run (calls, tokens, USD, md5s).
Checkpoints at 25 / 50 / 75 % of each part; stop early on a regression or when the pass is out of
reach. Runners stop on any 429 or two busy replies in a row.

If B loses only on closed-list rows where Index mode would pass, the report says so (the owner may
publish with Index mode).

## Publish (owner only, never this lane)

Prompts page: save the v107 text as a new version of `chatbot_semantic_parser`, move its
`production` label to it. Rollback: move the label back to v63.

## Not in scope

Code changes, Index-mode gates, Gemini, v104-v106 by_words.
