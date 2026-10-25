# PLAN: R5 ranking follow-ups, layer-2 contract check (lane RANK-REFINE-ROUTE)

Status: REVIEW (no code fix owed: every lost ranking row is SAME end to end or has no parser field to route on; contract
test pinned), small fix track (S: tests + docs only, no migration, no access change, no new ingest, no prompt change).
UAC: `rank-refine-route-1025-acceptance-criteria.md`. Seam under test: `report_ask.as_held_refine` (#1853, bb99b21c77).

## Why
CHAT-SLIM-INDEX phase 1 (crew `state/eval/slim-index/REPORT.md` top): every v63 prompt edit flips some R5 ranking follow-ups
with gpt-5.4-mini; arm B lost or5-5-03 "yang 3 tu sahaja", or5-c-02 "only project", or5-c-03 "dealer only", or5-c-04
"channel project sahaja" and or5-4-01 "Nvm can send me srt a3 flyer". A parser-gold loss is only a user-visible change when
the engine answers differently. Crew rule (a35910508): only rows whose END-TO-END answer differs get a code fix (red first);
position vs count stays the parser's call (no post-parser override).

## Method ($0, no LLM)
B's actual parses come from crew `slim-index/phase1/runs/r5_[AB]_*.jsonl` and `phase1/diag/run_v*.jsonl`. Those files store a
flat subset (order_status, entity_op, entities, reference_positions, open_question_answer, state_changes); the gold grader
lists EVERY mismatch (`scripts/chatbot_eval/parser_gold.py:154-242`), so a field the gold checks and the reasons do not name
held its gold value. Each A and B parse ran through the real engine seam (`_say_all`, the `test_report_channel_filter`
route body) over the gold row's held ranking.

## Result (per row)
| row | A parse | B parse (pinned fields) | end-to-end |
|---|---|---|---|
| or5-c-02 only project | sales_ranking, project, refine | top_selling, project, refine, no entity | SAME. The B full re-parses (crew `slim-index/diag/c02-c04-full-parses.jsonl`, arm B 1c2789f7 and variants v1, v2, v5) are top_selling with no grain (rank_group and group_by null), or sales_ranking with no axis or with group_by channel: all re-run the held agent ranking with Channel: Project team. (An item grain would have read "Across all sales agents", top 5 products; none was emitted) |
| or5-c-04 channel project sahaja | as c-02 | as c-02 | as c-02 |
| or5-c-03 dealer only | sales_ranking, dealer, refine | sales_ranking, channel null, refine | DIFFERENT: the held agent ranking re-runs with no channel. No field marks "dealer": prompt lane, no code fix |
| or5-5-03 yang 3 tu sahaja | refine true, positions [3] | refine false, positions [3] (one run also an open-question pick [3]) | SAME: all open rank 3 (customers and months of product 3) |
| or5-4-01 srt a3 flyer | promotion_kind a3_flyer, brand SORENTO | promotion_kind null, brand only (r5_B_2) | DIFFERENT: generic Sorento access-level menu, not A3 flyers. No field carries "a3": prompt lane. The kind is read from `promotion_kind` alone by design (`turn_runtime.py:2848`, PROMO-SUBJECT-FILTER AC-30); prompt variants v3-v6 that emit a promotion-hinted "a3 flyer" entity also get the unfiltered menu |

The earlier draft rule (a channel follow-up with `ranking_refine` null or false re-runs the held ranking) is dropped: no A or B
row carries that shape (every failing B ranking parse kept `ranking_refine` true).

## Tests
`tests/chatbot/test_rank_refine_route.py` pins the SAME rows: or5-c-02 / or5-c-04 A and B (B as `top_selling` with no grain,
the minimal parse the stored fields allow) filter the held agent ranking to Channel: Project team; or5-5-03 A, B and B pick all
open rank 3; or5-c-04 v2 (sales_ranking with the channel as the axis) filters too. Kill notes: turning off the R2
`bare_top_selling` refine (report_ask.py:1193) fails or5-c-02 B and or5-c-04 B; turning off the REPORT-CHANNEL-FILTER branch
(report_ask.py:1198) fails or5-c-04 v2.
