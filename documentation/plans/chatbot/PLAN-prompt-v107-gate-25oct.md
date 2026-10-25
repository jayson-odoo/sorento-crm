# PLAN: parser prompt v107 and its publish gate (PROMPT-V107)

Status: done, not published: v107 FAIL at part 1; v108 (crew go (a)) FAIL at part 4 and fixes no target row (small fix
track: prompt text + eval gate, no product code, no migration). Production stays on v63.
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
4. EXPLORE-1023C, 23 rows per arm. Pass: B no worse than A, part 6 turn 3 ("Project sales top 10 ...") fixed.

Spend: ledger at crew/state/eval/v107/LEDGER.md, one line per run (calls, tokens, USD, md5s).
Checkpoints at 25 / 50 / 75 % of each part; stop early on a regression or when the pass is out of
reach. Runners stop on any 429 or two busy replies in a row.

If B loses only on closed-list rows where Index mode would pass, the report says so (the owner may
publish with Index mode).

## Result (25 Oct 2026)

Arm A = md5 0f3b48e6 (copy id 44e007d0). Arm B = v107, md5 45d1b908 (copy id 12b3aa1c, version 109 on
sorento_explore1020; drafts 107 and 108 were rule-3 wording probes). Numbers only; the item texts are crew-only.

| gate part | A | B | verdict |
|---|---|---|---|
| 1 TRAIN 118, engine-built | 93 (78.8%) | 64 (54.2%), paired 38:9, p<0.0001, 6 of 7 slices down 3+ points | FAIL |
| 1 R5 ranking 62 | 17 | 45, paired 0:28 | B better |
| 1 held-out 113 | not run | not run | early stop |
| 2 R4 replay, 3 dealer battery, 4 EXPLORE-1023C | not run | not run | early stop |

Attribution: on the 47 split TRAIN items v103 (no new rules) scores 16/47 and v107 in Index mode 17/47 (A 38/47), so
the loss belongs to the v103 lineage (CODE LOOKUP swaps a typed code for a listed variant or another code; intent
drift), not to the three rules, and Index mode does not rescue it. The lineage parses rankings far better (R5).
Spend: USD 3.28 of the approved ~9-10 (ledger crew/state/eval/v107/LEDGER.md).

The three rules as written (appended to v103's candidate-pick line and its `sales_channel` line): crew/state/eval/v107/v107_vs_v103.diff.

## Round 2: v108 = production v63 text + the same 3 rules (crew go (a), cap USD 10.00)

v108 = md5 f0318489 (copy id 9ec5af65, version 111 on sorento_explore1020, unlabelled). Rules 1 and 2 sit in v63's
SALES RANKING section, rule 3 beside the FIND block (a first draft with rule 3 in the attachment_type section sent fit
asks to the file domain and was replaced). Arm A and config as above. Numbers only.

| gate part | A | B (v108) | verdict |
|---|---|---|---|
| 1 TRAIN 118 | 93 | 94 composite (draft-1 full run plus final re-run of the 15 fit/split items), paired 1:2 | PASS |
| 1 held-out 113 | 83 | 85, paired 3:5, no language slice down | PASS |
| 1 R5 ranking 62 | 17 | 22: 3 of v107's 28 gains recovered (11%) | small gain |
| 4 EXPLORE-1023C, run twice per arm | - | worse in both runs on 3 rows, better in both on 1 | FAIL |
| 3 dealer battery 117 conversations | 92 | 93 | PASS |
| 2 R3 + 10 of 30 R4 contacts, x1 (REDUCED for the cap) | 42 | 44 turn passes, no row worse | PASS (reduced) |

None of the three rules changed the parse of its own target row (same parse as v63 in the engine and in R5). Likely
cause, not verified: v63's own SALES_CHANNEL section, which reads "dealer" / "project" in a sales ask as the channel,
outweighs the new lines. Spend for the lane: USD 9.80.

## Publish (owner only, never this lane)

Not recommended for v107 or v108. If a later candidate passes, the steps are:

Prompts page: save the v107 text as a new version of `chatbot_semantic_parser`, move its
`production` label to it. Rollback: move the label back to v63.

## Not in scope

Code changes, Index-mode gates, Gemini, v104-v106 by_words.
