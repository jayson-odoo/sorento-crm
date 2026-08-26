# UAC - Order inquiry handshake

Plan: `PLAN-scm-oi-handshake.md`. Verified on the lane (:3080 / :8080) by browser evidence, pytest and vitest. Friday stations 4 and 6.

## A. Raise and acknowledge
- AC-H1 Confirming SO381895 on the board raises its rows `Awaiting`; none of them carries a link, and the Purchase Orders' Allocated to panels are unchanged by the confirm.
- AC-H2 Joey ticks three awaiting rows and presses Acknowledge (3): the rows read Acknowledged with her name and time, and the rows a PO or SPO can cover are linked at that moment (Linked to fills in without a reload).
- AC-H3 A CS user sees the Acknowledged column and the filter but no Acknowledge, Reject, Link now or Upload action; the endpoints answer 403 to her.
- AC-H4 The filter offers Awaiting / Acknowledged / Changed / Rejected, is clearable, and the list, schedule and export honour it.

## B. Reject
- AC-H5 Reject opens a dialog; an empty reason is refused; on submit the row reads "Rejected: <reason>" with Joey's name.
- AC-H6 A rejected row is absent from `committed_v` and from the reorder plan's project demand; the board cell for its line is undecided again and shows "Rejected by Joey: <reason>"; Eling re-deciding raises a fresh Awaiting row and the rejected one stays readable.

## C. Change after acknowledgement
- AC-H7 Amending an awaiting row on the board updates it in place with no mark; Joey sees only the new value.
- AC-H8 Amending an acknowledged row updates it in place, keeps its links, and the row reads Changed with a Was / Now table (Qty, Date, Decision); the Changed filter finds it; Acknowledge on it returns it to Acknowledged and links its unlinked remainder.
- AC-H9 A change that supersedes an acknowledged row raises the replacement rows as Changed, never as plain Awaiting.

## D. Demand
- AC-H10 The reorder plan's project demand for a product equals the unlinked remainder of its Acknowledged and Changed rows; Awaiting rows contribute nothing and are counted in an "N awaiting acknowledgement" chip on the plan page.
- AC-H11 Confirming a plan-generated PO links Acknowledged and Changed rows only; an Awaiting row stays unlinked.

## E. Upload on the Order Inquiries page
- AC-H12 The OI toolbar offers the PO book and SPO book uploads; the upload runs on the worker and shows in the upload activity drawer exactly as it does from the reorder page.
- AC-H13 When the upload lands, the drawer offers Link now and Open purchase orders; Link now links acknowledged unlinked rows of the uploaded products and reports how many; Open purchase orders opens the PO list filtered to the upload.
- AC-H14 Every new row field (`ack_state`, who, when, reason, changed_at) is on the wire from the list, the summary export and the SO detail's links.
- AC-H15 Tests in the same PR per plan section 6; browser evidence for AC-H1, H2, H5, H6, H8, H12, H13 on SO381895; no dashes in the diff.

**Result (27 Aug, `feat/scm-uat-oi-handshake`).** AC-H1 to AC-H12 and AC-H14 pass; the
evidence run is written up in `PLAN-scm-oi-handshake.md` section 8. **AC-H13 is half
done**: Link now and Open purchase orders are built and offered the moment an upload this
page queued is accepted, but the pair was not walked in a browser - it needs a real
purchase-order book to import, and that is the tester's step. AC-H12's own half (the two
uploads mount their home pages' dialogs) was walked.
