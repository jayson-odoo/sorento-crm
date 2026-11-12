# PLAN: project related records (SI, complaint, purchase request, sponsorship form, NPA, OCN)

Status: Q1-Q4 = (a) (crew 12 Nov), D1-D3 decided by the owner 13 Nov; mock v3 filed; waiting on the owner's OK on the mock. No product code before it. Track: L (migration: nullable project_id on SI and NPA). Lane PROJECT-RELATED-RECORDS, PR #2383.

Card: `CARD-project-related-records-12nov.md`. UAC: `project-related-records-12nov-acceptance-criteria.md`. Mock: `documentation/mockups/project-related/index.html`.
Q1-Q4 = (a). D1 = reviewed list, D2 = editable any time, D3 = optional.

## Reuse (no second copy)

| Need | Reuse | How |
|---|---|---|
| Project read + own scope | `require_any_permission(READ)` (`api/v1/projects/projects.py:53`), router guard `api/v1/projects/_own_scope.py` | as is; add the new route to `tests/portal_p2_allowed_routes.txt` |
| Per-type visibility | `own_scope.request_access`, `request_clause`, `npa_clause`, `me` (`services/own_scope.py:106,187,216,237`) | as is |
| Row list pattern | `sponsorship_link_service.list_sponsorships` (`:152`) | new service follows it; sponsorship endpoint stays (rollup + existing callers) |
| Link check | `project_service.assert_linkable_project` (`:185`) | as is, for SI and NPA |
| Portal project list | `sponsorship_link_service.projects_for_contact` + `assert_project_requirement` ownership half | as is |
| FE grid | `components/common/PanelDataGrid.tsx` (`serverSorting`), `SponsorshipsPanel.tsx` as template | new `RelatedRecordsPanel.tsx` |
| FE helpers | `buildDataGridParams`, `formatDate`, `statusPillClass`, `formatMyr`, `SearchableMultiSelect` | as is |
| FE project picker | `useProject` / `projectCodeLabel` (`PurchaseRequestForm.tsx:70-71,784`) | extract to one shared `ProjectLinkPicker` if PR and complaint pickers duplicate it; SI/NPA use it |

## Slices (one lane, commits on this branch)

1. **Migration** `400_si_npa_project_link` (id <= 32 chars, reparented with `scripts/alembic-reparent.sh`): nullable `project_id` UUID FK `projects.projects.id` ON DELETE SET NULL + partial index `WHERE project_id IS NOT NULL` on `stock_inquiries` and `new_product_applications`. Additive; timed on a dev copy.
2. **BE link**: portal complaint + purchase request forms gain the project picker too (only the portal SF has it today, `SubmissionForm.tsx:397`; the cause of 0 of 448 / 0 of 81 linked). Models, schemas (create/update/response incl. `project_code`, `project_title`), services call `assert_linkable_project` on change; portal paths check the contact's companies; NPA from SI inherits; Project field editable on closed/approved records by whoever may edit the record, approval untouched, audited (D2).
3. **BE related endpoint**: `services/project_related_records.py` with `RELATED_TYPES` registry and `register_related_type()`; `GET /api/v1/project-sales/projects/{project_id}/related-records?type=&status=&query=&sort=&dir=&page=&limit=` returns `ListResponse[RelatedRecordRow]` + `type_counts`; one `UNION ALL`, sorted and paged in SQL; limit capped per `test_list_pagination_limit.py`.
4. **FE**: `relatedRecordTypes.ts` registry; `RelatedRecordsPanel.tsx`; tab swap + legacy `?tab=sponsorships`; hook in `useProjects.ts` + `projectService.ts`; SI and NPA form pickers and detail display.
5. **D1 review sheet**: `sorento_crm_backend/scripts/project_link_review.py` with `--export` (read-only; exact title match to exactly one approved project of the same company; xlsx in the shared Excel style) and `--apply <ticked file>` (writes only ticked rows through the same service call the record page uses, so History logs each). Crew runs it; never run by the lane against any shared DB.
6. **Assistant**: registry entry for the related-records route (`app/services/assistant_registry/`) + 2 eval prompts.
7. **User guide**: project page guide + SI and NPA guides under `documentation/user-guides/`.

## Test list (tester writes red first)

BE (`tests/test_project_related_records.py`, `tests/test_si_npa_project_link.py`):
- rows of all five types linked to project P appear; unlinked and other-project rows do not (AC-A3)
- sort by each column asc/desc stable across pages; search; type and status multi-filters (AC-A4..A6)
- user with no complaint permission: no complaint rows, no complaint type count (AC-B2)
- view_own user: only rows with their contact / NPA applicant (AC-B2)
- company B project + its records invisible to company A user (404) (AC-B1, B3)
- fake sixth type registered in the test appears (AC-D1)
- SI/NPA create with approved project ok, unapproved refused 422, portal foreign-company project refused (AC-C2, C3)
- NPA from SI inherits project (AC-C4); project_name never fills project_id (AC-C5)
- closed SI: project-only change allowed and audited (AC-C6)
- guards: `test_schema_uuid_id_principle.py`, `test_list_pagination_limit.py`, `test_portal_p2_own_scope_projects.py`
FE (vitest): panel renders rows/columns/empty state, row click href per type, Type filter shows only permitted types, `?tab=sponsorships` maps to related + filter, sixth fake type renders from the registry.

## Kill tests
Remove the `request_access` filter -> B2 tests fail; drop the project_id predicate on one type -> A3 fails; drop company scope (project 404) -> B3 fails.
