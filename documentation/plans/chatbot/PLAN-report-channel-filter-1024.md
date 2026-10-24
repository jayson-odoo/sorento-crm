# PLAN: a channel word after a held ranking filters it (lane REPORT-CHANNEL-FILTER, owner ruling 24 Oct ~19:50)

Status: READY (Opus reviewer, 24 Oct), small fix track (S: report_ask.py only, no migration, no access change, no new ingest). UAC: `report-channel-filter-1024-acceptance-criteria.md`.
Branch `claude/report-channel-filter-1024` off main 8f7c7662e3 (#1816 + #1843).

## Why
EVAL-BENCH release gate 4 on #1816 (production prompt v63, Block, composer off, gpt-5.4-mini), row 15: after "Top 5 salesppl in
2026 for cb6635, by delivered qty", "Dealer sales only" parsed `order_status` sales_ranking, `group_by` channel, `sales_channel` dealer,
`ranking_refine` true (turn 054cc123). The report ask read that as a NEW axis (owner ruling B, 23 Oct: a new axis runs across all) and
answered a one-row channel ranking ("Across all sales agents, Top 1 channel ... Channel: Dealer, 269 pcs"). Row 16 had the same one-row
channel answer on v103 ("Project sales top 10 srt102-rg", EVAL-BENCH 1024g).
Owner ruling 24 Oct ~19:50: "<channel> sales only" after a held ranking = (a) FILTER that held ranking to the channel and keep its
axis, period, product and measure ("Top 5 sales agents, Channel: Dealer"); never a new channel axis across all.

## ARCHITECTURE
- Layer: the report ask lane (`report_ask.settle`), where the held ranking (`Focus.sales_ranking_frame`) and the parser's verdict meet.
  No engine, parser, prompt or schema change.
- Rule, parser fields only: a verdict whose `group_by` is channel while its `sales_channel` names one channel is that channel's FILTER
  on the held ranking (the frame's axis is kept), not an axis. Ranking by channel within one channel is one row by construction, so
  the two fields together can only mean the filter.
- It applies with a held ranking OR a held report-ask total on screen (any frame, not stale; review: a channel axis within one
  channel is one row for a total too). With nothing held, or a stale frame, today's behaviour stays.
- The message's own values still win (period, product, count, measure, basis), as every refine today.
- Unchanged: `group_by` channel with no `sales_channel` ("sales by channel") stays a channel ranking; a frame whose own axis is channel
  keeps today's refine rules.

## Tests (red first, real engine seam, v63 shapes)
Row 15 (filter keeps "Top 5 of N sales agents", Channel: Dealer, product, 2026, qty, delivered); row 16 (the message's own product and
count win, channel Project, the agent axis kept); guards: "sales by channel" after a ranking stays a channel ranking; nothing held ->
today's reply; a stale frame -> today's reply.

## Risks
Owner ruling B (a new axis runs across all) keeps holding for every real axis; only the channel-within-one-channel case changes.
