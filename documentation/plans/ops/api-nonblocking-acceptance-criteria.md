# API-NONBLOCKING acceptance criteria

Plan: `PLAN-api-nonblocking-28oct.md`. No behaviour change: no response, status code, header or
permission changes.

- **AN-1** While a slow report / export / PDF request runs, a light request on the same worker
  (`/health`) answers. `tests/test_api_nonblocking.py::test_a_slow_report_does_not_freeze_the_worker`
- **AN-2** An upload that imports a file does its parse and DB work off the event loop.
  `tests/test_api_nonblocking.py` (upload cases)
- **AN-3** `/health`'s DB check does not hold the event loop.
  `tests/test_api_nonblocking.py` (health case)
- **AN-4** No mounted route is `async def` without an await, except an allow-listed one with a
  reason. `tests/test_no_blocking_async_routes.py`
- **AN-5** Converted report/export handlers return the same bytes / JSON as before on the same
  seeded data. Evidence in the PR (script + result).
- **AN-6** Full backend + SCM suites: no new failure against main.
