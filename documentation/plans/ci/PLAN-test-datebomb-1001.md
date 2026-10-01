# PLAN: date-dependent tests blocking release (TEST-DATEBOMB-1001)

Status: in progress. Small fix track (tests only unless the stock-debt check proves a service bug).

## Problem

Release run 36798275466 (main 757b41da) failed full backend suites once the date rolled to
2026-10-01. Three tests depend on the wall clock:

1. `tests/scm/test_purchase_trend.py::test_the_endpoint_serves_it_and_rbac_holds` - POs
   hard-coded in Jun/Jul 2026, service windows off `date.today()`.
2. `tests/test_cost_price_apply.py::test_apply_writes_one_cost_row_per_line_with_set_dates_and_source`
   - a "future" `start_date` of 2026-10-01 is now today.
3. `tests/scm/test_stock_debt_lendable_routes.py::test_the_cell_value_is_the_same_with_and_without_date_to`
   - 0.0 == 38.0 on 2026-10-01. Must decide first: real Stock Debt bug at a month boundary, or
   a test-only date bomb.

## Plan

- Reproduce each with the date frozen at 2026-10-01 (and other month starts for 3).
- 3: verdict with file:line; red-first service fix if real, else fix the test.
- 1, 2: make the dates relative to today / pin the date; never loosen an assertion.
- Grep tests for other hard-coded 2026-10 / 2026-11 "future" dates.

## UAC

- The three tests pass on 2026-10-01 and on any other day (checked with a frozen clock at
  several month starts and mid-month).
- No assertion is weakened.
