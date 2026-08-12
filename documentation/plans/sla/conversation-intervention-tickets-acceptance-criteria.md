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
- **AC-C3 [FE][BE][T]** Given an open ticket with an open sibling, When Resolve is
  confirmed (AlertDialog, standard copy), Then only that ticket resolves; the sibling
  stays open; NO Respond API call is made. When the resolved ticket was the contact's
  LAST open ticket, the pre-existing best-effort Respond-conversation close fires
  (transport tidy-up - unchanged single-ticket behavior; decision 2026-08-12).

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
- **AC-E3 [BE][T]** (REVISED 2026-08-13 - keys on the CONTACT first, replier second) Given a
  staff member replies from the Respond app (not the CRM drawer), Then:
  (1) the contact has exactly ONE open unanswered ticket -> stamp it responded regardless of
  WHO replied (`responded_by` records the actual replier);
  (2) the contact has 2+ open unanswered -> if the replier owns exactly one of them, stamp
  that one; otherwise change nothing (`skipped_reason: "ambiguous"`);
  (3) zero open unanswered -> `"no_open_ticket"`.
  Rationale for the revision: the response clock measures "did the contact get a human
  response", not "did the assigned person type it". A ticket raised on an ALREADY-ASSIGNED
  Respond conversation is owned by the CRM round-robin pick (see AC-E6) while the Respond
  conversation stays with someone else - so the old replier-keyed rule found zero tickets
  for the replier and let a ticket breach while a human was actively answering it.
- **AC-E6 [BE][T]** Given an intervention on a conversation Respond has already assigned to
  another person, When the ticket is created with an explicit `assigned_to_id`, Then the
  ticket is owned by that CRM round-robin pick and the backend does NOT re-resolve or
  round-robin over it (verified in `create_tracking`'s `has_explicit_assignee` branch: an
  unknown id is a 400, never a silent re-pick). The Respond conversation assignee stays
  cosmetic. Rationale: enquiry #2 may belong to a different team than enquiry #1; forcing
  ownership to the Respond assignee reinstates the one-assignee limitation this feature
  removes and misroutes by topic.
- **AC-E7 [FE][T]** Given a ticket whose `source_message_text` is blank or whitespace (the
  n8n spine did not map `input_message`), When the worklist row renders, Then it shows a
  neutral fallback label, never an empty row.
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

### I. Contract surface for n8n (added post-review 2026-08-13)

- **AC-I1 [BE][T]** Given any create call to `POST .../conversation-sla-tracking/integration`
  (fresh insert, idempotent retry, out-of-hours), When it returns 200, Then the body ALWAYS
  contains the `in_working_hours` key. Rationale: n8n's strict type validation coerces an
  ABSENT key to `false` and routes on silently - a dropped key would tell in-hours contacts
  "we are outside working hours" with nothing red anywhere. The n8n side fails loudly on a
  missing key via a sentinel; this test is the CRM-side half of that contract.
- **AC-I2 [BE][T]** Given `GET /api/v1/external/conversation-sla-tracking/open-count`
  with `contact_id` (or `phone_number`/`contact_phone`), When the contact is unknown, has no
  tickets, or has zero OPEN tickets, Then it returns **200** with `{"contact_id": <resolved
  or null>, "open_count": 0}` - never 404. With open tickets, `open_count` is the count of
  OPEN conversation-scope rows only (form-SLA rows excluded via `conversation_tracking_scope`).
  Rationale: n8n gates the Respond "conversation closed and resolved" contact message on this;
  a 404-as-data or a sort-order-dependent read would silently tell a contact their still-open
  enquiry is resolved.
- **AC-I3 [BE][T]** Given a tracking that is ALREADY responded, When a caller sets
  `is_responded` again, Then the service returns 200 with an `already_responded` marker and
  leaves the clocks untouched - it does NOT raise 400. Rationale: resolve is already
  idempotent (`_already_resolved`); respond was not, and that asymmetry produced 53 refusals
  across 19 contacts on production data. Under multi-open the 400 aborts the fallback before
  the genuinely unanswered sibling is stamped.

- **AC-I4 [BE][T]** Given an agent replies in Respond, When n8n calls
  `POST /api/v1/external/conversation-sla-tracking/agent-replied` with
  `{contact_id, replied_by, replied_at?}`, Then the SERVER applies the REVISED AC-E3 rule in
  one place and ALWAYS returns 200 with
  `{matched, tracking_id, skipped_reason, open_ticket_count}`: contact has exactly one open
  unanswered ticket -> stamped responded regardless of replier (idempotent per AC-I3); 2+ ->
  narrow by replier, stamp only if the replier owns exactly one, else
  `skipped_reason: "ambiguous"`; zero -> `"no_open_ticket"`. Skipped outcomes are counted
  into `integration_log`.
  Rationale (LIVE DEFECT, predates this feature): the n8n `respond-send-user` workflow
  resolves rows in raw SQL with predicates `policy_id = <arbitrary first sla_policies row>`
  AND `is_responded = false` AND `assigned_to = <replying user>` and NO CONTACT PREDICATE,
  then PUTs once per returned row - so ONE reply to ONE contact stamps every unanswered
  ticket that agent owns across ALL contacts. Verified exposure on the dev snapshot: one
  assignee holds 5 open unanswered rows across 5 distinct contacts. The broken `LIMIT 1`
  policy predicate currently NARROWS the blast radius by accident (NORMAL matches, WAREHOUSE
  does not) - fixing policy resolution without the contact predicate makes it strictly worse.
  This endpoint retires that SQL entirely.
- **AC-I5 [BE][T]** Given the escalation scheduler, When it calls
  `POST .../conversation-sla-tracking/integration/escalate` with an optional `tracking_id`,
  Then that exact ticket escalates; contact+policy resolution stays only as the back-compat
  path. Rationale: `GET /integration/due-escalations` already returns one item PER ROW, but
  the escalate body is contact-scoped, so under multi-open the scheduler can escalate a
  different sibling than the one that breached. (The schema comment on
  `ConversationSLAEscalateRequest.policy_id` still asserts one-open-per-contact - fix with
  finding 10.)

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
