# NON-CANCELLABLE-ITEMS browser pass (cloud sandbox, seeded data, agent-browser 0.27.0)

Seed: Bathtubs + Taps categories; series "Mutiara Heights Standard" marks Bathtubs; model SRTBT1500-15 set to No;
proposal with SRTBT1872-17 x53, SRTWT51012 x53, SRTBT1500-15 x10. Login: superadmin seed user.

- rules-list-1280.png: Project Sales > Configuration > Non-cancellable Items, rule added through the Add item modal;
  table fits 1280 (950/950). Delete ran through the countdown and removed the row (verified in DB).
- rules-list-375.png: usable at 375, table scrolls sideways, page does not.
- series-detail-1280.png: "Non-cancellable categories" field on the series.
- series-products-1280.png: model No -> Applies blank; model following category -> Non-cancellable; tap -> blank.
- quotation-lines-1280.png: "Non-cancellable" badge under the bathtub line's description only; table fits (893/893).
Not walked in the browser (covered by backend tests): PDF REMARK column, sign page, amendment / board override dialogs.
