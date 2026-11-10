# PLAN: RELEASE-FIX-PORTAL - own-scope guard learns the quotation autosave / history / payment-terms routes

Status: PR #2327 open, reviewer READY + security-reviewer CLEAN; awaiting CI and merge (crew size S, security). Release blocker for the 11 Nov CRM release.
UAC: `release-fix-portal-11nov-acceptance-criteria.md` (alongside).

## Problem (measured on main 6e6657e261)

`tests/test_portal_p2_own_scope_projects.py` fails twice on main:

1. `test_every_project_id_route_is_404_for_a_foreign_project`:
   `GET /projects/{project_id}/quotation-documents/{document_id}/history/{entry_id}` answers **403**
   "Not available with access to your own records only." to a limited (`view_own`) user on another
   salesperson's project, instead of the standard own-scope **404**. The 403 tells them the route
   exists and is merely closed, and the same refusal hits them on their OWN project, so the History
   entry and Restore are dead for every limited user.
   Cause: `_own_scope.classify` refuses any route whose second-or-later id is not named in
   `_NESTED["projects"]` (`app/api/v1/projects/_own_scope.py`, `_NESTED`), and `entry_id` is not there.
   Affected: `GET .../history/{entry_id}` (`quotation_documents.py:556`) and
   `POST .../history/{entry_id}/restore` (`quotation_documents.py:577`), both from #2303.
2. `test_every_route_a_limited_user_reaches_is_pinned`: 10 routes a limited user reaches are not in
   `tests/portal_p2_allowed_routes.txt`:
   - #2303 QUOTE-AUTOSAVE: `POST .../new-draft/open` (:216), `GET .../new-draft/holder` (:236),
     `PUT .../new-draft` (:255), `POST .../{document_id}/form-draft/open` (:458),
     `GET .../{document_id}/form-draft/holder` (:480), `PUT .../{document_id}/form-draft` (:501),
     `GET .../{document_id}/history` (:536)
   - #2305 QUOTE-TERMS-SELECT: `GET /projects/{project_id}/quotation-documents/payment-terms` (:298),
     `GET /config/quotation-templates/payment-terms` (`quotation_templates.py:68`, reference prefix `/config/`)
   - #2299 STANDARD-HISTORY: `GET /order-inquiry-headers/{inquiry_id}/history` (`order_inquiries.py:2069`,
     cross-project screen, `_OWN_PERMISSION_PREFIXES`)

## Is trusting `entry_id` safe? (the review question)

Yes, by the same rule as every other `_NESTED` name: the route loads the entry under its parent.
Both routes call `svc.get_document_or_404(db, project_id, document_id)` (document under the project
the guard already resolved), then `drafts._entry_or_404(db, document, entry_id)`
(`app/services/quotation_form_draft_service.py:388-396`), which lists `QuotationDocumentSnapshot`
rows filtered on `document_id == document.id` and 404s `quotation_history_not_found` for any other
id. A foreign entry id under their own project and document is a 404 from the route itself.

## Architecture

- Layer: backend router-level dependency only (`project_own_scope_guard`). No FE, no schema, no migration.
- Mechanism: add `"entry_id"` to `_NESTED["projects"]` with the file:line justification in a comment,
  exactly like `certificate_id` / `sheet_id`. Nothing else in the guard changes.
- Pin: regenerate `tests/portal_p2_allowed_routes.txt` with the 12 routes (10 above plus the two
  `{entry_id}` routes the fix opens), after checking each scopes its ids (table above).
- The other 8 quotation routes already pass the guard (`document_id` is nested and every one loads
  the document via `get_document_or_404(db, project_id, document_id)` or works on the caller's own
  `new_draft(db, project.id, user_id)`), so they only need pinning and tests.

## Tests (red first)

New `tests/test_portal_p2_quotation_autosave_own_scope.py`, on the shared `scene` fixture:

- in scope: a limited user on their own project walks open -> holder -> autosave -> history list ->
  entry -> restore, new-draft open -> holder -> autosave, payment terms; each 200 with the right data.
- out of scope: every one of the 10 project routes on another salesperson's project is 404 with the
  guard's "Not found" and writes no draft row.
- nested ids: their own project with another project's document is 404; their own document with
  another document's history entry is 404 `quotation_history_not_found` (read and restore).
- unauthenticated: 401/403 as today for every route.
- the two id-less / cross-project routes are not refused by the guard (their own slug answers).

Kill test: drop `entry_id` from `_NESTED` and the in-scope entry / restore and out-of-scope tests fail.

## Out of scope

Quotation printing, the agent, migration tests and the global guard-list tests (other lanes).
