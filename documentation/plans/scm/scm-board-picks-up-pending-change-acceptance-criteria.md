# UAC: the board picks up a pending planning change on its own

Plan: `PLAN-scm-board-picks-up-pending-change.md`.

**AC-B1 (board names the batch).** Given an order with a pending planning-change batch, when
`GET /api/v1/project-sales/fulfilment-planning/board?orders=<so>` is called with no batch
parameter, then that order's entry in `orders[]` carries `pending_change_batch_id` = the newest
pending batch id; an order with none carries null; an order whose only batch is applied
carries null.

**AC-B2 (board loads it unasked).** Given AC-B1's order, when the board is opened from the
fulfilment-planning list (URL has `orders=` only), then the changed line shows the Was / Now
table and its suggested decision is pre-marked, exactly as if `batch=` had been in the URL.

**AC-B3 (two orders, two batches).** Given two orders on the board each with its own pending
batch, then both orders' changed lines are annotated, each suggestion is seeded once, and
Confirm sends each order its own `batch_id`.

**AC-B4 (URL batch still wins for a deep link).** Given `?batch=<id>` in the URL, then that
batch is loaded even if the board response names no batch for the order (an applied batch
opened from the planning-changes list still renders its Was / Now with the applied banner and
refuses Confirm for that order).

**AC-B5 (confirm carries batch per order).** `POST /fulfilment-planning/confirm-all` accepts
`orders[].batch_id`; an order with `batch_id` applies that batch's rows (rows marked applied,
batch `applied_at` set when every row is settled); an order without one confirms as an
ordinary revision; a body-level `batch_id` with no per-order ids behaves as before.

**AC-B6 (applied batch skips only its order).** Given a two-order board where one order's batch
is already applied, when Confirm runs, then that order returns the existing "already applied"
skipped result and the other order confirms.

**AC-B7 (list pill).** Given an order with a pending batch, then its row on
`/project-sales/fulfilment-planning` (list view) shows the `Changed` pill in the SO number
cell linking to the board on that order and batch; an order without one shows no pill. The
SCM Sales Orders pill behaves exactly as before.

**AC-B8 (browser, on the lane).** SO419772 (qty 134 to 234, batch `3beeca39`): open it from the
fulfilment-planning list. Was 134 / Now 234 shows, the extra quantity's suggestion is
pre-marked, the list row shows `Changed`.
