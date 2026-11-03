# PLAN: RELEASE-FIX-3NOV, main-red tests blocking the 3 Nov release

Status: in progress. Track: small fix (test-only, no migration, no product code).

## Problem

Release run 41621609504 (deploy.yml, full suite, main 016d68239d) failed 56 backend tests.

1. 55 fail with 422 `quotation_discount_pending_approval`. #2096 (PS-QUOTE-RULES, 75032d481c)
   made any line priced below its default price (series selling price, else the list price
   snapshot) a discount that needs a routed approval before Issue
   (`app/services/project_quotation_service.py:754-755`, gate
   `app/services/project_quotation_approval_service.py` `assert_issuable`). These seven files
   seed products at list price 300.00 (or 100.00) and price lines below it, then issue:
   `test_project_quotation_excel.py`, `test_project_quotation_changes_requested.py`,
   `test_project_quotation_export_downloads.py`, `test_quotation_lines_grid.py`,
   `test_quotation_form_save.py`, `test_project_quotation_images.py`,
   `test_project_spec_sheet.py`. #2096 fixed the four files it touched the same way, one
   constant per file (`FIXTURE_LIST_PRICE = "1.00"`).
2. `test_portal_p2_own_scope_projects.py::test_every_route_a_limited_user_reaches_is_pinned`
   fails on the new route `GET .../spec-sheet/page-images` (#2126).

## Fix

1. One shared constant module, `tests/_quote_fixture_prices.py`: the list price a quotation
   fixture product carries so no line it prices is a discount unless the test says so, with the
   reason. Each failing file's product factory reads it. The product rule is untouched; the
   tests that exercise the rule (`test_ps_quote_rules.py`, `test_project_quotation_approval*.py`)
   keep their own prices.
2. Pin the page-images route in `tests/portal_p2_allowed_routes.txt`. A limited user reaches it
   on the same terms as the pinned `GET .../spec-sheet` and `.../spec-sheet/preview`: same `READ`
   dependency, same `_document` (document filtered by `project_id`) and `_issue` (revision
   filtered by document) in `app/api/v1/projects/spec_sheet.py:181-196`, and the service returns
   only a visible page of that issue (`app/services/project_spec_sheet_service.py:665-676`).

## Verification

The eight files plus every test file that issues a quotation, and the `tests/test_project_*` +
`tests/test_quotation_*` slice, on a throwaway Postgres DB (`-n 2`). Red proof: the same tests on
main 016d68239d. Kill proof: revert the shared price, the same tests fail again.
