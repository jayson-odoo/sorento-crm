# UAC — Conversation Intervention Tickets (multi-open conversation SLA + CRM-native replies)

Status: Approved 2026-08-12 (lavish review) - contract locked
Related: PLAN-conversation-intervention-tickets.md

## End goal (one paragraph)

No contact enquiry is ever lost to Respond.io's one-assignee-per-contact limit. Every human
intervention request becomes its own CRM ticket with its own assignee and clocks; staff see
everything they owe in the existing dashboard pending-tasks widget, answer from an in-place
chat drawer with full conversational capability (text / attachments / sticker / reply-to),
and resolve there. Respond.io degrades to a message pipe. Success = a contact raises two
enquiries back-to-back and both get answered by the right people, each with an auditable
per-enquiry response/resolution trail, without anyone opening Respond.io.

## Problem

Respond.io allows one assignee per contact. When a contact requests human intervention twice
(two different enquiries), the second request cannot be assigned in Respond - today's n8n flow
(`sub-human-intervention`) only comments and tags the second assignee, and creates NO SLA row
on the already-assigned branch. The second assignee works from Respond's "Mine" inbox, never
sees the comment, and the enquiry dies silently.

## Journey

**Actors**: Contact (WhatsApp end user) - CS/sales staff (ticket assignee) - manager.

1. **Contact asks for help** in the WhatsApp bot conversation ("yes, escalate"). n8n routes
   the request (round-robin or explicit assignee), and **always** creates an intervention
   ticket in the CRM - regardless of Respond assignment state or working hours - carrying
   the triggering message id, the input message text, team and agent codes. Contact receives
   the existing auto-reply (in-hours vs out-of-hours copy chosen by n8n from the create
   response). Nothing new is asked of the contact.
2. **Assignee is notified** (in-app always; WhatsApp/email per their notify toggles) with a
   deep link to the ticket. The comment-and-tag hack in Respond becomes redundant.
3. **Assignee sees the ticket in the existing dashboard pending-tasks widget**
   (`MyPendingSLAWidget` / `GET .../my-pending`) - contact name, enquiry snippet, SLA
   countdown chips, escalation state. This widget replaces Respond's "Mine". No new page.
4. **Assignee clicks the ticket - a chat drawer opens in place**: enquiry reference header
   (quoted trigger message, team, requested time); the full shared WhatsApp thread; composer.
5. **Assignee replies from the ticket composer** - text, attachments, sticker, reply-to.
   Out-of-window sends fall back to template smart-send. The send is stamped with the ticket
   id: this ticket's first-response clock stops; siblings untouched.
6. **Conversation continues**; contact messages touch no clocks.
7. **Assignee resolves the ticket** in the drawer - resolution clock stops; sibling tickets
   live on; Respond conversation state untouched.
8. **On breach**, existing escalation machinery fires per ticket.
9. **Manager** sees all open tickets in the existing SLA tracking listing.

## Acceptance criteria

Format: per-AC id, Given/When/Then, tagged [BE] / [FE] / [E2E] / [T] (T = has automated test).

### A. Ticket creation and identity (Journey step 1)

- **AC-A1 [BE][T]** Given contact C has an open ticket assigned to user U1, When n8n POSTs
  create with a new `source_message_id` (routed to U2 OR to U1 again), Then a second open
  ticket is created with its own clocks; both rows are open simultaneously.
- **AC-A2 [BE][T]** Given an open ticket with `source_message_id` M, When create is re-POSTed
  with M (n8n retry), Then 200 `already_active: true`, no new row, no field refresh, and the
  response keeps the n8n-read fields (`initiated_at`, `due_at`, `due_at_resolution`,
  `assigned_to`).
- **AC-A3 [BE][T]** Given migration applied on a DB with existing open+resolved trackers,
  When `alembic upgrade head` runs, Then the migration-180 contact-singleton index is gone,
  `source_message_id` exists and is backfilled from `message_id`, a partial unique index on
  `source_message_id` (open + conversation scope only) exists, and every pre-existing row is
  still readable/resolvable.
- **AC-A4 [BE][T]** Given a create call arriving out of working hours, When the ticket is
  created, Then `initiated_at` = request time, clock start normalizes to the next working
  window (existing behavior), and the response includes `in_working_hours: false`.
- **AC-A5 [n8n]** Given the reworked `sub-human-intervention`, When an intervention fires on
  the already-assigned branch, Then a ticket is still created (always-create both branches);
  the out-of-hours Redis branch is deleted; resolve-on-close calls are removed. (Peer
  session owns; verified via the flow's `is_test` guard run.)

### B. Worklist - existing pending-tasks widget (Journey step 3)

- **AC-B1 [FE][T]** Given user U has 3 open tickets (2 for the same contact), When U opens
  the dashboard pending-tasks widget, Then all 3 render with contact, enquiry snippet,
  respond-by / resolve-by countdowns, and tier/escalated state - no de-dup by contact.
- **AC-B2 [FE][T]** Given the widget, When a ticket row is clicked, Then the chat drawer
  opens in place (no navigation), and loading/empty/error states render per CRUD standard.

### C. Ticket chat drawer (Journey steps 4-7)

- **AC-C1 [FE][T]** Given an open ticket, When the drawer opens, Then it shows the enquiry
  header (quoted trigger message, team, created time, SLA chips), the full shared contact
  thread, and the composer.
- **AC-C2 [E2E][T]** Given two open tickets for one contact, When each drawer is opened,
  Then both show the SAME thread but their own header and clocks.
- **AC-C3 [FE][BE][T]** Given an open ticket, When Resolve is confirmed (AlertDialog,
  standard copy), Then only that ticket resolves; the sibling stays open; no Respond API
  call is made.

### D. Full conversational send capability (Journey step 5)

- **AC-D1 [BE][FE][E2E][T]** Given an in-window conversation, When the assignee sends text /
  image / video / audio / document from the composer, Then the message reaches Respond
  (media uploaded via CRM storage, delivered by URL, CMYK JPEG converted to RGB) and appears
  in the thread. Sticker and reply-to included iff the Respond API supports them (R1);
  unsupported types are absent from the composer, never silently failing.
- **AC-D2 [BE][T]** Given the contact's messaging window is closed, When the assignee sends,
  Then the template smart-send fallback fires exactly as the existing unified composer.
- **AC-D3 [BE][T]** Given any send (success OR Respond 4xx/5xx), When it completes, Then an
  `integration_log` outbox row exists with the actually-attempted payload.
- **AC-D4 [FE][T]** Given inbound attachments/stickers/quotes in the thread, When rendered,
  Then each shows at least a typed placeholder; unknown types never crash the list.

### E. Attribution and clocks (Journey steps 5-7)

- **AC-E1 [BE][T]** Given ticket T1 and sibling T2 for the same contact, When the assignee
  sends from T1's drawer, Then T1 gets `is_responded/responded_at/responded_by/response_time`
  set; T2 is untouched.
- **AC-E2 [BE][T]** Given open tickets, When the contact sends an inbound message, Then no
  clock on any ticket changes.
- **AC-E3 [BE][T]** Given user U replies from the Respond app (not CRM), When U maps to
  exactly one open ticket for that contact, Then that ticket is marked responded; when U
  holds 2+ open tickets for the contact, Then nothing changes (CRM reply path is
  authoritative).
- **AC-E4 [BE][T]** Given a Respond conversation-close event, When it reaches the CRM (or
  n8n), Then no ticket resolves - resolution is manual CRM resolve only.
- **AC-E5 [BE][T]** Given a ticket breaching `due_at`, When the escalation scheduler ticks,
  Then it escalates exactly as today (tier up, notify, event log), independently per ticket.

### F. One-open-assumption consumers (regression surface)

- **AC-F1 [BE][T]** Every call site resolving "the" open row by contact
  (`get_tracking_by_contact_*`, thread-assignee lookups, MCP tools) has an explicit
  documented multi-row semantic (set / most-recent / retired) and a test pinning it. No
  silent `.first()` on a multi-row result.
- **AC-F2 [BE]** `sync_assignee_from_respond` is retired or no-ops for conversation tickets.
- **AC-F3 [BE][T]** Form-SLA rows (FORM_SLA_TYPES) are untouched: `conversation_tracking_scope()`
  still separates families; form-SLA suites pass unchanged.

### G. Notifications (Journey step 2)

- **AC-G1 [BE][T]** Given ticket creation, When the assignee has notify toggles on, Then
  in-app (always) + email/WhatsApp (per toggle) notifications fire with a deep link that
  survives the login redirect.

## No-regression strategy

The blast radius is the shared `conversation_sla_tracking` table and the Respond send path.
Regression is held by four independent nets:

1. **Existing suites stay green, run in full.** All current pytest SLA suites (conversation
   SLA idempotency, working-window clocks - 43 tests, form-SLA, handling lock, escalation,
   extension) plus vitest + playwright run on the branch AND on an empty scratch DB
   (CI-parity rule). Any red = stop.
2. **Family isolation pinned by test (AC-F3).** Form SLA (per-entity, `source_entity_type`
   in FORM_SLA_TYPES) shares the table; explicit tests assert its singleton/stage behavior
   is unchanged by the index swap.
3. **Contract-frozen seams.** (a) n8n create contract: AC-A2 keeps the response shape, so
   the OLD n8n flow keeps working until the flip - deploy order BE/FE -> n8n, each step
   backward compatible. (b) Send path: new send types are additive methods on
   `RespondClient`; the existing `send_text_or_template` smart-send used by
   complaint/SI/PR chat panels is reused, not forked (AC-D2), so those panels ride the same
   tested path.
4. **Consumer audit with pinned semantics (AC-F1).** Every reader of "the open row per
   contact" gets a test capturing its new multi-row behavior BEFORE the index drops -
   red/green proves the audit found them all; grep sweep for `conversation_tracking_scope`
   + `respond_contact_id` call sites is the completeness check.
