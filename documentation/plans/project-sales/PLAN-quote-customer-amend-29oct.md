# PLAN: Customer amendment requests on the quotation link (QUOTE-CUSTOMER-AMEND)

Status: Plan - behaviour card v1 + mock v1 (`documentation/mockups/QUOTE-CUSTOMER-AMEND/index.html`) filed for the owner on PR #1984. Build blocked on owner approval AND the QUOTE-SIGN-PAGE merge. Track: full (migration + new public write path, security review mandatory).

Source: owner team meeting 29 Oct 15:40 (Project Sales module); owner answer Q3 29 Oct 22:45 (an accepted amendment produces the next revision under the QUOTE-SIGN-PAGE numbering).

## Journey (one line)

A customer opens the quotation link, changes qty and/or unit price on the lines they disagree with
(description read-only), submits one request; the salesperson sees a per-line diff on the quotation
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
- Per-line Accept/Decline UI: `AmendmentDeltaTable` `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/AmendmentDeltaTable.tsx:63` (Decision column :359-441). Its row type `AmendmentDeltaRow` is SO-shaped (`so_line_id`, `verb`, `field`), so it takes a new mode/prop, not a fork.

### Rules (proposed)

1. **Where.** Only on the sign page of an issue that is (a) on a valid link, (b) not accepted, (c) the LATEST issue of its document. A superseded issue's page shows "This quotation has been replaced by Quotation No. PRJQ-...-R{n}" (the full QUOTE-SIGN-PAGE label, never a bare "R{n}") and offers neither edit nor sign (new: closes today's gap where an old revision can still be signed).
2. **What the customer can change.** Quantity and unit price, per line. Description, product code, brand, spec, band label, item number: read-only, and the request payload has no field for them (the server cannot be asked to write one).
   - Quantity: 0 to 9,999,999.99, two decimals (the `quantity` column, models/projects.py:1561). 0 = remove this item (Q2).
   - Unit price: greater than 0, at most 9,999,999,999.99 (Numeric(12,2)). Only on lines that carry a price (unit price above 0, or rate-only). Zero-priced companion lines (the cistern, seat cover and connector under a priced WC) show their price as read-only: their money sits on the parent.
   - A line counts as changed only if qty or price differs from what was issued; unchanged lines are not stored.
3. **One request.** One submit = the changed lines + an optional note (Q5). At least one changed line or a note, else 422. The lines must belong to the versions this issue carried (`quotation_issue_scopes`), else 422 without saying which ids exist.
4. **One open request per issue.** While a request is open the page shows it read-only ("With your salesperson since 30 Oct, 14:05") and a second submit is 409. Once answered, a new request is allowed only on the NEXT revision (it has its own link).
5. **Staff side.** The quotation document page gets a "Customer request" panel: per-line diff (issued value, requested value, change), a below-minimum badge on any requested price under the line's stored floor, Accept/Reject per line, optional reason on Reject, and the customer's note. "Apply" is enabled once every line has a decision.
6. **Apply.** Each scope with at least one accepted line is revised (`revise`, project_quotation_service.py:371) and the accepted qty/price are written through the existing line writer, so the floor flags recompute exactly as for a hand edit. Rejected lines carry over unchanged. Accepted qty 0 deletes the line from the new version. The result is a DRAFT revision (Q3); below-minimum lines stop it issuing until the existing approval passes (`assert_issuable`). Nothing goes out automatically.
7. **Customer told.** The original link (still valid) shows the outcome per line: accepted / not accepted + reason, and "Your salesperson will send the revised quotation". The new revision's link is sent the usual way. No new outbound channel.
8. **Salesperson notified** through `project_notify_service` with the same recipients rule as today's free-text request (Q4), one notification per request.
9. **Rate.** The public write route is rate-limited per IP and per token with the existing `app/services/rate_limit.py` (fail-open), e.g. 10 submits per hour per token. One open request per issue (rule 4) already caps what reaches staff.
10. **Accepted wins over pending.** If the customer somehow signs (stale tab) while a request is open, see Q1.
11. **Why Sign is disabled, always said (owner: "the user know why they cannot accept").** If Q1 (a) wins, Sign has TWO possible disabled reasons, and the page prints the one that applies directly under the button, never a bare greyed button:
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
| 40 | SHW-5005 shower head | 10 x 10.00 = 100.00 | 0 | removal |

Requested total RM 242,500.00. Staff accept 1, 2 and 40, reject 14 ("already at project price"): `PRJQ-0000-R2` is drafted at RM 243,700.00 with lines 1, 2 changed and line 40 gone; if 380.00 is below line 1's floor, Issue is blocked until a manager approves (existing S15 gate). The R1 link then reads: 3 accepted, 1 not accepted with the reason.

The other shapes the brief asks for (a multi-section issue where only the touched scope is revised; a request priced below the floor; an already-signed issue, refused 409) become Phase 2 test fixtures, also with fake values. This cloud lane has no shared dev DB access by contract.

### Edge cases

| Case | Behaviour |
|---|---|
| Expired link | Same 404 as today, read and write (`get_issue_by_sign_token`). Nothing stored. |
| Second request while the first is open | 409, page shows the open request read-only (rule 4). |
| Qty 0 | Removal (Q2); shown struck through on both sides; applying it deletes the line from the next version. All lines of a scope at 0: allowed, the scope total becomes 0 and staff decide. |
| Request on a superseded revision | Refused 409 "replaced by Quotation No. PRJQ-...-R{n}"; page shows the replacement notice (rule 1). If the salesperson issues R2 while R1's request is OPEN, R1's request closes as "superseded" and its lines show "not applied" to the customer. |
| Concurrent staff edit | If a scope already has an unissued draft version when staff press Apply, Apply refuses for that scope: "A revision is already open on {scope}; issue or discard it first." Merging into a hand-edited draft by position would be a guess (revise gives copied lines new ids). If the document is pending approval or approved, Apply refuses with the existing lock message (`assert_scope_unlocked`). |
| Customer signs while a request is open | Q1. |
| Price above the issued price | Allowed and shown as an increase; nothing special. |
| Rate-only line | Price editable, qty editable, amount still prints "rate only". |
| Same submit twice (double tap) | Row lock on the issue (as `request_changes` does); the second sees the open request and gets 409, the page already shows it. |

### Questions for the owner (5)

**Q1. Can the customer still sign while their amendment request is open?**
(a) No: Sign is disabled with "Waiting for your salesperson's answer" until the request is answered. (b) Yes, as today for the free-text box (document_service.py:1150); signing closes the request as withdrawn.
Recommendation: (a). A signature next to an open price request is a record that says both; with per-line prices the conflict is concrete (which price was signed?). The client decision of 2026-08-05 was made when the request was only words.

**Q2. Does qty 0 mean "remove this item"?**
(a) Yes: shown as a removal on both sides, applying it deletes the line from the next revision. (b) No: qty must stay at least 1, removal goes in the note.
Recommendation: (a), it is what a customer means by 0, and the staff accept/reject per line keeps control.

**Q3. What do accepted lines become?**
(a) A new DRAFT revision the salesperson reviews and issues (and sends for approval if below minimum). (b) Auto-issue R{n+1} when no line is below minimum.
Recommendation: (a). Issuing needs Sorento's signature (`issue` document_service.py:533) and a person choosing to send; auto-issue would put a price in front of the customer nobody looked at as a whole.

**Q4. How is the salesperson told a request arrived?**
(a) The existing project notification (`project_notify_service.py:465` pattern: project owner, else management; bell + whatever channels that type already uses). (b) A new channel (WhatsApp/email to the salesperson).
Recommendation: (a), same pattern as today's free-text request, no new channel.

**Q5. Keep the free-text box beside the per-line edits?**
(a) Yes, one optional note on the same request for anything that is not qty/price (delivery, finish, terms). (b) No, per-line edits only.
Recommendation: (a). The existing free-text request becomes the note of the new request (one submit, one notification), so there are not two "request changes" buttons.

## Storage (proposed, migration)

- `projects.quotation_amendment_requests`: id, company_id, issue_id (FK, cascade), requester_name, note, status (`open` / `applied` / `superseded`), submitted_at, ip_address, applied_at, applied_by, created/updated.
  Partial unique index: one `open` per issue_id.
- `projects.quotation_amendment_request_lines`: id, company_id, request_id (FK, cascade), line_id (FK to the ISSUED version's line), qty_from, qty_to, price_from, price_to, decision (`pending` / `accepted` / `rejected`), decision_reason, decided_by, decided_at.
- The three `changes_requested_*` columns stay (history) and keep being written for the note, so the existing panel and activity feed keep working.

## Component map (to be confirmed against QUOTE-SIGN-PAGE once it merges)

| Element | Repo path |
|---|---|
| Customer edit mode on lines | `sorento_crm_frontend/app/(auth)/quotation-sign/[token]/components/QuotationSignScopes.tsx` (adds an edit mode to `ScopeTable`) |
| Submit, note, open-request and outcome states | `.../quotation-sign/[token]/components/QuotationSignClient.tsx` (replaces the Request changes block :280-330) |
| Staff per-line diff + Accept/Reject | `.../project-sales/[projectId]/components/AmendmentDeltaTable.tsx`, new quotation mode (row shape: line, field qty/price, from, to) |
| Staff panel | `.../quotation-documents/[documentId]/components/QuotationChangesRequestedPanel.tsx` (grows into the request panel) |
| Below-minimum badge + approval | `QuotationApprovalPanel.tsx` + `Badge` |
| BE public route | `app/api/v1/public/quotation_sign.py` |
| BE service | `app/services/project_quotation_document_service.py` (new functions beside `request_changes`) |
