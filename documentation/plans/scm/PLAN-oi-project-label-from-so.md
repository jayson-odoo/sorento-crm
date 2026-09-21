# PLAN: Order inquiry Project column and handover email read the sales order's project label

Status: in progress, draft PR #1084. Sections 1-4 reviewed + browser passed 21 Sep 2026; section 5 (Project filter) building. Track: started as small fix, section 5 adds a query param and a frontend change.
Branch: `fix/oi-project-label-from-so` (worktree `sorento_crm-oi-project-label`, off origin/main 170d6ece3)
UAC: `oi-project-label-from-so-acceptance-criteria.md`

## Problem (measured 21 Sep 2026, prod-copy)

The order inquiries worklist prints `No project` on every row raised against an AutoCount
sales order (12,834 rows, page 1 all `No project`), and the handover email to purchasing
carries no project either. The sales order detail for the same order (SO414347) prints
`KITACON / PHASE 6A & 6B@BDR TSK PUTERI · Inquiry sheet`.

Two "project" fields exist and the inquiry surfaces read the wrong one:

- `projects.projects.title` via `ProjectSalesOrder.project_id`. NULL by design for every
  adopted AutoCount order (`project_so_adoption_service.py` `_insert_record`,
  `project_id=None`; `project_so.py` "no project registration, inventing one would put 605
  registrations nobody asked for into the pipeline").
- `sales_orders.project_label` (core table, free text, `app/models/order.py`), resolved by
  `app/services/project_label_rules.py` from the inquiry sheet cell > AutoCount note >
  AutoCount Ref > delivery address. This is what the SO detail shows.

The worklist query already outer-joins core `SalesOrder` (to reach the sales agent) and
never selects `project_label`. Same in `_handover_order_facts` and `_project_customer_labels`
in `project_order_inquiry_service.py`.

## Fix (one rule, three readers)

Project text for an inquiry row = `coalesce(Project.title, SalesOrder.project_label)`. A
registered project wins; an adopted order falls back to the label the SO detail already
prints. No migration, no new endpoint, no schema change (`project_title` /
`project_customer` / handover `project` keys keep their names and types).

1. `app/services/order_inquiry_worklist_service.py`: a module-level `_PROJECT_TITLE =
   func.coalesce(Project.title, SalesOrder.project_label)`; use it for the `project_title`
   sort/filter column and select, inside `_PROJECT_CUSTOMER`, and in the free-text search
   `or_` (alongside the existing `Project.title.ilike`).
2. `app/services/project_order_inquiry_service.py` `_handover_order_facts`: select
   `SalesOrder.project_label` too (the `SalesOrder` join is already there) and set
   `"project": title or project_label`.
3. `app/services/project_order_inquiry_service.py` `_project_customer_labels`: same
   fallback before calling `project_customer_label`.

Frontend: no change. `orderInquiryWorklistColumns.tsx` already prints `project_title` and
falls back to `No project` only when both sources are empty.

## 4. Hand to purchasing whether or not there is a project (owner ruling, 21 Sep 2026)

`_hand_to_purchasing` returned before creating the purchasing task and the in-app
notification when `order.project_id` is NULL, so every adopted order got only the handover
email. Owner: "whether got project or not should also hand to purchasing".

- `tasks.project_id` is NOT NULL and a task only surfaces under its project's Tasks tab, so
  a project-less task has nowhere to appear. No migration: for an order without a project
  the `ProjectTask` is skipped and the in-app notification is still queued.
- `_notify_purchasing` takes `project: Optional[Project]` and a `project_label`; the body
  leads with `project.title`, else the SO's `project_label`, else the SO reference.
  `data.project_id` / `data.project_code` are `None` when there is no project.
- Duplicate guard without a task: the notification service dedupes on
  `(user, source_entity_type, dedup_key, event_type)` with
  `dedup_key = f"{inquiry_id}:order_inquiry_raised"` (`uq_notification_user_dedup_event`),
  and that is the ONLY guard. A pending-queue check inside the savepoint was measured dead
  (review, 21 Sep): `after_commit` fires on the `begin_nested()` release inside
  `_hand_to_purchasing` itself and drains the queue before any second caller could see it.
- The label read here is the same `SalesOrder.project_label` as readers 1-3; one query on
  `order.so_id`, only on the no-project branch.

## 5. Project filter follows the Project column (owner ask, 21 Sep 2026)

Measured on the prod-copy clone: 515 distinct labels across 12,716 inquiry rows, and ZERO
inquiries on a registered project, so the Project filter dropdown is empty today.

The filter answers "show me this project's rows", and the project is the text the column
prints. So the filter works on that text; no id encoding, no second concept.

- Backend: a new optional text filter `project` on every worklist entry point that takes
  `project_id` today (list, summary, export, matrix, and the BODY scopes of the bulk
  actions: acknowledge scope, unplace all preview and apply). It filters
  `_PROJECT_TITLE == project` (exact match) in `_base`. A bulk action that ignored it would
  act on rows outside the view, so the body schemas carry it too.
- `_projects()` groups by `_PROJECT_TITLE` (non-null), returns `{id: <text>, label: <text>,
  rows}` ordered by label, and is computed with `project` cleared (as it clears
  `project_id` today).
- `project_id` stays as it is (UUID-validated) for any existing deep link; the dropdown no
  longer sends it.
- Frontend: the Project filter sends `project=<text>`; the stored filter blob key becomes
  `project` (a stored `project_id` from before is ignored). Types and the two services
  (`orderInquiryService.ts`, `orderInquiryMatrixService.ts`) gain `project`.

## Known, not fixed here

- Pre-existing: the purchasing notification commits on a fresh session at the savepoint
  release, before the caller's outer commit, so a later rollback can leave a notification
  pointing at an inquiry that no longer exists. Same shape as before for project-bearing
  orders; this fix extends it to adopted orders (730 of 740 project-less orders on the 0918
  copy carry a label).

## Verification

- pytest: new `tests/test_oi_project_label_from_so.py` (AC-1..AC-5) plus the touched
  files `tests/test_order_inquiry_worklist.py`,
  `tests/test_order_inquiry_worklist_search_tokens.py`,
  `tests/test_order_inquiry_handover_automation.py`, `tests/test_project_order_inquiry.py`.
- Browser: worklist row for an adopted order prints the SO's project label (on a stack
  already up).
