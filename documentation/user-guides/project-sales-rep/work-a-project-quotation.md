# Project Sales Rep - Quote a project, send it, and handle the customer's suggestions

Use this when you build a quotation for a project, send it to the customer by email or your own
WhatsApp, and deal with what comes back: the customer signs it, or suggests different quantities
or prices first. It also covers asking for a missing drawing or photo of a product on a line.

This is the **Project Sales** quotation (inside a project). The older **Commercial >
Quotations** screen is a different module.

## Where to find it

1. Open **Project Sales > Projects** and open the project.
2. Click the **Quotation** tab. Each quotation document is listed with its number (for example
   `PRJQ-2026-0003`) and revision (**R1**, **R2** ...).
3. Click a quotation to open it. Its **Lines** tab holds the priced lines.

To start a new one, use **New quotation** from the project's **Quotation** tab.

## Fill the cover page

Every quotation sent from now on starts with a cover page: page 1 of the PDF (portrait) and the
first card on the customer's sign link. It replaces the separate Excel cover sheet. It shows, in
this order: **Reference No.**, **Date**, **Attn**, **Company**, **Contact**, **Add**, **Email**,
**Quotation Purpose**, **Terms & Conditions**, **Payment Terms**, **Validity**, **Prepared By**.

* **Reference No.** is the quotation number with its revision and the project name (for example
  `PRJQ-2026-0042-R2 SERI MUTIARA RESIDENCES`). The same reference shows on the price pages and
  on the sign link. You do not type your own code any more.
* On the **Header** tab: **Email** sits under **Phone** and fills from the customer's main contact
  on a new quotation. **Quotation Purpose** sits under **Subject** and is optional.
  **Prepared By** is the project's salesperson and cannot be edited here.
* On the **Terms** tab: **Payment Terms** and **Validity** sit above the terms. A new quotation
  fills them from the company's active terms template; change them for this quotation if needed.
* **Validity** is printed for the customer only. The sign link keeps working after it.
* An empty field is left off the cover page rather than printed blank.
* **Your Ref** (the customer's own reference) stays on the **Header** tab and prints on the price
  pages as before.

The terms print the way you wrote them: a heading stays a heading, a blank line keeps its gap,
bullets and indented bullets print as bullets, and nothing is numbered for you. They print once,
on the cover page. Quotations sent before this change keep their old layout when downloaded
again.

## Every line must be a catalogue product or set

A quotation line must name a product or a product set from the catalogue. You cannot type a
free-text description as a line.

* A line with nothing picked shows **Pick a catalogue product or set** in its Product cell, and
  the quotation does not save until you pick one.
* On the quotation form the refusal reads *One line still needs a catalogue product or set.*
* A **Non-standard** flag on a line means the product is real but outside the series this scope
  is quoted from (hover: *Outside the series this scope is quoted from*). That is allowed, but
  the quotation then needs approval before it can be sent (see below).

### Minimum price, while you type

* Under a line's rate, **Minimum price RM x** appears as soon as the price you type is below the
  lowest price allowed for that item. It shows on a new quotation too, before the first save.
* **Non-standard** also appears while you pick, on a new quotation as on a saved one.
* A quotation with a line below the minimum price says *One line is priced below the minimum
  price* (or *N lines are ...*) and needs approval before it can be sent.

### Which quotations need approval, and who approves

A quotation needs approval before it can be sent when any line:

* is priced below its **default price**, even by RM 1. The default price is the price a new line
  opens at: the series price where the scope's series names one, else the list price. The
  banner reads *One line is priced below the default price*.
* is **outside the project's series** (*One line is outside the project's series*).

Press **Send for approval**. The request goes to ONE person, worked out in this order:

1. a line outside the series: the company's **off-series approver** (set in Settings);
2. the project's own **Discount approver** (on the project's Critical / final negotiation card,
   set by a sales manager);
3. your **superior** (your regional sales manager; set on your user in Settings > Users);
4. the company's **default quotation approver** (Settings).

The banner names who it is with (*... is with Aminah for approval*). Only that person, someone
they report to, or an admin can approve or reject it. If nobody is set up, Send for approval
says *Nobody is set up to approve this quotation* and names what an admin should set.

Approval covers the revision you send: issuing spends it, and the next revision that still has a
discount or an off-series line asks again.

### A discount puts the project in Final Negotiation

Sending a quotation with a discount for approval raises the project's **Critical / final
negotiation** flag and moves the project to the **Final Negotiation** stage, if it is at an
earlier stage. A project already at Final Negotiation or later (Sponsorship Form, PO Received,
Lost, Dormant) keeps its stage. An approval asked only for an off-series line does not move it.
If the approver rejects the discount, or you take it back to change it, the project stays in
Final Negotiation; a sales manager moves it back by hand if the deal cooled.

### The customer wants something we do not sell yet (bespoke item)

Get the product into the catalogue first, then quote it:

1. Raise a **New Product Application** (**Procurement > New Product Applications**, or the New
   Product Application item in the sidebar's **MY REQUESTS** section).
2. When the product exists in the catalogue, add it to the quotation line as usual.

### Why a product cannot be deleted

A product or product set that is on any quotation (draft or issued) cannot be deleted from the
catalogue. The refusal names the first quotation it sits on: *This product is on quotation
PRJQ-..., so it cannot be deleted.* (or *This product set is on quotation ...*). Remove it from
that quotation first if it really must go.

## Send the quotation to the customer

1. On the quotation, click **Send to Customer R{n}** (n is the revision you are sending).
2. Choose **Email** or **WhatsApp**.
   * **Email** sends it the usual way.
   * **WhatsApp** marks it sent and then opens the WhatsApp dialog (below).
3. You see *Sent to the customer as PRJQ-...-R{n}*.

### Send through your own WhatsApp

The system does not send WhatsApp messages for you here. It prepares the message and opens
WhatsApp on your phone or computer, and you press Send.

1. Open the dialog either straight after **Send to Customer > WhatsApp**, or later from the
   quotation's gear menu (or the list row's **...** menu): **Send via WhatsApp**. It is greyed
   out with *Send it to the customer first* until the quotation has been sent once.
2. The dialog **Send R{n} via WhatsApp** opens:
   * **To**: filled with the customer's first mobile number (a local `01x` number becomes
     `601x`). Landlines and 1300/1700/1800 numbers are left blank; type a mobile number.
   * **Message**: a ready message with the quotation number, subject and the sign link. You can
     edit it; your edits are not saved anywhere.
3. Click **Open WhatsApp**. WhatsApp opens in a new tab with the message filled in. Press Send
   there.
4. **Copy link** copies just the sign link (it shows **Copied**). If your browser blocks copying,
   the link is selected for you: press Ctrl+C (Cmd+C on a Mac).

The project's activity log records *Quotation ... link opened in WhatsApp by ...*.

## What the customer sees on the link

The link opens a sign page that matches the PDF:

* First, the cover page card: your company logo and name, then the same rows as PDF page 1,
  including the terms written the same way.
* Then **Quotation No.** (the same reference as the PDF), **Revision**, **Date** and **Sales
  contact** (your name and phone).
* One **Quotation** card. Each section is a row with its item count and total; with more than one
  section they start closed. The last row is **Total amount**.
* To accept, the customer types **Your name**, ticks *I have read and agree to the Terms and
  conditions.*, signs in **Sign here** and clicks **Sign and accept**. If they skip a step, the
  page tells them which one. The terms they agree to are the ones on the cover page card.
* A link for a quotation sent before the cover page existed looks as it did then, with the terms
  at the bottom.
* After signing, both signatures show side by side: **Prepared by** (you) and **Accepted by**
  (the customer).
* An old or replaced link shows *This link is no longer valid*, or *This quotation has been
  replaced by Quotation No. ...* when you sent a newer revision. Send them the new link.

## See whether the customer opened it

Under the customer's name at the top of the quotation page you see **Viewed 3 times, last
02/11/2026, 9:41 pm** for the revision the customer holds now, or **Not viewed yet**. Nothing shows
before the first time you send it. Managers see the same line.

Click the line to open the **View log**: every open, newest first, with the time, the Quotation
No. of the revision opened (R1, R2 ...) and the device (Phone, Tablet or Computer). After you send
a new revision the line starts again at **Not viewed yet**; opens of the old link stay in the log
under the old number.

What counts as a view:

* One open per browser every 30 minutes. Refreshing the page, or opening it again a few minutes
  later on the same phone, counts once. A colleague of the customer opening it on another device
  counts at once.
* The preview WhatsApp or email shows under the link is not a view.
* Opening the link in a browser where you are signed in to the CRM is not a view. **Opening it
  anywhere else counts**, for example tapping the link in WhatsApp on your own phone, where you
  are not signed in to the CRM. Check your own link from the CRM, not from your phone.

Nothing that identifies the reader is kept: no IP address and no name, only the time, the
revision and the kind of device.

## The customer suggests changes (quantity, price, remove a line)

Instead of signing, the customer can click **Suggest changes** on the sign page. They can change a
line's **Qty** or **Unit rate**, or remove a line, add an optional note, and click **Send
suggestions**. They cannot change descriptions or anything else.

While their suggestions wait for you, their page says *Your suggestions are with Sorento* and
they cannot sign.

### How you hear about it

The project owner (or management, if the project has no owner) gets an in-app notice, an email and
a WhatsApp: *{project}: changes suggested on {quotation}*. The project's activity log records it
too.

### Answer the suggestions

1. Open the quotation's **Lines** tab. A summary row at the top shows who suggested, when, how
   many lines, the total before and after (**RM x -> RM y**) and their note. Tick **Suggested
   lines only** to hide the rest.
2. On each suggested cell (Qty, Rate) or removed row, click **Accept** or **Reject**. Reject asks
   for an optional **Reason**. Click a decision again to undo it.
3. When every suggestion is decided, click **Apply decisions**.
   * If you accepted anything, a **new draft revision** opens with those changes: *Decisions
     applied. The revision is a draft for you to check and send.* It goes through the normal
     minimum-price approval, then you send it like any revision.
   * If you rejected everything: *Decisions applied. Nothing was accepted, so no revision was
     opened.*
4. The customer's page then shows **Your suggestions** with **Answered**, how many were accepted
   and not accepted, and *Your salesperson will send the revised quotation for signing.*

**Apply decisions** stays greyed out until every suggestion is decided (*Accept or reject N more
suggestions to apply.*). If a revision is already open on that scope, you are told to issue that
revision first. You need edit rights on the project.

## Ask for a missing drawing or photo of a product

On a saved line, if the product has no technical drawing, the **Drawing** cell shows
**Escalate**. The **Photo** cell does the same when the product has no photo at all.

1. Click **Escalate** (hover: *Ask for a drawing of {code}*).
2. You see *Escalated: you will be told when the request is resolved*. If someone already asked
   for the same product, you are added to that request instead: *Already escalated: added you to
   the request*.
3. The cell now shows **Escalated {date}** (or **Replied {date}** once the product team
   answered). Click it to join the request.
4. The marketing product team gets it as a task with an SLA clock. If your user is linked to a
   WhatsApp contact, you get a WhatsApp acknowledgement too.
5. When they add the file you are told *Drawing added for {code}*, and when they close the
   request, *Product drawing request for {code} resolved*.

A PDF filed as **Technical Specifications** counts as a drawing. Refusals you may see: *This
product already has a drawing.*, *This line has no catalogue product to request a file for.*, or
*The marketing product team is not set up for this company* (tell your admin).

This **Escalate** opens a new request for a file. It is not the same as escalating a task to a
higher tier (see [Escalate a task or enquiry](../_shared/escalate-a-task-or-enquiry.md)).

## See also

* [Start a sample request from the project's quotation](sample-request-from-quotation.md)
* [Marketing - Answer a drawing or photo request](../marketing/answer-a-drawing-or-photo-request.md)
* [Escalate a task or enquiry you can't handle](../_shared/escalate-a-task-or-enquiry.md)
