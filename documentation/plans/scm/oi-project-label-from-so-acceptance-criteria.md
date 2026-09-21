# UAC: Order inquiry Project column and handover email read the sales order's project label

Plan: `PLAN-oi-project-label-from-so.md`. Track: small fix.

Setup for every AC: an adopted `ProjectSalesOrder` (`status='adopted'`, `project_id=None`,
`so_id` set) whose core `SalesOrder` has `project_label='KITACON / PHASE 6A'`,
`project_label_source='inquiry'`, and an `OrderInquiry` + one `OrderInquiryRow` raised
against it. Seed the whole chain in the test; never `LIMIT 1` off an existing table.

- **AC-1 worklist Project cell.** `GET` the worklist (the route
  `tests/test_order_inquiry_worklist.py` already exercises): the row's `project_title` is
  `KITACON / PHASE 6A` and `project_customer` is `<customer> / KITACON / PHASE 6A` (or
  `KITACON / PHASE 6A` when the order has no resolvable customer).
- **AC-2 registered project wins.** Same row shape but `project_id` set to a `Project`
  titled `TUJU RESIDENCE` and the core SO still carrying `project_label='KITACON / PHASE
  6A'`: `project_title` is `TUJU RESIDENCE`.
- **AC-3 search.** `query=KITACON` on the worklist returns the adopted row; `query=ZZZNOPE`
  does not.
- **AC-4 sort and filter column.** `sort=project_title` orders the adopted row by its label
  (two adopted rows, labels `ALPHA` and `BETA`, come back in that order asc).
- **AC-5 handover email facts.** `_handover_order_facts(pso.id)["project"]` is
  `KITACON / PHASE 6A` for the adopted order; `TUJU RESIDENCE` when a project is registered.
- **AC-6 per-project inquiry label.** `_project_customer_labels({pso.id})[pso.id]` ends
  with `KITACON / PHASE 6A` for the adopted order.
- **AC-7 no label anywhere.** Adopted order with `project_label=None` and no project:
  `project_title` is `None` (the FE prints `No project`); nothing raises.
- **AC-9 adopted order still hands to purchasing.** With one active user holding a
  `purchasing%` role, raise an inquiry on the adopted order (no project) and commit: a
  `notifications` row of `event_type='project_order_inquiry_raised'` exists for that user,
  body starts with `KITACON / PHASE 6A:`, `data.project_id` is `None`, `data.sales_order_ref`
  is the SO number; no `ProjectTask` row was created (`task_for(inquiry.id)` is `None`).
- **AC-10 no label and no project.** Same as AC-9 with `project_label=None`: the body
  starts with the SO reference; nothing raises.
- **AC-11 registered project unchanged.** Order with a `Project`: `ProjectTask` created
  as before and the body starts with the project title.
- **AC-12 one notification per header.** Raising twice on the same adopted header in one
  transaction queues one payload; a second commit later creates no second notification row
  for the same user (dedup key `{inquiry_id}:order_inquiry_raised`).
- **AC-8 browser.** Worklist row for an adopted order prints the SO's project label in the
  Project column, at 1280 and 375 (screenshot under
  `documentation/plans/scm/evidence/oi-project-label-from-so/`).

## Section 5: Project filter follows the Project column

- **AC-13 facet lists labels.** Summary `projects` facet for a view holding adopted rows
  labelled `ALPHA` (2 rows) and `BETA` (1 row) plus one row on a registered project
  `TUJU RESIDENCE`: three options, `{id: 'ALPHA', label: 'ALPHA', rows: 2}`, `BETA`,
  `TUJU RESIDENCE`, ordered by label. A row with neither is not an option.
- **AC-14 filter by text.** `project=ALPHA` on the list returns exactly the two ALPHA rows;
  `project=TUJU RESIDENCE` returns the registered-project row; `project=alpha` (wrong case)
  returns none (exact match).
- **AC-15 facet ignores its own filter.** With `project=ALPHA` applied, the `projects` facet
  still lists all three options.
- **AC-16 every entry point honours it.** Summary counts, the matrix, and the export
  with `project=ALPHA` cover only ALPHA rows.
- **AC-17 bulk scope honours it.** The acknowledge-scope and unplace-all preview bodies with
  `project: 'ALPHA'` count only ALPHA rows, never BETA's.
- **AC-18 `project_id` unchanged.** `project_id=<uuid>` still filters by registered project
  and a non-UUID value is still rejected the way it is today.
- **AC-19 frontend (vitest).** Picking an option in the Project filter sends
  `project=<label>` and no `project_id`; a stored blob holding only `project_id` restores to
  no project filter; clearing the filter drops the param.
- **AC-20 browser.** Filters > Project lists labels, searching `KITACON` finds the option,
  picking it narrows the list to those rows and the row count changes; clear restores. 1280
  and 375.
