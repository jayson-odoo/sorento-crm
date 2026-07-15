# Reading the SLA KPI Dashboard

[**SLA Management → KPI Dashboard**](/sla-management/kpi-dashboard) ("**SLA KPI Dashboard**") shows how your SLA timers are performing: how many opened, how many were responded to and resolved, how many made their deadline vs breached, and which open work is at risk. This page defines **every card and number precisely** so you read them the same way the system computes them.

## Scope selector

Top-right dropdown:

* **All SLA** — every timer.
* **Form SLA** — only Form SLA timers (form types: stock inquiry, purchase request, sponsorship form, complaint, ticket).
* **Conversation SLA** — only Conversation SLA timers (the WhatsApp ones, which carry no form type).

Changing scope re-filters every card below and clears any drilldown filter. (See [Conversation SLA vs Form SLA](./conversation-vs-form-sla.md) for what the split means.)

## The headline counts

* **Opened** — the total number of timers in scope (the *"… total"* figure). Everything else is a slice of this.
* **Responded** — timers where a response was recorded.
* **Resolved** — timers that have been resolved.

## Two deadlines, two clocks

Every timer has **two** deadlines, evaluated independently:

* **Response clock** → **Due at (response)** (`due_at`).
* **Resolution clock** → **Due at (resolution)** (`due_at_resolution`).

"Met" and "breach" are judged **per clock**:

* **Response met** = responded **and** responded at or before the response deadline.
* **Response breach** = responded **after** the deadline, **or** not yet responded and the deadline is already past.
* **Resolution met** = resolved **and** resolved at or before the resolution deadline.
* **Resolution breach** = resolved **after** the resolution deadline, **or** not yet resolved and the resolution deadline is already past.

(A timer with no resolution deadline set is never counted as a resolution met or breach.)

## Section 1 — Stage breakdown

A **MECE** (mutually exclusive, sums to **Opened**) split of every timer into exactly one stage. Each card is clickable and filters the **Tasks** table below; the percentage is *count ÷ Opened*.

* **Awaiting response** — not resolved **and** not responded. (Amber.)
* **Responded, awaiting resolution** — not resolved **and** responded. (Blue.)
* **Resolved** — resolved. (Green — takes priority, so a resolve-without-a-recorded-response still lands here.)

## Section 2 — Timeliness drilldown (within due vs overdue)

How the **completed** work did against its deadline. Denominator is the **subset**, not the whole population.

* **Responded** card — among the **Responded** subset:
  * **Within due** = responded at or before the response deadline.
  * **Overdue** = responded **after** the response deadline.
  * The big number is *within ÷ Responded*.
* **Resolved** card — among the **Resolved** subset:
  * **Within due** = resolved at or before the resolution deadline.
  * **Overdue** = resolved **after** the resolution deadline.
  * The big number is *within ÷ Resolved*.

Note this **Overdue** count differs from "Response breach" above: breach also counts never-responded-past-due timers, whereas this card's overdue is only among timers that *were* responded/resolved.

## Section 3 — Open work at risk (within due vs overdue)

For **open** (unfinished) work, is it still inside its live clock, or already past due but not done? Evaluated against **now**.

* **Awaiting response** card — among **Awaiting response** timers:
  * **Overdue** = response deadline is already past (and one is set).
  * **Within due** = the rest (still inside the response clock, or no deadline set).
* **Responded, awaiting resolution** card — among **Responded, awaiting resolution** timers:
  * **Overdue** = resolution deadline is already past (and one is set).
  * **Within due** = the rest.

## The Tasks table (drilldown)

Sits under the cards. By default it shows all timers in scope; **click a card or a bar segment** (within / overdue) to filter it to exactly that slice — the active filter shows as a badge, and **Clear filter** resets it. The within/overdue filters use the **same** predicates as the cards, so the table totals reconcile with the card numbers.

Columns: **Type**, **Tier**, **Owner**, **Tier started**, **Response due**, **Resolution due**, **Resp** (response time, hours), **Reso** (resolution time, hours), **Esc (m/a)** (manual / auto escalation counts), **Resp met** (✓ / —), **Reso met** (✓ / —). Clicking a row opens the underlying record (complaint / inquiry / request) or, for a pure conversation timer, its Conversation SLA detail.

## Opened vs resolved trend

A line chart of **Opened** vs **Resolved** counts per day (bucketed by the day each timer was initiated), for the current scope.

## Other numbers the dashboard computes

These back the cards (and are available to the AI assistant):

* **% Response met** = response met ÷ (response met + response breach).
* **% Resolution met** = resolution met ÷ (resolution met + resolution breach).
* **Average / median response time** (hours) and **Average / median resolution time** (hours).
* **Escalated**, split into **auto** (overdue scan) and **manual** (user-triggered).

## See also

* [Conversation SLA vs Form SLA](./conversation-vs-form-sla.md) — what the scope selector splits.
* [SLA Policies](./sla-policies.md) — where the response/resolution deadlines come from.
* [SLA Event Logs](./sla-event-logs.md) — the per-event trail behind the aggregates.
* [SLA data analysis (for the AI assistant)](./data-analysis.md) — exact fields and met/breach formulas for answering questions.
