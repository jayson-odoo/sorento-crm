# UAC: SCM reorder + order-inquiry feedback batch (1 Sep 2026)

Plan: `PLAN-scm-reorder-oi-feedback-1sep.md` (journeys J1-J4 at its top)

## S1 - OI auto-acknowledge

- AC-1.1 [BE] Given a CS form upload, when rows are created, then every row is born
  `acknowledged` (system-attributed or the uploader) and its links are firm, not drafts. (J1)
- AC-1.2 [BE] Given a board confirm raise, when the row is created, then it is born
  `acknowledged`; a carried re-raise keeps its handshake verbatim. (J1)
- AC-1.3 [BE] Given a CS amendment, when it settles, then the row stamps `changed` +
  previous_qty/previous_delivery_date AND is immediately acknowledged again - no manual
  confirm exists anywhere. (J1)
- AC-1.4 [BE] Given the migration runs, then every pre-existing `awaiting` row is
  `acknowledged` with system attribution. (G4)
- AC-1.5 [FE] The order-inquiries page has no Confirm action, no Confirmed column, and no
  default ack filter; rejected reason and Was/Now render in the qty/status cell; the ack
  filter still selects rejected/changed. (J2, G5)
- AC-1.6 [BE] Reject still works end-to-end: reason captured, links removed first, board
  line uncovered with "Rejected by <name>: <reason>". (J2)
- AC-1.7 [BE] Given an automation with trigger `order_inquiry_changed_with_links` and
  recipient_config, when a row THAT HAS LINKS is amended, then configured recipients are
  notified per their channel toggles; a linkless amendment fires nothing. (G6)
- AC-1.8 [FE] The reorder plan shows no awaiting chip; fresh-upload OI demand reaches the
  next run's committed figures with no confirm step. (J1, J3)

## S2 - Engine scope (committed-demand-only)

- AC-2.1 [BE] Given a full-network Start Plan, when the run completes, then every row's
  product x location has committed demand > 0 inside the horizon; a product with on-hand,
  movement, or an AutoCount level but zero committed demand produces NO row of any type. (G1)
- AC-2.2 [BE] Given Start Plan with explicitly named products, then those products enter the
  run regardless of committed demand. (G10)
- AC-2.3 [BE] No disposition/dead-stock rows are emitted by a run; the dead-stock report is
  a recorded backlog item. (G2)
- AC-2.4 [BE] `needs_level` rows appear only for committed products with no resolvable
  level; buy sizing arithmetic for committed products is unchanged (goldens re-pinned). (G3)
- AC-2.5 [E2E] On the prod-copy data a full-network run lands at ~213 buys and a few hundred
  rows total, not thousands. (J3)

## S3 - Perf

- AC-3.1 [BE] Index on `purchase_order_lines (source_ref, source_system)` exists; decisions
  and list-count paths use it (EXPLAIN shows no seq scan on purchase_order_lines).
- AC-3.2 [BE] `list_plan_row_decisions` runs a constant number of queries regardless of
  decision count (verified at 1,500 decisions).
- AC-3.3 [BE] Plans list + Decided sort read denormalised counts; no join to the PO-lines
  table per page.
- AC-3.4 [BE] (amended 2 Sep, pending captain confirm) The coder measured (PR #491 body)
  that `plan_basis` was never serialized into the HTTP response body in the first place -
  it lived only in the SQL projection's `inputs` column, and `_row()` in `reorder_runs.py`
  only ever pulls specific keys off `inputs` (`supplier`, `alternatives`, ...), discarding
  the rest before JSON encoding. So "response bytes drop by more than half" is unmeetable
  as written: measured before vs after on the reference run (`c9c575c8-3bf3-4c32-8d1e-
  d02af73162ef`, `/recommendations?page=1&limit=1000`), `3,549,063 -> 3,529,148` bytes
  (~0.6%), not "more than half". The real, testable claim: the recommendations SQL no
  longer fetches the `plan_basis` blob (`(rr.inputs - 'plan_basis') AS inputs`) nor
  evaluates the per-row `LEFT JOIN LATERAL` unnesting it
  (`reorder_run_service._plan_basis`'s locations) - reading precomputed
  `pool_warehouse_id`/`pool_warehouse_code` columns instead, set once at generation time.
  Warm-cache query time on that same reference run improves ~1.9x (~38ms -> ~20ms,
  page limit 1000, PR #491 body). Independently re-measured here at a smaller page
  (`EXPLAIN (ANALYZE, BUFFERS)`, warm cache, page 1/limit 50, run `1e58c6f7-2105-4f91-
  9535-d45ddbeb38ff`, 11,892 recommendation rows) shows the same direction at a larger
  ratio - OLD (LATERAL) 38.5-43.7 ms vs NEW (precomputed columns) 4.3-4.6 ms across two
  warm runs each (~9x) - consistent with the LATERAL's cost growing with page size while
  the precomputed-column read stays flat. Verified in
  `tests/scm/test_s3_reorder_perf_quickwins.py::test_recommendations_payload_never_carries_plan_basis`
  (no `plan_basis` string anywhere in the response) and the two `pool_warehouse_*`
  precomputed-column tests alongside it.
- AC-3.5 [FE] Deciding one row does not refetch the full decisions list; the grid updates
  without a visible stall.

## S4 - Dynamic filter + segments

- AC-4.1 [FE] Filters popover composes field + operator + value rows with AND/OR and
  fully recursive groups over the declared descriptor; evaluation is client-side and
  instant. (J4, G9)
- AC-4.2 [FE] Saving a segment captures the FULL view: filters + sort + visible columns +
  column order; applying it restores all four exactly. (G9)
- AC-4.3 [BE] Segments are scope-keyed by listing key; mine/shared listing, publish +
  set-default follow the report-views permission model incl. the one-default guard. (G9)
- AC-4.4 [FE] The segments dropdown sits beside Filters (no chips row); a personal default
  auto-applies on open; a published default applies for users with none. (G9)
- AC-4.5 [FE] The builder + segments menu mount on a second listing by supplying only a
  field descriptor and listing key (proven by test, not by shipping a second page). (T)
- AC-4.6 [FE] Usable and non-clipped at 375px and 1280px.

## S5 - Tabs + Re-plan

- AC-5.1 [FE] Plan detail shows Header and Lines tabs; header holds Plan until,
  warehouse/product scope, cut-off, status, counts; view and edit share the layout.
- AC-5.2 [BE] Editing Plan until or scope offers Re-plan: a NEW run with the edited values,
  the old run superseded, two-way link, list label. (G8)
- AC-5.3 [BE] Decisions carry to the new run for products present in both runs with an
  unchanged suggestion; products leaving scope drop; entering arrive undecided; changed
  suggestions arrive undecided flagged "re-check". (G8)
- AC-5.4 [FE] The superseded run stays readable and labelled in the plans list.

## S6 - Dedication-aware OI takes

- AC-6.1 [BE] Given PO line qty 100 with SO A (30) claimed, then 30 is reserved and 70 is
  free to other SOs; adding SO B (50) reserves 80, leaving 20. Claims reserve in SO-date
  order. (G7)
- AC-6.2 [BE] A fully-claimed line is never auto-taken by a different SO; the cascade's free
  quantity excludes all other-SO reservations. (J2, G7)
- AC-6.3 [BE] Reservation reads the claiming SO line's LIVE outstanding: a fulfilled or
  cancelled SO line reserves 0; the claim row is never deleted. (G7)
- AC-6.4 [BE] A line claimed by the row's OWN SO ranks first among candidates. (G7)
- AC-6.5 [FE] The Link dialog shows dedicated lines greyed with "Dedicated to SO xxxx";
  a manual link to one is still possible and audited. (G7)
- AC-6.6 [BE] Unresolved claims match by (po_number, item_code); SPO allocations follow the
  same rule via spo_allocation_id claims. (G7)
- AC-6.7 [BE] Existing OI links are untouched (no retro-unlinking).
- AC-6.8 [BE] Given a PO line destined for a project-segment warehouse with NO claim, when
  the cascade runs for any row, then the line is never auto-taken; the Link dialog shows it
  greyed "Unattributed - link manually". (G12)
- AC-6.9 [BE] Given Joey manually links an unclaimed project-bin line to a row, then an
  order_inquiry claim is written and the line thereafter behaves as claimed by that SO. (G12)
- AC-6.10 [BE] A pool-destination line's candidacy is unchanged by G12.
- AC-6.11 [FE] The PO/SPO upload result and the PO view surface the count/filter of
  unclaimed project-bin lines. (G12)
- AC-6.12 [T] The reorder engine still nets an unclaimed project-bin PO line's quantity at
  its location (no duplicate buy suggestion from the lock). (G12)
