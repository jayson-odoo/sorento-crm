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

Most fields are picked from a list, not typed.

* **Details**: **Registered company / SPV**, **State**, then **Area** (the districts of the state
  you picked; pick the State first), **Address**, **Reference**, value and dates.
* **Parties and contacts**: **Architect** and **Main contractor**, then **Subcontractors**,
  **Trading houses** and **Tender parties** (pick as many as the job has), **Consultant** and
  **Interior designer** (one each). Under every party you picked, **Contacts at {party}** lists the
  people at that firm: pick the ones on this project. They are added to the project's
  **Stakeholders**. Someone missing? Type the name and choose **Add contact "{name}"** (needs the
  right to edit parties). A phone number is not required.
* **Lead source, customer and salesperson**: **Lead source** (required: where the project came
  from), **Customer** (optional, you can add it later) and **Salesperson**.

Then click **Register project** (a salesperson without edit rights gets **Save draft** and
**Submit for approval**; a draft needs only the title).

There is no lead field: registering a project never links or changes a lead. A lead is linked
only from the lead's own page (**Qualify**).

When you submit, the server runs the same check again. If a clash appeared in the meantime, the
submit is refused and you are told the project code and title.

## Move a Registered project to Spec In

A **Registered** project's header shows **Spec In**, whether or not it has documents yet. Upload
requirement files on the **Documents** tab whenever you have them; they are not needed to move on.

## Keep each party's contacts

Open **Parties**, click the firm, and use its **Contacts** section: **Add contact** (only the name
is required), edit, or delete (the button counts down; click **Cancel** to keep the contact). A
project that already has the person keeps them in its Stakeholders.

## Send a quotation on WhatsApp to a party

In **Send via WhatsApp**, pick the party or person under **Send to**. Their number fills **To**.
If they have no number yet, type it: when you click **Open WhatsApp** it is saved to that party or
person, so next time it is there. A number already on file is never changed from here. To send to
another party, pick them and click **Open WhatsApp** again.

## Leads on a project (primary and secondary)

The project's **Overview** tab shows its cards one under the other, full width.

The **Access** card lists every lead on the project in one table:

* **Salesperson**
* **Lead**: **Primary** marks the salesperson who found and registered the project first;
  **Secondary** marks anyone who registered as a secondary lead later.
* **Date**: when they found it. For the primary, this is the date the lead was raised, or the
  registration date if the project had no lead.
* **How they found it**: the lead source for the primary, or the note a secondary lead wrote.
* **Owner**: **Yes** on the salesperson who owns the project now.
* **Status**: **Pending** or **Dismissed** for a secondary lead not yet reassigned to.

If the project's owner is someone who is neither the primary nor a secondary lead, they get a row of
their own with Lead left blank.

**Managers:** right-click a salesperson's row and choose **Reassign to {name}**. The reassign
window opens with that person already picked; click **Reassign**. You can move the project to any
of the listed leads and back again, for example back to the primary after a change of decision.
On a pending secondary lead, the right-click menu also has **Dismiss**.

Each reassignment:

* keeps the previous owner on the project as a collaborator;
* adds a line to the **Activity** tab, *Reassigned from {name} to {name}*;
* notifies the new owner and the previous owner.

## See everything linked to a project (Related tab)

The project page's **Related** tab (it used to be called **Sponsorship Form**) lists every stock
inquiry, complaint, purchase request, sponsorship form and new product application linked to the
project, in one grid. Columns: **Type**, **Number**, **Status**, **Approval**, **Date**,
**Raised by**, **Subject**, **Value**.

* Use **Search**, and the **Type** and **Status** filters, to narrow the list. Click a column
  heading to sort. Use **Columns** to hide or reorder columns.
* Click a row to open that record.
* If the project has sponsorship forms, the sponsorship spend line stays above the grid.
* You only see the types you are allowed to view. A rep who can only view their own requests sees
  only their own.

A record shows here only once it is linked to the project. Older records are not linked
automatically: open the record and pick the project in its **Registered project** field (the
Sorento team may also link some older ones from a reviewed list). A project name typed on a record
that is not picked from the list does not link it.

## Link a record to a project

* **Stock inquiry** and **new product application** forms (in the CRM and in the portal or
  WhatsApp link), and the portal **complaint** and **purchase request** forms, have an optional
  **Registered project** field. Search by project code or title and pick the project. Leave it
  empty for a project that is not registered; the typed project name stays for that.
* A new product application raised from a stock inquiry starts with that inquiry's project. You
  can change it.
* On a record's own page, anyone who can edit the record can set or change its **Registered
  project** at any time, even when the record is closed or approved. An approval stays as it is.
  The record's **History** shows the change as *Project: old -> new*.

## See also

* [Quote a project, send it, and handle the customer's suggestions](work-a-project-quotation.md)
* [Start a sample request from the project's quotation](sample-request-from-quotation.md)
