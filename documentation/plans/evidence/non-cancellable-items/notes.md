# NON-CANCELLABLE-ITEMS browser pass (cloud sandbox, seeded data, agent-browser 0.27.0)

Seed: Bathtubs + Taps categories; series "Mutiara Heights Standard" marks Bathtubs; model SRTBT1500-15 set to No;
proposal with SRTBT1872-17 x53, SRTWT51012 x53, SRTBT1500-15 x10. Login: superadmin seed user.

- rules-list-1280.png: Project Sales > Configuration > Non-cancellable Items, rule added through the Add item modal;
  table fits 1280 (950/950). Delete ran through the countdown and removed the row (verified in DB).
- rules-list-375.png: usable at 375, table scrolls sideways, page does not.
- series-detail-1280.png: "Non-cancellable categories" field on the series.
- series-products-1280.png: model No -> Applies blank; model following category -> Non-cancellable; tap -> blank.
- quotation-lines-1280.png: "Non-cancellable" badge under the bathtub line's description only; table fits (893/893).
- series-detail-375.png, quotation-lines-375.png: usable at 375 (page 360 wide, no page-level sideways scroll; the
  lines grid scrolls inside its box as before).
- override-dialog-1280.png / -375.png: a published SO consumes the bathtub line; the edit view lowered it 53 -> 40 and
  Save proposal got 409 non_cancellable_line; the dialog listed the line; Override with a reason resent the PATCH (200),
  the line saved at 40 and audit_logs holds `non_cancellable_override` with the reason. (The dialog's "53.00 to 40"
  was then normalised server-side to "53 to 40".)
Not walked in the browser (backend + vitest only): PDF REMARK column, sign page, amendment publish and board Transfer
to Cancel SO dialogs (same shared dialog component as the one walked above).

## Pass 2 (12 Nov, fix round for crew-pass 878bb236), head 06e7680b, sandbox DB at alembic head
- pass2-rules-countdown.png: toolbar "Create"; rows have no icon buttons; right-click gives Edit / Delete; Delete ran the
  countdown and removed the row (a plain right-click opens no dialog).
- pass2-series-1280.png: "Follows category" and "No" each on one line (16 px label height) in the products table.
- pass2-override-dialog.png / pass2-proposal-history.png: SO-consumed bathtub line lowered 40 -> 39 in Edit proposal,
  refused, Override with a reason saved it; the proposal History lists "Non-cancellable override: SRTBT1872-17 40 to
  39. Reason: Customer pays storage (pass 2)" with name and time.
- pass2-so-history.png / -375.png: the project SO page has a History tab on the shared AuditTrail (empty for this
  seeded SO, which was written without an actor).
- 375 px: SO page 360, rules list 375, series 360 wide: no page-level sideways scroll. Console: no errors.

## Pass 3 (12 Nov, crew re-pass on 6a728344): fixture + dialog wording, sandbox DB at alembic head
- Fixture `laneboard/fixtures/2339-non-cancellable.sql` applied twice (idempotent). Project ZZT-NC-PRJ opened from the
  sidebar (Projects); proposal ZZT-NC-Q1 shows the Non-cancellable badge under the ZZT-NC-TUB-A line.
- pass3-fixture-block.png: Edit proposal, 5 -> 4, Save proposal: 409, "Non-cancellable lines" dialog lists
  "ZZT-NC-TUB-A 5 to 4", Override disabled until a reason is typed. Reason "owner test", Override: saved (qty 4).
- pass3-fixture-history.png: proposal History lists "Non-cancellable override: ZZT-NC-TUB-A 5 to 4. Reason: owner test".
- ZZT-NC-SO-1 opens from the project's SO tab (Published, 1 line) with its History tab.
- Revert run after that walk (proposal draft + History present): removes every fixture row; run twice, no error;
  re-apply after revert works. audit_logs rows stay (append-only trigger).
- Create dialog: title and submit read "Create" (vitest NonCancellableRuleDialog.test.tsx).

## Pass 4 (12 Nov, crew pass R10 on f4d7b93d6f): fixture part 2, merged main (#2355 History tab)
- Fixture part 2 applied twice over part 1. Fulfilment Planning lists ZZT-NC-CORE-1 (selectable); Plan, line 1,
  Decide > Transfer to Cancel SO, reason, Save, Confirm: pass4-board-block.png, "Non-cancellable lines" lists
  "ZZT-NC-CORE-1 line 1, 5 to 0"; Override with a reason: "1 of 1 orders confirmed", core line cancelled.
- pass4-so-history.png: the SO History tab (main's STANDARD-HISTORY-W2 feed, which now carries the override) lists
  "Non-cancellable override, transferred to Cancel SO: ZZT-NC-CORE-1 line 1, 5 to 0" (pre-fix casing; the feed
  title now reads "Non-cancellable override: Transferred to Cancel SO", pinned by test_sales_order_history.py).
- ZZT-NC-Q2 (sent, R1 "ZZT-NC-Q2-A"): Download PDF is enabled; the worker rendered the PDF (upload then failed on
  the sandbox's missing S3 bucket, as expected here); rendered directly: REMARK before GRAND TOTAL, "Non-cancellable"
  on ZZT-NC-TUB-A, blank on ZZT-NC-TAP-B.
- Revert after the board walk: no error, no ZZT-NC row left outside audit_logs (append-only).
- Create rule dialog, Category dropdown (crew UNVERIFIED item): not reproducible with real mouse clicks at 1280 and
  375, on a short list and an 80-item list, on a two-line option, on an option hanging below the dialog's edge, and
  after dragging the list's scrollbar: each click selected the option and the dialog stayed open.

## Pass 5 (12 Nov, owner hand test F1: badge live on the open quote form), sandbox at alembic head
Fixture reset first. ZZT-NC-Q1 > Edit proposal, nothing saved (DB line and series unchanged after):
- (c) scope tab right-click > Rename, Series cleared, Save changes: Non-cancellable badges 1 -> 0.
- (a) line ZZT-NC-TUB-A added with no series: 0; Series ZZT NC Fixture Series picked: 0 -> 2
  (pass5-f1-series-picked.png).
- (b) another ZZT-NC-TUB-A added with the series set: 2 -> 3 at once.
- (c) that line changed to ZZT-NC-TAP-B: 3 -> 2; one TUB-A line's item cleared: 2 -> 1 (pass5-f1-item-cleared.png).
Mechanism: the line verdict (`_judge_line`, also used for Non-standard / Below minimum price) answers
`is_non_cancellable`; the badge reads `lineFacts` / `useLineFacts` in QuotationLineFlags.tsx.
