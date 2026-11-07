# PLAN: CRM ingest names every dropped document line (INGEST-DROP-WARN-CRM)

Status: in review, small fix track (backend only, no migration, no auth/RBAC, no new ingest surface). PR #2175.

CRM half of INGEST-LINE-DROP-GUARD; the SS half merged as SS #199.

## Problem

`DocumentIngestService._apply` (`sorento_crm_backend/app/services/document_ingest_service.py`)
catches `MissingReference` for a sales/purchase order line and only counts it
(`lines.dropped`). Since the 3 Oct PRODUCT-REF-COLLISION ruling products match by code only
(`master_ref_resolver.py`, `_resolve_master` Product branch), so a line with no
`product_code` is always dropped, with nothing in the reply or the log saying which line or why.
Found 4 Nov: a v1 SS connection stripped `product_code` and all 4 FXT test lines were dropped silently.

## Change

- `master_ref_resolver.py`: `WARN_LINE_PRODUCT_UNRESOLVED = "line_product_unresolved"` and
  `line_product_unresolved_warning(doc_no, line_ref, line_no, product_code)`.
- `document_ingest_service.py` drop handler: appends one entry per dropped line,
  `line_product_unresolved:doc=<number>:line_ref=<source_ref>:line_no=<line_number>:product_code=<code>`
  (blank values stay blank). `lines.dropped` unchanged.
- `app/api/v1/external/ingest.py::_log_record_outcomes`: a landed record that dropped a line
  also gets its `ingest.record` line, with those warnings (max 20 per line, then `+N more`).
- `contract.py` `WARNINGS` and `PLAN-autocount-cross-repo-contract.md` list the new prefix.

No UI.

## Tests

`tests/test_ingest_documents.py::TestUnresolvedReferences`: a line with no product_code, a line
with an unknown code (two lines, two entries), a clean document with no such warning.
