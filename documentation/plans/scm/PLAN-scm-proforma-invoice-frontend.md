# PLAN - Proforma invoices get their screen

**Status:** Approved by the captain, 20 Aug 2026 ("for proforma invoice, we need the frontend
also"). Implementation starting on branch `fm/scm-demo-followups-20aug`.

**Serves:** `scm-proforma-invoice-acceptance-criteria.md` (the contract - its backend slice
shipped in PR #222 and explicitly deferred "the consuming screen" to a next task; this is that
task). Sibling of `PLAN-scm-loading-plan-demand-first.md` (the two land together so the
stakeholder's flow - request out, packing list / proforma back - is walkable end to end).

## Journey

The UAC's own Journey section governs, unchanged: Ms Tee picks the supplier, drops the
proforma workbook, is asked for a currency ONLY when neither the document nor the supplier's
price list says (AC-P3.1/P3.3 - no house default, and the preview names which source won),
reads the preview (documents found, numbers, dates, totals, unmatched item codes NAMED), Tests
if she wants the verdict, Applies. Re-upload updates in place and the result says created vs
updated. Afterward she can list what is on file per supplier, open one to read its lines, and
hard-delete a wrong upload.

## Scope - all frontend, zero backend

- Sidebar: `Proforma Invoices` under Supply Chain, after Incoming Containers,
  `permission: 'scm.dashboard.view'` (the read gate the list route enforces); the Upload
  button inside the page gates separately on `scm.proforma_invoice.upload` (AC-P4.3).
- `/scm/proforma-invoices`: supplier filter (existing `useFulfilmentSuppliers` source) +
  DataGrid (PI number, supplier code + name, invoice date, container ref, BL ref, currency,
  lines, total, uploaded) + Upload dialog + per-row delete
  (`ConfirmDeleteDialog`, hard delete, standard copy).
- Upload dialog mirrors `PackingListUploadDialog` (the exemplar that already has the optional
  3-letter currency field and multi-document summary) on `useTwoStepUpload`, with
  `supplier_id` REQUIRED (unlike packing lists). Preview panel per document: number (marked
  derived when `pi_number_stated` is false, AC-P2.5), date, container, lines, total vs
  stated total, currency + source in words (AC-P3.1). Unmatched codes named (AC-P1.3).
- `/scm/proforma-invoices/[id]`: detail page - header meta (PI number, supplier, date,
  refs, currency, total, source file, uploaded by/at) + lines grid (line no, item code,
  description, qty, UOM, unit price, amount, PO ref, matched). Every section rendered even
  when empty, per the CRUD standard. No edit surface - a proforma is the supplier's
  document; the correction path is re-upload (updates in place) or delete.
- No UUID reaches a human anywhere (AC-P4.4): supplier code + name, product code.

## Contract notes (read off the backend, no schemas exist)

- List: `GET /api/v1/scm/proforma-invoices?supplier_id&limit&offset` - offset paging, fixed
  `created_at DESC` sort, NO `page/sort/query` params, so `buildDataGridParams` does NOT
  apply; the service converts `pageIndex * pageSize -> offset`. `limit` caps at 100.
- Preview/apply: multipart `file` + `supplier_id` + optional `currency` (append only when
  typed - an empty string reads as an unresolvable currency). `apply?validate_only=true`
  returns the standard `{valid, errors, warnings, summary}` envelope (`UploadTestResult`).
- Delete: 204, empty body.

## Tests

- vitest: upload dialog (preview render incl. derived-number marker + currency source words,
  test verdict, apply result created/updated counts, currency field behavior), list view
  (loading / empty / error / data, supplier filter, delete confirm copy), detail (lines +
  empty states). Mock `useListingColumnPreferences` per the jsdom lesson.
- Evidence run (agent-browser): sidebar -> Proforma Invoices -> upload the real Kailu /
  pre-loading-list fixture (backend tests carry fixtures) -> preview -> apply -> row appears
  -> detail shows priced lines -> delete removes. Network filter confirms the four routes.

## Out of scope

- The PI-vs-PO verification screen (variance, overcharge) - the UAC's own "next task", still
  next.
- Any backend change; any new pytest (route suite exists: `tests/scm/test_proforma_invoice_routes.py`).
