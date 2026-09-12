# Project Sales Rep - Portal overview (access, OTP, dashboard)

You file complaints, stock inquiries, purchase requests, and sponsorship forms from a **portal** that opens in your phone or laptop browser. You do not need to install anything or remember a password - access is granted through a link sent to you on WhatsApp.

## How to get the portal link (WhatsApp)


1. Send a WhatsApp message to the **Sorento number** (the company's Respond.io WhatsApp number - ask your manager if you don't have it).
2. The system replies with a **portal link** addressed to your contact.
3. Tap the link. The portal opens in your default browser.

The same link works again for as long as your portal session is valid. Once it expires, you'll be sent through OTP verification (see below).

## OTP verification

If your session has expired (or if you've just been issued a new link), the browser lands on the **Verify your identity** card.

The card shows, in order:

1. A line telling you where the code is going: *"We'll send a code to your WhatsApp <your masked number>"*.
2. A **Not your number?** link directly under that line (only shown when you arrived on your own portal link; not shown on the older, generic verify link).
3. The **Verification code** field - type or paste the 6-digit code you receive on WhatsApp. Verification fires automatically the moment the sixth digit lands; you don't need to click anything.
4. A **Resend code** button (reads **Send code** the first time, then **Resend code**, then **Resend in {n}s** while it's cooling down).

If you logged out yourself, the card also shows a notice: *"You have been logged out. Verify with an OTP to continue."*

The code is valid for **10 minutes** - tap **Resend code** if it expires or never arrives.

## The portal dashboard (`/portal`)

After verifying you land on the dashboard. It shows:

* **Welcome, {your name}** - the heading, with **Log out** at the top-right corner.
* A **Search...** box.
* **Submission type** combobox - switches between the tabs you have access to:
  * **Stock Inquiry**
  * **Complaint**
  * **Purchase Request**
  * **Sponsorship Form**
  * **Price Tag Request** (only shown if your account has been granted it - see [Submit via portal](submit-via-portal.md#price-tag-request))

  The tab marked with a star is the one the dashboard opens on. Use the **"{Type} is your default tab"** button to set the current tab as your default.
* A toolbar row above your list of submissions, left to right:
  * **Filter** - opens a popover with one dropdown per field the current tab's cards carry (for example Status, Customer, Product, Project, Need by, Created). Picking a value narrows the list; the Filter button shows a count badge while any filter is active, and **Clear all** resets it.
  * **Sort** - opens a menu of the same fields, each with **Ascending** / **Descending**. The default is Created, newest first.
  * A view toggle (List view / Board view, shown as icons) - Board view shows submissions as cards, List view shows one compact line per submission. Your choice is remembered on this device and stays even when you switch tabs.
  * **New {Type}** - opens the submission form for the active tab (e.g. *New Complaint* → `/portal/complaint/new`).
* A list of your existing submissions. Each card (or row, in List view) shows:
  * Status pill: **Draft**, **New**, **Submitted**, **Pending**, **Pending project sales**, **Pending purchasing**, **Pending approval**, **Approved**, **Rejected**, **Responded**, **Updated**, **Completed**.
  * Document number (or title for drafts).
  * Product / Project / Customer / date metadata.

Tap any card to open the submission and continue editing (if it's a Draft) or to view the read-only details. Long-press (or right-click) a card to open a preview with **Duplicate** and **Open** (and **Revise** when offered) without leaving the list.

If a filter or your search leaves nothing to show, the list reads *"No submissions match your filters."* with a **Clear filters** action.

## Duplicate an existing submission

Any submission type can be copied into a fresh draft:

1. Long-press (or right-click) a card and choose **Duplicate** from the preview, or open the submission and choose **Duplicate** from its gear menu.
2. A new form opens with every field (and every line - product, complaint, etc.) copied from the source. Attachments are **not** copied - the sales order / photos / quotes start empty.
3. Nothing is saved until you click **Save as draft** / **Save Draft** or **Submit** on the new form.

If the source submission can no longer be found, a toast reads *"Could not copy that submission."* and the form opens empty instead.

## Logging out

Click the **Log out** icon on the top-right of the dashboard. You'll be sent back to the **Verify your identity** card with the message: *"You have been logged out. Verify with an OTP to continue."*

## See also

* [Submit via portal](submit-via-portal.md) - how to fill in and submit a complaint, stock inquiry, purchase request, sponsorship form, or price tag request.
