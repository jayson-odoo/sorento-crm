# PLAN SAMPLE-FROM-QUOTE: a sample request starts from the project's quotation

Status: owner hand test 30 Oct FAIL fixed (line products only from the source quotation, SFQ-27/28) and owner Q3
answered (free text never becomes a row; the switch is gone); reviewer, browser pass and hand test re-run pending.
PR #1985. S1 (portal read breadth) asked of crew. Track: M lane (migration, portal read surface).

Card: `CARD-sample-from-quote-29oct.md`. UAC: `sample-from-quote-29oct-acceptance-criteria.md`.

## Owner answers (30 Oct ~00:30)

Q1 a (latest issue; picker when more than one document; never-issued uses current versions), Q2 a (qty 1),
Q4 a (one row per product), Q5 a (record the source quotation, shown on the request page), Q6 a (the staff
form pre-fills too), Q7 a (discontinued but active products pre-fill as-is). Q3 (free-text lines) pending:
skip-with-note vs add-as-row, one switch.

Q6 a means the staff form, which #1953 keeps for users who are not limited salespeople, needs the
pre-fill too. So the pre-fill is one hook (`hooks/useSampleRequestPrefill.ts`) over one set of pure rules
(`lib/sample-request-form.ts`), called by the two form components that exist; the portal form is the
single component the portal and the CRM's My Requests share (28 Oct ruling), so no third copy exists.

## Contract

`GET /api/v1/project-sales/projects/{project_id}/sample-requests/quotation-prefill[?document_id=]`
(`projects.sample_requests.create`; a limited user's own-project rule) and
`GET /api/v1/public/portal/sample-request/quotation-prefill?project_id=[&document_id=]`
(`assert_portal_project_allowed`, contact companies). After #1953 the portal route also mounts on
`/api/v1/my-requests` at the same relative path.

```json
{
  "documents": [{"id": "...", "document_no": "...", "issue_id": "...|null", "issue_no": 2, "label": "<no> (R2)"}],
  "document_id": "...|null",
  "issue_id": "...|null",
  "lines": [{"product_id": "...", "product_code": "...", "product_name": "...", "brand_name": "...|null"}],
  "skipped": [{"reason": "no_product|inactive", "description": "..."}]
}
```

Write: `quotation_document_id`, `quotation_issue_id` on create / update (422
`SAMPLE_REQUEST_QUOTATION_INVALID` unless the document is the request's project's and the issue that
document's). Detail: both plus `quotation_ref`.

## Slices

| Slice | What | State |
|---|---|---|
| BE | `sample_request_service.quotation_prefill`, `_check_source`, `quotation_label`; both routes; `sfq_0001_sample_request_source` (two nullable FK columns, SET NULL) | red f43c16d6, green de621365 (20 tests) |
| FE shared | form state + payload source fields, `linesUntouched`, `prefillFromQuotation`, `prefillNote`, `QUOTE_FREE_TEXT_LINES`; `useSampleRequestPrefill`; staff + portal fetchers | red a1332e53, green dfec4272 (18 tests) |
| FE forms | portal `SampleRequestForm` and `StaffSampleRequestForm` call the hook; quotation picker (more than one document, rows untouched) above the items; the note under the table; `?project_id=` seed triggers it too | red 780b1aa7, green a118ecef |
| FE request page | "Quotation" read-only row from `quotation_ref` (staff detail; "Quotation: ..." on the shared form) | red 332ecca9, green d7aa237c |
| My Requests | the pre-fill route lives inside `register_sample_request_routes`, so `/api/v1/my-requests` serves it | merge dfadf3aa |
| Security B1, N1 | own-project rule on the shared route for a contact linked to a limited CRM user (read and recorded source); `/my-requests` read needs `.create` | red c68f65ec, green b04877b3 |
| Review B1, S2, S3 | a project change drops the recorded source (new or loaded draft, failed read too); no picker once rows are edited | see branch log |
| Owner hand test + Q3 | product search narrowed to the source quotation (staff, portal, My Requests) and off-quote line products refused; `QUOTE_FREE_TEXT_LINES` removed | red f77af2f8, see branch log |
