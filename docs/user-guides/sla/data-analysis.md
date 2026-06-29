# SLA data analysis (for the AI assistant)

Reference for answering analytical questions about SLA timers. Field names, clocks, and met/breach rules below are taken verbatim from the backend (`app/models/sla.py`, `app/services/sla_kpi_service.py`, `app/services/sla_service.py`, `app/services/form_sla_service.py`). Compute met/breach exactly as defined — they are split **per clock** (response vs resolution), not a single pass/fail.

## The two SLA systems (one table, two meanings)

Conversation SLA and Form SLA share one table, `conversation_sla_tracking`, discriminated by **`source_entity_type`**:

* **Form SLA** — `source_entity_type` ∈ `FORM_SLA_TYPES` = `stock_inquiry`, `purchase_request`, `sponsorship_form`, `complaint`, `ticket`. Per-entity, **multiple open rows allowed** (one per active stage).
* **Conversation SLA** — `source_entity_type` IS NULL **or** NOT IN `FORM_SLA_TYPES`. One open row per contact (mirrors Respond.io).
* **KPI scope** maps directly: `scope=form` → in `FORM_SLA_TYPES`; `scope=conversation` → null/not-in; `scope=all` → no filter.

Never aggregate across both unless the user asks for "all SLA". If they say "conversations" use the conversation scope; "forms/complaints/inquiries/requests/tickets" use the form scope (or filter `source_entity_type` to the one type).

---

## Entity: SLA Policy (`sla_policies` + `sla_policy_tiers`)

The tier ladder that sets deadlines.

**Policy fields:** `id`, `code`, `name`, `description`, `is_active`, `max_extension_days_per_request`, `max_extension_count`, `max_extension_days_total` (extend soft-limits; nullable = no limit, breach is warning-only), `created_at`, `updated_at`.

**Tier fields (`sla_policy_tiers`):** `id`, `policy_id`, `tier_level` (1, 2, 3…; unique per policy), `tier_name`, `response_hours` (decimal — `0.5` = 30 min), `resolution_hours` (default 24), `created_at`, `updated_at`.

**Tier resolution / clamp:** a row's clock uses the tier matching `(policy_id, current_tier)`. If that exact tier is missing, clamp to the highest tier ≤ requested, else the lowest defined tier.

---

## Entity: Conversation SLA tracking row (`conversation_sla_tracking`, conversation scope)

**Identity / routing:** `id`, `policy_id`, `current_tier`, `assigned_to_id` (FK users), `assigned_to` (legacy text), `respond_contact_id`, `agent_id`, `team_set_code`, `message_id`.

**The two clocks:**

* **Response clock:** `due_at` = `current_tier_started_at` + tier `response_hours` (working-hours/holiday calendar). Completion flagged by `is_responded` / `responded_at` / `responded_by`. `response_time` = recorded hours to respond.
* **Resolution clock:** `due_at_resolution` = `current_tier_started_at` + tier `resolution_hours`. Completion flagged by `is_resolved` / `resolved_at` / `resolved_by`. `resolution_duration` = recorded hours to resolve.

**Escalation:** `escalated_at`, `escalation_reason`, `current_tier`, `current_tier_started_at`. Escalation moves `current_tier` up and resets `current_tier_started_at` (so both clocks restart on the new tier). **Tier ceiling = 3** (no escalation above tier 3).

**Extend counters:** `extension_count`, `extension_days_total` (denormalized; the event log is the trail).

**Date columns:** `initiated_at` (when the row opened — KPI date filters and the trend bucket use this), `current_tier_started_at`, `due_at`, `due_at_resolution`, `responded_at`, `resolved_at`, `escalated_at`, `created_at`, `updated_at`. **All stored as naive UTC.** "Now" for overdue checks is `datetime.utcnow()`.

---

## Entity: Form SLA tracking row (`conversation_sla_tracking`, form scope)

Same columns as above, plus meaning carried by:

* `source_entity_type` — the form type (one of `FORM_SLA_TYPES`).
* `source_entity_id` — the form record's id.
* `team_set_code` — copied from the spawning config; `(source_entity_type, team_set_code)` uniquely identifies the **stage**.
* Server-resolved (not columns): `reference` (human entity number — complaint_number / inquiry_number / request_number / ticket_number), `next_action` (humanized stage to-do, e.g. *Send for approval*, *Approve*, *Mark CS resolved*).

Multiple form rows can be open for the same `source_entity_id` (different stages). Don't assume one-per-entity.

---

## Entity: Event Log (`conversation_sla_event_log`)

Immutable history; one row per event. **Join to a timer via `sla_tracking_id`.**

**Fields:** `id`, `sla_tracking_id`, `event_type` (`escalation` | `response` | `resolution` | `reassignment`), `from_tier`, `to_tier`, `event_at` (when), `from_time`, `duration` (hours), `reason`, `assigned_to` / `assigned_to_id`, `due_at`, `response_time`, `resolution_time`, `reminder_count`, `last_reminder_at`, `trigger` (`auto` = overdue scan, `manual` = user-clicked), `triggered_by_id` (the human for manual; NULL for auto), `created_at`.

Escalation auto-vs-manual = `event_type='escalation'` grouped by `trigger`.

---

## Met / breach — compute EXACTLY like this

`now = utcnow()`. Evaluate the two clocks independently.

**Response clock:**
* **Response met** ⇔ `is_responded AND responded_at <= due_at`.
* **Response breach** ⇔ `(is_responded AND responded_at > due_at)` OR `(NOT is_responded AND due_at < now)`.
* **% response met** = response_met ÷ (response_met + response_breach).

**Resolution clock:**
* **Resolution met** ⇔ `is_resolved AND due_at_resolution IS NOT NULL AND resolved_at <= due_at_resolution`.
* **Resolution breach** ⇔ `(is_resolved AND due_at_resolution NOT NULL AND resolved_at > due_at_resolution)` OR `(NOT is_resolved AND due_at_resolution NOT NULL AND due_at_resolution < now)`.
* **% resolution met** = resolution_met ÷ (resolution_met + resolution_breach).
* Rows with `due_at_resolution IS NULL` count as **neither** met nor breach for resolution.

**Stage partition** (MECE, sums to opened): `Resolved` = `is_resolved`; `Responded, awaiting resolution` = `NOT is_resolved AND is_responded`; `Awaiting response` = `NOT is_resolved AND NOT is_responded`. (Resolved takes priority.)

**Subset timeliness (completed work):** among **responded** rows, late ⇔ `responded_at > due_at`; among **resolved** rows, late ⇔ `resolved_at > due_at_resolution`. Denominator = the subset (responded / resolved), distinct from breach which also counts never-finished-past-due.

**Open-work at risk:** `Awaiting response` overdue ⇔ `NOT resolved AND NOT responded AND due_at NOT NULL AND due_at < now`; `Responded, awaiting resolution` overdue ⇔ `NOT resolved AND responded AND due_at_resolution NOT NULL AND due_at_resolution < now`.

**Durations:** `response_time` and `resolution_duration` (and event-log `duration` / `response_time` / `resolution_time`) are in **hours**. Averages = `avg(response_time)` / `avg(resolution_duration)`; medians computed over non-null values.

**Common filters:** scope (form/conversation/all); `initiated_at` between date_from/date_to; `source_entity_type` = a specific type; `assigned_to_id` = an assignee; for events, `event_type` and `trigger`.

---

## Example questions and how to answer them

1. **"How many overdue conversation SLAs does Aisha have right now?"** — scope=conversation, `assigned_to_id`=Aisha, count rows that are open-overdue on either clock: `(NOT responded AND due_at < now)` or `(responded AND NOT resolved AND due_at_resolution < now)`.
2. **"What's our average response time this month?"** — filter `initiated_at` in this month; `avg(response_time)` over non-null, in hours. Offer median too (more robust to outliers).
3. **"Form SLA breaches by entity type last quarter."** — scope=form, `initiated_at` in quarter, group by `source_entity_type`; per group count response_breach and resolution_breach (state them separately — they're different clocks).
4. **"How many tasks were escalated to tier 2 or higher last week?"** — `conversation_sla_event_log` where `event_type='escalation' AND to_tier >= 2 AND event_at` in last week. If they mean current state, count timers with `current_tier >= 2`.
5. **"What % of conversation SLAs were resolved within due?"** — scope=conversation; resolution_met ÷ (resolution_met + resolution_breach). If they mean "within due among resolved ones", use resolved-subset timeliness: `count(resolved AND resolved_at <= due_at_resolution) ÷ count(resolved)`. Ask which they want if ambiguous.
6. **"Who has the most open SLA tasks?"** — group open rows (`NOT is_resolved`) by `assigned_to_id`, order desc; resolve ids to user name/email for display.
7. **"How many escalations were manual vs automatic last month?"** — events `event_type='escalation'`, `event_at` in month, group by `trigger` (`manual` / `auto`).
8. **"Which complaints breached resolution and are still unresolved?"** — scope=form, `source_entity_type='complaint'`, `NOT is_resolved AND due_at_resolution NOT NULL AND due_at_resolution < now`; show `reference`.
9. **"Average resolution time for purchase requests vs sponsorship forms."** — scope=form, group by `source_entity_type` in (`purchase_request`,`sponsorship_form`), `avg(resolution_duration)` hours.
10. **"How many SLA timers opened vs resolved each day this week?"** — bucket by `date(initiated_at)`; per day count opened (all) and resolved (`is_resolved`). This is the trend chart's data.
11. **"Show tier-3 tasks awaiting response that are overdue."** — `current_tier=3 AND NOT is_responded AND due_at < now`.
12. **"What's the response-met rate for stock inquiries this month, and who's dragging it down?"** — scope=form, `source_entity_type='stock_inquiry'`, `initiated_at` this month: overall % response met, then per-`assigned_to_id` breach_count (response_breach + resolution_breach) to find the worst.

## Disambiguation reminders

* "Within due %" is ambiguous: it can mean **met ÷ (met+breach)** (counts never-finished-past-due as breach) or **within ÷ subset** (only among finished). Default to the subset interpretation for "of the resolved/responded ones", else the met-rate. State which you used.
* "Overdue" with no clock named: report both response-overdue and resolution-overdue, or ask.
* Always resolve `assigned_to_id` to a person's name/email; never surface raw UUIDs.
* `due_at`/`responded_at`/etc. are naive UTC — compare to `utcnow()`, not local time.
