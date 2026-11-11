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
