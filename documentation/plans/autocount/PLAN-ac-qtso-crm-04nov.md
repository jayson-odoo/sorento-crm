# PLAN: AutoCount write-back phase 2 (CRM side): quotation + sales order create / update / cancel from project sales

Lane: AC-QTSO-CRM. Status: Mock (owner answered Q1-Q5 5 Nov ~07:20 MYT; Q6 asked; mock on the existing screens next).
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

## SS contract (pinned by crew from SS main f71e6ecf, `57-autocount-write-qtso-contract.md`, `routers/write_v1.py`)

- Capabilities: `GET /api/v1/autocount/write-capabilities?companyCode=` -> `{capabilities:[{op, kind, enabled, reasonCode}]}`.
  For `quotations` and `sales-orders`: `create_doc`, `edit_doc`, `add_line` enabled; `delete_line` and `cancel_doc` OFF
  (VENDOR_UNSUPPORTED). No balance-cancel op. The CRM reads the feed when the menu opens and never hard-codes it, so today
  **Cancel in AutoCount** and a removed / cancelled line are greyed "Waiting for AutoCount".
- Create: `POST /documents/{quotations|sales-orders}` (wv1:273). Edit: `PATCH /documents/{kind}/{docKey}` (:295).
  Add line: `POST /documents/{kind}/{docKey}/lines` (:319). Delete line (:342) and cancel (:364) answer 409 VENDOR_UNSUPPORTED.
- `Idempotency-Key` header required (1-128 ASCII): same key + body replays; different body 409 IDEMPOTENCY_CONFLICT; running 409
  OPERATION_IN_PROGRESS. The CRM builds it from the intent (kind, CRM document id, amendment id or revision no, op).
- Answer `{operationId: null, actionId, outcome, errorCode, message, warnings[], docKey, docNo, replacedLines, document}`:
  200 done / 202 pending_verification / 422 / 403 WRITE_DISABLED, WRITE_NOT_ALLOWED / 409 / 502 mismatch, FIELD_IGNORED.
  QT / SO have no resume and no GET-operation path: 202 shows "Sent; AutoCount has not confirmed yet. It will show after the next sync."
- db3 only (SS guard) plus WRITE_COMPANY_NOT_TEST.

### Field map, corrected to the pinned contract

Create header (`header{}`):
| AutoCount | CRM source |
| --- | --- |
| debtorCode (required) | customer `customer_code` (SO: the PO issuer's customer, `_customer_for`; QT: the recipient party's customer). Missing -> refused in the CRM before any call: "No debtor code on <customer>". |
| docDate | today (MYT), dd/mm/yyyy on screen |
| currencyCode, currencyRate (required by the CRM) | `MYR`, `1`. Project SOs and quotations carry no currency today (no column in `project_so.py` / `projects.py`). |
| displayTerm | `Net N days` from the PO's `term_days` (SO); quotation `payment_terms` text is free text, so QT sends none |
| yourPONo | customer PO number (SO); quotation `your_ref` (QT) |
| ref | project title (today's "Our Ref No.") |
| refDocNo (create only) | not sent |
| salesAgent | customer's sales agent code |
| remark1 | CRM ref: SO `provisional_ref` (PSO-...), QT `document_no (Rn)`, so the next pull can adopt the document |
| docNo | not sent; AutoCount numbers it |

Create lines (`lines[]`): itemCode = product code; uom; qty (> 0); unitPrice (>= 0); location (required) = SO line
`stock_location`, else `derived_stock_location` (`project_so_draft_service.py:3323`), else refused in the CRM "No location on line N";
description; deliveryDate (SO); discount blank. SO line made from a quotation line that is already in AutoCount: send
`fromQuotation{docNo, dtlKey}`; AutoCount then copies price and location from it (warning QT_ROW_VALUES_INHERITED, shown amber).
Quotation lines: rate-only lines and product sets (`is_rate_only`, `product_set_id`) cannot be one AutoCount row; refused in the CRM
by name until the owner says how (see question 6).

Edit (`PATCH`): header ref, description, remark1-4, displayTerm, salesAgent, yourPONo; lines qty, unitPrice, discount, location,
description, deliveryDate. Anything else answers 422 FIELD_NOT_EDITABLE. Always sends `docDate` (DOC_DATE_REQUIRED) and
`expectedLastModified` from the last read-back; a change in AutoCount answers DOC_STALE -> "Changed in AutoCount since dd/mm/yyyy,
open Compare first". Qty below what is already delivered or PO-linked -> QTY_BELOW_TRANSFERRED, shown as AutoCount's refusal.
Amendment verbs: QTY_CHANGE and ADVANCE / DELAY = edit; ADD_LINE = add line (no dtlKey back: the CRM diffs `document.Details`
against the lines it knew); REMOVE_LINE / CANCEL_BALANCE / REPOINT_SO / MODEL_CHANGE = greyed "Waiting for AutoCount" (need
delete_line / cancel). An amendment mixing both: the editable rows go, the rest stay listed as waiting.

### SS gaps (crew opens an SS lane)

1. Cancel: `cancel_doc` for QT / SO (AutoCount ignores header Cancelled). Needed for Cancel in AutoCount.
2. Balance cancel / line cancel for a partially delivered SO (a Cancel SO document for the outstanding qty, or `delete_line`).
3. A header quotation reference on SO create (today only per-line `fromQuotation`), for SOs whose lines were not copied from an AutoCount QT.
4. Resume or `GET` by actionId for QT / SO writes, so a 202 can be confirmed without waiting for the next sync.
5. `dtlKey` of the new row in the add-line answer (today the CRM diffs `document.Details`).

## Questions for the owner

1. Switch. #2168 already has "AutoCount links from Stock Debt". (a) reuse it; (b) a sibling "AutoCount quotations and sales orders from Project sales", OFF. Recommendation: (b), so links can go live without document creation.
2. Import file. Create in AutoCount sits beside "Download import file". (a) keep the download as a fallback; (b) hide it once the switch is ON. Recommendation: (a), AutoCount can refuse and CS still needs a way to key it in.
3. Update source. Published orders are locked today (`so_not_editable`). (a) only a published amendment's change list; (b) also direct line edits. Recommendation: (a), the amendment already carries approval and the reason trail.
4. Partially delivered SO cancel. (a) cancel the undelivered balance only, delivered lines stay; (b) refuse. Recommendation: (a), matches AutoCount Cancel SO and how the CRM derives cancelled qty (AC-CANCEL-CRM).
5. Quotation timing. (a) Create on issue, Update on each new issued revision; (b) only once the customer accepted / signed. Recommendation: (b), AutoCount does not fill with quotations never accepted; a later revision of an accepted one goes as Update.
6. Quotation lines AutoCount cannot hold as one row (rate-only lines, product sets). (a) refuse the whole quotation by name; (b) send a set as its parts and skip rate-only lines with a note. Recommendation: (a) for now, because sending something different from the issued quotation breaks "AutoCount = what the customer accepted".

Note on 4 (pinned contract): there is no cancel op today, so Cancel in AutoCount is greyed "Waiting for AutoCount" either way; the answer decides what we build once SS adds it.

## Owner rulings (5 Nov ~07:20 MYT, "Ok for the qtso question": every recommendation of 61aad31d)

- R1: own switch "AutoCount quotations and sales orders from Project sales" (`system_settings.project_autocount_write_enabled`), default OFF; off hides every write action and every write route answers 403 with no SS call.
- R2: "Download import file" stays beside Create in AutoCount as the fallback.
- R3: only a published amendment updates the AutoCount document; no direct edits of a published order.
- R4: Cancel in AutoCount = cancel the remaining (undelivered) balance. Greyed "Waiting for AutoCount" until SS ships cancel (SS gaps 1-2).
- R5: a quotation is created in AutoCount only after the customer accepted it (issue `accepted_at` set); a later accepted revision goes as Update.
- Q6 (rate-only lines and product sets): asked separately, not yet answered.
