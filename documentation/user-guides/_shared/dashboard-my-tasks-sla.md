# 0.2-Dashboard - My Tasks & My Team Tasks (SLA actions)

The dashboard home page shows your pending SLA tasks and your team's, with the actions you can take on each. This explains **My Pending** vs **My Team** and what each button does.

## Where

Open the [**Dashboard**](/) (home page). The **My Pending SLA** widget has two tabs:

- **My Pending** - tasks assigned to **you** that still need action.
- **My Team** - tasks owned by your **teammates** (peers + teams below you) that you could take over.

Each row is one task (a conversation or a form awaiting your team). The buttons shown depend on the tab, the task type, and your permissions.

## The buttons

**[Escalate](#guide_target=dashboard.sla-tasks.escalate)** - *(My Pending, conversation tasks)*
Moves the task up to the next tier and reassigns it per the SLA policy. Asks you for a **reason**; the new assignee is notified. Not available once it's already at the top tier (3).

**[Resolve](#guide_target=dashboard.sla-tasks.resolve)** - *(My Pending, conversation tasks)*
Marks the task resolved: stops the SLA clock and closes the conversation in Respond.io. Asks you to confirm - **this cannot be undone**.

**[Extend](#guide_target=dashboard.sla-tasks.extend)** - *(My Pending, when you are the assignee)*
Pushes the resolution deadline out - either by a number of **working days** or to a **specific date** (it respects the holiday calendar). A **reason** is required; you'll see a live preview of the new due date before confirming. Resets the reminder cycle.

**[Reassign](#guide_target=dashboard.sla-tasks.reassign)** - *(both tabs)*
Hands the task to a colleague you pick from the list. The team, tier, and SLA clock stay the same - only the owner changes.

**[Takeover](#guide_target=dashboard.sla-tasks.takeover)** - *(My Team)*
Takes a teammate's task onto **your** pending list at your tier. The SLA clock is **not** reset. Use this when you're picking up a task a colleague can't get to.

## Which button when

| You want to… | Use | Where |
|--------------|-----|-------|
| Push it to the next tier for help | **Escalate** | My Pending |
| Mark it done | **Resolve** | My Pending |
| Buy more time on the deadline | **Extend** | My Pending (you're the assignee) |
| Give it to a specific colleague | **Reassign** | either tab |
| Pick up a teammate's task | **Takeover** | My Team |

## Notes

* Buttons only appear when you have the matching permission and the task is in a state that allows it (e.g. **Extend** only when you own the task and it isn't resolved).
* **Reassign** vs **Takeover**: Reassign *gives* a task away; Takeover *pulls* a teammate's task to you.
* **Extend** vs **Escalate**: Extend keeps the same owner with more time; Escalate moves it up a tier to someone else.
