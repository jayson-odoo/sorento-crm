# PLAN: Spare-part order request slice 2 (history lightbox, OR <-> OI link column, OI approved qty)

Status: Merged (#2412, 14 Nov 2026). Track L (one additive migration). Follow-up: SPARE-PART-OR-B C (`PLAN-spare-part-or-c-14nov.md`).

## Owner asks (14 Nov ~09:00)

1. Approver qty edit: no inline "was" under the qty field; a History icon next to the field opens a lightbox with the changes.
2. After approval and hand-off, the OI number shows on the order request line; jump OR <-> OI both ways like SO (OI column) <-> OI (line column), ONE shared link column component.
3. OI: purchasing sees only the APPROVED qty; OI history / "was" only when the OR qty changes after approval.
4. Define what History means on OR/SO vs on OI.

Discovery and behaviour card: to follow in this file and as a crew-ask on the PR.

## Discovery (measured, 14 Nov)

The order request (OR) and the purchasing inquiry are ONE row today: `projects.order_inquiries` with
`inquiry_type = 'spare_part_request'` and its own `OR-YYMM-NNNN` series (`app/models/project_so.py:1053-1067`,
`_stamp_inquiry_no` `:1100`). Final approval flips the same header to `raised`
(`app/services/spare_part_request_service.py:1092-1169`); the OR page then links "Raised to purchasing" to
`/project-sales/order-inquiries/<same id>` (`SparePartRequestRecord.tsx:117-123`). There is no OI- number for it.

| Piece | Exists at | Decision |
|---|---|---|
| Line History lightbox | `OrderInquiryLineHistoryDialog.tsx:194` (History tab = `OrderInquiryHistory` narrowed by `rowIds`, `:239`) | reuse as is for item 1 and item 3 |
| Line History icon | `LineHistoryButton`, `orderInquiryHeaderLinesColumns.tsx:504`, today in the State cell (`:756`) | move beside Qty on spare part lines (one icon per line) |
| Inline "was" | `WasMark` `orderInquiryHeaderLinesColumns.tsx:538`, used under Qty `:666` and Unit price `:696` | remove |
| SO line -> OI cell | `SoLineOrderInquiryCell.tsx:146` (`InquiryEntryView` `:71`, href `/project-sales/order-inquiries/<id>?row=<row>`) | lift to ONE shared link cell (`_shared/components/RecordLinkCell.tsx`), SO line + OR line call it |
| OI line -> SO line | No. column `orderInquiryHeaderLinesColumns.tsx:861-886` (`orderInquirySoLineHref`) | OR line link uses the same shared cell on spare part lines |
| History reader | `order_inquiry_history_service.history` `:127`, spare part events `_request_events` `:196` (SPR_* map `:161`) | extend with a "from first raise" cut for the OI view |
| Approver line edit + audit | `spare_part_request_service.edit_line` `:979` (SPR_LINE_CHANGED, old -> new per row_id) | reuse as is |
| Requester edit audit | `_audit_edit` `:740` (per row_id, rows updated in place by `_replace_lines` `:615`) | reuse as is |
| Number minting | `next_inquiry_no` `project_so.py:1070` | reuse for the OI- number at final approval (Q1 a) |

Behaviour card: crew-ask on PR #2412.

## Crew decisions and data (14 Nov 15:50)
- Q1 (a), Q3 (a), Q5 (a) decided by crew; Q2, Q4 to the owner. R5 built assuming Q2 (a); R4 ack_state part held.
- Prod-copy data (11 spare part requests): 6 raised with OR- numbers, 4 legacy ones numbered OI-2611-0082..0089 before the OR- series, 1 test-pinned. Approver qty edits are common (10 -> 6, 5 -> 3, 100 -> 200 -> 300). SPR_REVISED never used yet. Backfill: OR- raised rows get a fresh OI- number; legacy OI- rows reuse their own number (UAC U2.2b).
