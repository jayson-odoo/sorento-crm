# UAC: rank-refine-route (lane RANK-REFINE-ROUTE, 25 Oct 2026)

Context: a sales ranking is on screen ("Top 5 sales agents, 2026, product <code>, by delivered qty").

- AC-RR1: "only project" re-runs that ranking with Channel: Project team; the axis, count, period, product, measure and basis
  on screen stay; the bot asks nothing.
- AC-RR2: the same holds when the parser labels the follow-up `top_selling`, or `sales_ranking` with `ranking_refine` null or
  false, or repeats the held axis.
- AC-RR3: "dealer only" filters to Channel: Dealer the same way.
- AC-RR4: a count in the same message ("project top 3") applies too.
- AC-RR5: a dealer contact gets the existing refusal (as "Dealer sales only", #1844).
- AC-RR6 (unchanged): no ranking held, a stale one, a held total or month list, a named product / customer / brand, another
  axis, the parser's explicit new ask (axis typed + `ranking_refine` false) or a `new_subject` op keep today's reply.
- AC-RR7 (unchanged): a position ("yang 3 tu sahaja") keeps today's rank pick.
