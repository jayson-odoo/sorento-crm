# PLAN: AutoCount write-back phase 2 (CRM side): quotation + sales order create / update / cancel from project sales

Lane: AC-QTSO-CRM. Status: Review (fix round 1).
Track: full pipeline (writes to an external system, new admin switch, security review required).

## Owner rulings carried in

- AutoCount is the source of truth. Every write is followed by a GET read-back.
- CRM decides intent; the Shared Service (SS) owns the AutoCount steps. Writes only reach the db3 test book until sign-off (SS guard).
- Never delete an AutoCount document; cancel instead. Anything needing the SS delete door is greyed "Waiting for AutoCount".
- Ships inert: an admin switch, default OFF, hides every write action and the API refuses.

## Behaviour card


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

Update (SO): only the published amendment's accepted change-list rows (ORDER / RESERVE & ORDER = qty up on an existing line, ADVANCE/DELAY = delivery date; CHANGE SO NO and CANCEL BALANCE wait, never delete). Update (QT): the newly issued revision replaces the lines.

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
Quotation lines: rate-only lines are skipped and product sets go as their components (ruling R6).

Edit (`PATCH`): header ref, description, remark1-4, displayTerm, salesAgent, yourPONo; lines qty, unitPrice, discount, location,
description, deliveryDate. Anything else answers 422 FIELD_NOT_EDITABLE. Always sends `docDate` (DOC_DATE_REQUIRED) and
`expectedLastModified` from the last read-back; a change in AutoCount answers DOC_STALE -> "Changed in AutoCount since dd/mm/yyyy,
open Compare first". Qty below what is already delivered or PO-linked -> QTY_BELOW_TRANSFERRED, shown as AutoCount's refusal.
Amendment verbs (the delta service's own, `project_so_delta_service.py:65-70`; fix round 1):

| Verb | AutoCount |
| --- | --- |
| ORDER, RESERVE & ORDER (qty up on an existing line) | PATCH line qty to `to_value` |
| ADVANCE, DELAY | PATCH line deliveryDate to `to_value` |
| CANCEL BALANCE | waits ("Waiting for AutoCount") while `_SEND_CANCEL_BALANCE_AS_QTY_EDIT = False`; a qty edit down to `to_value` when the owner turns it on. Both paths built and tested. |
| CHANGE SO NO | waits |

A new product is never a row (the delta service reports it in `unmatched`), so there is no add-line from an amendment. A line with no core
line yet (right after a CRM create) waits with "Waiting for the next AutoCount sync". An amendment mixing both: the editable rows go in ONE
PATCH (key `crm-amd-{id}-update-edit`, marked `so_amendments.autocount_edit_sent_at` on done), the rest stay listed as waiting. A second press
after done answers done ("Already in AutoCount.") with no call.

### SS gaps (crew opens an SS lane)

1. Cancel: `cancel_doc` for QT / SO (AutoCount ignores header Cancelled). Needed for Cancel in AutoCount.
2. Balance cancel / line cancel for a partially delivered SO (a Cancel SO document for the outstanding qty, or `delete_line`).
3. A header quotation reference on SO create (today only per-line `fromQuotation`), for SOs whose lines were not copied from an AutoCount QT.
4. Resume or `GET` by actionId for QT / SO writes, so a 202 can be confirmed without waiting for the next sync.
5. `dtlKey` of the new row in the add-line answer (today the CRM diffs `document.Details`).
6. `/write-capabilities` returns a top-level `book` (string, e.g. `"db3"`) so the CRM can allow Update / Cancel on adopted orders (R7). Done on SS: #223 merged on SS main as cab276b3 (5 Nov), top-level `book`, null when writes are off or the book is refused; not live until crew releases SS. The CRM reads exactly that field; null or missing keeps adopted orders waiting.

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
- R6 (Q6, 5 Nov ~07:25 MYT, "For read-only line should be skip. Then for product set, then it should be like exploded to the component under the set."): option (b).
  Rate-only lines (`is_rate_only`) are not sent. A product set line goes as its components from `set_parts_snapshot`, qty = part qty x set qty,
  priced as the SO draft already splits a set (`project_so_draft_service.py:1229`: driver at the set's quoted rate, other parts zero, so the
  set's money is counted once). The result note names every skipped line and every exploded set with its components, so CS sees it.
  Red tests: `sorento_crm_backend/tests/test_project_autocount_qt_payload.py` (rate-only skipped, set exploded codes + qty x set qty,
  mixed quotation, only-rate-only quotation sends nothing). The builder is pure: `build_quotation_lines(lines, *, location)` in
  `app/services/project_autocount_write_service.py`.

## Phase 2 contract (build, 5 Nov; mock v2 approved 08:43 MYT)

### Data (migration `acqs_0001_project_ac_write`, down_revision `oiod_0002_pending_restore`, idempotent DDL)
- `system_settings.project_autocount_write_enabled` BOOLEAN NOT NULL DEFAULT false (U1). Model, `SystemSettingUpdate`, GET dict, `AppConfigResponse`, NOT-NULL null->False loop (U4).
- `projects.sales_orders`: `autocount_doc_key` VARCHAR(80), `autocount_last_modified` VARCHAR(64) (raw string from SS `document`).
- `projects.quotation_documents`: `autocount_doc_no` VARCHAR(80), `autocount_doc_key` VARCHAR(80), `autocount_last_modified` VARCHAR(64), `autocount_issue_id` UUID (the accepted issue last sent).
- Permission `projects.autocount.write` "Send quotations and sales orders to AutoCount", granted to superadmin + admin (pol_0001 pattern) and in `permission_registry.py` (U18).

### Client (`foundryx_autocount_client.py`)
`write_capabilities(company_code)` and `write(path, body, *, idempotency_key)` copied verbatim from #2168, plus `patch(path, body, *, idempotency_key)` with the same answer rule (a body with `outcome` is returned as-is for any status; anything else goes through `_parse`; transport error -> FoundryxPullError UNREACHABLE).

### Service `app/services/project_autocount_write_service.py`
- `build_quotation_lines(lines, *, location)` pure, R6 (tests already red: `tests/test_project_autocount_qt_payload.py`).
- `build_sales_order_body(db, order)` -> `{companyCode, header{...}, lines[...]}` per U6. Missing debtor code -> AppException 422 `ac_missing_debtor` "No debtor code on <customer name>."; a line with no location after `derived_stock_location` -> 422 `ac_missing_location` "No location on line <n>." (U7).
- `ProjectAutocountWriteService(db, client=None)` methods: `capabilities(company_id)`, `create_sales_order(pso_id, actor)`, `update_sales_order(amendment_id, actor)`, `cancel_sales_order(pso_id, actor)`, `send_quotation(document_id, actor)` (create when no `autocount_doc_key`, else update), `cancel_quotation(document_id, actor)`.
- Capability shape `{"sales_orders": {op: {enabled, reason}}, "quotations": {...}}`, ops `create_doc, edit_doc, add_line, delete_line, cancel_doc`. Reasons: VENDOR_UNSUPPORTED (and any unknown) "Waiting for AutoCount"; WRITE_DISABLED / WRITE_NOT_ALLOWED / WRITE_COMPANY_NOT_TEST "Changes to AutoCount are switched off here"; SS unreachable -> every op "Could not reach AutoCount". companyCode = `companies.code` of the record's `company_id`, never from the request (U19).
- Idempotency-Key: `crm-pso-{pso_id}-create`, `crm-amd-{amendment_id}-update`, `crm-qt-{document_id}-{issue_id}-create|update`, `crm-pso-{pso_id}-cancel`, `crm-qt-{document_id}-cancel`.
- Result: `{outcome, message, doc_no, lines[{line_no, item_code, description, qty, unit_price, location, delivery_date}], warnings[], skipped[], exploded[], waiting[]}`. `lines` from `document.Details` (AutoCount field names ItemCode, Description, Qty, UnitPrice, Location, DeliveryDate). Only `outcome == done` writes to the CRM (`autocount_doc_no`, `autocount_doc_key`, `autocount_last_modified` = `document.LastModified`, QT also `autocount_issue_id`) (U8, U9).
- Update SO (U10-U13): rows of the published amendment's AutoCount change list. ORDER / RESERVE & ORDER -> PATCH line qty; ADVANCE / DELAY -> PATCH line deliveryDate; CHANGE SO NO and CANCEL BALANCE -> `waiting` (no call), see the verb table. PATCH body `{companyCode, header{docDate}, expectedLastModified, lines[{dtlKey, ...}]}`; dtlKey = last `:` segment of the core SO line's `source_ref`. DOC_STALE -> message "Changed in AutoCount since dd/mm/yyyy, open Compare first." (date from the stored last-modified).
- Cancel (U14): reads capabilities; `cancel_doc` off -> 409 `ac_waiting` "Waiting for AutoCount" with no write call.

### Routes (`app/api/v1/projects/project_autocount_write.py`, `projects.autocount.write`)
Check order: permission -> switch (403 `ac_write_switched_off` "AutoCount quotations and sales orders from Project sales are switched off in Settings.", no SS call) -> record in the user's company (404) -> eligibility (409) -> SS.
- `GET  /api/v1/project-sales/autocount-write/capabilities` -> `{enabled, sales_orders, quotations}`; switch off -> `enabled: false`, op maps empty, no SS call.
- `POST /api/v1/project-sales/sales-orders/{pso_id}/autocount` (create; eligible: status published|amended, `can_export`, no `autocount_doc_no`).
- `POST /api/v1/project-sales/sales-orders/amendments/{amendment_id}/autocount` (update; amendment published, order has `autocount_doc_key`).
- `POST /api/v1/project-sales/sales-orders/{pso_id}/autocount/cancel`.
- `POST /api/v1/project-sales/quotation-documents/{document_id}/autocount` (kind quotation; latest issue `accepted_at` set, else 409 "The customer has not accepted this quotation yet."; nothing new to send -> 409 "Already in AutoCount.").
- `POST /api/v1/project-sales/quotation-documents/{document_id}/autocount/cancel`.
- Row/detail payloads gain `autocount_doc_key` presence only as `in_autocount: bool` (no keys in the UI).

### Frontend
`settings` switch row beside the others; `app/models/system.ts` field; `_shared/services/projectAutocountWriteService.ts` + `_shared/hooks/useProjectAutocountWrite.ts`; `components/AutocountWriteDialog.tsx` + `lib/autocountWriteWording.ts`; worksheet button (after Download CSV); `AmendmentAutocountChangeList` "AutoCount" column + "Update in AutoCount (N)"; `SalesOrdersPanel` Decide > Cancel in AutoCount; `QuotationDocumentPageHeader` Create / Update / Decide. Each renders only when app-config switch on AND permission held; greyed with the capability reason otherwise.
### Assumed, to confirm on the hand-test SS (8114)
PATCH body field names (`lines[].dtlKey`, `expectedLastModified`) and `document.LastModified` / `document.Details[]` key casing. The tests pin the CRM side; a mismatch is a one-line mapping fix.
- `LastModified` time zone. `_since` reads a stamp with no zone as UTC and shows dd/mm/yyyy in Malaysia time; the AutoCount ingest reads a naive stamp as +08:00 (`autocount_doc_ingest_service.py`, ruling V1), so confirm which one SS sends and flip the one line if it is +08:00.
- Whether SS stores a REFUSED answer under an Idempotency-Key, so that a retry with the same key and body replays the refusal (the CRM relies on a stable key and body per step; if SS does not store refusals, a retry simply sends again).
- Adopted orders: the doc key is read from the core order's `source_ref` (`{database}:{DocKey}`) without checking `{database}` against the book the company writes to, because no per-company book mapping exists in the code (the book arrives with each pulled snapshot). Owner to say where that mapping lives before the check is added.

## Owner ruling R7 (5 Nov): adopted orders wait for SS to name the book

An ADOPTED order is one whose AutoCount doc key comes from the core order's `source_ref` (`{book}:{DocKey}`), not from our stored
`autocount_doc_key`. Update and Cancel are allowed for it ONLY when SS's `/write-capabilities` answer carries a top-level string `book`
equal (trimmed, case-insensitive) to that `{book}`. Missing, null or empty is "not named". Until then both answer 409 `ac_waiting`,
"Waiting for AutoCount", with no write call, and the FE greys them with that reason. CRM-created orders are unaffected.
`in_autocount` stays true for an adopted order; `autocount_adopted` (SO row and detail) says why it waits; the capabilities route returns
`book`. The FE greys when the book is missing; a different book is refused by the server (the row carries no book to compare).

## Owner ruling R8 (5 Nov): every stored key also stores its book; every Update / Cancel is gated on it

Replaces R7's "CRM-created orders are unaffected". `autocount_book VARCHAR(40)` on `projects.sales_orders` and `projects.quotation_documents`
(migration `acqs_0001`). A done SO or QT create stores the `book` that `/write-capabilities` names at write time, trimmed (NULL when SS names
none); an adopted order's first done update stores its `source_ref` book segment beside the key; a refusal stores nothing. Update and Cancel
for EVERY SO and QT are allowed only when the record's book (stored, or for an adopted order with no stored key the `source_ref` segment)
equals the book SS names now, trimmed and case-insensitive. A NULL on either side or a mismatch answers 409 `ac_waiting` "Waiting for
AutoCount" with no write call. Create has no key yet and is not gated. The gate sits after the "already sent" shortcuts, so a repeat press
that sends nothing makes no call. The FE greys Update and Cancel with "Waiting for AutoCount" while the capabilities' `book` is
empty; the server enforces a mismatch. The stored book is never on a payload.

## Owner ruling R9 (5 Nov): no AutoCount write of any kind without a book

Extends R8 to create. SO create and QT create answer 409 `ac_waiting` "Waiting for AutoCount" with no write call while `/write-capabilities`
names no book (missing, null, empty or blank); when a book is named, create proceeds and stores it (R8). Eligibility and validation errors
(not accepted, missing debtor or location) still come first and make no call. The FE greys Create in AutoCount on the worksheet and the
quotation header with "Waiting for AutoCount" while the capabilities' `book` is empty. The capabilities route's field is `book` (SS names one
book per company), renamed from `sales_orders_book`.

## Owner ruling R6a (5 Nov ~10:15 MYT, "for QTSO ok a"): set money always equals the accepted quotation

Raised by the security review: pricing the main (driver) part at the set's rate times its qty per set overstates the money when the
main part is more than one per set (set RM100 x 2 sets, main part 2 per set -> 4 x 100 = RM400, accepted RM200).
- The main part's unit price = set rate / its qty per set, rounded to cents.
- If qty x that price does not equal set rate x set qty, the remainder cents go on that part: it is sent as two lines of the
  same item, (n - 1) at the rounded price and 1 at the price that makes the total exact. Example: RM100 a set, 3 per set,
  2 sets = 6 units: 5 x 33.33 + 1 x 33.35 = RM200.00. Only `qty` and `unitPrice` are used, so no discount semantics are assumed.
- The other parts stay at zero. The result note says the set went as its parts (unchanged).
- The SO draft's set split (`project_so_draft_service.py:1237`) is NOT changed in this lane; crew decides a lane after the proof note.
