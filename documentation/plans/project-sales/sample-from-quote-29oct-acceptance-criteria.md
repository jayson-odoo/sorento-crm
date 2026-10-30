# UAC SAMPLE-FROM-QUOTE: a sample request starts from the project's quotation

Card: `CARD-sample-from-quote-29oct.md`. Plan: `PLAN-sample-from-quote-29oct.md`. Owner answers 30 Oct ~00:30:
Q1 a, Q2 a, Q4 a, Q5 a, Q6 a (staff form too), Q7 a (discontinued pre-fills as-is); Q3 pending, behind a switch.

## Backend (pre-fill read)

- **SFQ-1** A project with no quotation document answers `documents: []`, `lines: []`, `skipped: []`.
- **SFQ-2** A never-issued document pre-fills from each scope's CURRENT version (MAX version_no), scopes in
  `sort_order`, lines in `sort_order`; `issue_id` is null.
- **SFQ-3** An issued document pre-fills from the latest issue (MAX issue_no), using the version each scope
  had IN THAT ISSUE (`quotation_issue_scopes.version_id`), not the scope's current version.
- **SFQ-4** A product-set line contributes its parts' products (`set_parts_snapshot`), in part order.
- **SFQ-5** The same product appears once (first occurrence wins), across scopes and set parts.
- **SFQ-6** A line with no product (free text) is not a line; it is listed in `skipped` with reason
  `no_product` and its description. An inactive product is listed in `skipped` with reason `inactive`.
- **SFQ-7** A discontinued but active product pre-fills like any other.
- **SFQ-8** With several documents, `documents` lists them (issued ones first, newest issue first, then
  never-issued newest first), each with a human label (`<document no> (R<n>)` or `<document no> (not issued)`);
  the default is the first; `document_id` picks another. A `document_id` of another project is 422
  `SAMPLE_REQUEST_QUOTATION_INVALID`.
- **SFQ-9** No prices leave the read: a line carries product id, code, name and brand only.
- **SFQ-10** Staff route requires `projects.sample_requests.create` (403 without). An unknown or unapproved
  project is 422 `SAMPLE_REQUEST_PROJECT_INVALID`, the same answer the request write gives; a project outside
  a limited user's own projects is refused by the projects router's own-scope guard (404) before that. Through
  `/api/v1/my-requests` the same user gets 422 `SAMPLE_REQUEST_PROJECT_NOT_ALLOWED`, and the read needs `.create`.
- **SFQ-11** Portal route answers only for a project `assert_portal_project_allowed` accepts; any other is 422
  `SAMPLE_REQUEST_PROJECT_NOT_ALLOWED`.

## Backend (source recorded, Q5)

- **SFQ-12** Create / update accept `quotation_document_id` and `quotation_issue_id`; the detail returns both
  plus `quotation_ref` (the same label as SFQ-8).
- **SFQ-13** A document that is not the request's project's, or an issue that is not that document's, or an
  issue without a document, is 422 `SAMPLE_REQUEST_QUOTATION_INVALID` (field `quotation_document_id`).
- **SFQ-14** Migration is additive: two nullable FK columns, `ON DELETE SET NULL`; existing rows untouched.

## Frontend (both forms: the shared portal form and the staff form)

- **SFQ-20** New request, project set (URL seed or picker), item list untouched: rows = the pre-fill lines, qty 1,
  no remark; the source document and issue are recorded in the form state.
- **SFQ-21** Editing an existing draft never pre-fills.
- **SFQ-22** Project changed: untouched pre-filled rows are replaced by the new project's; edited rows stay and
  the source is cleared. A loaded draft whose project changes drops its recorded source too (the rows stay).
- **SFQ-23** Each pre-filled row has the existing Remove line control; Add item still adds a blank row.
- **SFQ-24** More than one document: a quotation picker above the items, defaulting to the first; picking another
  replaces untouched rows. Once the rows are edited the picker is not offered.
- **SFQ-25** Owner Q3 (30 Oct ~21:15, "free text product shouldn't be allowed"): a quotation line with no catalogue
  product never becomes a row; it is left out and counted in one muted line under the items, as an inactive
  product is. No switch.
- **SFQ-26** The request page shows the source quotation (read-only) when one is recorded.
- **SFQ-27** Owner hand test 30 Oct ("when I add the product it must source from the product in the quotation"):
  while a request carries its source quotation, the line product search (staff, portal, My Requests) offers only
  that quotation's catalogue products (set parts included); an empty search lists them all. A portal or My Requests
  search names only a quotation of a project the contact may pick (the SFQ-11 rule, plus the own-project rule for
  a limited user). Without a source the search is the catalogue, unchanged.
- **SFQ-28** Create / update with a source quotation refuse a line product that is not on it: 422
  `SAMPLE_REQUEST_PRODUCT_NOT_ON_QUOTATION` (field `lines`).
