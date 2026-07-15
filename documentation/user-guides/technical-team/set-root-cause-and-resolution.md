# 7.2-Technical Team — Set Root Cause & Resolution and notify salesperson

Every complaint should have a **Root Cause** (why it happened) and a **Resolution** (what we did about it) selected from the master data. After you set either field you can fire a one-tap notification to the salesperson so they can update the customer without waiting for the next sync.

## Where

Open [**Complaint Management → Complaints**](/complaint-management/complaints) → click a complaint row to open its detail page.

The Root Cause and Resolution panels sit just under the complaint summary.

## Step 1 — Pick a Root Cause

1. Click **Edit** on the action menu, or use the inline edit on the detail page.
2. Pick a value from the **Root Cause** dropdown.
   * The list is managed under [**Complaint Management → Root Causes**](/complaint-management/complaint-root-causes) (admins maintain this; ask if you need a new value added).
3. Save.

The complaint detail page now shows the Root Cause name and an enabled **Notify salesperson** button.

## Step 2 — Notify salesperson about the Root Cause

Click **[Notify salesperson](#guide_target=complaint-management.complaints.tech-team.notify-root-cause)** in the Root Cause panel.

* Confirms in a dialog before sending.
* On confirm, posts a templated message to the salesperson's Respond.io inbox.
* The "Last notified" timestamp updates under the Root Cause name.

The button is **disabled** when:

* The complaint has no Root Cause yet, **or**
* The complaint has no linked `respond_inbox_url` (no Respond.io conversation associated).

## Step 3 — Pick a Resolution

Same flow as Root Cause:

1. Edit the complaint and pick a value from the **Resolution** dropdown (managed under [**Complaint Management → Resolutions**](/complaint-management/complaint-resolutions)).
2. Save.

## Step 4 — Notify salesperson about the Resolution

Click **[Notify salesperson](#guide_target=complaint-management.complaints.tech-team.notify-resolution)** in the Resolution panel.

Same dialog → confirm → message posted → "Last notified" timestamp recorded.

## What the salesperson sees

The Respond.io message identifies the complaint number, the chosen Root Cause / Resolution value, and a link back to the complaint detail page. From there the salesperson can choose whether to forward the message to the customer or relay it in their own words.

## Permissions

* `complaint_management.complaints.edit` — covers both setting the values and firing either notification.

## See also

* [Respond to a complaint](respond-to-complaint.md)
* [Approve or reject a complaint](approve-or-reject-complaint.md)
