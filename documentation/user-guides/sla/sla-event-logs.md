# SLA Event Logs - the audit trail for every SLA timer

[**SLA Management → SLA Event Logs**](/sla-management/escalation-logs) is the immutable history of what happened to SLA timers: every **escalation**, **response**, **resolution**, and **reassignment**, with who and when. It covers **both** SLA systems (Conversation SLA and Form SLA share the same log).

> The in-page heading reads **Event Logs**; the menu entry is **SLA Event Logs**.

## What an event row shows

| Column | Meaning |
|--------|---------|
| **Event Type** | `escalation`, `response`, `resolution`, or `reassignment`. |
| **Tracking ID** | The id of the SLA timer this event belongs to. |
| **From Tier** | The tier the timer was on before (for escalations). |
| **To Tier** | The tier it moved to (for escalations). |
| **Event At** | When the event happened. |
| **Assigned To** | The user the timer was assigned to at the event. |
| **Response Time** | For response events: hours taken to respond. |
| **Resolution Time** | For resolution events: hours taken to resolve. |

## Search & filter

* **Filter by tracking ID...** - paste a timer's tracking id to see only its history.
* **Advanced filters** (the filter popover):
  * **Event type** - **All events** / **Escalation** / **Reassignment** / **Response** / **Resolution**.
  * **Assigned to** - **All assignees** or a specific Respond-synced user.
  * **Clear advanced filters** resets both.
* **Export** produces `sla_event_logs_export.xlsx`.

## Things worth knowing

* Escalations also record **how** they fired - **auto** (the overdue scan moved the timer up) or **manual** (a person clicked Escalate) - and, for manual ones, **who** triggered it. The KPI Dashboard splits escalations into auto vs manual using this.
* Escalation events carry a **reason** (manual escalations always ask for one).
* The log is the **source of truth** for history - extend/resolve actions overwrite some fields on the live timer, but the events here survive, so the trail stays complete.
* Response/resolution events store their **duration in hours**.

## See also

* [Reading the KPI Dashboard](./reading-the-kpi-dashboard.md) - aggregates these events (escalations auto vs manual, etc.).
* [Escalate a task or enquiry](../_shared/escalate-a-task-or-enquiry.md) - the action that writes an `escalation` event.
* [Conversation SLA vs Form SLA](./conversation-vs-form-sla.md) - both systems log here.
