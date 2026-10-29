# PLAN SAMPLE-FROM-QUOTE: a sample request starts from the project's quotation

Status: backend and shared frontend pieces built and green on the lane branch (PR #1985, draft); the
form wiring and the request page line wait for #1953 (PORTAL-P4-REQUESTS) to merge. Q3 waits on the
owner, held behind `QUOTE_FREE_TEXT_LINES`. Track: M lane (migration, portal read surface).

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
| FE forms (after #1953) | portal `SampleRequestForm` and `StaffSampleRequestForm` call the hook; quotation picker (only for more than one document) above the items; the note under the table; `?project_id=` seed triggers it too | waiting |
| FE request page (after #1953) | "Quotation" read-only row from `quotation_ref` | waiting |
| My Requests (after #1953) | register the portal pre-fill route on `/api/v1/my-requests` like the other portal form routes | waiting |
