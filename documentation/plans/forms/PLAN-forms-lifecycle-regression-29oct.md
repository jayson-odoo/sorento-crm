# PLAN: Forms lifecycle regression suite (FORMS-REGRESSION, Part A)

**Status:** Building. Small fix track by process (test-only, no migration, no product code), M by effort.
**Domain:** forms / procurement / complaints / sla
**Owner ask (29 Oct 2026):** "do we have a regression test for end to end flow of submission of forms,
rejection, revision, save as draft, including all the outbox, extension, undo, revert, handle,
escalation? I just need you to make sure these still work."

## Scope

Test-only. No product code changes: a test that exposes a real bug is reported as a crew-note with
the red test, not fixed silently.

1. API chain tests (FastAPI TestClient on Postgres, every test seeds its own data) per form kind:
   complaint, stock inquiry, purchase request, sponsorship form, sample request, price tag request,
   project registration. Chains: draft -> save -> submit -> handle (lock) -> reject -> revise /
   resubmit -> approve / void, plus undo (cancel in grace), revert (`/form-actions/undo`), SLA
   extension, manual escalation and the overdue sweep, all through the real routes, asserting the
   outbox rows (respond / email) after each decision.
2. Add the new files to `sorento_crm_backend/tests/release_core.txt` so every release runs them.
3. Make `tests/test_form_handling_lock_routes.py` and `tests/test_sla_due_escalations.py` seed their
   own data and remove them from `tests/ci_excluded.txt`.
4. `tests/test_complaint_status_guard.py::test_edit_response_moves_submitted_to_updated` is stale
   (asserts the auto-flip that 36c1aaeb35 removed on purpose): fix or delete, with the reason stated.
5. Second commit after #1953 (PORTAL-P4-REQUESTS) merges: the same chains on salesperson-created
   rows through `/my-requests`.

Out of scope: Part B (Playwright on seeded data), a later lane.

## Test list

Recorded in the PR body as files land.
