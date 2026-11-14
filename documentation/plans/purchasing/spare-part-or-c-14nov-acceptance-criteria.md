# UAC: SPARE-PART-OR-B C (follow-up to #2412)

Card v1 + correction accepted 14 Nov (crew relaying owner rulings): Q1 (a) final-level team member or admin; Q2 (b) relabel; Q3 (a) one record. Paths: POI = `sorento_crm_backend/app/services/project_order_inquiry_service.py`, SPR = `sorento_crm_backend/app/services/spare_part_request_service.py`.

## C1 Approver raises / revises without approval
- C1.1 "Approver" = an active member of the team of the FINAL configured Form SLA level for `spare_part_request` (the level with no next level), or admin/superadmin. One shared helper `is_final_approver(db, user_id, company_id)`; no second membership check (reuse `_on_stage_team` / `UserService.get_user_tier_in_team_set`).
- C1.2 Submit by an approver: no SLA stage opens; the request goes straight through the same final-approval step as an approval (state raised, approved_at/by = the actor, oi_no minted, rows raised, purchasing notification + email per C2), audit "Raised by approver". The 422 "no approval level configured" does NOT apply to an approver (an admin may raise with no chain).
- C1.3 Revise by an approver who is the requester: the revision is applied at once on Submit (C4.4 settle), no stage opens, audit "Revised by approver"; between Revise and Submit the rows read Waiting for CS as any open revision.
- C1.4 A non-approver requester is unchanged: submit opens level 1; revision needs approval.
- C1.5 An approver still can never approve a request raised by someone else at a level they are not on (existing `can_decide` unchanged).

## C2 Purchasing email on approval (FP confirm path)
- C2.1 The final approval of a first submit (and C1.2) calls `mark_purchasing_email_trigger` (POI:352) and `_record_handover(kind="raised")` (POI:4781) for every raised row, in the same transaction; the email fires at commit through `_fire_pending_handover` like an FP confirm. A row cancelled at 0 records no raised line.
- C2.2 `handover_item` (POI:~4921) for a `spare_part_request` inquiry fills the header facts from the request: order number = OR number (inquiry_no), date = submitted_at (dd/mm/yyyy, Asia/Kuala_Lumpur), customer slot = requester name, project slot = reason ("-" when blank). Subject reads `OI: <location> @ OR-YYMM-NNNN`.
- C2.3 Header rows dedup on `pso_id or order_inquiry_id` (POI:~15425): two ORs in one email are two header rows; two SOs unchanged.
- C2.4 Header labels for an OR-sourced header row read `OR NO`, `OR DATE`, `REQUESTER`, `REASON`; SO rows keep `S/O NO`, `SO DATE`, `CUSTOMER`, `PROJECT`. Done by a data migration on the seeded default template `order_inquiry_handover_default` (conditional on a per-row flag, e.g. `is_order_request`); a template whose body differs from the last seeded version is left alone (same guard earlier template migrations use).
- C2.5 The "Send to purchasing" preview (`oi_handover_resend.py` -> `HandoverResendDialog.tsx`) shows the same subject, labels and values (one builder).
- C2.6 A revision's final approval keeps today's behaviour (settled lines, only when something moved), now with the same OR header facts.

## C3 OI page: approved qty and post-raise changes only
- C3.1 On the OI page a spare part line's Qty shows `qty` (the approved figure). Never `revised_qty`, `requested_qty`, submitted values or revised product / date.
- C3.2 The spare part OI Qty cell is the SO-line Qty cell: value, "Was N" + `QtyAnnotationButton` (`orderInquiryWorklistColumns.tsx:~661`) only when the row has a post-raise change (`previous_qty` set), and the Changed pill as SO lines show it. No clock (`LineHistoryButton`) in the Qty cell on the OI page.
- C3.3 The OI page History tab and its line popup show only events at or after the request's FIRST raise (`order_inquiry_raises`, earliest raised_at): raised, purchasing actions, post-raise revisions applied. Pre-raise events (created, edited, submitted, approver line changes, rejected) are not returned for that view. The OR page History tab and line popup keep the whole life.
- C3.4 Backend: `GET /order-inquiry-headers/{id}/history?view=inquiry` applies C3.3; no param = whole life (OR page). Sales-order inquiries: `view=inquiry` returns the same as today.

## C4 Revise mirrors an SO change
- C4.1 Revise (requester or approver, any time after approval, as #2412) opens the SAME edit form as Create in revision mode: qty, product, line delivery date, add / remove lines. Values go to the row's revision fields (`revised_qty`, new `revised_product_id`, new `revised_delivery_date`), new lines as draft rows that purchasing never sees, removed lines marked to cancel. `qty`, `item_code`, `product_id`, `delivery_date` never change before the final re-approval.
- C4.2 While a revision is open, every live OI row whose revision moved (qty, product or date differs, or the row is to be removed) reads `waiting_for_cs = true`, by widening the ONE clause pair in `oi_waiting_for_cs.py`; so the worklist, the header and purchasing's confirm guard treat it exactly as an SO change waiting for CS (purchasing cannot confirm that row; the pill reads "Waiting for CS"). Unmoved rows: false.
- C4.3 A rejected revision keeps Waiting for CS until the requester resubmits or the revision is closed; nothing moves for purchasing.
- C4.4 Final re-approval (or C1.3 approver submit) = CS Confirm: each moved row goes through `_settle_row_in_place` (POI:~2985), made `decision`-optional as ONE function (the SO path still passes its decision): qty, delivery date, item code / product (`_restate_product` POI:~3273), previous_*, "Was" note, `_trim_links`, `refresh_link_state`, `_amended_by_cs` (acknowledged -> changed / To order unless still covered), `_record_handover` settled line. A removed row goes through `cancel_row_told` (POI:~6664). An added line becomes a raised row with its own handover raised line. #2412's `restate_row` call in `_approve_revision` is replaced by the settle; `restate_row` stays only if `_restate_borrow_hole` still needs it (no second path for ORs).
- C4.5 After settle: revision fields cleared, revision_state null, Waiting for CS false, oi_no unchanged, one email if anything moved (C2.6).

## C5 Line delivery date
- C5.1 Each OR line has a Delivery date (shared date picker, dd/mm/yyyy, in the shared line table); new lines default to the header date. The header field is renamed "Needed by" -> "Delivery date" on the form, General card, OR list column and guide (API field name unchanged).
- C5.2 Submit validation: every line has a delivery date (header default fills a blank line).
- C5.3 The OI row's `delivery_date` is the line's; `oi_delivery_date.resolve` returns it (no SO line).
- C5.4 Changing the header date on a draft fills only lines still on the previous header date.

## Migration
- One additive revision (id <= 32 chars, single head): `order_inquiry_rows.revised_product_id` uuid FK products NULL, `order_inquiry_rows.revised_delivery_date` date NULL; plus the C2.4 template data step (guarded). Nothing dropped.
