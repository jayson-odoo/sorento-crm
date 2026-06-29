# PLAN — Respond.io SLA actions: async + always logged + escalate reassigns

**Status:** Draft → implement
**Trigger:** Resolve in production did not close the Respond conversation, and there was
no outbox row to diagnose it. Reassign logs; Resolve/Escalate don't. Escalate doesn't
push the new owner to Respond at all.

## Current (verified)

| Action | Respond call | Sync/async | Outbox log |
|--------|--------------|------------|------------|
| Resolve | `close_conversation(category=Resolved)` (`sla_service.py:3818`) | sync, post-commit | **none** |
| Reassign | `set_conversation_assignee` (`:1307`, called `:1677`/`:1552`) | sync, post-commit | yes |
| Escalate | — | — | none |

## Target

All three go through the RQ **`respond_io`** queue (worker-executed, decoupled from the
request) and write an `integration_logs` row (the Respond outbox) on success AND
failure — including the Respond HTTP status_code + body on 4xx/5xx, so a prod failure
(WAF 403, "category required", closed window, bad workspace key) is diagnosable. Escalate
additionally pushes the new-tier assignee to Respond (it is a reassignment).

## Changes

### 1. `app/tasks/respond_io_tasks.py` — two new worker tasks
Mirror `_send_and_log`'s structure (fresh `SessionLocal`, success+failure
`create_integration_log`, capture `e.response` status/body, re-raise so RQ marks the job
FAILED). `business_table="conversation_sla_tracking"`, `business_id=tracking_id`,
`integration_channel="respond_io"`, `direction="outbound"`.

- `close_respond_conversation(tracking_id)` — resolve the contact's `respond_io_id`
  (via `RespondContact`, never the internal `respond_contact_id`), call
  `RespondClient.for_contact_id(...).close_conversation(respond_io_id,
  category="Resolved", summary=...)`. Endpoint logged:
  `/v2/contact/id:{respond_io_id}/conversation/close`.
- `set_respond_conversation_assignee(tracking_id, respond_user_id)` — resolve
  `respond_io_id`, call `set_conversation_assignee(identifier, respond_user_id)`.
  Endpoint: `/v2/contact/id:{respond_io_id}/conversation/assignee`.

Skip conditions (logged, not failed): form-SLA row, no linked contact, no `respond_io_id`,
(assignee task) no `respond_user_id`.

### 2. `app/services/sla_service.py` — enqueue instead of calling inline
- `_close_respond_conversation_best_effort(tracking)` → enqueue
  `close_respond_conversation(tracking.id)` on `respond_io` (job_timeout ~60). Keep the
  post-commit call site at `update_tracking` (`:3781`). Enqueue wrapped best-effort.
- `_push_respond_assignee(tracking, respond_user_id)` → validate (form-SLA skip, has
  `respond_user_id`) then enqueue `set_respond_conversation_assignee(tracking.id,
  respond_user_id)`. This makes reassign (`:1677`) AND takeover (`:1552`) async+logged too.
  The inline call + inline integration_log are removed (the task owns the log now).

### 3. `app/api/v1/sla/sla_tracking.py` — escalate pushes the new owner
After `escalate_tracking(...)` in the UI escalate route (`:1018`), call
`service._push_respond_assignee(tracking, assignee.get("respond_user_id"))` so the Respond
conversation owner follows the new-tier assignee. (Integration `/integration/escalate`
left as-is — n8n owns that routing.)

## Tests
- pytest: each task writes a success log (mock RespondClient OK) and a failure log with
  status_code/body (mock raising an `HTTPStatusError` carrying `.response`); re-raises on
  failure. Skip conditions write no Respond call.
- pytest: escalate route enqueues an assignee job (mock `enqueue_job`).
- Existing reassign/resolve tests updated to assert an ENQUEUE instead of an inline call.

## Notes
- `respond_io` is NOT in `_IMMEDIATE_DRAIN_QUEUES` → the **worker must run** for these to
  execute (already true for all Respond sends). Local: restart the worker.
- The prod resolve-not-closing root cause will surface as a `status='failed'` outbox row
  once this ships — check `integration_logs` where `business_table='conversation_sla_tracking'`
  and `endpoint LIKE '%/conversation/close'`.
