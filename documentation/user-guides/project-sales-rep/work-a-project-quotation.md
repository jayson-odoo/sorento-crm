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

## Every line must be a catalogue product or set

A quotation line must name a product or a product set from the catalogue. You cannot type a
free-text description as a line.

* A line with nothing picked shows **Pick a catalogue product or set** in its Product cell, and
  the quotation does not save until you pick one.
* On the quotation form the refusal reads *One line still needs a catalogue product or set.*
* A **Non-standard** flag on a line means the product is real but outside the series this scope
  is quoted from (hover: *Outside the series this scope is quoted from*). That is allowed.

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

* Your company logo, **Quotation No.**, **Revision**, **Date** and **Sales contact** (your name and
  phone).
* One **Quotation** card. Each section is a row with its item count and total; with more than one
  section they start closed. The last row is **Total amount**.
* To accept, the customer types **Your name**, ticks *I have read and agree to the Terms and
  conditions.*, signs in **Sign here** and clicks **Sign and accept**. If they skip a step, the
  page tells them which one.
* After signing, both signatures show side by side: **Prepared by** (you) and **Accepted by**
  (the customer).
* An old or replaced link shows *This link is no longer valid*, or *This quotation has been
  replaced by Quotation No. ...* when you sent a newer revision. Send them the new link.

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
