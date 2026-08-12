# PLAN - Linked complaints on root cause / resolution + complaint list filters

Status: DONE (2026-07-31) - browser-verified; all AC met. Uncommitted.

## Journey

**Actor:** CS / quality staff reviewing complaint patterns, arriving from the sidebar.

1. Opens **Complaint Management -> Root Causes**. Each row already shows a Complaints count. The count is currently a dead end: you can see "Manufacturing Defect: 6" but not *which* 6.
2. Two ways forward, both wanted:
   - **Click the count chip** -> dialog lists those complaints, each a hyperlink. Fast peek without leaving the list.
   - **Click the row** (the chevron already implies it) -> dedicated detail page: the root cause's own fields plus the full linked-complaints grid, deep-linkable and shareable.
3. From either surface, clicking a complaint lands on `/complaint-management/complaints/{id}`.
4. Reverse direction: on **Complaints**, the Filters popover gains **Root cause** and **Resolution** multi-selects, so "show me everything caused by Manufacturing Defect or Packaging Faulty" is one query.

Nothing new is asked of the user: the links are derived from `complaints.root_cause_id` / `complaints.resolution_id`, which already exist and are already indexed.

## Decisions (confirmed with user 2026-07-31)

- Linked complaints appear on **both** a dedicated detail page **and** a dialog off the count chip.
- Root cause / resolution filters are **multi-select** (OR within each field, AND across the two).

## Contract

`GET /api/v1/complaints-management/complaints`
- new query params: `root_cause_ids`, `resolution_ids` - comma-separated UUIDs
- semantics: `root_cause_id IN (...)` AND `resolution_id IN (...)`; omitted/blank = no constraint
- unchanged response shape; combines with existing `query` / `assigned_to` / `status` / sort / paging

Master-data detail GETs already exist and are reused as-is:
`GET /complaint-management/complaint-root-causes/{id}`, `.../complaint-resolutions/{id}` (both carry `complaint_count`).

## Acceptance criteria

- AC-1 Root cause list: clicking the count chip opens a dialog listing that root cause's complaints; each row hyperlinks to the complaint detail.
- AC-2 Root cause list: clicking the row navigates to `/complaint-management/complaint-root-causes/{id}`.
- AC-3 Detail page renders name, description, active state, count, AND the linked-complaints grid - the grid section renders even at zero, with an explicit empty state (ADR: never hide a section).
- AC-4 Same for resolutions, sharing one component (no duplicated panel per domain).
- AC-5 Complaints Filters popover has Root cause + Resolution multi-selects; active count includes them; Reset clears them.
- AC-6 Selecting two root causes returns complaints matching either.
- AC-7 Filters compose with search + status + assignee.
- AC-8 Zero UUIDs shown in the UI; complaints render by complaint number.

## Files

BE
- `app/services/complaints_service.py` - `_build_list_query` + `list_complaints` gain `root_cause_ids` / `resolution_ids`
- `app/api/v1/complaints/complaints.py` - list route parses the two comma-separated params

FE
- `app/(protected)/complaint-management/_shared/LinkedComplaintsPanel.tsx` - grid, shared by both detail pages
- `app/(protected)/complaint-management/_shared/LinkedComplaintsDialog.tsx` - chip dialog, wraps the same query
- `complaint-root-causes/[id]/page.tsx`, `complaint-resolutions/[id]/page.tsx` - detail pages
- `complaint-root-causes/components/ComplaintRootCausesList.tsx`, resolutions equivalent - row click + chip
- `complaints/components/ComplaintsList.tsx` - two multi-selects
- `complaints/services/complaintService.ts`, `hooks/useComplaints.ts` - pass the ids through

## Tests

- pytest: filter by one id, by two ids (OR), by both fields (AND), invalid id -> empty not 500, composes with status
- vitest: panel data/empty states, dialog opens with the right query key, filters update active count + reset
- Playwright: sidebar -> Root Causes -> chip dialog -> detail page -> complaint; Complaints -> Filters -> multi-select
