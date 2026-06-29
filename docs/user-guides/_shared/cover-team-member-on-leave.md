# 0.3-Dashboard — Cover for a team member on leave

When a colleague is away (leave, off sick), you can set up **coverage** so their SLA tasks are handled while they're out. This is done on the **Coverage** tab of the dashboard.

## Where

Open the [**Dashboard**](/) (home) → the **My pending tasks** widget → the **[Coverage](#guide_target=dashboard.coverage.tab)** tab (third tab, after *My Pending* and *My Team*).

## Set up coverage

It's one short form:

1. **Coverer** — who does the covering. It defaults to **You**. (Managers with team-coverage permission can pick a different colleague to be the coverer.)
2. **Covers for** — the colleague who is **away**. Pick them from the list.
3. **Until (optional)** — the last day of the coverage (e.g. their return date). Leave blank for no end date.
4. **Mode** — choose how their tasks are handled:
   - **Auto-assign** — the away colleague's SLA tasks **and escalations are routed to the coverer automatically**. Only **one** auto-assign coverer is allowed per person.
   - **Notify only** — the tasks stay assigned to the away colleague; the coverer is **notified** and can pick the task up manually with **Takeover** (on the *My Team* tab). Several people can be notify-only coverers.
5. Click **[Add](#guide_target=dashboard.coverage.add)**.

The new coverage shows in the list as a **Coverer → Covers for** row, with an **Active** badge, the **Until** date, and the **Auto-assign / Notify only** mode.

## Managing coverage

- **Edit** (pencil) a row to change its end date or switch between **Auto-assign** and **Notify only**.
- **Remove** (trash) stops the coverage — you'll confirm *"their SLA tasks will stop routing"*. This can't be undone.
- A manager (team-coverage permission) can set up coverage **on behalf of** team members — assigning one person to cover another; those rows show **Assigned by …**.
- Coverage ends automatically once the **Until** date passes.

## Which mode should I use?

| You want… | Use |
|-----------|-----|
| The coverer to receive and own the away person's tasks automatically | **Auto-assign** |
| To keep tasks with the away person but have someone watching + able to step in | **Notify only** (then **Takeover** when needed) |

## Notes

* Auto-assign needs a **sole** coverer — you can't have two auto-assign coverers for the same person at once.
* Routing only starts for **new** SLA tasks/escalations while coverage is active; it stops when you remove it or the **Until** date passes.
