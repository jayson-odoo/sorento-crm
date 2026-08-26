# PLAN - Ticket-resolved closing message (one per ticket)

Status: BUILT 2026-08-26 on feat/external-conversation-comments (same branch as optimistic send,
user decision): pytest 11/11 new + 122 neighbours green, FE use-case entry in, n8n
respond-close-convo DRAFT edited (sendmsg node disconnected, AC-C1) - NOT promoted, user's call.
Dev-stack evidence run PASSED (tester, see below); uncommitted.
UAC: ticket-resolved-closing-message-acceptance-criteria.md

## Decision summary

- The CRM owns the closing message and sends one per resolved conversation ticket, on every
  resolve lane (user or api-key). n8n `respond-close-convo` keeps only the contact-level
  housekeeping (unassign, bot resume) on the last-open lane and drops its message node.
- Wording is an admin-configured WhatsApp template use case (`ticket_resolved`), same contract
  as the `sla_*` use cases: `send_text_or_template` renders the default body in-window and sends
  the mapped approved template out-of-window; a built-in fallback text covers "nothing
  configured yet".
- Delivery is an RQ job on the `respond_io` queue (like the Respond assignee push), enqueued
  post-commit from `update_tracking`, best-effort.
- The job goes through the existing `_send_and_log` worker body (window-aware send, outbox log,
  CRM outbound webhook), which additionally mirrors the sent message into `chat_histories`
  (the optimistic-send helper) so the thread shows it at once.

## Phase 2 - Backend (test-first)

- `app/models/respond_template.py`: `TEMPLATE_DEFAULT_USE_CASES` += `ticket_resolved`.
- `app/tasks/respond_io_tasks.py`: `send_ticket_resolved_message(tracking_id)`; `_send_and_log`
  mirrors locally when `emit_outbound_webhook` (never for OTP).
- `app/services/sla_service.py` `update_tracking`: inside the existing
  `resolved_in_this_request and not form` block, enqueue the job (before the sibling gate, so
  every ticket gets one).
- Tests: `tests/test_ticket_resolved_closing_message.py` (AC-A1..A6, AC-B2..B6).

## Phase 1 - Frontend

- `services/whatsappTemplateService.ts`: use-case union + list entry with label and the param
  hint (Contact name, Full update message).

## Phase 3

- n8n `respond-close-convo`: disconnect `Update a Contact` -> `sorento-sub-respond-sendmsg-respond`
  in the draft; user promotes (AC-C1).
- Browser: resolve a ticket on the dev stack, see the closing message land in the thread.

## Evidence run (tester, dev stack, 2026-08-26)

Resolved ticket `f452acd0-ab79-45e1-9bf7-7428b3041b5f` (contact Jayson, no source text) from the
dashboard widget. RQ job `send_ticket_resolved_message` enqueued 0.17 s after `resolved_at`
(stolen and failed by the stale sibling-worktree worker, expected locally). Job body run inline
from this checkout: Respond ack `messageId 1787708006449159`; integration_log `respond_io`
success against the ticket; `chat_histories` row 36872 (outgoing, same message_id); Respond's
own `message/list` returns it as the newest message; thread screenshot
`scratchpad/closing-message.png` shows it once at 9:33 am. AC-A1, B3, B4, B5 PASS. Note for the
dev stack: the RQ worker must run from THIS checkout for the job to succeed end to end.
