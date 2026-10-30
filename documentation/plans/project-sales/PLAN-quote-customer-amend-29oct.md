# PLAN: Customer amendment requests on the quotation link (QUOTE-CUSTOMER-AMEND)

Status: Build, Phase 2 (red-first tests) - mock v3 approved by the owner (30 Oct 10:28). BE + staff-grid tests now; sign-page code and its FE tests after QUOTE-SIGN-PAGE (#1987) merges. Track: full (migration + new public write path, security review mandatory).

Source: owner team meeting 29 Oct 15:40 (Project Sales module); owner answer Q3 29 Oct 22:45 (an accepted amendment produces the next revision under the QUOTE-SIGN-PAGE numbering); owner answers to this card's Q1-Q5, 30 Oct ~00:30 (see Decisions).

## Journey (one line)

A customer opens the quotation link, changes qty and/or unit price on the lines they disagree with
(description read-only) or marks a line for removal, submits one request; the salesperson sees a per-line diff on the quotation
document and accepts or rejects each line; accepted lines become the next draft revision
(below-minimum prices go through the existing approval before it can be sent); the customer sees
the outcome on the same link.

## Behaviour card v1

### What exists today (main ec29a81c, read, not guessed)

- One free-text request per issue, latest only: `request_changes` `sorento_crm_backend/app/services/project_quotation_document_service.py:1121`, columns `changes_requested_at/_note/_by_name` `app/models/projects.py:1284-1286`, public route `app/api/v1/public/quotation_sign.py:83`.
- Today the customer MAY still sign after asking for changes ("The reverse order is deliberately ALLOWED", document_service.py:1150-1154, client decision 2026-08-05).
- The link: 30-day token (`SIGN_TOKEN_TTL_DAYS` document_service.py:896), expired and unknown answer the same 404 (`get_issue_by_sign_token` :1001-1034). A SUPERSEDED issue's link still resolves and can still be signed today: nothing checks for a later issue.
- The sign page renders the ISSUED version's lines, never live rows (`serialize_sign_page` :1282).
- An issued version is frozen (`is_frozen` `app/services/project_quotation_service.py:140`); `revise` (:371) freezes the live version and copies its lines into the next one, with NEW line ids and no back-reference.
- Below-minimum: every line write stores `is_below_floor` via `_apply_guardrails` (project_quotation_service.py:622); the gate is at ISSUE (`assert_issuable` `app/services/project_quotation_approval_service.py:195`, called from `issue` document_service.py:538). `revise` refuses while a document is pending approval or approved (`assert_scope_unlocked` project_quotation_service.py:206).
- The salesperson sends the link by hand; the system sends nothing to the customer (`create_quotation_sign_link` `app/api/v1/projects/quotation_documents.py:609`).
- Staff notification pattern: `notify_quotation_changes_requested` `app/services/project_notify_service.py:465` (project owner, else management; deduped).
- Per-line Accept/Decline UI: `AmendmentDeltaTable` `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/AmendmentDeltaTable.tsx:63` (Decision column :359-441). Considered and NOT used (owner, mock v2 note 2): the suggestions are decided on the quotation's own line grid instead.

### Rules (owner-approved answers applied)

1. **Where.** Only on the sign page of an issue that is (a) on a valid link, (b) not accepted, (c) the LATEST issue of its document. A superseded issue's page shows "This quotation has been replaced by Quotation No. PRJQ-...-R{n}" (the full QUOTE-SIGN-PAGE label, never a bare "R{n}") and offers neither edit nor sign (new: closes today's gap where an old revision can still be signed).
2. **What the customer can change.** Quantity and unit price, per line, or a staged removal of the line (Q2). Description, product code, brand, spec, band label, item number: read-only, and the request payload has no field for them (the server cannot be asked to write one).
   - Quantity: 1 to 9,999,999.99, two decimals (the `quantity` column, models/projects.py:1561). 0 is refused (422); qty 0 does NOT mean remove (Q2).
   - Removal: a delete icon on each line STAGES a removal suggestion, the same way the quotation editor stages a line delete (`QuotationLinesGrid.tsx` `ActionsCell`: Trash2 "Remove {line}" :687-697 strikes the row through and makes its cells read-only; Undo2 "Restore {line}" :628-640 takes it back). Nothing is sent until Send. A line staged for removal carries no qty/price change.
   - Unit price: greater than 0, at most 9,999,999,999.99 (Numeric(12,2)). Only on lines that carry a price (unit price above 0, or rate-only). Zero-priced companion lines (the cistern, seat cover and connector under a priced WC) show their price as read-only: their money sits on the parent.
   - A line counts as changed only if it is staged for removal or its qty or price differs from what was issued; unchanged lines are not stored.
3. **One request.** One submit = the changed lines + an optional note (Q5). At least one changed line or a note, else 422. The lines must belong to the versions this issue carried (`quotation_issue_scopes`), else 422 without saying which ids exist.
4. **One open request per issue.** While a request is open the page shows it read-only ("With your salesperson since 30 Oct, 14:05") and a second submit is 409. Once answered, a new request is allowed only on the NEXT revision (it has its own link).
5. **Staff side (owner, mock v2 note 2).** No new tab and no separate table. The quotation's own line grid on its Lines tab (`QuotationLinesGrid`, view-mode columns #, Photo, Drawing, Product, Description, Brand, Qty, UOM, Rate (RM), Total (RM), :801-958) gets a review mode: each suggestion sits in the cell it concerns (Qty, Rate), quoted value struck through above the suggested one, Accept / Reject right under it in the same cell, and a Reject's reason field opens there too. A suggested removal sits in the row-actions column, where the editor's own Remove icon lives. A suggested price below the minimum shows the grid's existing `MinimumPriceFlag` under the price (`RateCell`, :528-531). One summary row above the grid holds the customer's note, the counts, the totals and Apply; Apply is enabled once every suggestion has a decision.
6. **Apply.** Each scope with at least one accepted row is revised (`revise`, project_quotation_service.py:371) and the accepted qty/price are written through the existing line writer, so the floor flags recompute exactly as for a hand edit. Rejected rows carry over unchanged. An accepted removal deletes the line from the new version; a rejected removal keeps it as issued. The result is a DRAFT revision (Q3); below-minimum lines stop it issuing until the existing approval passes (`assert_issuable`). Nothing goes out automatically.
7. **Customer told.** The original link (still valid) shows the outcome per line: accepted / not accepted + reason, and "Your salesperson will send the revised quotation". The new revision's link is sent the usual way. No new outbound channel.
8. **Salesperson notified** (Q4 = a AND b), one notice per request, through `project_notify_service._send` (:122) with the same recipients rule as today's free-text request (project owner, else management, :491): in-app project alert, email (`send_email` defaults on, :132) and WhatsApp (`send_whatsapp=True` + `_whatsapp_for`, the precedent the approval alerts already use, :384 and :447). No new provider. WhatsApp reaches a recipient only when they have `notify_whatsapp` on and a resolvable Respond contact (`notification_service.create_with_channel_preferences`); otherwise that one channel is skipped and the other two still go.
9. **Rate.** The public write route is rate-limited per IP and per token with the existing `app/services/rate_limit.py` (fail-open), e.g. 10 submits per hour per token. One open request per issue (rule 4) already caps what reaches staff.
10. **No signing while a request is open (Q1 a).** This reverses the 2026-08-05 client decision for the free-text request (document_service.py:1150-1154); `accept_issue` refuses 409 `quotation_amendment_open` while one is open.
11. **Why Sign is disabled, always said (owner: "the user know why they cannot accept").** Sign has TWO possible disabled reasons, and the page prints the one that applies directly under the button, never a bare greyed button:
    - an open request: "You can sign once Sorento has answered your suggested changes (sent 30 Oct, 14:05)." The terms tick is hidden in this state, because ticking it could not enable anything;
    - no open request, terms not ticked (QUOTE-SIGN-PAGE's tick): "Tick that you have read the terms to sign."
    The open-request reason is checked first; the two never show together. The server refuses the same way (409 `quotation_amendment_open`), so a stale tab gets the same sentence.

### Worked example (FAKE values)

The repo is public, so every code, description and price below is invented. The shape is the
one real project quotations have: a priced item followed by zero-priced companion lines at the
same quantity (the money sits on the parent). Labels follow the QUOTE-SIGN-PAGE ruling: one
label `Quotation No. PRJQ-0000-R1` plus the Revision row (`PRJQ-0000` is a placeholder).

Fake quotation `Quotation No. PRJQ-0000-R1`, Customer A, Project P1: 40 lines, one scope, grand total RM 250,000.00.

| Line | Item (fake) | Issued | Requested | Outcome shown to staff |
|---|---|---|---|---|
| 1 | WC-1001 one-piece WC | 120 x 400.00 = 48,000.00 | 110 x 380.00 = 41,800.00 | qty -10, price -20.00 (-5.0%); below-minimum badge if 380.00 < stored floor |
| 2 | CON-0001 connector (companion of line 1) | 120 x 0.00 | 110 x 0.00 | qty -10 (price read-only) |
| 14 | BSN-4004 basin | 120 x 160.00 = 19,200.00 | 120 x 150.00 = 18,000.00 | price -10.00 (-6.3%) |
| 40 | SHW-5005 shower head | 10 x 10.00 = 100.00 | removal staged with the delete icon | "Remove line" row |

Requested total RM 242,500.00. Staff accept 1, 2 and 40, reject 14 ("already at project price"): `PRJQ-0000-R2` is drafted at RM 243,700.00 with lines 1, 2 changed and line 40 gone; if 380.00 is below line 1's floor, Issue is blocked until a manager approves (existing S15 gate). The R1 link then reads: 3 accepted, 1 not accepted with the reason.

The other shapes the brief asks for (a multi-section issue where only the touched scope is revised; a request priced below the floor; an already-signed issue, refused 409) become Phase 2 test fixtures, also with fake values. This cloud lane has no shared dev DB access by contract.

### Edge cases

| Case | Behaviour |
|---|---|
| Expired link | Same 404 as today, read and write (`get_issue_by_sign_token`). Nothing stored. |
| Second request while the first is open | 409, page shows the open request read-only (rule 4). |
| Qty 0 | Refused: the input's minimum is 1 and the server answers 422 (Q2). Removal is the delete icon. |
| Every line of a scope staged for removal | Allowed; staff decide per line. If all are accepted the scope's next version has no lines and a total of 0, and the salesperson sees that before issuing (Q3 a). |
| Remove staged, then Restore | The row returns to the issued values; nothing was sent. |
| Request on a superseded revision | Refused 409 "replaced by Quotation No. PRJQ-...-R{n}"; page shows the replacement notice (rule 1). If the salesperson issues R2 while R1's request is OPEN, R1's request closes as "superseded" and its lines show "not applied" to the customer. |
| Concurrent staff edit | If a scope already has an unissued draft version when staff press Apply, Apply refuses for that scope: "A revision is already open on {scope}; issue or discard it first." Merging into a hand-edited draft by position would be a guess (revise gives copied lines new ids). If the document is pending approval or approved, Apply refuses with the existing lock message (`assert_scope_unlocked`). |
| Customer signs while a request is open | Refused 409 with the rule 11 sentence (Q1 a). |
| Price above the issued price | Allowed and shown as an increase; nothing special. |
| Rate-only line | Price editable, qty editable, amount still prints "rate only". |
| Same submit twice (double tap) | Row lock on the issue (as `request_changes` does); the second sees the open request and gets 409, the page already shows it. |

### Decisions (owner, 30 Oct ~00:30)

| Q | Answer | Where it lands |
|---|---|---|
| Q1 Sign while a request is open? | (a) No. Sign greyed with the reason shown, same clarity rule as the terms tick. Reverses the 2026-08-05 client decision. | Rules 10, 11 |
| Q2 Qty 0 = remove? | NO. Qty minimum 1. A per-line DELETE icon stages a removal suggestion, reusing the quotation editor's staged delete; the salesperson accepts or rejects it like any line change. | Rule 2, edge cases, mock 1-6 |
| Q3 What do accepted lines become? | (a) A draft revision the salesperson checks and sends. | Rule 6 |
| Q4 How is the salesperson told? | (a) AND (b): in-app project alert AND WhatsApp/email notice, existing channels, no new provider. | Rule 8 |
| Q5 Free-text box? | (a) One optional note on the same request. | Rule 3 |

Owner layout notes on mock v1 (30 Oct 00:30), applied in mock v2:

1. "the decision needs to be at proximity to where the customer suggest changes": Accept / Reject sits beside each quoted -> suggested value (and a Reject's reason field opens in the same place), not in a far-right Decision column.
2. "i need the quotation to be more cleanly designed and less information fatigue": only changed lines are open, unchanged lines fold into one row; three columns on the staff side (line, item, suggestion and decision), four on the customer side; ONE summary row (number of suggestions, total before -> after) is the only place totals appear; even row spacing.

Owner notes on mock v2 (30 Oct 09:52), applied in mock v3:

1. "the columns supposed to be same as the current quotation view, our current quotation view got put item code and uom at the bottom of description meh?" No, it does not: on the CRM Lines tab the item code is its own Product column before Description (`QuotationLinesGrid.tsx` `ProductCell` :305) and UOM is its own column after Qty (:904-916); the Description cell shows only the description (:360-366). The customer sign page has Product code as its own column and no UOM column (`QuotationSignScopes.tsx:64-72`). Mock v2 invented "code + UOM under the description"; mock v3 uses each view's own columns unchanged (the sign page's nine on the customer side, plus one narrow delete column; the Lines grid's ten on the staff side), and the sign page keeps its in-card sideways scroll at 375 instead of v2's line cards.
2. "should reuse our quotaiton line and put the button at the correspodning column and row, don't invent a new tab caleld custoemr suggestion": rule 5. `AmendmentDeltaTable` is not used.

## Storage (migration)

- `projects.quotation_amendment_requests`: id, company_id, issue_id (FK quotation_issues, cascade), status (`open` / `applied` / `superseded`), requester_name (200), note (text), ip_address (64), submitted_at, applied_at, applied_by (FK users, set null), created_at, updated_at.
  Partial unique index: one `open` per issue_id. `CompanyScopedMixin`, audited.
- `projects.quotation_amendment_request_rows`: id, company_id, request_id (FK, cascade), line_id (FK quotation_lines of the ISSUED version, cascade), field (`quantity` / `unit_price` / `remove`), value_from Numeric(12,2) null, value_to Numeric(12,2) null (null for `remove`), decision (`pending` / `accepted` / `rejected`, default pending), decision_reason (500), decided_by (FK users, set null), decided_at.
  Unique (request_id, line_id, field). One row per field, so the salesperson can accept the quantity and reject the price of the same line.
- The three `changes_requested_*` columns stay and are still written from the note, so the existing panel and activity history keep working.

## API contract

Public (`app/api/v1/public/quotation_sign.py`, token only):

- `POST /api/v1/public/quotation-sign/{token}/amendment-request`
  body `{ "requester_name": str|null (<=200), "note": str|null (<=4000), "lines": [ { "line_id": str, "quantity": "110.00"|null, "unit_price": "380.00"|null, "remove": bool } ] (<=500) }`
  -> 200 the sign page. Errors per UAC AC-QCA-02..12.
- `POST /{token}/accept` -> 409 `quotation_amendment_open` while a request is open; 409 `quotation_superseded` on a superseded issue.
- Sign page payload adds: `lines[].id`, `amendment_request` (null or `{id, status, submitted_at, requester_name, note, rows: [{id, line_id, field, value_from, value_to, decision, decision_reason}]}`), `superseded_by_ref` (null or the later issue's `our_ref_text`), `can_sign` (bool), `sign_blocked_reason` (null | `amendment_open` | `amendment_applied` | `superseded` | `accepted`).

Service (`app/services/quotation_amendment_service.py`, new module):

- `submit_request(db, *, record, lines, note, requester_name, ip_address) -> QuotationAmendmentRequest`
- `open_request(db, issue_id) -> Optional[QuotationAmendmentRequest]`
- `latest_request_for_document(db, document) -> Optional[QuotationAmendmentRequest]`
- `decide_row(db, *, request, row_id, decision, reason, actor_user_id) -> QuotationAmendmentRequestRow`
- `apply_request(db, *, request, actor_user_id) -> List[ProjectQuotationVersion]` (the new draft versions)
- `serialize_request(db, request) -> dict` (rows carry `below_floor` and `floor_value` on `unit_price` rows for staff)
- `close_open_requests_superseded_by(db, document, new_issue)` called from `issue()`.

Staff (`app/api/v1/projects/quotation_documents.py`, `require_permission(EDIT)`, `_editable_project`):

- `GET /projects/{project_id}/quotation-documents/{document_id}/amendment-request` -> the serialized open or latest request of the latest issue, or `null`.
- `PUT /projects/{project_id}/quotation-documents/{document_id}/amendment-requests/{request_id}/rows/{row_id}` body `{ "decision": "accepted"|"rejected"|"pending", "reason": str|null }` -> the serialized request.
- `POST /projects/{project_id}/quotation-documents/{document_id}/amendment-requests/{request_id}/apply` -> `{ "request": {...}, "version_ids": [...] }`.

FE (staff): `QuotationLinesGrid` gains an optional prop
`review?: { rows: QuotationAmendmentRow[]; onDecide: (rowId: string, decision: 'accepted' | 'rejected' | 'pending', reason?: string) => void; disabled?: boolean }`
with `QuotationAmendmentRow = { id, line_id, field: 'quantity' | 'unit_price' | 'remove', value_from: string | null, value_to: string | null, decision, decision_reason: string | null, below_floor?: boolean, floor_value?: string | null }` in `_shared/types/project.types.ts`.

## Component map (to be confirmed against QUOTE-SIGN-PAGE once it merges)

| Element | Repo path |
|---|---|
| Customer edit mode on lines | `sorento_crm_frontend/app/(auth)/quotation-sign/[token]/components/QuotationSignScopes.tsx` (adds an edit mode to `ScopeTable`) |
| Staged remove / restore icon | same Trash2 / Undo2 pair and strike-through as `.../project-sales/[projectId]/components/QuotationLinesGrid.tsx` `ActionsCell` (:619-697) |
| Notify (in-app + email + WhatsApp) | `app/services/project_notify_service.py`, new `notify_quotation_amendment_requested` beside `notify_quotation_changes_requested` (:465) |
| Submit, note, open-request and outcome states | `.../quotation-sign/[token]/components/QuotationSignClient.tsx` (replaces the Request changes block :280-330) |
| Staff suggestion + Accept/Reject in its own cell | `.../project-sales/[projectId]/components/QuotationLinesGrid.tsx`, a review mode on `QtyCell` :433, `RateCell` :516, `ActionsCell` :619 (no new tab, no new table) |
| Staff summary row + Apply | `.../quotation-documents/[documentId]/components/QuotationScopesTab.tsx` (the Lines tab), above the grid while a request is open |
| Below-minimum badge + approval | `QuotationApprovalPanel.tsx` + `Badge` |
| BE public route | `app/api/v1/public/quotation_sign.py` |
| BE service | `app/services/project_quotation_document_service.py` (new functions beside `request_changes`) |
