# PLAN: a sales analysis with a count and one channel, over a held ranking, re-runs that ranking (lane CHAT-CHANNEL-RANK-ROUTE)

Status: IN PROGRESS, small fix track (S: report_ask.py only, no migration, no access change, no new ingest, no prompt change).
UAC: `chat-channel-rank-route-1025-acceptance-criteria.md`. Owner OK 25 Oct ~15:20 ("ok for code fix").

## Why
EXPLORE-1023C row 6 on prod v63 (prompt md5 0f3b48e6): t1 "Top 5 salesppl in 2026 for cb6635, by delivered qty" (ranking of
sales agents), t2 "Dealer sales only" (filtered, #1844), t3 "Project sales top 10 srt102-rg". The parser reads t3 as
`order_status` sales_analysis + `sales_channel` project + `top_n` 10 + product SRT102-RG, no `group_by`, no `ranking_refine`.
`by_capability` keeps it a sales analysis (no axis is in `CAN_DRAW["sales_analysis"]`, report_ask.py:381-383) and
`as_held_refine` needs `ranking_refine` true (report_ask.py:627), so `crm_sales_analysis` answers a TOTAL ("No sales found").
The parse is right; the routing is wrong.

## Ruling that covers the axis
AC-CF2 (`report-channel-filter-1024-acceptance-criteria.md:6`, owner ruling 24 Oct ~19:50): "Project sales top 10 srt102-rg" after
the agent ranking keeps the agent axis with Channel: Project; the message's own product and count win. No new ask needed.

## Rule (parser fields only, report ask lane)
In `as_held_refine` (the engine seam where a held report and the verdict meet): a `sales_analysis` or `sales_report` verdict (a
sales analysis naming a product or customer is already `sales_report` here, `turn_runtime.py:1963-1970`) with a count (`top_n`),
one channel (`sales_channel` dealer | project) and no axis (`group_by` null), with a ranking frame held and not stale, is a refine
of THAT ranking: it goes to the report ask with `ranking_refine` true, and `settle` -> `_refine` applies the channel, product and
count (the same path #1844 uses). Neither report has a count of its own (`CAN_DRAW`: a total, or by month / year), so a count with no
axis can only rank the rows already ranked.

Unchanged: no frame or a stale frame (today's analysis); a sales analysis with no count ("Project sales 2026"); with an axis
(`group_by` month / year / channel); `top_n` with no channel (out of scope, not this lane); a dealer contact keeps the lane's refusal.

## Tests (red first, real engine seam, v63 shapes)
`tests/chatbot/test_chat_channel_rank_route.py`. CR1 row 6 t3 after the agent ranking and "Dealer sales only" (CR1b straight after the
ranking): one `crm_report_ask` call, axis sales_agent, top 10, channel project, the message's product, 2026, qty, delivered kept;
no `crm_sales_report` (today's total). Guards (today's `crm_sales_report`): CR2 nothing held, CR3 no count, CR4 an axis (month),
CR6 no channel, CR7 a stale frame, CR8 a held total (no ranking); CR5 a plain refine ("top 3") unchanged.
Kill notes: dropping each of the six conditions fails exactly one named test (channel CR6, count CR3, axis CR4, frame axis CR8,
stale CR7, the whole rule CR1+CR1b).
