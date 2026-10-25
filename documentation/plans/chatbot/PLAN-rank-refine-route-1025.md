# PLAN: a channel-only follow-up over a held ranking refines it, whatever the parser's report label (lane RANK-REFINE-ROUTE)

Status: IN PROGRESS (Plan), small fix track (S: report_ask.py only, no migration, no access change, no new ingest, no prompt change).
UAC: `rank-refine-route-1025-acceptance-criteria.md`. Seam: the same as #1853 (CHAT-CHANNEL-RANK-ROUTE, bb99b21c77).

## Why
CHAT-SLIM-INDEX phase 1 (crew `state/eval/slim-index/REPORT.md` top, ask a35332697): every v63 prompt edit flips R5 ranking
follow-ups with gpt-5.4-mini. After a held sales ranking, a message that only NARROWS it ("only project", "dealer only",
"channel project sahaja") comes back as a new ranking ask instead of a refine. Gold rows `scripts/chatbot_eval/gold/
parser_one_ranking_r5.jsonl` or5-c-01..04.

Measured on the real engine seam (scratch probe over the `test_report_channel_filter` agent ranking, 25 Oct), "only project"
after "Top 5 salesppl in 2026 for <code>, by delivered qty":
| parse shape | today |
|---|---|
| `top_selling`, channel, no axis, no grain (any `ranking_refine`) | refine (R2 `bare_top_selling`, report_ask.py:1193) - OK |
| `top_selling`, channel, `group_by` = the held axis, `ranking_refine` null | asks period, count, measure, basis again - BUG |
| `sales_ranking`, channel, no axis, `ranking_refine` null or false | asks period and basis again - BUG |
| `sales_ranking`, channel, `group_by` = the held axis, count, `ranking_refine` null | asks period, measure, basis - BUG |
| `sales_ranking`, channel, `group_by` = the held axis, `ranking_refine` false | asks again (parser: a new ask, v63 "naming its own axis") |
| `top_selling`, channel, `group_by` product (another axis) | "Across all sales agents" top products (a new axis) |

`as_held_refine` (report_ask.py:646) re-runs the held report only when `ranking_refine` is true, so a channel-only follow-up
that the parser labels without it falls through to a fresh ask, which owes its own period, basis and count (owner Q3).

## Rule (parser fields only, `report_ask.as_held_refine`, the engine seam where the held ranking and the verdict meet)
A `sales_ranking` verdict (a `top_selling` one already is, `by_capability` runs first, engine.py:5044) that names ONE channel
(`sales_channel` dealer | project), with a ranking of a population held (`_drill_source`) and not stale, is a refine of THAT
ranking (`ranking_refine` true) when it names nothing new:
- no subject: no current-message entity (`_current_kinds`), no `new_subject` op, no `topic_reset`;
- no other axis: no typed `group_by`, or the held axis echoed (the parser repeats the held axis on most refines,
  `restates_the_ask` docstring), and a `top_selling` default axis (`bare_top_selling`) counts as none;
- not the parser's own new-ask statement: `ranking_refine` false WITH an axis typed stays a new ask (v63 "A message naming
  its own axis or subject is a NEW ask: ranking_refine false").
`_refine` then applies the channel and any count, period, measure or basis the message carries, and keeps the rest held.
A dealer contact gets `_refine`'s refusal, as #1844 / #1853 already do.

Unchanged: nothing held, a stale frame, a held total / month list / channel ranking, no channel, a subject or another axis
named, a `new_subject` op, the explicit new ask above, and every non-ranking status.

## Out of scope (evidence, not code)
- Position ("yang 3 tu sahaja", or5-5-03): the parse carries `reference_positions` [3]; today it picks rank 3 of the
  ranking (the rank-number drill) whether `ranking_refine` is true, false or null (probe P8, P9, P10), and with `top_n` 3 too
  (P11). The flip in the gold changes nothing downstream. Whether "yang 3 tu sahaja" is "rank 3" or "the top 3" is the parser's
  call (`reference_positions` vs `top_n`); code must not turn a position into a count. Filed to crew as an ask.
- Channel dropped by the parser (`sales_channel` null on "dealer only", v63 runs v1/v2/v4/v5/v6): no field marks it, so code
  cannot route it (prompt lane).
- "only X" product rows (or5-2-01/02): the parser never emits the product entity (bakeoff 25 of 25 / 23 of 25); prompt lane.
- `top_selling` with `rank_group` item or `group_by` product after a held agent ranking: the parser says items are ranked;
  v63 has no `by_words` / `axis_words` to tell an echoed grain from a typed one, so code follows the parser.
- The R5 parser gold scores the raw parse, so this code fix does not move R5 parser numbers; crew re-gates.

## Tests (red first, real engine seam, v63 shapes, fake codes)
`tests/chatbot/test_rank_refine_route.py`, on the `test_report_channel_filter` agent ranking:
- RR1 `sales_ranking` + channel, no axis, `ranking_refine` null ("only project") -> one `crm_report_ask`: sales_agent, top 5,
  channel project, held product, 2026, qty, delivered; "Channel: Project team"; no question.
- RR2 same with `ranking_refine` false ("channel project sahaja").
- RR3 `top_selling` + channel + the held axis echoed, `ranking_refine` null ("dealer only") -> channel dealer, held rest.
- RR4 `sales_ranking` + channel + held axis + `top_n` 3, `ranking_refine` null -> top 3, channel project.
- RR5 a dealer contact gets the refusal (no question, no run).
Guards (today's): RG1 nothing held; RG2 stale frame; RG3 a current-message entity; RG4 another axis (customer); RG5 the
held axis + `ranking_refine` false (explicit new ask); RG6 a `new_subject` op; RG7 a held month list; RG8 no channel;
RG9 `top_selling` no grain (R2, already a refine) stays a refine.
Kill notes: dropping each condition fails a named guard.
