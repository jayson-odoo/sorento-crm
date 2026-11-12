# UAC: Sorento Town (phase 0 + 1)

Plan: `PLAN-sorento-town-08nov.md`. Owner answers 8 Nov 2026 (1a 2a 3a 4a 5a 6a).

## Phase 0: snapshot backend

- AC-1 Today's town total equals the sales report for that day, to the sen, for the company (one sales
  calculation; a subtotal line is never counted twice; a credit note subtracts).
- AC-2 Opening the town makes no query against business tables; only the sign-in lookup every page pays.
  100 viewers cost the database the same as 1.
- AC-3 A user without the sales report permission sees counts but never an RM amount, in the response
  itself (not hidden in the browser). An admin or a sales report holder sees amounts.
- AC-4 Wallboard mode shows no customer names or codes.
- AC-5 Shops are the top 30 Dealer-type accounts by 90-day invoiced sales, one per AutoCount account with
  its [A/C] label; any other Dealer-type customer invoiced today gets a stall.
- AC-6 The warehouse district shows one building per pool with stock volume, and one "!" count of
  products below their reorder level (buyer-owned SCM level).
- AC-7 The approvals sign counts pending purchase requests plus quotation documents awaiting approval.
- AC-8 The snapshot refreshes every 3 minutes between 07:00 and 22:00 MYT, at most one build at a time;
  one company failing does not stop the others; a slow build is cut off at 5 seconds.
- AC-9 At 22:00 the day is frozen into a stored day record (snapshot + event log) for replay.
- AC-10 Polling faster than 30 times a minute is refused (429); an unchanged snapshot answers 304.

## Phase 1: the town screen (after the owner OKs the mock)

- AC-11 `/town` is its own lazily loaded page; no other CRM page downloads the 3D code.
- AC-12 Usable at 375 px and 1280 px; plain card view when WebGL is missing or reduced motion is on.
- AC-13 Clicking a shop opens its invoices for the day (existing permission-checked screen); clicking the
  warehouse district opens the existing stock / SCM reorder screens.
- AC-14 Polls every 60 s only while the tab is visible; renders on demand, 30 fps cap, pixel ratio <= 1.5,
  under 100 draw calls; after 22:00 shows "Closed for the day".
