# UAC - far-dated landed pins become lendable to nearer sales orders (STOCK-DEBT-LENDABLE)

Plan: `PLAN-stock-debt-lendable.md`. Status: in progress, 30 Sep 2026.

## Journey

**Actor:** purchasing or CS planner on Supply Chain > Project Demand > Stock Debt, opening the
drawer for one product.

**Where they arrive from:** SRTSS8710, book Project. Sep 26 reads -76, Oct -29, Dec -207 while
SO381065 (due 29/03/2027) holds 88 on hand at BRW-BB because its own SPO was received.

**Steps and the single decision each:**

1. Planner opens the Sep 26 cell. SO396071 reads covered, Covered by "On hand BRW-BB (from
   SO381065)". The cell reads -44.
2. Planner opens the Mar 27 cell. SO381065 reads "order back 88", Covered by "Lent to
   SO396071 (32) · SO402118 (29) · SO404890 (27)". The cell reads -88, amber.
3. Planner presses Rebalance. A Preview lists, per receiving sales order, the Borrow from
   SO381065 and the order-back SO381065 gets at 29/03/2027, and the Confirm button.
4. Planner presses Confirm. Each order is confirmed on its own; the result names what was
   written; the order-back rows are on the order inquiry worklist.

**What they hold at the end:** near months that state what can actually ship, a far order
whose re-buy is on the worklist, and no stock moved by a filter.

## Acceptance criteria

- **AC-1 `[T]` A lendable pin lends to nearer lines first.** Given 88 on hand at BRW-BB landed
  for a line due on or after `today + lead + 14`, and lines of the same group short 32 (Sep),
  29 (Oct), 207 (Dec), when the view walks, then Sep and Oct read `covered`, Dec `short 180`,
  the far line `order_back` with `lent_qty 88`, `lent` naming the three receivers with 32 / 29
  / 27, and the months read Sep 0, Oct 0, Dec -180, Mar -88.
- **AC-2 `[T]` A partly lent pin stays pinned for the rest.** Only Sep short 32: the far line
  reads `order_back`, `lent_qty 32`, one pinned landed take of 56, uncovered 32.
- **AC-3 `[T]` A non-lendable pin is unchanged.** A landed pin whose line is due inside the
  window, undated, TBA or unlocated behaves exactly as on main (existing tests green).
- **AC-4 `[T]` Free stock first.** 100 on hand, 88 landed: a nearer line of 32 takes 12 free
  then 20 lent (two Covered by entries); a nearer line of 10 lends nothing and the far line
  reads plain `pinned`.
- **AC-5 `[T]` Short outranks.** A far line open 100 with 88 landed and all 88 lent reads
  `short` with `lent_qty 88`.
- **AC-6 `[T]` Chronology holds.** A line due AFTER the far line gets none of its landed goods.
- **AC-7 `[T]` Two claims on one floor.** The earlier-due far line takes its claim first; the
  later one bears the lend; claims are capped by the floor in hold order.
- **AC-8 `[T]` A lend never crosses an ownership group.**
- **AC-R1 `[T]` The window is the board's.** `required_date >= reserve_window_end(as_of,
  lead)` and `< tba_from`, off the product's stated lead (30 -> due in 60 days lends; default
  90 -> it does not); the day on the window itself lends.
- **AC-R2 `[T]` View independence.** The nearer month's balance and the nearer line's status,
  assigned and short quantities are the same with and without `date_to`; `date_from` never
  frees a pin that cannot wait.
- **AC-R3 `[T]` Board parity.** `assignments_for` (board, ladder) reads the far line `pinned`
  and the nearer line `short`; nothing is lent there.
- **AC-R4 `[T]` The wire.** Demand line carries `status: "order_back"`, `lent_qty`; an on-hand
  `assigned_from` entry carries `lent_from_so_number` and the ref "On hand <bin> (from
  SOxxxx)"; a `lent` entry carries `so_number`, `sales_order_id`, `qty`, ref "Lent to SOxxxx
  (N)". Supply tab unchanged.
- **AC-R5a `[T]` Rebalance preview.** `GET .../stock-debt/{product_id}/rebalance` (fulfilment
  EDIT permission) lists per receiving adopted order: lines with `borrow[]` (qty, bin, donor
  SO / line / agent / required date, the engine's reason) and `buy_qty`; `order_backs[]` at the
  donor's date; `skipped[]` for receivers not adopted; `confirm_body` in `confirm-all`'s
  shape (`source other_location`, `warehouse_id`, `donor_core_line_id`, `donor_required_date`,
  `buy_qty`, `amend_reason` when split). Nothing written. A product with no lend answers
  empty. Stock-debt view right alone is 403.
- **AC-R5b `[T]` Confirm.** Posting `confirm_body` to `confirm-all` confirms the receiver and
  raises one ORDER_BACK inquiry row for the lent quantity on the donor's own line at the
  donor's required date; afterwards the receiver reads `pinned` and nothing is lent.
- **AC-V1 `[V]` Pill.** Status `order_back` renders "order back N" in the violet pill; `short`
  with `lent_qty` renders "short N · order back M".
- **AC-V2 `[V]` Covered by.** Lent entries and the "(from SO...)" on-hand wording render as
  muted text, the lent entry linking the receiving order.
- **AC-V3 `[V]` Rebalance.** Button in the dialog header, disabled with a title when the cell
  has no lend; press loads the preview inline above the tabs; Confirm posts `confirm_body`
  through `confirmMany`, shows the per-order result, refetches the cell; Cancel closes the
  preview.
- **AC-V4 `[B]` 1280 and 375** per the mockup.

`[T]` pytest, `[V]` vitest, `[B]` browser evidence.
