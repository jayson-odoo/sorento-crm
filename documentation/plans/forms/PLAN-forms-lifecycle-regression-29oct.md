# PLAN: Forms lifecycle regression suite (FORMS-REGRESSION, Part A)

**Status:** Built, in review. Small fix track by process (test-only, no migration, no product code), M by effort.
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

## CI wiring (owner, 30 Oct 2026)

- Release: the nine files below are in `sorento_crm_backend/tests/release_core.txt`, so every
  release runs them.
- PR: the PR gate (`lean-gate`, check `PR gate`) has a step "Detect a forms lifecycle change"
  (path filter `FORMS_RE` over the PR's merged diff: form services, routes, models, SLA,
  form-action, handling-lock, revision, outbox and Respond send paths, the chains and their
  helpers, deploy.yml) and a step "Run the forms lifecycle chains (executing gate)" under xdist.
  A step, not a job: the PR runs one job (CI-COST round 2, pinned by
  tests/test_ci_docs_only_filter.py). About 100 s wall on 4 workers.

## Test list

Harness: `tests/_forms_chain_support.py` (real routes, real RBAC grants, real SLA chain; only
`respond_messaging_service.send_text_or_template` is stubbed; respond_io RQ jobs drained inline
so every outbox row is the app's own).

| File | Tests | Covers |
| --- | --- | --- |
| `test_forms_chain_purchase_request.py` | 24 (PR + SF) | draft/save/submit; reject -> resubmit -> pending approval -> approve -> process, outbox per decision; approval reject; revise + stale + cap; cancel in grace; commit on lapse; revert + correction; extend kept across undo; manual escalate + claim + take-over; overdue sweep; void; void-then-approve (strict xfail, bug VOID-APPROVE-GUARD) |
| `test_forms_chain_complaint.py` | 8 | draft/save/submit; respond -> reject -> resubmit -> respond -> approve -> process; cancel in grace; commit via sweep; revert + undo slug 403; extend + escalate + claim/release; overdue sweep; void |
| `test_forms_chain_stock_inquiry.py` | 9 | draft/save/submit; project-sales reject -> resubmit -> approve -> purchasing respond; purchasing reject + reopen; revise; cancel in grace; revert; extend + escalate + claim; overdue sweep; void |
| `test_forms_chain_price_tag.py` | 6 | draft/save/submit once (D8 auto-assign); proof -> changes -> proof -> approve -> collection -> collected; terminal reject; revise; void; extend + sweep + top-tier refusal |
| `test_forms_chain_sample_request.py` | 2 | draft/save/submit -> processing -> confirmed -> delivered; cancel rules; nothing sent |
| `test_forms_chain_project_registration.py` | 1 | draft/save/submit -> reject -> resubmit -> approve with PPF code |
| `test_form_handling_lock_routes.py`, `test_sla_due_escalations.py`, `test_complaint_status_guard.py` | 33 | rejoined CI (removed from ci_excluded.txt); stale complaint test inverted |

Follow-up after #1953 (PORTAL-P4-REQUESTS) merges: the same chains on salesperson-created rows
through `/my-requests`.
