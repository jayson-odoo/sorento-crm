# UAC: CONFIRM-DIALOG-SPEED

Plan: `PLAN-confirm-dialog-speed-3nov.md`. Tests: `FulfilmentBoardPanel.confirmGuide.test.tsx`,
describe "CONFIRM-DIALOG-SPEED".

- **S1** Step 1 (Review split) renders and is usable (the split sheet, Next) while the email dry
  run is still pending. Its REMARK cells read "Preparing email preview..." and take no typing
  until that page's words land (S9); split-row remarks are the sheet's own and stay editable.
- **S2** The email dry run starts as the guide opens, before the board re-read answers, and is
  not sent again when that read leaves the order's body unchanged.
- **S3** The Confirm step shows "Preparing email preview..." and keeps Confirm disabled until
  the dry run lands; the run out when Next was pressed is not cancelled.
- **S4** A split Save on a guide page runs the dry run again; Confirm waits for it.
- **S5** A failed dry run keeps the sheet and any unsaved edit; it shows its own Retry and holds
  Confirm only.
- **S6** Words read for a body from before the re-read are never shown once the re-read changed
  the body.
- **S7** Opening Confirm while a board read is in flight joins it; no second read is sent.
- **S8** #2091 holds: the sheet never prints decisions older than the last board save.
- **S9** Every page's dry run starts from the open, one at a time in page order; paging cancels
  none; a page without its words prints "Preparing email preview..." in its REMARK cells;
  Confirm waits for every page.
- **S10** A placement pass writes exactly the same links with the per-pass document memo as
  without it, and reads each product's documents a handful of times, not once per row.
- **S11** A dry run still runs the placement pass (ordinary and planning-change paths), and the
  planning-change preview prints the REMARK the press sends.

## PR 2 (lane CONFIRM-SPEED-PR2)

- **P1** `_oi_placements` returns exactly the rows the one-join statement returned (same
  `(source_ref, product, company, spo_number, qty, received)` multiset), with and without
  `company_id`; a cancelled inquiry row and an SPO row of another product or company place
  nothing.
- **P2** A board GET reads the stock-debt assignment at most twice (`assignments_for`), however
  many covered orders and donor lookups it has; its JSON is identical to main's (each `incoming`
  list compared as a set, main orders it nondeterministically).
- **P3** `assignments_for` over several products equals one call per product.
- **P4** The placement pass reads a project line's product/core line once per line and an
  inquiry's SO number once per inquiry; it writes exactly the same links and claims as before.
- **P5** A confirm-all dry run and a real confirm return the same response and issue the same
  writes in the same order as main.
- **P6** A Confirm page whose dry run answers `ok=false` shows the dry run's error in the
  failed-run pattern with Retry, its REMARK cells print no words, and Confirm is disabled.
- **P7** Every line of a page's dry-run email appears on that page's Review split (pending the
  line-8 verification, plan item 5).
- **P8** On the clone (SO373923): board GET under 3 s warm, dry run under 5 s.
