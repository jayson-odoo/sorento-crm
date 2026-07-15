# Conversation SLA vs Form SLA — what the difference is

The CRM tracks two kinds of SLA timers. They look similar (both have tiers, deadlines, escalation, and event logs) and they share the same underlying records, but they are started by different things and behave differently. This page explains which is which so you open the right screen.

## The one-sentence version

* **Conversation SLA** — one live timer per **WhatsApp contact**, mirroring their open Respond.io conversation. Started automatically by the chat integration. View it under [**SLA Management → Conversation SLA Tracking**](/sla-management/conversation-sla-tracking).
* **Form SLA** — one timer per **form record** (complaint, stock inquiry, purchase request, sponsorship form, ticket), and a record can have **several** over its life as it moves through stages. Started by transitions on the form itself. View it under [**SLA Management → Form SLA Tracking**](/sla-management/form-sla-tracking).

## Conversation SLA

* **What it tracks:** the responsiveness clock on a single WhatsApp conversation with a contact.
* **How many can be open:** at most **one open timer per contact** at a time — exactly like Respond.io, where a contact has one open conversation (unresolved = open, resolved = closed).
* **Who starts it:** the chat automation (n8n), when a contact messages in. You do not create these by hand.
* **Resolving it:** closes the conversation in Respond.io and stops the clock.
* **Columns you'll see:** **Contact Phone**, **Contact Name**, **Policy**, **Current Tier**, **Assigned To**, **Initiated At**, **Due at (response)**, **Due at (resolution)**, **Time elapsed**, **Response**, **Resolution**, **Agent Code**, **Team Set Code**, **Status**.

## Form SLA

* **What it tracks:** the responsiveness clock on one **stage** of a form record's workflow.
* **How many can be open:** **multiple** — one per active stage. A purchase request can have a "send for approval" stage timer, then an "approve" stage timer, then a "customer service" stage timer, spawned one after another as the record advances. Form timers are **never** merged into one.
* **Who starts it:** a transition on the form (e.g. submitting, sending for approval, approving) that matches a rule in [**SLA Management → Form SLA Configuration**](/sla-management/form-sla-config).
* **Supported form types:** **Stock Inquiry**, **Purchase Request**, **Sponsorship Form**, **Complaint**, **Ticket**.
* **Extra columns vs Conversation SLA:** **Reference** (the human-readable record number), **Type** (the form type), and **Next action** (the concrete to-do for the current stage, e.g. *Send for approval*, *Approve*, *Mark CS resolved* — derived from the stage config, not a generic "respond/resolve").

## Why they're easy to confuse (and how the system keeps them apart)

Under the hood both kinds of timer live in the **same** table. The system tells them apart by a hidden *source entity type* field:

* **Form SLA** rows carry a form type (`stock_inquiry`, `purchase_request`, `sponsorship_form`, `complaint`, or `ticket`).
* **Conversation SLA** rows carry **none** of those.

This is why there are two separate listing pages and why the **KPI Dashboard** has a scope selector (**All SLA** / **Form SLA** / **Conversation SLA**) — picking a scope filters the numbers to one system or the other. Chat events (from WhatsApp / Respond.io) only ever touch **Conversation** SLA; the in-record SLA banner on a complaint / inquiry / request / form only ever touches **Form** SLA.

## Quick comparison

| | Conversation SLA | Form SLA |
|---|---|---|
| Timer is keyed to | a WhatsApp **contact** | a **form record** (and stage) |
| Open timers at once | **one** per contact | **many** (one per active stage) |
| Started by | chat automation (n8n) | a form transition (per config) |
| Resolving it | closes the Respond.io conversation | closes the stage; may spawn the next stage |
| Has a **Reference** / **Type** / **Next action** column | no | yes |
| Listing page | [Conversation SLA Tracking](/sla-management/conversation-sla-tracking) | [Form SLA Tracking](/sla-management/form-sla-tracking) |

## See also

* [SLA Policies](./sla-policies.md) — the tier ladder (response/resolution hours per tier) that both systems share.
* [Form SLA Configuration](./form-sla-configuration.md) — the rules that start, respond, and resolve form-stage timers.
* [Reading the KPI Dashboard](./reading-the-kpi-dashboard.md) — the metrics, with the scope selector that splits the two systems.
* [SLA Event Logs](./sla-event-logs.md) — the immutable trail of escalations, responses, and resolutions for any timer.
* [Dashboard — My Tasks & My Team Tasks](../_shared/dashboard-my-tasks-sla.md) and [Escalate a task or enquiry](../_shared/escalate-a-task-or-enquiry.md) — the day-to-day actions on your own pending tasks.
