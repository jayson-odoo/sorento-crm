# PLAN: PS-PROPOSAL-QUOTATION (proposal vs quotation flow, PO tallies with quotation)

Status: Build (card Q1-Q5 asked on #2097; built on the recommendations, adjusted when answered).
Track: full (size L: migration, approval rule change, new document kind, PO soft stop).

Lane: PS-PROPOSAL-QUOTATION, from the 2 Nov 2026 Project Sales demo (owner rulings ~21:05 MYT).
Card: `CARD-proposal-quotation-2nov.md`. UAC: `proposal-quotation-2nov-acceptance-criteria.md`.
Mock: `mockups/proposal-quotation.html`.

## Shape (simplest thing that works)

No new tables. A quotation is the SAME `quotation_documents` row shape with `kind = 'quotation'`, so the
editor, issue, sign, PDF, Excel, sign page, amendments and the approval gate all work on it unchanged.
Its scopes / versions / lines are copies of the picked proposal revision, so every FK that points at a
version (PO binding, samples, SO draft) keeps working.

## Migration `ppq_0001_proposal_quotation` (down_revision = main head at merge time)

- `projects.quotation_documents.kind` varchar(16) NOT NULL DEFAULT 'proposal', CHECK in
  ('proposal','quotation'). Every existing row becomes a proposal (Q2 a).
- `projects.quotation_documents.source_issue_id` uuid NULL FK `projects.quotation_issues(id)` ON DELETE SET NULL.
- Partial unique index `uq_quotation_documents_one_quotation` on (project_id) WHERE kind = 'quotation'.
- `projects.quotation_issues.revision_label` varchar(8) NULL; backfill `'R' || issue_no` for every row.
- `projects.purchase_orders.qty_over_reason` text NULL, `qty_over_reason_by` varchar(100) NULL FK users SET NULL,
  `qty_over_reason_at` timestamp NULL.
- Numbering rule per company: doc_type `project_sales_quotation`, prefix `QT-{year}-`, 4 digits, yearly
  (same insert shape as `327_quotation_document_layer.py:256-270`).
- Downgrade drops all of the above and the seeded rules.

## Backend contracts

### Labels (Q1 a) - `project_quotation_document_service.py`
- `revision_letter(n)`: 1 -> A ... 26 -> Z, 27 -> AA.
- At `issue()`: label = `R{n}` if the document is a quotation OR any earlier issue of this document has a
  label starting with "R"; otherwise `revision_letter(n)`. Stored on `revision_label`, and
  `our_ref_text = f"{document_no}-{label}"`.
- `quotation_no(document_no, issue_no, label=None)` -> `f"{document_no}-{label or 'R' + str(issue_no)}"`.
  Every caller passes `issue.revision_label` (pdf :457/:854, excel :313/:355, cover :34, doc service :739/:1551,
  route :924).

### Price alert (rule 3)
- In `issue()`, when kind == proposal and a previous issue exists: compare the previous issue's lines
  with the new issue's lines (via `quotation_issue_scopes` -> version -> lines). Key = product_id, else
  `set:<product_set_id>`, else `code:<UPPER product_code_snapshot>`. A key present in both with a different
  unit_price is a change. Any change -> `project_notify_service.notify_proposal_price_changed(db, project,
  document, record, changes)` best-effort (never fails the issue). notif_type `project_proposal_price_changed`,
  recipients `management_user_ids`, dedup `<issue_id>:proposal_price_changed`, email event key
  `project_proposal_price_changed` (registry + `notification_tasks` map).

### Make quotation (rule 4) - `make_quotation(db, *, proposal, issue_id, actor_user_id)`
- 422 `quotation_source_not_proposal` if the document is not a proposal.
- 404 `quotation_issue_not_found` if the issue is not on this document.
- 409 `project_not_won` unless `project.outcome == 'won'`.
- 409 `project_has_quotation` if the project already has a kind='quotation' document.
- Creates: kind quotation, number from `project_sales_quotation` (fallback `QT-{year}-{n:04d}`),
  `source_issue_id`, recipient party + snapshots + attn + your_ref + subject + purpose from the proposal,
  `cover_letter_html`/`terms_html`/`payment_terms`/`validity` from the ISSUE's frozen copies, signatory
  name/phone (NOT the signature). For each issue scope whose scope is not lost: a new scope (label, series,
  notes, sort_order, outcome won, decided_at now) with version 1 holding copies of every line of the issued
  version (all snapshot columns, prices, qty, flags), version total recomputed.
- Route: `POST /project-sales/projects/{project_id}/quotation-documents/{document_id}/make-quotation`
  body `{ "issue_id": uuid }` -> 201 `ProjectQuotationDocumentResponse`. Permission: projects.projects.edit +
  write access to the project (same as issue).
- Serializer adds `kind`, `source_issue_id`, `source_label` (e.g. "PRJQ-2026-0003-B"), `source_document_id`,
  `quotation_document_id` (on a proposal: the project's quotation if made from it), `recipient_party_type`.

### Further discount (rule 5, Q4 a) - `project_quotation_approval_service.py`
- `below_proposal_line_count(db, document)`: 0 unless kind == quotation and source_issue_id set. Source prices
  = lines of the versions the source issue froze, keyed as above (lowest price per key). Count current-version
  lines whose key is in the source and `unit_price < source price`.
- `requires_approval` = below floor > 0 OR below proposal > 0. `serialize_approval` adds `below_proposal_count`.

### PO (rule 6, Q5 a) - `project_po_service.py`, `project_po_confirm.py`
- `project_quotation_document(db, project_id)` -> the kind='quotation' document or None.
- Binding a PO (create, or update that changes the version) to a version whose scope's document is a proposal,
  while the project has a quotation: 422 `po_bind_proposal_refused` ("This project has a quotation; check the
  PO against it."). Existing bindings are never touched.
- `_bind_quotation_version`: when the project has a quotation, candidates are only its scopes.
- `qty_over_quotation(db, project_id)` -> list of `{key, product_code, description, ordered, quoted}`:
  quoted = sum qty of the quotation's current-version lines per key; ordered = sum qty of PO lines on the
  project's POs with status != superseded that are bound to a version of a quotation scope. Over = ordered > quoted
  (a key not quoted at all is a model mismatch already, not counted here).
- `enforce_qty_over(db, po, reason, actor_user_id)`: called after the lines are written by the PO document save
  route (`save_po_document`) and by `confirm_version`. Over and the PO has no reason: with a non-blank reason ->
  store reason/by/at, `notify_po_qty_over(...)` best-effort to management + owner (notif_type
  `project_po_qty_over_quote`); without -> 409 `po_qty_over_quoted`, `details = {"products": [...]}` (the route's
  rollback undoes the save; the screen re-sends with `qty_over_reason`). PO already has a reason -> nothing.
- `serialize_pos` adds `qty_over_reason`, `qty_over_reason_at`, `qty_over_reason_by_name`.

### Party types and the "To" picker
- `PARTY_TYPES` gains `tender_party` only (`project_reference_service.py:26`); FE label "Tender party".
  PS-REGISTRATION-V3 (#2099) owns `subcontractor` and `interior_designer` (agreed on #2097, 2 Nov).
- The proposal "To" picker reuses #2099's read: `GET /api/v1/projects/{project_id}/parties`
  (`project_party_contact_service.list_project_parties`, FE `useProjectParties(projectId)`). Wired after
  #2099 merges (merge main, then wire); until then the recipient block stays as today.

### Bot / reports
- `GET /project-sales/projects/{id}/quotations` rows gain `document_kind` and `document_no`; MCP catalog text
  for `crm_project_quotations_list` says proposal vs quotation. Forecast unchanged (quotation scopes are won).

## Frontend (Phase 1 mock, then wired)

- Project tab label "Proposals"; `QuotationsPanel` title/search/add say proposal; Kind badge column.
- Document page header: title "Proposal <no>" / "Quotation <no>"; "From proposal <label>" meta link; "Make
  quotation" action (issued proposal, project won, no quotation yet) opening `MakeQuotationDialog`.
- Recipient: SearchableSelect of the project's parties (reuse PS-REGISTRATION-V3's read if it lands first).
- Approval panel: "N lines priced below the proposal" next to the below-minimum count.
- `PurchaseOrderDialog` / PO confirm: on 409 `po_qty_over_quoted`, a dialog with the product table + Reason,
  re-sent as `qty_over_reason`; `PurchaseOrdersPanel` badge "Qty over quote" (title = reason).
- Sign page + PDF + Excel: noun from `kind` ("Proposal" / "Quotation"), file names `proposal-...` / `quotation-...`.

## Test list (red first)

Backend `tests/test_project_proposal_quotation.py` (blank_session, marker `zzt-ppq`):
1. existing/new documents default to kind proposal; first issue of a new proposal is labelled A, then B.
2. a document whose first issue is R1 keeps R2 on its next issue.
3. issuing B with a changed unit price calls the management alert with old/new; qty-only change does not.
4. make_quotation refused when project not won (409), when source is a quotation (422), when a quotation exists (409).
5. make_quotation copies lines, prices, party, terms; skips lost scopes; new scopes won; number from QT rule; label R1 on issue.
6. a quotation line below the source price requires approval; equal/higher does not.
7. binding a new PO to a proposal version on a project with a quotation -> 422; to the quotation -> ok.
8. qty over quoted without reason -> 409 po_qty_over_quoted with products; with reason -> saved + reason stored;
   superseded PO lines not counted.
9. migration: kind default + revision_label backfill (checked by the alembic gate on a copy).

Frontend vitest: Make quotation button visibility rules; qty-over dialog re-sends with reason; Kind badge.
