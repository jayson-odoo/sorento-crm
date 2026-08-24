# Form SLA Configuration - wiring SLA timers to form transitions

[**SLA Management → Form SLA Configuration**](/sla-management/form-sla-config) is where you decide **which form transition starts an SLA timer**, which marks it **responded**, and which marks it **resolved** - and how stages **chain** into one another for multi-step flows. Each row is **one stage** of one form's SLA pipeline.

This page configures the **Form SLA** system only. The Conversation SLA system (WhatsApp timers) is not configured here - see [Conversation SLA vs Form SLA](./conversation-vs-form-sla.md).

## The page

The header reads **Form SLA Configuration** with the note:

> Per-form SLA stage rules. Each row defines which form transition starts a tracker, marks it responded, and marks it resolved. Chain stages via the Next stage column for multi-step flows (e.g. stock inquiry: project sales → purchasing).

Rows are **grouped by form type** - **Stock Inquiry**, **Purchase Request**, **Sponsorship Form**, **Complaint**, **Ticket** - each in its own card. Add a row with **Add stage**.

## Columns in a stage row

| Column | Meaning |
|--------|---------|
| **Stage** | The stage code (a label for this rung of the pipeline, e.g. `main`, `customer_service`). |
| **Policy** | The [SLA Policy](./sla-policies.md) whose tiers set the response/resolution hours for this stage. |
| **Agent** | The access agent (the team owner) whose tier teams the timer is assigned and escalated through. |
| **Team set** | The team-assignment set used for routing/escalation at this stage (blank = the agent's default). |
| **Start** | The form event that **spawns** a timer for this stage (e.g. `submit`, `send_for_approval`). |
| **Respond** | The event(s) that mark the timer **responded** (stops the response clock). May be a list. |
| **Resolve** | The event(s) that mark the timer **resolved** (closes the stage). May be a list. |
| **Next stage** | The stage to spawn when this one resolves - this is how a multi-step chain advances. |
| **Active** | **Active** / **Inactive**. Inactive rows do not spawn timers. |

A stage is uniquely identified by its **form type + team set** - that pair is what the system uses to figure out which stage a live timer belongs to (and therefore its **Next action**).

## How a chain runs (example: stock inquiry)

1. A **Start** event (e.g. the inquiry is submitted) spawns the first stage's timer, assigned to the **Agent**'s tier team for that **Team set**.
2. A **Respond** event stops the response clock; a **Resolve** event closes the stage.
3. If the stage has a **Next stage**, resolving it spawns that next stage's timer (e.g. project sales → purchasing). The chain continues until a stage with no next stage resolves.

Some chains only advance on a **specific** resolve event - e.g. an approval stage advances to customer service on `approved` but a `rejected` simply closes the stage without advancing. (That "advance only on this event" gate is part of the stage definition.)

## Notify toggles

Each stage can be set to spawn **silently** (assign the timer without notifying the new assignee) and/or escalate silently (not notify on escalation). By default both notify. Use silent spawn for stages that route in the background.

## Add / edit / delete

* **Add stage** / edit (pencil) opens the stage dialog where you pick the form type, stage code, policy, agent, team set, and the start/respond/resolve events plus the next stage.
* Delete (trash) opens a **Confirm delete** dialog: *"Delete the {type}/{stage} SLA stage configuration? Existing trackers are not affected. This action cannot be undone."* - so deleting a config row never disturbs timers already running.

## See also

* [SLA Policies](./sla-policies.md) - the tiers each stage's **Policy** provides.
* [Form SLA Tracking](./conversation-vs-form-sla.md) - where the timers this config spawns show up.
* [SLA Event Logs](./sla-event-logs.md) - the trail each stage's start/respond/resolve/escalation writes.
