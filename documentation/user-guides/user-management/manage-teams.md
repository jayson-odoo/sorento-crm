# Manage teams and round-robin assignment

Use this when you need to group users for **automatic SLA assignment**. A team is an ordered list of members; SLA work is handed out round-robin among the members flagged for auto-assignment. Teams also form a **hierarchy** (a parent-team member can see and act on all descendant teams' work), and they are the routing target that **AI Agents** point at per **tier**.

## Create a team

1. Go to **[User Management → Teams](/user-management/teams)**.
2. Click the add control to open the **Create Team** dialog.
3. Fill:
   * **Name**
   * **Description (optional)**
   * **Parent team (optional)** — choose **No parent team** for a top-level team, or pick a parent to nest it. A member of the parent can see/act on this team's work.
4. Save.

**What gets created:** a row in `teams`. If you set a parent, `parent_team_id` links it; deleting a parent later re-roots its children (they are not deleted).

The list renders as a **tree** reflecting the hierarchy; use the **Search teams…** box to filter.

## Add members and set round-robin order

1. From the Teams list, open a team to reach its **Members** page (`/user-management/teams/{id}`).
2. Click **Add member** and pick users in the **Add members** dialog.
3. In the members table, each row shows:
   * **Order** — the round-robin sequence (`sort_order`); assignment cycles through members in this order.
   * **User** — the member.
   * **Auto-assign (round robin)** — a switch (`include_in_round_robin`). On = the member receives automatic assignments; off = excluded from auto-distribution **but** still reachable by manual takeover/reassign and still shown in Team Tasks.
4. Toggle **Auto-assign (round robin)** per member as needed.

**What gets created:** rows in `team_members` (one per user), each carrying its `sort_order` and `include_in_round_robin` flag.

> **Round-robin eligibility is per-team, not per-user.** The same person can be auto-assignable in one team and excluded in another.

## How teams drive SLA assignment (tiers)

A team only becomes "tier 1 / 2 / 3 of a team set" through an **AI Agent**, not on the team itself:

* On **[User Management → AI Agents](/user-management/access-agents)**, an agent's **Team Assignments** bind a **team-set code** + a **tier** (1 = initial, 2 / 3 = escalation) to a team, optionally with an SLA **policy**.
* When SLA work starts, the resolver picks the **first existing team at or above** the requested tier (`resolve_team_with_tier_fallback`) — a missing intermediate tier is skipped, not fatal — then assigns round-robin among that team's auto-assignable members.
* On escalation, the next-higher tier's team is used the same way; whether that tier's team is *notified* of a lower-tier deadline extension is the per-tier `notify_on_extension` flag.

So the same team can be tier 1 for one agent's team-set and tier 2 for another — "what tier is this team?" is only meaningful for a specific agent/team-set.

See [SLA — form-SLA configuration](../sla/form-sla-configuration.md) for the full tier + team-set model.

## Delete a team

Use the delete action on the Teams list (confirmation required). Removing a team detaches its members; a deleted **parent** re-roots its children to top-level rather than cascade-deleting them.

## See also

* [User Management — Data reference for admins](data-analysis.md)
* [Manage users and roles](manage-users-and-roles.md)
* [SLA — form-SLA configuration (team tiers)](../sla/form-sla-configuration.md)
* [SLA — policies & notification matrix](../sla/sla-policies.md)
</content>
