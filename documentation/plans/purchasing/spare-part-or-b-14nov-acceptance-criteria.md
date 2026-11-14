# UAC: SPARE-PART-OR-B (slice 2 of #2381)

Crew 14 Nov 15:50: Q1 (a), Q3 (a), Q5 (a) decided. Q2 assumed (a) for R5. Q4 open: no R4 code beyond "approved qty only, no was" until answered.

## R1 Approver edit: History icon beside Qty, no "was"
- U1.1 On a spare part request line (OR page and OI page) no text matching /^was /i renders in the Qty or Unit price cell, in any state, for any viewer (WasMark gone from spare part lines).
- U1.2 Every spare part line renders exactly ONE History button (aria-label "History"), inside the Qty cell, after the value/input. The State cell of a spare part line has no History button.
- U1.3 The button carries `data-changed="true"` when the line changed: qty differs from submitted qty, OR unit price differs from submitted unit price, OR photo_changes added+removed > 0. Otherwise `data-changed="false"` (muted styling).
- U1.4 Clicking it calls `onLineHistoryClick(line)` (the existing `OrderInquiryLineHistoryDialog`), and does not toggle row selection / expansion.
- U1.5 The Qty cell stays one line: the input/value and the icon sit in one `flex items-center` row (no flex-col).
- U1.6 Sales-order inquiry lines are unchanged (their History button stays where it is).

## R2 OI number at final approval (same record)
- U2.1 Migration adds `projects.order_inquiries.oi_no varchar(20) NULL` and a unique index on (company_id, oi_no) where oi_no is not null. Additive only; single alembic head; revision id <= 32 chars.
- U2.2 Backfill: every `spare_part_request` header whose state is not draft / pending_approval / rejected and has no oi_no gets one, in raised_at order (then inquiry_no), numbered `OI-YYMM-NNNN` by the month of its raised_at (Asia/Kuala_Lumpur), continuing after the highest OI- number already issued that month (inquiry_no OR oi_no) for that company. Idempotent (a second run changes nothing).
- U2.2b Legacy rows (crew data 14 Nov: 6 of 11 spare part requests on the prod copy were numbered in the OI- series before the OR- series existed, e.g. OI-2611-0087 raised): a header whose inquiry_no already starts with `OI-` gets `oi_no = inquiry_no` (no new number), whatever its state at approval time. Backfill and approval both apply this.
- U2.3 Final approval (`spare_part_request_service.approve`, the branch that sets state raised) sets `oi_no` once from the OI- series. A non-final approval (another level open) sets nothing.
- U2.4 The OI- series counts both columns: a sales-order OI created after a spare part approval in the same month takes the next number after the spare part's oi_no, and vice versa (`next_inquiry_no` considers inquiry_no and oi_no). No collision ever.
- U2.5 Revise keeps oi_no; the re-approval does not mint a second number.
- U2.6 Draft / pending / rejected requests have oi_no null; the API returns `oi_no: null`.
- U2.7 `oi_no` is returned by: the spare part request detail (`spare_part_request_service.detail`), the spare part request list rows, the OI header list rows and detail (`OrderInquiryHeaderOut`, `OrderInquiryDetail`), and each OI worklist / lines row (`OrderInquiryWorklistRow.oi_no`, the row's header's oi_no). Asserted in tests (response_model drops undeclared fields).
- U2.8 OI header list search matches oi_no as well as inquiry_no.

## R3 One shared link cell, both directions
- U3.1 `SoLineOrderInquiryCell`'s entry view is lifted to ONE shared component `app/(protected)/project-sales/_shared/components/OrderInquiryLinkCell.tsx` (export `OrderInquiryLinkCell`, `orderInquiryLinkEntries`); `SoLineOrderInquiryCell` becomes a thin caller (or is replaced) and SO line rendering is unchanged (existing SO tests still pass).
- U3.2 OR page Lines tab (spare part columns, viewed from the OR record): an "OI" column after State. For a line whose header has oi_no and whose row is not cancelled: link text = oi_no, href `/project-sales/order-inquiries/<inquiry id>?row=<row id>`. Otherwise "-". Same component as U3.1.
- U3.3 OI page Lines tab of a spare part inquiry: first data column "Order request" showing the OR number (inquiry_no) as a link to `/procurement-management/spare-part-requests/<inquiry id>?line=<row id>`; mirror of the SO No. link (same Link styling, stopPropagation).
- U3.4 Purchasing-facing labels: the OI page header title and the OI header list No. cell show `oi_no` when set, else inquiry_no. The OR page header title stays inquiry_no (OR-).
- U3.5 Both new columns: explicit size, truncate + title, hideable in Columns, one line.

## R4 OI page shows approved qty only; a post-approval change follows the SO-change path (owner 14 Nov ~15:54, Q4 (a))
- U4.1 On the OI page (not the OR page) a spare part line shows no submitted qty / submitted price and no "was" (covered by U1.1).
- U4.2 Revise (owner 14 Nov ~16:00, (a)) is ONE path for every approved request, whatever purchasing did (the `_taken_on` refusal is gone). It opens a REVISION on the same record: new header column `revision_state` (null | draft | pending_approval | rejected) and new row column `revised_qty` numeric(15,4) (same migration as oi_no). On Revise: `revision_state = draft`, every live row `revised_qty = qty`; header `state` stays raised (or actioned), rows untouched (state, qty, ack_state, links), so purchasing keeps seeing and working the approved request; open SLA trackers voided; audit SPR_REVISED. Requester only (403 otherwise); 409 when the header is not raised/actioned or a revision is already open.
- U4.3 During a revision only Qty changes, per existing line: the requester (revision draft / rejected) and a decider (revision pending_approval) change `revised_qty` (>= 0) through `edit_line`; `qty` never changes; unit price edits, line add / remove and the edit form are refused 409 with a plain message. Each change audited SPR_LINE_CHANGED old -> new.
- U4.4 Submit a revision: requester; 422 "Nothing changed" when every live row has revised_qty == qty; else `revision_state = pending_approval`, `submitted_at` now, the same Form SLA submit as a first submit. Reject: `revision_state = rejected`, reason, back to the requester. Non-final approve: unchanged rule (next level).
- U4.5 Final approval of a revision: for each live row with revised_qty != qty, the row is restated through the SO-change functions, ONE shared method extracted from `_restate_borrow_hole` (`project_order_inquiry_service.py:6431`) that `_restate_borrow_hole` itself now calls: `handover_moves` -> row.qty = new, `previous_qty` = old, "Was N" note, `_amended_by_cs(row)` (acknowledged row -> ack_state changed, To order unless still covered), `_record_handover(kind="settled", was=moves)` (the same order inquiry email to purchasing), and `_dispatch_changed_with_links` when the row had links. revised_qty 0: the row is cancelled the way an SO change that removes the line cancels its OI row (reuse that function). Rows with revised_qty == qty: untouched, no email. Then `revision_state` and every `revised_qty` cleared, `approved_at/by` = this approval, `oi_no` unchanged, audit.
- U4.6 Reads: the OR page (detail `lines[].qty`) shows `revised_qty` while a revision is open (plus `revision_state` on the detail and list rows); the OI page / worklist / header list / purchasing counts read `qty` only (never revised_qty). The OR status pill shows the revision state label (Draft / Pending approval / Rejected) while a revision is open, else the header state.
- U4.7 On the OI page the History icon is coloured (`data-changed="true"`) only when the row has `previous_qty` (a post-approval change); on the OR page U1.3 applies.

## R5 History meaning (owner 14 Nov ~15:54: "history show everything")
- U5.1 `GET /order-inquiry-headers/{id}/history` shows the whole life on BOTH the OR page and the OI page (History tab and the line lightbox): created, edited, submitted, line changed (old -> new), approved, rejected, revised, raised, purchasing events. No scope cut, no new param.
