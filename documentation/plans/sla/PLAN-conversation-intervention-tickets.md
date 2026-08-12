# PLAN — Conversation Intervention Tickets

Status: Approved 2026-08-12 (lavish review) - Phase 1 in progress
UAC: conversation-intervention-tickets-acceptance-criteria.md

## Decision summary

- Conversation SLA rows become per-enquiry intervention tickets: multiple open per contact,
  no contact-level uniqueness, idempotent by `source_message_id`.
- CRM is the worklist ("Mine") and the reply surface. Respond.io = transport only (Option A).
  Respond assignee cosmetic; Respond close events ignored.
- Clocks are event-driven per ticket: first-response stops on a ticket-stamped CRM send
  (fallback: unambiguous user-match from Respond-app replies); resolution stops on manual
  CRM resolve. Contact messages touch no clocks.
- Ticket model stays channel-agnostic (`source_message_id`, message refs in event logs) so
  the chat surface can later swap to the shared-service omnichannel embed without touching
  the ticket layer.
- Worklist = the EXISTING dashboard pending-tasks widget (`MyPendingSLAWidget` +
  `/my-pending`); a ticket opens as an in-place chat drawer, no new page. (Decided in
  lavish review 2026-08-12.)
- Out-of-hours decisioning moves from n8n (Redis queue) into the CRM create path, which
  already owns working-window clock normalization. (Decided in lavish review.)
- Rollout: accept the transition escalation noise - no grace multiplier. Clock pressure
  trains reply-from-CRM. (Decided in lavish review.)

## Current state (verified 2026-08-12)

- `RespondClient` (integration_service.py): `send_message` (text) + `send_template_message`
  only. `list_messages` / `get_message` power the chat panel. No attachment/sticker/reply-to.
- `conversation_sla_tracking` already carries per-row clocks: `due_at`, `due_at_resolution`,
  `is_responded/responded_at/responded_by/response_time`, `escalated_at`. Multi-open needs
  identity + attribution work, not new clock machinery.
- Migration 180: partial unique index `respond_contact_id WHERE is_resolved=false` (conversation
  scope) - the singleton to drop.
- n8n `sub-human-intervention` (rrYXzE61gCNUck_zmXe-G): already passes `message_id` (trigger
  message) to the create endpoint; creates SLA ONLY on the unassigned branch - the
  already-assigned branch is comment-only (the bug).
- Unified composer smart-send (in-window text / out-window template) and `RespondChatList`
  exist and are shared across complaint / stock-inquiry / PR chat panels.

## Research items (resolve during Phase 1, before contract freeze)

- R1. Respond.io API v2 message types: confirm attachment subtypes, sticker support, and
  reply-to/quote support on `POST /contact/{id}/message`. Composer capabilities = whatever
  the API confirms; unsupported types are omitted from the UI (UAC D1).
- R2. Media delivery: Respond fetches attachments by URL - confirm URL lifetime requirements
  vs presigned S3/R2 expiry; CMYK-to-RGB conversion applies (existing rule).
- R3. Who sets `is_responded` today (n8n agent-reply event? backend?) - map the full write
  path before changing semantics.
- R4. RESOLVED: the create path already normalizes clock start to the next working window
  (PLAN-sla-clock-start-next-working-window.md, Phase 2 complete, 43 tests green). Remaining
  work is only exposing `in_working_hours` on the create response for n8n's auto-reply
  choice.

## Phases (three-phase loop)

### Phase 1 — FE prototype (mock data, no backend changes)

- S1.1 Extend `MyPendingSLAWidget` mocks: intervention tickets in all states (fresh,
  near-breach, escalated, responded-awaiting-resolve), incl. two tickets for one contact.
  No new page.
- S1.2 Ticket chat drawer (opens in place from the widget): enquiry header (quoted trigger
  message, team, SLA chips), shared thread (mock `RespondMessageRenderable` fixtures incl.
  attachments/sticker/quote), composer with all send types (text / attach / sticker /
  reply-to), out-of-window template state, resolve confirmation.
- S1.3 Two-tickets-same-contact demo state: same thread, different headers/clocks.
- S1.4 Document the API contract at the top of the ticket service file: create/my-pending/
  detail/send/resolve request+response shapes, send-type enum (bounded by R1),
  `in_working_hours` create-response field (R4).
- Verify via Playwright MCP through the sidebar. Screenshot golden path + edge states.
- Gate: prototype rendered via lavish for user review; proceed autonomously unless
  feedback arrives.

### Phase 2 — BE wiring + tests (TDD)

- S2.1 Migration: add `source_message_id` (Text, nullable), backfill from `message_id`;
  drop the migration-180 contact-singleton index; add partial unique index on
  `source_message_id` WHERE open AND conversation scope. Alembic single head check.
- S2.2 Create endpoint semantics: multi-open create; idempotency by `source_message_id`
  (keep `already_active` response shape so the n8n contract stays stable); stop refreshing
  `message_id`; keep the response fields n8n templates read (`initiated_at`, `due_at`,
  `due_at_resolution`, `assigned_to`).
- S2.3 Audit one-open consumers (UAC F1): `get_tracking_by_contact_*`, thread-assignee
  endpoints, MCP tools, `sync_assignee_from_respond` retirement. Each gets an explicit
  multi-row semantic + test.
- S2.4 Send capability in `RespondClient`: attachment (upload via CRM storage -> URL),
  sticker, reply-to per R1; outbox `integration_log` on success+failure with
  actually-attempted payload; out-of-window template fallback reused from smart-send.
- S2.5 Ticket-context send endpoint: stamps ticket id, sets responded fields on that ticket,
  writes event log with message ref (naive-UTC gotcha: wrap datetimes with `_to_aware_utc`).
- S2.6 Fallback attribution: inbound agent-reply path (per R3) marks responded only on an
  unambiguous (contact, user) -> single-open-ticket match.
- S2.7 `/my-pending` + drawer detail + resolve endpoints wired; FE off mocks.
- S2.8 Notifications: assignment notify via existing matrix + deep link.
- S2.9 Out-of-hours in create path (R4): clock start normalized to next working window,
  `in_working_hours` in the response; `initiated_at` keeps the real request time.
- Tests: pytest (create idempotency, multi-open, index, attribution, fallback ambiguity,
  send outbox on failure, consumer audit semantics - all self-seeded, Postgres only);
  vitest (listing/detail/composer states); Playwright e2e (mine -> ticket -> send -> resolve
  round-trip; real media fixtures).
- Gate: all suites green; browser-verified against prod build before handoff.

### Phase 3 — Review + n8n cutover

- S3.1 `/code-review` + `/codex-review` (cross-model) on the branch; fix findings.
- S3.2 n8n coordination (peer session via SendMessage): always-create on both branches,
  remove the out-of-hours Redis branch (`sorento-respond-assignee-queue`) - auto-reply
  choice driven by the create response's `in_working_hours`; stop message_id refresh
  reliance; stop resolve-on-close calls; keep comment/tag optional. Contract doc = S1.4 +
  UAC sections A + H. Verify with a test-guard run (`is_test` path exists).
- S3.3 Cutover order: deploy BE/FE first (n8n's existing single-create calls remain valid -
  A1/A2 are backward compatible; out-of-hours branch keeps working until flipped), then
  flip the n8n workflow. No deploy without explicit go.

## Execution model (per PRINCIPLES.md - named executor per step)

Run through `/feature`. Fable (main session) is the brain and stays autonomous end-to-end:
planning/grilling/contract decisions/phase gates stay in the main session; Phases 1-2
implementation is delegated to the `coder` agent in a worktree; tests to the `tester`
agent; review runs `reviewer` + `/code-review` + `/codex-review` (cross-model second
opinion); n8n changes coordinate with a peer session via SendMessage. Slice to GitHub
Issues with `/to-tickets` (bodies link back to these files - the files stay the contract).
Main already fast-forwarded to origin/main (af2dad409). User checkpoints happen through
lavish artifacts, not blocking waits.

## Risks / open questions

- Q1. Respond API may not support sticker or reply-to sends (R1) - composer scope shrinks,
  not blocks.
- Q4. `assigned_to` is Text + `assigned_to_id` FK both exist - tickets should write both
  (existing convention) - confirm no consumer reads only one.
- (Resolved) Q2 rollout noise: accepted, no grace period. Q3 placement: existing
  pending-tasks widget + chat drawer.
