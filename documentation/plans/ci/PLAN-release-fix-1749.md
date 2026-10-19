# PLAN: fix forward the 20 Oct release failures from #1749 (RELEASE-FIX-1749)

Status: implemented (PR #1791). Small fix track: tests plus one service call (`_record_cancel` in
`_keep_split_rows`), no migration, no RBAC change in product code.

## Problem

Release run 39288462357 (full_suite, main 9e97c340c6) failed in three places.

1. SCM shard, xdist worker gw1: five RBAC "denied" tests got 200/404 for a user with no
   permission (`test_fulfilment_priority_policy::test_rbac_denied_without_manage`,
   `test_coverage_routes::test_a_principal_without_the_view_permission_is_denied_before_any_work`,
   `test_container_request_document::test_the_document_requires_the_read_permission`,
   `test_customer_orders_route::test_denied_without_dashboard_view`,
   `test_cover_sources_endpoint::test_cover_sources_rbac_denied_without_view`).
   Cause: `tests/scm/test_line_splits_api.py:206` and `:411` (#1749) call
   `monkeypatch.setattr(UserPermissionService, "check_user_has_permission", ...)` on top of the
   `api` fixture (`tests/test_planning_change_apply_on_board.py:154`), which already swapped in
   an always-true stub (`tests/test_planning_changes.py:195`) and restores the real method in its
   own `finally` (`:204`). `monkeypatch` is set up first by the autouse
   `_no_live_external_calls` (`tests/conftest.py:469`), so it tears down LAST and puts back the
   value it saw at `setattr` time: the always-true stub. Every later permission check on that
   worker passes.
2. Shard 8: `tests/test_planning_why_cancel_cause.py::test_no_service_cancels_an_inquiry_row_without_recording_the_cause`
   and `::test_every_cancel_assignment_in_the_services_is_followed_by_its_record`.
   `_keep_split_rows` sets `other.state = INQUIRY_CANCELLED`
   (`app/services/project_order_inquiry_service.py:6208`) with no `_record_cancel(`.
3. Shard 10: `tests/test_sales_achievement_perf.py` `[delivered]` timing stall (2.10 s vs 1.0 s).
   One-off runner load; no change.

## Fix

1. The two tests assign `UserPermissionService.check_user_has_permission` directly; the `api`
   fixture's restore puts the real method back. Backstop in `tests/conftest.py`: the
   `_STUBBABLE_SYMBOLS` backstop also restores that class attribute, and it moves from an autouse
   fixture to `pytest_runtest_setup`/`pytest_runtest_teardown` wrappers: as a fixture it tore down
   before `monkeypatch` (conftest fixtures register in name order), so it could not catch this
   leak (kill run 2 showed the RBAC tests still failing with only the backstop in place). The
   next leaked stub of it cannot reach another file.
2. `_keep_split_rows` takes the caller's `actor_user_id` (from `refresh_for_decision`) and
   records each folded row: `_record_cancel(self.db, other, "superseded", actor_user_id=...,
   decision=decision)` ("superseded" is already labelled in `PlanningHistorySheet.tsx:44`).

## Tests

- New: `test_joining_a_split_lines_rows_records_one_superseded_cancel_by_the_actor`.
- Red on main, green after: the two guard tests, the five RBAC tests in one xdist run where
  `test_line_splits_api.py` runs before them on the same worker.
