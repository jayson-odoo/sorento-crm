# UAC: CONFIRM-DIALOG-SPEED

Plan: `PLAN-confirm-dialog-speed-3nov.md`. Tests: `FulfilmentBoardPanel.confirmGuide.test.tsx`,
describe "CONFIRM-DIALOG-SPEED".

- **S1** Step 1 (Review split) renders and is interactive (Remark box, Next) while the email dry
  run is still pending.
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
