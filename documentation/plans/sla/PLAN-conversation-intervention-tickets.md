# PLAN — Conversation Intervention Tickets

Status: Phases 1-3 DONE (PR #137 open); defect batch D1-D6 in flight; Phase 4 (parity + liveness) PLANNED 2026-08-14, awaiting user review
UAC: conversation-intervention-tickets-acceptance-criteria.md (sections J/K/L/M + B3/B4 added 2026-08-14)

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

- R1. RESOLVED (Respond OpenAPI spec, 2026-08-12): types `text`, `attachment`
  (`image|video|audio|file`), `quick_reply`, `whatsapp_template`. NO sticker, NO reply-to
  parameter. Sticker omitted from composer; reply-to = quote-prefix emulation
  (`buildQuotedReplyText`/`splitQuotedPrefix`); `reply_to_message_id` event-log only.
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
- S3.3 Cutover order (refined with the n8n peer session, 2026-08-12): deploy BE/FE first
  (old n8n calls remain valid - A1/A2 backward compatible; out-of-hours branch keeps
  working until flipped) -> verify old flow green -> flip DURING working hours with
  `LLEN sorento-respond-assignee-queue == 0` verified (or right after a drain tick;
  stranded queue items = lost enquiries) -> publish reworked sub to rrYXzE61gCNUck_zmXe-G
  -> post-flip canary with the dev contact (437264483), user-gated. FLIP SCOPE also
  includes `respond-close-convo` (-WkzJMQZHmsFQm6A2abLJ): gate/unpublish its
  conversation-scope resolve leg (it resolves + unassigns + messages the contact on
  Respond close events - AC-E4 noise/loop source). Post-flip tidy: remove the dead
  drain leg in `schedule-working-day-detection` (ss9S83XF7ZtmnaUyFtYZc). Post-flip BE
  hardening follow-up: reject conversation-scope is_resolved from API-key principals
  (defense-in-depth; cannot ship pre-flip without breaking the old contract).
  n8n create node moves to `POST .../conversation-sla-tracking/integration` (the bare
  POST / lacks in_working_hours in its response_model); body drops policy_id/current_tier
  (ignored), keeps agent_code/team_set_code/contact_phone_number, sends
  assigned_to_id + source_message_id (string) + source_message_text + message_id.
  AC-A5 note: the flow's is_test guard run is fail-closed proof ONLY (it short-circuits
  all branch logic); functional verification = pin-data matrix on the fork
  (vUfFUDjLAuMaeQE6), 5 cases incl. the assigned-branch create and already_active retry.
  No deploy without explicit go.
  CRITICAL (peer recon 2026-08-12): `respond-close-convo` resolves via RAW SQL with NO
  is_resolved filter - one close event would mass-resolve OPEN siblings post-flip
  (AC-E4 violation). Its edit is hard-mandatory at flip: If TRUE -> unassign, delete
  tracking-update + event-log nodes, keep unassign + is_human_intervened clear; closing
  message KEPT but gated on "contact has no open tickets" (empty open-rows GET). #133
  (BE API-key resolve rejection) ships immediately post-flip, same day.
  USER DECISION AT FLIP APPROVAL: keep or kill the contact-facing "conversation closed
  and resolved" auto-message (currently kept, gated).
  resolved_by pollution check: clean (zero non-UUID / orphan values on dev DB).

## Phase 4 — Omnichannel parity + liveness (planned 2026-08-14, dogfooding feedback)

Grounded on three read-only investigations (send-path diagnosis, n8n trigger trace with
live execution payloads, Respond API v2 capability inventory). Defect batch D1-D6
(attachment isinstance, /conversation threadpool, template sync-for-drawer, duplicate
refetch + poll fallback + silent-degrade guard, window-state TTL cache, widget
Reassign/Extend on ticket rows) runs ahead of this phase as straight fixes against the
existing UAC.

### S4.1 Human-send signal (UAC J) [BE coder + n8n peer]

- CRM side: call `enqueue_crm_chat_outbound_webhook(...)` from the human ticket-drawer
  send path (`send_chat_message_for` return / `send_ticket_message`), best-effort
  post-commit, payload per the established `crm_chat_outbound_webhook.py` builder
  (single-element array, `source: "User"`, real Respond user id via
  `_webhook_agent_respond_id`, `crm.business_id` = tracking id). Covers text, attachment,
  template sends. Never from bot paths.
- Ingest idempotency (AC-J5): `POST /api/v1/external/chat_history/messages` upserts on
  Respond `messageId` - kills the double-mirror (webhook lane + Respond trigger lane)
  at our boundary. Check existing PR-notification sends for historical duplicates.
- n8n peer edit (AC-J4): wire the webhook lane into the `If source == "User"` branch so
  `Update a Contact` (is_human_intervened) + ht lane arm for CRM sends. Safe: the
  webhook carries only CRM human traffic. Also fixes what a manual Respond reply already
  gets. Peer session owns the edit; verify with a pin-data run before publish.

### S4.2 Live thread via server push (UAC K) [BE coder + FE coder]

- Transport: SSE endpoint on FastAPI (`/api/v1/sla-management/conversation-events/stream`),
  Redis pub/sub bridge so API + worker processes can publish. No websocket infra.
- Publishers: chat ingest (inbound message -> event keyed by respond_contact_id),
  ticket create/clock mutations (-> event keyed by assignee user id).
- Subscribers: drawer (refetch thread on contact event; open drawers only - AC-K2),
  pending-tasks widget (refetch on assignee event - AC-K3). 10-15s poll stays as
  fallback (already added in D4b) and is suppressed while the stream is healthy.
- Idempotent by construction: events carry ids; FE refetches rather than appending
  pushed payloads (AC-K4).

**Shipped BE contract (2026-08-15, backend half; the FE subscriber slice builds
against this).**

- Channel: `sorento:conversation-events:v1`, one Redis pub/sub channel, override per
  environment with `CONVERSATION_EVENTS_CHANNEL` (settings
  `conversation_events_channel`). Namespaced because one broker is shared with RQ and
  with every local worktree.
- Endpoint: `GET /api/v1/sla-management/conversation-events/stream?contacts=<id>[,<id>]`
  (JWT, same principal as the sibling sla-management routes; 401 without one; max 25
  contacts). `text/event-stream`, chunked, `X-Accel-Buffering: no`.
- Frames: `event: ready` on connect (the FE's cue to refetch), then
  `event: <type>` with a JSON `data:` line, plus a `: keep-alive` comment every 25s.
  Types: `message`, `ticket_created`, `ticket_updated`.
- Payload, exactly five keys, no content ever:
  `{"type","contact_id","user_id","entity_id","ts"}`.
  - `contact_id` = the **Respond.io contact id** (`respond_contacts.respond_io_id`),
    NOT the internal `respond_contacts.id` UUID. DEVIATION from the bullet above,
    deliberate: the chat ingest receives that id verbatim (so nothing is resolved on
    the hot path) and the drawer already holds it as `respond_io_id` from
    `GET .../{tracking_id}/ticket`, so the FE has the key it must pass in `?contacts=`
    without a new field and without a UUID in a query string.
  - `user_id` = `users.id` whose worklist changed. `entity_id` = the tracking id for
    ticket events, null for `message`. `ts` = UTC ISO-8601 with `Z` (transport clock,
    not a domain datetime).
- Filtering is server-side: a client receives events where `user_id` is its own OR
  `contact_id` is in its `?contacts=` list. Nothing else leaves the process.
- Stateless: no Last-Event-ID, no replay. A reconnect resubscribes; the gap is
  covered by the refetch on `ready` plus the drawer's 10-15s poll fallback.
- Publishers wired: chat ingest (new row only, never the AC-J5 dedupe path), ticket
  create (not the idempotent retry), the shared update path (resolve / respond /
  assignment), first-response stamp, reassign, escalate, extend. Reassign and escalate
  poke BOTH the old and the new owner; the update path snapshots the assignee before
  applying, because resolving a conversation ticket unsets `assigned_to_id`. Form-SLA
  rows never reach the channel (AC-F3).

### S4.3 Internal comments with @mention (UAC L1-L3) [BE coder + FE coder]

- Model: `conversation_ticket_comments` (id, tracking_id FK, author_id, body,
  mentioned_user_ids uuid[], respond_comment_mirrored bool, created_at). CRM DB is the
  source of truth (Respond has no comment read-back API - verified).
- FE: comment mode toggle in the drawer composer (visually distinct, yellow-note style),
  @ typeahead over CRM users, inline render in the thread. In-app notification + deep
  link for mentioned users (existing notification service).
- Mirror OUT (L2): best-effort `POST /v2/contact/{id}/comment` with `{{@user.<id>}}` for
  mentioned users that map to Respond users. Mirror IN (L3): n8n forwards
  `comment.created` webhooks to a new ingest route; dedupe by (contact, created_at,
  text) since Respond gives no comment id in the webhook (verify payload at build time).

BUILT 2026-08-15. The as-built wire contract, and the four places it deviates from the
sketch above, are written under AC-L3 in the UAC file (that is the contract; this bullet
is the design note). Summary of the deviations: the table is
`conversation_ticket_comments` with a NULLABLE `tracking_id` because Respond comments are
contact-scoped; dedupe keys on Respond's own `comment_id` rather than
(contact, created_at, text); the mention notification is the in-app lane only; and
comments are never written into `chat_histories` - the drawer merges the two streams at
render time. FE: a "Reply | Comment" mode switch in the drawer, an amber
`InternalCommentComposer` (shared, in `components/common/conversation/`) with an @
typeahead over `userSelectService`, and amber "Internal" bubbles interleaved by
`RespondChatList`'s new `comments` prop.

### S4.4 Snippets + variables + emoji + AI assist (UAC L4-L5) [FE coder + BE coder]

- `message_snippets` table + admin CRUD (UI-visible, workspace-global v1), "/" picker in
  the composer, `$` variables resolved from ticket context at insert time.
- Emoji picker: client-side component, insert at cursor.
- AI assist: existing CRM AI assistant drafts into the composer input, grounded on the
  visible thread; no new AI surface.

BUILT 2026-08-15 (code + tests; awaiting tester/review). The as-built wire contract and
its seven deviations are written under AC-L5 in the UAC file (that is the contract; this
bullet is the design note). The three that changed the design rather than filling it in:

- **Variable resolution moved to the BACKEND.** `GET .../message-snippets/select` returns
  `resolved_body` alongside the stored `body`, so the preview and the delivered text come
  from one implementation and the fallbacks ("Hi there" for a nameless contact) cannot
  drift. The FE only inserts.
- **`$ticket_ref` is derived (`ENQ-<last 6 hex>`), not a new column.** A real reference
  sequence would need a backfill for every existing tracker to buy nothing a customer can
  tell apart.
- **The AI draft raises instead of degrading.** `product_spec_understanding` falls back to
  a deterministic reading; there is no deterministic way to write a sentence to a customer,
  so a missing/failing/empty model is a 503 with a readable message.

All three composer features are opt-in props on the SHARED
`SharedConversationComposer`, so the complaint / stock-inquiry / PR panels inherit them by
passing a prop and are unchanged until they do. Emoji reuses `emoji-picker-react`, already
a dependency, behind `next/dynamic` with `ssr: false`.

### S4.5 Post-resolve reassurance + close semantics (UAC M) [FE coder + BE coder + n8n peer]

- Drawer stays open post-resolve in a Resolved state (badge, composer disabled, thread
  readable); "recently resolved" affordance links to the SLA tracking listing filtered
  to the contact.
- Close signal (AC-M3 REVISED, user direction 2026-08-14): mirror the respond-send-user
  dual-trigger pattern. n8n peer adds a plain-webhook trigger to respond-close-convo;
  CRM resolve calls it directly with a deterministic payload (tracking id, contact,
  real resolved_by, category/summary), best-effort post-commit. The Respond-trigger
  lane gains a `closedBySource == "user"` gate so the CRM's API close cannot double-run
  the flow; manual Respond-app closes keep working unchanged. Kills the
  literal-"undefined" resolved_by risk by construction.
- AC-M4 DECIDED: keep the contact-facing close message, gated on no-open-tickets.

### S4.6 Inbound quote rendering (UAC L6) [FE coder]

- `message.received` webhook `replyTo` object -> ingest stores quoted context -> thread
  renders "replying to" block above the message body. Outbound quoting stays the
  existing prefix emulation (no API support - verified).

### S4.7 Attachment filename fidelity + in-thread preview (UAC D5-D6) [BE+FE coder]
(added 2026-08-15 from captain hands-on testing)

- D5 root cause: `upload_chat_attachment` key is `{table}/{id}/{uuid}_{name}` - uuid glued
  into the URL basename, and WhatsApp names the delivered document from the basename.
  Fix: uuid as its OWN path segment (`{table}/{id}/{uuid}/{name}`), clean basename;
  verify both R2 CDN and S3 signed-url branches.
- D6: attachment bubbles open the EXISTING CRM attachment preview surface on click; no
  new viewer.
- Live-verified 2026-08-15: delivered payload URL basename is the clean filename
  (canary_d5_stock.xlsx), Respond accepted. Gotcha discovered: Respond 400s some
  extensions ("attachment url is not valid") via its own allowlist - a .txt was
  rejected while the URL served 200; xlsx/jpg fine. Route degrades gracefully
  (per-file failed entry).

Built 2026-08-15 (code + tests; awaiting tester/review):
- D5 `upload_chat_attachment` key is now `{table}/{id}/{uuid}/{name}`; `chat_attachment_basename`
  collapses whitespace to underscores (stem+extension kept). The S3 branch already
  percent-encodes via the CloudFront signer; the R2 branch encodes the key at the call
  site (`quote(key, safe="/")`) rather than changing `get_cdn_base_url`, which every
  stored attachment row's URL format depends on. No Respond fileName field exists (R1).
- D6 handled in the SHARED `RespondChatList` (so complaint / SI / PR / portal threads get
  it too, no fork): an attachment bubble with a url is a button opening
  `components/common/AttachmentPreviewModal` with `{id, name, url}` items - no
  `downloadUrl`, since chat media has no `attachments` row (which also keeps the
  token-authenticated portal thread working: the modal's authenticated byte-fetch is
  never reached). The modal's fallback slide now offers the CDN url as a download when
  there is no same-origin route, so an unpreviewable type is no longer a dead end.

### S4.8 Thread scroll-back + message search (UAC L7-L8) [BE coder + FE coder]
(added 2026-08-15 from captain hands-on testing)

- L7: cursor pagination on scroll-up; prepend with scroll anchoring, dedupe on
  message_id.
- L8: server-side search over `chat_histories` (ILIKE v1), match list + jump-to-message
  + up/down navigation + highlight. Reference: foundryx-shared-service
  `service_backend/modules/omnichannel` chat search (studied before building).

Built 2026-08-15 (code + tests; awaiting tester/review):

- **Lane order flipped vs the original bullet** (see the revision note on AC-L7).
  Respond.io's `cursorId` walk is the primary pagination lane because it is the
  system of record AND returns the full message object, so a scrolled-back page
  renders exactly like the live window; `chat_histories` is the fallback lane and
  the search substrate. Verified against the live API 2026-08-15: `cursorId=<id>`
  returns OLDER messages newest-first, `cursorId=-<id>` returns NEWER messages
  oldest-first, and `GET /message/{id}` supplies the anchor for an `around` jump.
- BE `app/services/conversation_thread_service.py`: `fetch_thread_page`
  (before / after / around + limit, **items always oldest-to-newest**,
  `has_more_older` = "the page came back full") and `search_thread`. The local lane
  is keyset on `(sent_at, id)`, NOT `created_at`: `created_at` is ingest order, so a
  backfilled 2026-05 message written today would sort as the newest thing in the
  thread. Every Respond page is written into `chat_histories` best-effort (explicit
  "which ids do we already hold" probe first, because the dedupe unique index is
  PARTIAL on `created_at >= 2026-08-14` and a pre-cutover row is invisible to
  `ON CONFLICT`). The read marks nothing seen and touches no window cache.
- Routes: `GET .../{tracking_id}/conversation/page` and `.../conversation/search`.
  Migration 327 adds `CREATE EXTENSION IF NOT EXISTS pg_trgm` + a
  `gin (message gin_trgm_ops)` index so the leading-wildcard ILIKE is indexable.
- FE lives in the SHARED layer, not the drawer: `useConversationThread`
  (window + dedupe + fetch-sequence guard + search cursor + around-jump) and
  `ConversationSearchBar`, both under `components/common/conversation/`, plus new
  optional props on the shared `RespondChatList` (`onLoadOlder` / `hasMoreOlder` /
  `isLoadingOlder` / `atConversationStart` / `searchController` / `highlightTerm`).
  The chat list owns the scroll container, so the top-threshold trigger, the
  scroll-anchored prepend (`useLayoutEffect`, `scrollTop += growth`), the bubble ref
  map and the pin-to-bottom suppression live there. Complaint / stock-inquiry / PR
  panels inherit the feature by passing the same loaders; passing none leaves them
  byte-for-byte as they were.
- A search jump to an unloaded message REPLACES the window with the `around` page
  (a spliced window would render a silent gap), and `resetKey` discards the window
  when the drawer swaps tickets in place, so one contact's history can never leak
  into another's thread.

### Phase 4 execution order (user-approved 2026-08-14)

S4.1 and S4.2 first (they close the two live operational gaps: bot does not pause, thread
does not update). S4.3-S4.4 next (parity). S4.5-S4.6 last (polish). ALL slices are built
in full with equal diligence - the order is sequencing, not priority-cutting (user:
"you must build all with diligence").

Revised 2026-08-15 after captain hands-on testing: S4.7 (defect-class, small) runs
immediately, then S4.8, then S4.3 -> S4.4 -> S4.5 -> S4.6 as approved.

**n8n change cycle (binding, user 2026-08-14): plan -> build -> test -> promote, and the
promote step ALWAYS needs the user's explicit call** - per the sorento-crm-n8n working
convention: build on a fork/staging copy, verify with pin-data runs and a dev-contact
canary, publish to the live workflow only on the user's go. Applies to every n8n edit in
this phase (respond-send-user webhook-lane wiring, respond-close-convo webhook trigger +
closedBySource gate, flip-window edits). Decisions locked: AC-M4 keep-the-close-message;
comment mirroring to Respond best-effort; outbound reply-to confirmed impossible
(custom_payload 403 on our channel, tested 2026-08-14).

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

- Secret ops (binding, from n8n rev-2 manifest 2026-08-15): n8n retains the plaintext
  X-CRM-Webhook-Secret verbatim in execution runData on every authenticated call and
  nothing in n8n prevents it - treat the secret as disclosed to anyone with n8n access;
  never dump a webhook-lane execution with the Webhook node included; rotation order is
  digest SET first, then CRM env change, and rotation is complete only when
  pre-rotation executions age out of retention. Durable fix = HMAC-over-body -
  deliberately out of S4.1 scope; becomes a named follow-up if this secret ever gates
  more than the one bot-pause lane.

- Q1. Respond API may not support sticker or reply-to sends (R1) - composer scope shrinks,
  not blocks.
- Q4. `assigned_to` is Text + `assigned_to_id` FK both exist - tickets should write both
  (existing convention) - confirm no consumer reads only one.
- (Resolved) Q2 rollout noise: accepted, no grace period. Q3 placement: existing
  pending-tasks widget + chat drawer.
