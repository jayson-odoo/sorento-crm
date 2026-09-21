# PLAN: Order inquiry Project column and handover email read the sales order's project label

Status: in review, draft PR (Track: small fix). Browser AC-8 passed 21 Sep 2026 on :3080 / :8080.
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

## Known, not fixed here

- The Project filter dropdown (`_projects()`) still lists registered projects only, so it
  cannot offer a label the column now prints. `project_id=` is the filter's contract; a
  label filter is a separate ask.
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
