# Configure Portal Revisions (allow dealers to revise a submitted form)

Use this when a dealer needs to change a submission after it's already been submitted, without opening a new one. Once a form type is switched on here, a dealer sees a **Revise** action on that form's portal page instead of having to start over.

## Where

**[User Management → Settings → Portal Revisions](/user-management/settings/portal-revisions)**.

## Global switch and cap

At the top of the page:

* **Enabled** - the switch for the whole feature. Off means no form type can be revised on the portal, regardless of its own row below.
* **Max revisions** - the fallback cap used by any form type whose own row doesn't set a narrower one.

Click **Save Settings** to apply, or **Reset** to discard your changes.

## Form Types table

One row per portal submission type: **Stock Inquiry**, **Purchase Request**, **Sponsorship Form**, **Complaint**, and **Price Tag Request**. All five rows are already there - there's nothing to create or delete, only **Edit**.

Each row shows:

* **Form type** - the name.
* **Enabled** - **On** / **Off** for that type specifically.
* **Max** - that type's own revision cap, or **Global** if it just uses the fallback above.
* **Allowed statuses** - which of that form's own statuses a dealer can revise from (for example Price Tag Request allows **New**, **Designing**, **Changes requested** to choose from - typically only New and Changes requested are ticked).
* **Restart stage** - which stage of internal review a revision sends the form back to, or **First stage** if it restarts from the beginning.

Click **Edit** on a row to change its switch, cap, allowed statuses, or restart stage.

## What gets created

Turning a row on doesn't touch existing submissions retroactively - it changes what a dealer is offered the next time they open a submission of that type on the portal. Each revision a dealer sends is recorded as its own entry (reason, what changed, files at that point in time) on the submission's **Revisions** tab, both in the portal and on the internal record.

## See also

* [Project Sales Rep - Submit via portal](../project-sales-rep/submit-via-portal.md#price-tag-request) - what Revise looks like from the dealer's side, for Price Tag Request.
* [User Management - Data reference for admins](data-analysis.md)
