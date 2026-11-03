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

## Upload a requirement before Spec In

A **Registered** project needs at least one document before it can move to **Spec In**. Until it
has one, the header shows **Upload Requirement** instead of **Spec In**. Upload any file (it then
appears on the **Documents** tab) and **Spec In** comes back.

## Keep each party's contacts

Open **Parties**, click the firm, and use its **Contacts** section: **Add contact** (only the name
is required), edit, or delete (the button counts down; click **Cancel** to keep the contact). A
project that already has the person keeps them in its Stakeholders.

## Send a quotation on WhatsApp to a party

In **Send via WhatsApp**, pick the party or person under **Send to**. Their number fills **To**.
If they have no number yet, type it: when you click **Open WhatsApp** it is saved to that party or
person, so next time it is there. A number already on file is never changed from here. To send to
another party, pick them and click **Open WhatsApp** again.

## Secondary leads on a project

On the project's **Access** card, secondary leads are listed as a table: **Salesperson**,
**Date**, **How they found it**, **Status**. Managers can **Reassign** or **Dismiss** each one.

## See also

* [Quote a project, send it, and handle the customer's suggestions](work-a-project-quotation.md)
* [Start a sample request from the project's quotation](sample-request-from-quotation.md)
