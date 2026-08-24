# Project Sales Rep - Portal overview (access, OTP, dashboard)

You file complaints, stock inquiries, purchase requests, and sponsorship forms from a **portal** that opens in your phone or laptop browser. You do not need to install anything or remember a password - access is granted through a link sent to you on WhatsApp.

## How to get the portal link (WhatsApp)


1. Send a WhatsApp message to the **Sorento number** (the company's Respond.io WhatsApp number - ask your manager if you don't have it).
2. The system replies with a **portal link** addressed to your contact.
3. Tap the link. The portal opens in your default browser.

The same link works again for as long as your portal session is valid. Once it expires, you'll be sent through OTP verification (see below).

## OTP verification

If your session has expired (or if you've just been issued a new link), the browser lands on `**/portal/verify**`. The page is titled **Verify your identity** and explains: *"Your portal session expired. Verify with an OTP to continue."*


1. The system **automatically sends a 6-digit code** to your registered contact channel. A small note shows where it was sent (e.g. *"Code sent to your registered contact. It expires in 10 minutes. Please do not share with anyone."*).
2. If you don't see it, click **Send code** (first time) or **Resend code** (subsequent attempts).
3. Type the 6-digit code into the **Verification code** field.
4. Click **Verify and continue**. On success the portal opens.

The code is valid for **10 minutes** - request a new one if it expires.

## The portal dashboard (`/portal`)

After verifying you land on the dashboard. It shows:

* **Welcome, {your name}** - the heading.
* **Search submissions** - search box at the top.
* **Filter by status** - quick filter (Draft / Submitted / etc.).
* **Submission type** combobox - switches between four tabs:
  * **Stock Inquiry**
  * **Complaint**
  * **Purchase Request**
  * **Sponsorship Form**

  The tab marked *"default"* is the one the dashboard opens on. Use the **"{Type} is your default tab"** button to set the current tab as your default.
* **New {Type}** button - opens the submission form for the active tab (e.g. *New Complaint* → `/portal/complaint/new`).
* A list of your existing submissions. Each card shows:
  * Status pill: **Draft**, **New**, **Submitted**, **Pending**, **Pending project sales**, **Pending purchasing**, **Pending approval**, **Approved**, **Rejected**, **Responded**, **Updated**, **Completed**.
  * Document number (or title for drafts).
  * Product / Project / Customer / date metadata.

Tap any card to open the submission and continue editing (if it's a Draft) or to view the read-only details.

## Logging out

Click the **Log out** icon on the top-right of the dashboard. You'll be sent back to `**/portal/verify**` with the message: *"You have been logged out. Verify with an OTP to continue."*

## See also

* [Submit via portal](submit-via-portal.md) - how to fill in and submit a complaint, stock inquiry, purchase request, or sponsorship form.
