# PLAN - Takeover cooldown (pending-intent + veto window)

**Status:** Grilled + designed 2026-06-23. Not started. Three-phase: FE prototype → BE wiring+tests → review.

## Business value / user process

Takeover today is **instant + irreversible**: a peer clicks Takeover on a Team Task and it's
reassigned the moment they confirm. Problem: the original assignee might be *actively working it*
right now - the grab yanks it out from under them with no recourse.

This feature inserts a **configurable cooldown** (default 60s, global) between the click and the
actual reassignment, turning takeover into a **pending intent the current owner can veto**:

1. Peer (initiator) clicks Takeover → confirm. A **pending takeover request** is created
   (`commit_at = now + cooldown`). **Nothing about the assignment changes yet** (model A).
2. Original assignee is notified (in-app always; email/WhatsApp gated by their **assignment**
   channel toggles) - "X wants to take over CMP-0010, reject by <time>", with a deep link.
3. During the window BOTH parties can stop it: initiator **Cancel**, owner **Reject**. The owner
   doing any terminal action (resolve / reassign-away / escalate-out) is an **implicit veto**.
4. If unchallenged at `commit_at`, the **scheduler sweep** commits the takeover (today's exact
   reassignment logic) and notifies both parties.

Value: protects the person actually doing the work; makes contested ownership explicit and
auditable; keeps the customer's SLA clock untouched (cooldown never pauses escalation).

## Decisions (grilled - all confirmed)

| # | Decision |
|---|----------|
| Q1 | **Model A - pending intent.** Assignee stays the original throughout cooldown. Initiator's click is an intent, not a transfer. Zero assignment change until commit. SLA clocks/escalation keep pointing at the real owner. |
| Q2 | **Owner terminal action = implicit veto.** Resolve, reassign-away, or escalate-out by the owner during cooldown voids the pending takeover + notifies initiator. |
| Q3 | **One pending takeover per task, FCFS lock.** A second peer's Takeover button is disabled ("pending · <initiator> · m:ss") until the first resolves. |
| Q4 | **Soft lock on human mutations** (third-party Reassign blocked while pending). **Auto-escalation always wins** - SLA breach mid-cooldown escalates and voids the pending takeover; never freeze the SLA machinery. |
| Q5 | **Scheduler sweep commits** (reuses heartbeat + `scheduled_tasks` registry). DB `commit_at` is truth; UI bar is cosmetic. Commit lands within one tick (~10s) of deadline. **Seeded via data migration** so it exists on live deploy (idempotent, like `product_discontinued_check`). |
| Q6 | **Global setting** `takeover_cooldown_seconds` on `system_settings`, default **60**, **`0` = instant** (today's behavior; clean kill-switch). Stored in seconds. Edited on General settings tab. Per-team deferred. |
| Q7 | **New table `sla_takeover_requests`** (full intent lifecycle + audit). Partial-unique on pending mirrors migration-180 singleton pattern. Applies to **both** conversation and form SLA rows. |
| Q8 | **Gate on assignment toggles** (`notify_{email,whatsapp}_on_assignment`); in-app always. Matrix below. |
| Q9 | Reject deep link → **`/?takeover=<tracking_id>`** (query param survives `callbackUrl` deep-link-after-login; hash would not). Lands on the home **My Pending** widget. |
| Q10 | **Pin-fetch banner**, not compute-and-jump. Param present → fetch that one tracking row by id → render pinned flashing banner at top of widget with Reject, above the paginated list. Bulletproof vs pagination/sort/search. |
| Q11 | Bar driven by server **`commit_at`**, animated locally, re-synced on refetch. At zero → "**Finalizing…**" + poll until sweep commits (≤10s gap accepted). Light `refetchInterval` (~5 - 10s) only while a pending takeover is on screen. |
| Q12 | `POST /{tracking_id}/takeover` **becomes initiate** (creates pending, returns `{request_id, commit_at}`; **cooldown 0 → commit inline**). New: `POST /takeover-requests/{request_id}/cancel`, `/reject`. **No public commit endpoint** (sweep + inline-0 only). |
| Q13 | **Cancel** = initiator + admin. **Reject** = contested assignee + admin. **Snapshot `contested_assignee_id`** on the request. **Unassigned task → instant commit** (no owner to protect, same path as cooldown 0). |
| Q14 | **Defense in depth (C):** owner-actions actively void (status→`voided`, notify initiator now) AND the sweep **re-validates at commit** - (1) not resolved, (2) `assigned_to_id` still == `contested_assignee_id`, (3) initiator still eligible - and **re-derives initiator tier/team/agent at commit time**. Any fail → `voided`, notify, don't flip. |
| Q15 | Original's own My Pending row shows inline "**Being taken over · m:ss · Reject**" (organic discovery) in addition to the guided banner. **All terminal request rows retained** for audit; partial-unique only blocks a second *pending*. |

## Notification matrix (Q8)

In-app always; email/WhatsApp gated by the **recipient's** `notify_{email,whatsapp}_on_assignment`.

| Event | Recipient | Channels |
|---|---|---|
| Cooldown **starts** | original (contested) assignee | in-app + assignment toggles; includes reject deep link |
| Owner **rejects** | initiator | in-app + assignment toggles ("<original> kept the task") |
| Initiator **cancels** | original assignee | **in-app only** (low stakes) |
| Cooldown **commits** | original ("taken over by X") **and** initiator ("you now own CMP-0010") | in-app + assignment toggles |
| **Voided** (resolve/reassign/escalate) | initiator | in-app + assignment toggles (reason: resolved/escalated/…) |

Known limitation: with a short cooldown, the start-email may arrive after commit (outbox drainer +
SMTP latency). In-app + the persistent banner (which shows "already taken over" post-commit) cover
this gracefully. Not a blocker.

## Data model

**New table `sla_takeover_requests`:**
```
id                    uuid pk
tracking_id           fk conversation_sla_tracking(id)   # both conversation + form SLA
initiator_id          fk users(id)
contested_assignee_id fk users(id) nullable               # snapshot at create; null = was unassigned
team_id               uuid                                 # queue team context for tier re-derivation
status                text  pending|committed|cancelled|rejected|voided
commit_at             timestamp (naive UTC)                # now + cooldown
resolution_reason     text nullable                        # 'cancel'|'reject'|'resolved'|'escalated'|'reassigned'|'committed'|'ineligible'
resolved_by_id        fk users(id) nullable
created_at            timestamp
resolved_at           timestamp nullable
```
- **Partial unique index** `WHERE status='pending'` on `tracking_id` → at most one pending per task.
- Index `(status, commit_at)` for the sweep.

**`system_settings`:** add `takeover_cooldown_seconds Integer NOT NULL default 60 server_default '60'`.

## Migrations

1. `sla_takeover_requests` table + partial-unique(pending) + `(status, commit_at)` index.
2. `system_settings.takeover_cooldown_seconds` (default 60, server_default '60').
3. **Data migration**: seed `scheduled_tasks` row `takeover_request_commit` (interval ~10 - 15s),
   idempotent INSERT-if-absent (mirror `c1d2e3f4a5b6_seed_product_discontinued_task.py`).

## Backend

- **`SlaTakeoverService`** (or methods on `SLATrackingService`):
  - `initiate(tracking_id, initiator_id, team_id)` → if cooldown==0 OR task unassigned →
    commit inline (existing `takeover()` body), return committed tracking. Else create pending
    request, fire start-notification, return request. Validates: can-act, not resolved, no existing
    pending (FCFS 409/idempotent - decide: **409** with the existing request so UI shows the bar).
  - `cancel(request_id, actor_id)` - initiator/admin; status→cancelled; notify original (in-app).
  - `reject(request_id, actor_id)` - contested-assignee/admin; status→rejected; notify initiator.
  - `commit_due()` - sweep handler: for each pending past `commit_at`, re-validate (Q14), then run
    the **existing takeover reassignment logic** (re-derive tier/team/agent at commit, flip
    assignee, advance RR cursor, event log, Respond push) and notify both; else `voided` + notify.
  - `void_for_tracking(tracking_id, reason)` - called by resolve/reassign/escalate paths to
    actively void any pending request (best-effort, post-commit side-effect rules).
- **Hook void into** `reassign()`, the resolve path, and the escalation path
  (`_escalate_tracker` / scheduler escalation) - active voiding (Q14).
- **Scheduler:** `register_handler("takeover_request_commit", _handler_takeover_commit)` in
  `task_scheduler.py`; handler calls `commit_due()`.
- **Notifications:** reuse `create_with_channel_preferences` with `email_pref_attr=
  "notify_email_on_assignment"`, `whatsapp_pref_attr="notify_whatsapp_on_assignment"`. Distinct
  `source_entity_type` (e.g. `takeover`) + `event_type` so idempotency keys don't collide with the
  normal assignment notifications. Wrap naive datetimes with `_to_aware_utc()` (event-log lesson).
- **Endpoints** (Q12): `POST /{tracking_id}/takeover` (initiate),
  `POST /takeover-requests/{request_id}/cancel`, `POST /takeover-requests/{request_id}/reject`.
  Pin-fetch: ensure a `GET /conversation-sla-tracking/{tracking_id}` single-row endpoint exists for
  the banner (add if missing). Each pending response carries `{request_id, commit_at, initiator_name,
  contested_assignee_name, status}` so both widgets render the bar + correct buttons.

## Frontend

- **Settings (General tab):** number input "Takeover cooldown (seconds)", 0 = instant. Wire through
  `system_settings` general settings form + its API proxy.
- **My Team widget / team-pending page (initiator + observers):**
  - Pending row: depleting bar (server `commit_at`) + **Cancel** (initiator only); Reassign hidden.
  - Observer row (other members): "Takeover pending · <initiator> · m:ss", buttons disabled.
- **My Pending widget (original):**
  - `?takeover=<tracking_id>` → pin-fetch that row → flashing banner at top with bar + **Reject**;
    clear param after action/dismiss; banner shows terminal state if already resolved.
  - Inline "Being taken over · m:ss · Reject" on the contested row even without the link (organic).
- **Countdown component:** shared, `commit_at`-driven, local animation, "Finalizing…" at zero.
- **Polling:** react-query `refetchInterval` ~5 - 10s while any pending takeover visible; off otherwise.
- Hooks: `useInitiateTakeover` (already `useTakeover` - change return to request), `useCancelTakeover`,
  `useRejectTakeover`, `useTakeoverRow(trackingId)` (pin-fetch).

## Tests

**pytest:**
- initiate: cooldown>0 → pending row, no assignment change, start-notif fired; cooldown==0 → instant
  commit (old behavior); unassigned task → instant commit; second initiate while pending → 409 returns
  existing request.
- cancel: initiator ok, admin ok, stranger denied; status→cancelled; original notified in-app only.
- reject: contested-assignee ok, admin ok, stranger denied; status→rejected; initiator notified.
- active void: owner resolve / reassign / escalate during pending → request voided + initiator notified.
- sweep commit: pending past commit_at → reassignment runs, tier re-derived at commit, RR cursor
  advanced, event log written, both notified; re-validation fails (resolved / owner changed /
  initiator ineligible) → voided, no flip.
- channel gating: email/whatsapp follow recipient assignment toggles; in-app always.
- both conversation and form SLA rows covered.
- migration seed: `takeover_request_commit` task present + idempotent.

**vitest:** countdown component (animates, Finalizing at zero); My Team pending row (Cancel, observer
disabled state); My Pending banner (pin-fetch loading/empty/terminal); inline reject affordance;
settings cooldown field.

**playwright:** initiate from My Team → bar appears → (a) original rejects via banner → row returns,
initiator notified; (b) initiator cancels; (c) let it ride → sweep commits → row moves to initiator's
My Pending. Assert `/takeover`, `/cancel`, `/reject` network calls. cooldown=0 path = instant.

## Open implementation notes

- Reuse the **existing `takeover()` reassignment body** verbatim for the commit step - don't fork the
  tier/RR/event-log/Respond logic; extract it into a `_commit_takeover(tracking, initiator, team_id)`
  helper called by both the inline-0 path and the sweep.
- FCFS conflict: return **409 with the existing pending request payload** so the UI just renders the
  running bar instead of erroring.
- `commit_at` is frozen at create - changing the global setting mid-flight does NOT move in-flight
  deadlines (correct).
- Top-tier task goes overdue mid-cooldown (no escalation possible) → no void; overdue doesn't change
  owner, takeover commits normally at T.
