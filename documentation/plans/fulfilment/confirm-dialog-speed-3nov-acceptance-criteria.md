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
