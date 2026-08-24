# User Acceptance Criteria - SLA notifications, KPI, PWA epic (TCK-28..33)

Testable acceptance criteria for the directors' 2026-06-17 epic. Each criterion is a **gate the loop must validate against** before marking that slice done. Criteria are derived from the grilled ticket specs (`../TCK-2026-0000XX.md`) and the decisions locked in those grilling sessions.

## How the loop uses this

Execution model: a `/loop` drives each ticket through the three-phase dev loop (FE prototype → BE wiring + tests → code review). **A criterion is only `[x]` when its `Validate:` step has been run and passed in this environment** - never on inspection alone.

Validation channels:
- **BE** → `pytest` (in `sorento_crm_backend/`, worker/redis up where noted) or `curl` against `:8000`.
- **FE** → Playwright MCP against `:3000` (prod build `npm run build && npm start`, no HMR) - navigate via sidebar, check `browser_console_messages`, `browser_network_requests`.
- **Data/storage** → `psql` query asserting columns/rows.
- **Scalability** → query-count / latency assertion (pytest with a seeded N, or `EXPLAIN`/timing), stated per criterion.

Rules:
1. Run the `Validate:` step; record pass/fail. Mark `[x]` only on pass. On fail, fix and re-run - do not advance.
2. If an env dependency is missing (worker down, no Respond sandbox, no VAPID), mark the criterion **BLOCKED** with the reason; do not fake-pass.
3. **Definition of Done per ticket** = all its `[F]/[B]/[D]/[R]/[UX]/[S]` criteria `[x]` **AND** the three-phase test suites that cover them committed and green (vitest + playwright + pytest, per CLAUDE.md Phase 2).
4. Negative criteria (e.g. "no ack endpoint exists") are real gates - validate the absence.

Category tags: **F** functional · **B** business · **D** data/storage · **R** RBAC/security · **UX** user experience · **S** scalability.

## Build order (dependency-driven)

`31 → (28, 32, 33 parallel) → 29 → 30`. TCK-31 is the foundation (link + phone + prefs); 29/30 depend on its toggles + `resolve_user_respond_io_id`. 28's `trigger` column feeds 32.

## Per-ticket UAC

- [TCK-2026-000028](./TCK-2026-000028-UAC.md) - Form SLA auto-scan fix + manual escalate
- [TCK-2026-000029](./TCK-2026-000029-UAC.md) - WhatsApp on escalation + assignment
- [TCK-2026-000030](./TCK-2026-000030-UAC.md) - Conversation SLA summary via WhatsApp
- [TCK-2026-000031](./TCK-2026-000031-UAC.md) - User↔RespondContact link + phone + prefs
- [TCK-2026-000032](./TCK-2026-000032-UAC.md) - Management KPI dashboard
- [TCK-2026-000033](./TCK-2026-000033-UAC.md) - PWA + web push

## Business-requirement traceability (directors' directives → criteria)

| Director directive (2026-06-17) | Ticket | Key business criteria |
|---|---|---|
| Manual escalate for form SLA (complaint / stock inquiry / purchase request / sponsorship) | 28 | AC-28-B1, AC-28-F4 |
| Escalation owned by **our system**, not n8n; scheduled check | 28 | AC-28-B2 |
| Escalation reaches management (CK / Jayden / Mr. Loo) | 28 + 29 | AC-28-B1, AC-29-B1 |
| WhatsApp escalation notification with "OK" | 29 | AC-29-F1, AC-29-F4, AC-29-B1 |
| Conversation SLA summary via email / WhatsApp | 30 | AC-30-F1, AC-30-B1 |
| Toggled per user; key in phone; link to respond contacts | 31 | AC-31-F1, AC-31-F2, AC-31-UX1 |
| Dashboard for management to view KPI of each task; stored | 32 | AC-32-F1, AC-32-F2, AC-32-D1, AC-32-R1 |
| PWA for normal users to get notifications | 33 | AC-33-F2, AC-33-B1 |

## Cross-cutting scalability gates (apply to every ticket)

- **XS1 - Async, not in-request.** All WhatsApp/email/web-push sends go through RQ queues (`respond_io` / notifications), never block the HTTP request. Validate: request returns < 500ms while a send is pending; delivery completes on the worker.
- **XS2 - No N+1.** List/scan/aggregate paths use set-based queries. Validate: with N≥200 seeded rows, query count is bounded (assert via SQLAlchemy event counter or `EXPLAIN`), not O(N).
- **XS3 - Best-effort side effects.** A failed send/notification marks its delivery `failed` and is logged; it never raises to the caller or aborts the committed primary operation (CLAUDE.md post-commit rule).
- **XS4 - Indexed lookups.** New hot-path lookups (`users.respond_contact_id`, phone match, event-log aggregations, push subscriptions) hit indexes. Validate: `EXPLAIN` shows index usage / FK+unique constraints present.
- **XS5 - Idempotent repeats.** Re-running a scheduled job (scan, daily summary) the same period does not double-send or double-escalate. Validate: run twice, assert single effect.
