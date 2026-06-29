# SLA Policies — the tier ladder behind every SLA timer

An **SLA policy** is a named set of **tiers**, where each tier says how many hours you have to **respond** and to **resolve**. Both the Conversation SLA and the Form SLA systems point at these policies, so editing a policy's tier changes the deadlines every new timer on that policy gets. Manage them under [**SLA Management → SLA Policies**](/sla-management/sla-policies).

## What a policy is made of

* A **policy** — has a **Code**, a **Name**, an optional **Description**, and a **Status** (Active / Inactive).
* One or more **tiers** — each tier has a **Tier Level** (1, 2, 3…), a **Tier Name**, **Response Hours**, and **Resolution Hours**.

A timer always sits on **one tier** at a time (its **Current Tier**). The tier sets two deadlines:

* **Due at (response)** = when the tier started + that tier's **Response Hours**.
* **Due at (resolution)** = when the tier started + that tier's **Resolution Hours**.

Hours are counted against the **working-hours / holiday calendar**, not raw wall-clock, and **Response Hours** are decimal — e.g. `0.5` = 30 minutes, `24` = one working day's worth of hours, `72` = three.

## View the policy list

Open [**SLA Management → SLA Policies**](/sla-management/sla-policies). The grid shows **Code**, **Name**, **Description**, **Tiers** (count), and **Status**. Search with **Search SLA policies...**; filter by **Status** (**All statuses** / **Active** / **Inactive**).

## Create a policy

1. From the list, start a new policy. You'll see **Create SLA Policy**.
2. Fill in **Code \*** (e.g. `SLA-001`), **Name \***, and an optional **Description**.
3. Save. Then add tiers (below).

## Add / edit tiers

1. On the policy, click **Add Tier** (or edit an existing one).
2. In the tier dialog fill in:
   * **Tier Level \*** — the rung on the ladder (e.g. `1`).
   * **Tier Name \*** — e.g. `Tier 1 - Initial Response`.
   * **Response Hours \*** — e.g. `0.5`, `24` or `72`.
   * **Resolution Hours \*** — e.g. `0.5`, `24` or `72`.
3. Save. The tiers table lists each tier with **Tier Level**, **Tier Name**, **Response Hours**, **Resolution Hours** and the **Users** assigned at that tier.

Tier levels must be unique within a policy. If a timer ever asks for a tier level that isn't defined, the system **clamps** to the nearest defined tier (the highest tier at or below the one requested, or the lowest tier if none qualifies) so the clock still gets sensible hours.

## How escalation uses tiers

Escalating a timer moves it **up to the next tier** and reassigns it per policy. The tier ladder tops out at **tier 3** — once a timer is at tier 3 there is nowhere higher to send it, so **Escalate** is unavailable. (The day-to-day escalate flow is covered in [Escalate a task or enquiry](../_shared/escalate-a-task-or-enquiry.md).)

## Extend-deadline soft limits

A policy can also carry optional caps on how far the resolution deadline may be pushed with **Extend**: a max per single extend, a max number of extends, and a max cumulative working days. These are **warnings only** — exceeding a cap is flagged but the extension still applies. (Extending is covered in [Dashboard — My Tasks & My Team Tasks](../_shared/dashboard-my-tasks-sla.md).)

> Note: these soft-limit caps are stored on the policy but are not currently editable from the **SLA Policies** form in the UI — confirm the values with an administrator if a cap matters to you.

## Delete a policy

Deleting a policy is a **hard delete** behind a **Confirm delete** dialog and also removes its tiers. Don't delete a policy that still has live timers pointing at it.

## See also

* [Conversation SLA vs Form SLA](./conversation-vs-form-sla.md) — which timers exist and how they differ.
* [Form SLA Configuration](./form-sla-configuration.md) — picks a policy per form stage.
* [Reading the KPI Dashboard](./reading-the-kpi-dashboard.md) — how response/resolution hours turn into met/breach numbers.
