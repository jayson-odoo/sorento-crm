# Project Sales Rep - Register a project (Check first, secondary lead)

Use this when you find a new project and want it registered to you. The system first checks
whether someone already registered the same project, so two salespeople do not chase it
separately.

## Where to find it

Open **Projects** (**Project Sales > Projects**, or **MY WORK > Projects** for a salesperson) and
click **Register a project**. The page **Register a project** opens as two steps: **Check**, then
**Details**.

## Step 1: Check

1. Type the **Project title** (required). You can use **AI extract** to fill it from a document.
2. Pick the **Developer** if you know it.
3. Click **Check** (bottom right).

You get one line back:

* **No clash** - nobody has this project. Click **Next** to go to step 2.
* **Clash: {code} {title}** - a project like this one is already registered (click the code to
  open it, if you may see it). The one button becomes **Register as secondary lead on {code}**.
  Click it, say how you found the project, and confirm: *Registered as secondary lead on
  {code}*. The project's owner and managers are told; a manager can then reassign or dismiss
  your secondary lead.
* *The check did not finish. Try again.* - click **Check** again.

## Step 2: Details

Fill in the project facts (**Location**, **State**, **Area**, **Address**, **Reference**,
**Project launch date**, **Architect**, **Main contractor** and so on), and under **Customer and
salesperson** pick the customer and the **Salesperson**. Then click **Register project**.

There is no lead field: registering a project never links or changes a lead. A lead is linked
only from the lead's own page (**Qualify**).

When you submit, the server runs the same check again. If a clash appeared in the meantime, the
submit is refused and you are told the project code and title.

## Upload a requirement before Spec In

A **Registered** project needs at least one document before it can move to **Spec In**. Until it
has one, the header shows **Upload Requirement** instead of **Spec In**. Upload any file (it then
appears on the **Documents** tab) and **Spec In** comes back.

## Secondary leads on a project

On the project's **Access** card, secondary leads are listed as a table: **Salesperson**,
**Date**, **How they found it**, **Status**. Managers can **Reassign** or **Dismiss** each one.

## See also

* [Quote a project, send it, and handle the customer's suggestions](work-a-project-quotation.md)
* [Start a sample request from the project's quotation](sample-request-from-quotation.md)
