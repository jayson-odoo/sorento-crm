# PLAN: AutoCount write-back phase 2 (CRM side): quotation + sales order create / update / cancel from project sales

Lane: AC-QTSO-CRM. Status: Plan (behaviour card being drafted; no code before the owner answers).
Track: full pipeline (writes to an external system, new admin switch, security review required).

## Owner rulings carried in

- AutoCount is the source of truth. Every write is followed by a GET read-back.
- CRM decides intent; the Shared Service (SS) owns the AutoCount steps. Writes only reach the db3 test book until sign-off (SS guard).
- Never delete an AutoCount document; cancel instead. Anything needing the SS delete door is greyed "Waiting for AutoCount".
- Ships inert: an admin switch, default OFF, hides every write action and the API refuses.

## Behaviour card

To follow (posted as a crew-ask on the PR, then copied here with the owner's answers).

### Where it lives (existing screens only)

| Screen (existing) | Action added | Shown when |
| --- | --- | --- |
| Project > Sales orders > an order > AutoCount worksheet (`sales-orders/[psoId]/worksheet/components/SalesOrderWorksheetClient.tsx`) | **Create in AutoCount** beside today's "Download import file" | order `published`, `can_export` true (`project_so_draft_service.py:3084`), no `autocount_doc_no` yet |
| Same order > Revisions (`revisions/components/AmendmentReviewClient.tsx`, the AutoCount change list) | **Update in AutoCount** | amendment `published`, order already in AutoCount |
| Project > Sales orders list (tick rows) + order detail header | Decide > **Cancel in AutoCount** | order in AutoCount, not already cancelled |
| Project > Quotation (the project's one `kind = quotation` document, `models/projects.py:1268`) | **Create in AutoCount** / **Update in AutoCount** / Decide > **Cancel in AutoCount** | issued revision exists; proposals never go to AutoCount |

Switch OFF (default): none of these render, every write route answers 403 with no SS call.

### What each sends (CRM field -> AutoCount field)

Sales order, built from `worksheet()` (`project_so_draft_service.py:3024`), so the document sent is the one CS looks at:
- Header: DebtorCode = customer `customer_code` (company + debtor code identity, CARD-debtor-code-link); DocDate = today;
  RefDocNo / Your Ref = customer PO number; Our Ref = project title; Our QT Ref = the quotation's AutoCount number when it has one,
  else its CRM `document_no`; Terms = PO term days; Agent = customer's sales agent; Remark carries the provisional ref (`PSO-...`) so
  the next pull adopts it.
- Lines: ItemCode = product code, Description, Qty, UOM, UnitPrice, Discount (blank), DeliveryDate, Location = line `stock_location`.
- Read-back: AutoCount DocNo + DocKey written to `autocount_doc_no` (the same field the ingest adopts today, `project_so_ingest_service.py:201`), line DtlKeys onto the core SO lines.

Quotation: header as above (DebtorCode from the recipient party's customer), lines = the issued revision's priced lines across scopes
(ItemCode, Description, Qty, UOM, UnitPrice, Amount), Remark = CRM `document_no (Rn)`.

Update (SO): only the published amendment's accepted change-list rows (QTY_CHANGE, ADVANCE/DELAY = delivery date, ADD_LINE, REMOVE_LINE / CANCEL_BALANCE = line cancel, never delete). Update (QT): the newly issued revision replaces the lines.

Cancel: SS cancel operation on the whole document; never a delete.

### Results and refusals

Every write is followed by SS's GET; the dialog shows AutoCount's answer line by line, same wording table as #2168:
done (green, "SO412345 created in AutoCount"), refused ("AutoCount refused: <reason>. Nothing was changed."),
VENDOR_UNSUPPORTED greyed "Waiting for AutoCount", WRITE_DISABLED "Changes to AutoCount are switched off here",
needs_attention + Resume (`/write-operations/{id}/resume`), unreachable "Could not reach AutoCount". The Idempotency-Key is built from
the intent (order id + amendment id / revision no), so a double press replays SS's stored answer.

### Edge cases

- Already in AutoCount (`autocount_doc_no` set, or keyed by hand from the import file and adopted): Create is not offered; the number shows instead.
- Edited in AutoCount after our last read-back: Update first reads the document; if it differs from what we last read, refuse
  "Changed in AutoCount since <dd/mm/yyyy>; open Compare first" (the existing divergence screen).
- Partially delivered SO cancel: see Q4.
- Order with an unacknowledged hard finding: Create disabled with the existing `so_export_blocked` message.

### Assumed SS contract (not verified: this sandbox cannot read foundryx-shared-service)

`/write-capabilities` entries for kinds `quotations` and `sales-orders`, ops `create_doc`, `edit_doc`, `add_line`, `cancel_doc`
(+ partial line cancel), and POST routes for each with `{outcome, errorCode, docKey, docNo, document}` answers. Crew please pin
these against SS #191 `57-autocount-write-qtso-contract.md`; any missing op becomes the SS ask.

## Questions for the owner (open)

1. Switch. #2168 already has "AutoCount links from Stock Debt". (a) reuse it; (b) a sibling "AutoCount quotations and sales orders from Project sales", OFF. Recommendation: (b), so links can go live without document creation.
2. Import file. Create in AutoCount sits beside "Download import file". (a) keep the download as a fallback; (b) hide it once the switch is ON. Recommendation: (a), AutoCount can refuse and CS still needs a way to key it in.
3. Update source. Published orders are locked today (`so_not_editable`). (a) only a published amendment's change list; (b) also direct line edits. Recommendation: (a), the amendment already carries approval and the reason trail.
4. Partially delivered SO cancel. (a) cancel the undelivered balance only, delivered lines stay; (b) refuse. Recommendation: (a), matches AutoCount Cancel SO and how the CRM derives cancelled qty (AC-CANCEL-CRM).
5. Quotation timing. (a) Create on issue, Update on each new issued revision; (b) only once the customer accepted / signed. Recommendation: (b), AutoCount does not fill with quotations never accepted; a later revision of an accepted one goes as Update.
