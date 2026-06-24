# PLAN — SLA "Extend" resolution deadline

**Status:** Designed (grilled 2026-06-24). Not started.

Adds an **Extend** action alongside Takeover / Escalate / Resolve / Reassign on SLA task
rows. Lets the current assignee push out the **resolution** deadline (`due_at_resolution`)
when work legitimately can't finish in the policy lead time (e.g. waiting on supplier).

## Decisions (locked)

1. **Clock:** resolution only (`due_at_resolution`). Never the response clock (`due_at`) —
   "response has no excuse, can always reply 'will get back to you'."
2. **Both SLA systems:** conversation SLA (n8n, `source_entity_type` NULL) and form SLA
   stages. Same shared UI + endpoint.
3. **Increment semantics:** user enters *additional* working days (≥1). Base point =
   the **current `due_at_resolution`** — always relative to the existing deadline, NEVER
   `now`. Extending an overdue row adds working days onto its original due (due 13/05 + 1 wd
   = 14/05), not onto today; the result may still be in the past, which is fine. Strictly
   after the current due (days≥1 / target_date guard) so it can only extend, never reduce.
   (Revised 2026-06-24 from the original `max(current, now)` rule per user feedback — the
   deadline must move relative to itself, not jump to today.)
4. **Dual input:** "By working days" (number) ↔ "By specific date" (date picker). Two views
   of one target datetime. Date mode: validate strictly-after current due; derived
   working-day count shown read-only. **Time-of-day preserved** = same time as current
   `due_at_resolution` (matches `add_working_days_from_hours` behaviour).
5. **Gating (button visible when):** `is_resolved = false` AND `due_at_resolution` not null
   AND caller == current assignee AND not pending takeover. NO response-first requirement.
   Allowed at any tier (unlike Escalate's tier<3 cap).
6. **Permission:** assignee only (403 otherwise).
7. **Limits = soft warning, config-driven, never block.** 3 nullable columns on
   `sla_policies`: `max_extension_days_per_request`, `max_extension_count`,
   `max_extension_days_total`. Null = no limit. Breach → warning string in preview/response,
   extension still applies. Single click with visible ⚠ (no double-confirm). Hard guard only:
   increment ≥ 1.
8. **Persistence:** denormalize `extension_count` (int, default 0) + `extension_days_total`
   (numeric, default 0) on `conversation_sla_tracking` (shared table). Event log is the
   immutable trail; these two are fast-read for threshold checks + row chip.
9. **Audit:** one `conversation_sla_event_log` row per extend — `event_type="extend"`,
   `from_time`=old due, `due_at`=new due, `reason`=user text (required), `duration`=working
   days added, `trigger="manual"`, `triggered_by_id`=assignee, tier cols = current tier.
   Add `"extend"` wherever event_type is rendered/filtered in SLA history UI.
10. **Reminders:** reset on extend (`reminder_count`→0, `last_reminder_at`→null) so the new
    deadline gets a fresh reminder cycle.
11. **Notification:** notify the **next escalation tier only** (notify-only, no tier/clock
    mutation — resolve via existing escalation-assignee resolution per system). **If no next
    tier → skip silently.** No team-lead, no coverage subscriber, no self-notify, no contact
    notify. Best-effort (catch + warn, never raise — must not 500 a successful extend).
    New notification kind `deadline_extended` / use_case `sla_deadline_extended`.
12. **Preview is a backend endpoint** (holiday calendar + work-calendar config are
    backend-only). Returns `{new_due_at, working_days, warnings[]}`. FE calls debounced;
    submit posts the confirmed value and backend **recomputes authoritatively** (never trusts
    client preview).
13. **Surfaces:** both the My Pending Tasks widget rows AND the in-form SLA banner
    (PR / stock-inquiry / complaint detail). One shared component.

## Backend

### Migration (single revision)
- `sla_policies`: + `max_extension_days_per_request` (Int, null), `max_extension_count`
  (Int, null), `max_extension_days_total` (Numeric, null).
- `conversation_sla_tracking`: + `extension_count` (Int, default 0, server_default '0'),
  `extension_days_total` (Numeric, default 0, server_default '0').
- `users`: + `notify_email_on_deadline_extended` (Bool, default true),
  `notify_whatsapp_on_deadline_extended` (Bool, default false).

### Endpoints (`app/api/v1/sla/sla_tracking.py`)
- `POST /conversation-sla-tracking/{id}/extend/preview`
  body `{ days?: int, target_date?: "YYYY-MM-DD" }` (exactly one) →
  `{ new_due_at, working_days, current_due_at, warnings: string[] }`.
- `POST /conversation-sla-tracking/{id}/extend`
  body `{ days?: int, target_date?: "YYYY-MM-DD", reason: string }` →
  updated tracking. Validations: reason non-empty; resulting due strictly after current;
  403 if caller≠assignee; 422/409 if resolved or no resolution due; increment≥1.

### Service (`sla_service.py` + `form_sla_service.py`)
- `compute_extension(tracking, days|target_date)` → resulting datetime + working-day count,
  reusing `CalendarService.add_working_days_from_hours` / a working-day counter. Base =
  `max(current due, now)`.
- `evaluate_extension_warnings(tracking, policy, added_days)` → list of breached soft
  thresholds.
- `extend_tracking(...)`: recompute authoritatively → set `due_at_resolution`, bump
  `extension_count` / `extension_days_total`, reset reminders, write `extend` event log
  (wrap `due_at`/`from_time` with `_to_aware_utc()` per the naive-UTC gotcha), then
  best-effort `_notify_next_tier(kind="deadline_extended")`.
- Next-tier resolution: conversation SLA via policy tiers; form SLA via
  `(source_entity_type, team_set_code)` + tier using
  `resolve_team_with_tier_fallback`. No next tier → return without notifying.

### Notification wiring (existing 6-spot pattern)
- `TEMPLATE_DEFAULT_USE_CASES` += `"sla_deadline_extended"`.
- User prefs columns (above) — **also add to BOTH manual `UserResponse(**dict)` builders**
  in `get_user`/`get_me` or the toggle won't surface (CLAUDE.md gotcha).
- `_NOTIFICATION_TYPE_TO_EVENT_KEY` += entry for the extend kind.
- Reuse existing `PARAM_VARIABLES` (`entity_number`, `contact_name`, `reason`,
  `resolve_due_at`, `form_url`) — no new template vars. Title/body branch per-kind.

## Frontend

- Shared `components/.../ExtendDueDialog.tsx` + `ExtendDueButton.tsx`.
- Hook `useExtendSLATracking` (mutation) + debounced preview call in `conversationSLATrackingService.ts`.
- Mode toggle (working days / specific date), live preview from endpoint, required reason,
  soft-warning banner, single-click submit. Min 1 working day; date min = current due + 1 wd.
- Drop button into `MyPendingSLAWidget.tsx` rows + the in-form SLA banner. Render only when
  gating passes (assignee + unresolved + has resolution due + not pending takeover).
- Optional row chip "Extended N×" from `extension_count`.
- On success: invalidate + toast; key the in-form banner query on the entity's changing
  field (updated_at / status) so the new due shows instantly (CLAUDE.md staleness gotcha).

## Three-phase

- **P1 prototype:** dialog + button against mock preview (stub returns `{new_due_at,
  working_days, warnings}` for success / warning / overdue-base cases). Verify states via
  Playwright MCP through the sidebar.
- **P2 wiring + tests:** migration, endpoints, service, notification kind; FE off mocks.
  pytest (extend happy / 403 non-assignee / 422 resolved / reduce-rejected / threshold-warn /
  overdue-base / next-tier-notify + no-next-tier-skip). vitest (dialog days↔date modes,
  warning render, required reason). playwright (widget → extend → row due updates).
- **P3 review:** `/code-review`, then PR.

## User Acceptance Criteria

Gherkin-style. Each maps to a P2 test.

### Visibility & gating
- **UAC-1** Given a row where `is_resolved=false`, `due_at_resolution` is set, I am the
  current assignee, and no takeover is pending — When I view the row in the pending-tasks
  widget OR the in-form SLA banner — Then the **Extend** button is shown.
- **UAC-2** Given a row I do **not** own (assignee ≠ me) — Then the Extend button is hidden,
  and a direct `POST /extend` returns **403**.
- **UAC-3** Given a **resolved** row (`is_resolved=true`) — Then no Extend button; direct
  call returns **422/409**.
- **UAC-4** Given a row with no resolution deadline (`due_at_resolution` null) — Then no
  Extend button.
- **UAC-5** Given a row with a **pending takeover** — Then Extend is hidden/locked (same as
  Reassign).
- **UAC-6** Extend is available at **any tier** (1–3), unlike Escalate.
- **UAC-7** Extend appears for **both** conversation SLA and form SLA rows; it never targets
  the response clock (a response-phase "Reply" row still shows Extend because the resolution
  clock is independent).

### Working-days input mode
- **UAC-8** Given the dialog in "Working days" mode — When I enter `N` (≥1) — Then "New due"
  shows the date `N` working days after `max(current due, now)`, **skipping weekends + KL
  public holidays**, preserving the current due's time-of-day, and labels "+N working days".
- **UAC-9** Entering `0`, negative, or blank days is rejected (cannot reduce / no-op).
- **UAC-10** Given an **already-overdue** row (current due in the past) — When I extend by
  N working days — Then the base is the **current due** (not now): new due = current due + N
  working days, strictly after the current due, even if that is still in the past. (Revised
  2026-06-24: base is current due, never now.)

### Date input mode
- **UAC-11** Given "Specific date" mode — When I pick a date strictly after the current due —
  Then the dialog shows the derived working-day count (read-only) and the resulting datetime
  (current due's time-of-day on that date).
- **UAC-12** Picking a date on/before the current due is rejected inline ("can only extend").

### Soft limits (config on policy)
- **UAC-13** Given the row's policy sets `max_extension_days_per_request` — When my requested
  days exceed it — Then a non-blocking ⚠ warning shows in the dialog AND in the response, and
  the extension **still applies** on confirm.
- **UAC-14** Same soft-warn behaviour for `max_extension_count` (this would be the Nth
  extension beyond the cap) and `max_extension_days_total` (cumulative would exceed the cap).
- **UAC-15** Given a policy with all three thresholds **null** — Then no warning ever shows.
- **UAC-16** Confirming a warned extension is a **single click** (no second confirm modal).

### Reason & submit
- **UAC-17** Reason is **required**; submitting empty reason is rejected (client + server).
- **UAC-18** On confirm, the backend **recomputes** the new due authoritatively (ignores the
  client-previewed value) and persists it to `due_at_resolution`.
- **UAC-19** After a successful extend, the widget row and detail banner show the **new due
  immediately** (no manual refresh).

### Side effects
- **UAC-20** Each extend writes exactly one `conversation_sla_event_log` row with
  `event_type="extend"`, old due (`from_time`), new due (`due_at`), working-days added
  (`duration`), the reason, `trigger="manual"`, and me as `triggered_by_id`. The SLA history
  view renders it.
- **UAC-21** `extension_count` increments by 1 and `extension_days_total` increases by the
  added working days.
- **UAC-22** Reminder state resets (`reminder_count`→0, `last_reminder_at`→null); the new
  deadline drives a fresh reminder/escalation cycle (auto-escalation breach point moves to
  the new due).
- **UAC-23** The **next escalation tier** assignee receives a `deadline_extended`
  notification (in-app always; email/WhatsApp per their `notify_*_on_deadline_extended`
  prefs, using the `sla_deadline_extended` template). I (the actor) am **not** notified.
- **UAC-24** Given the row is already at the **top tier** (no next tier) — Then **no
  notification** is sent; the extend still succeeds.
- **UAC-25** Given the notification send fails — Then the extend still returns success (200);
  the failure is logged best-effort, never surfaced as a 500.
