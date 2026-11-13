# UAC: Spare part request, an Order Inquiry type routed to purchasing after approval

Status: FINAL (owner approved mock v5 + card v4, 12 Nov 20:14). Contract: `PLAN-spare-part-order-request-12nov.md` "Build contract".
One record: a spare part request IS an Order Inquiry with `inquiry_type = spare_part_request`.

## Request (requester, slug `procurement.spare_part_requests.create`)
- R1 Create a request with currency (required), needed-by date, optional default location, reason, and one or more lines. It saves as Draft with an OI number from the same series (`OI-YYMM-NNNN`).
- R2 Each line: a catalogue product (searchable by code and name; description fills from the product; no free-text line), location (starts with the header default; each line can differ), qty, unit price. Total = qty x unit price, server-side; request total = sum, in the request currency.
- R3 Each line expands to the existing OI stock table (`OrderInquiryStockGrid`), information only, never caps qty.
- R4 Each line's photos use fulfilment planning's paperclip + lightbox (`SoLineAttachmentsButton`), stored through the same attachment service.
- R5 Save as draft keeps it editable. Submit checks: currency, >= 1 line, every line qty > 0, unit price >= 0, location set; problems show next to the field. Submit with no approval stage configured is refused with a plain message for the admin.
- R6 Edit opens the same form as Create (draft or rejected only).

## Approval (Form SLA stages for `spare_part_request`)
- A1 Submit moves the request to Pending approval at the first configured stage; the stage's team is notified by the existing SLA machinery.
- A2 Only a member of the current stage's team, or an admin, can approve, reject or edit; never the requester (403 for anyone else, also by direct API call).
- A3 While Pending approval the approver can change each line's qty (0 allowed) and unit price, and add or delete photos. The requester's submitted qty and unit price stay on the line and show as "was ..." next to a changed value, on the approval screen and for purchasing. Each change is a History row (old -> new, who, when). The approver cannot add or remove lines.
- A4 Approve with every line at 0 is refused (422).
- A5 Reject needs a reason; the request becomes Rejected, the requester edits and resubmits from the first stage.
- A6 Approve on a non-final stage moves to the next stage; on the final stage the inquiry becomes Raised: lines with qty > 0 go to purchasing, lines at 0 are cancelled.

## Purchasing
- P1 Purchasing sees the inquiry only from Raised: never in its list, counts, exports or notifications while Draft, Pending approval or Rejected.
- P2 On final approval purchasing gets the existing "Order inquiry" notification once.
- P3 The Order Inquiries list has a Type column and a Type multi-select filter (Sales order, Spare part request); the S/O no cell reads "-" for this type.
- P4 The OI page for this type shows the same header card and tabs; General has Request and Approval cards; Lines shows unit price, total, location, photos and the "was" marks; Acknowledge, per-row Reject and PO linking work as for sales-order inquiries.
- P5 (crew ruling 12 Nov, owner told after) An approved spare part request is NOT customer demand: it changes neither `scm.committed_v` nor the reorder engine's suggestions. It enters SCM only through the PO purchasing raises (incoming like any PO). Mechanism: instruction "Replenish", which those readers ignore.
- P6 Sales-order inquiries are unchanged: existing rows read type Sales order, a sales order stays required for that type (database check), and every existing OI test still passes.

## Change after approval
- V1 Until purchasing acknowledges any line (and no PO is linked), the requester can Revise: the inquiry returns to Draft, leaves purchasing's list, and approval runs again on Submit.
- V2 After a line is acknowledged, Revise is not offered and the server refuses it.

## History and assistant
- H1 Submit, approve (per stage), reject, each approver change, revise and the final raise show on the OI History tab.
- H2 Assistant: OI headers have no assistant reader today (impact check); this lane adds none. The PR says so.

## Hand-test round (owner 13 Nov, confirmed flow; supersedes R1c "opens on the OI page")
Approval stays the existing Form SLA config, exactly like the other forms (owner: "the setting should be same like other form sla config"): no new Settings approver, no new approve permission.
- G1 Description: the create/edit line table has a Description column, prefilled from the picked product's name, editable; stored in the line's description; shown on the record page and to purchasing.
- G2 Save as draft and Submit stay on the spare part request (its own record page), never redirect to the Order Inquiry page.
- G3 Own pages: sidebar Spare Part Requests opens a Spare Part Requests list (standard DataGrid: number, status, requested by, needed by, lines, total, submitted; search, multi-select status filter, server sort, columns, Create) and a row opens the spare part request record page: header card (number, status pill Draft / Pending approval / Approved / Rejected, actions), tabs Lines, General (Request + Approval cards), History. Once approved the header shows "Raised to purchasing" with a link to the order inquiry. The approver's notification and the SLA task link open this record page.
- G4 Photos can be attached per line on the Create page; they upload on the first Save as draft / Submit.
- G5 The requester can edit while Draft, Pending approval or Rejected. An edit while Pending approval restarts approval at the first level and is recorded in History ("Edited, approval restarted").
- Unchanged: approver edits qty / unit price / photos while pending; purchasing works it on the Order Inquiry pages only after approval; prices masked by cost access.
