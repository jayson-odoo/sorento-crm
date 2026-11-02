# Project Sales Rep - Quote a project, send it, and handle the customer's feedback

Use this when you build a quotation for a project, send it to the customer by email or your own
WhatsApp, and deal with what comes back: the customer signs it, or leaves feedback notes first.
It also covers quoting in a grid (unit types or levels across, areas or rooms below) and asking
for a missing drawing or photo of a product on a line.

This is the **Project Sales** quotation (inside a project). The older **Commercial >
Quotations** screen is a different module.

## Proposals and the quotation

What you send while the project is still being negotiated is a **proposal**. Once the project is
**Won**, you turn one proposal revision into the project's **quotation**. The customer's POs are
checked against the quotation, not against the proposals.

* A proposal can go to any party on the project: the tender party, a trading house, the main
  contractor or a subcontractor. Make one proposal per party when they get different prices.
* Proposal revisions are lettered: `PRJQ-2026-0005-A`, then `-B`, `-C`. A proposal that was
  already sent as `-R1` before this change keeps counting `-R2`, `-R3`.
* When you send a revision whose unit price for a product differs from the previous revision of
  the same proposal, management gets an alert with the old and new price. The revision still goes
  out. A quantity-only change sends no alert.
* The quotation has its own number (for example `QT-2026-0001`) and its own revisions `-R1`, `-R2`.

## Where to find it

1. Open **Project Sales > Projects** and open the project.
2. Click the **Proposals** tab. Each proposal is listed with its number, the **Kind** column
   (**Proposal** or **Quotation**) and its latest revision. The project's quotation is listed first.
3. Click one to open it. Its **Lines** tab holds the priced lines.

To start a new proposal, use **Add a proposal** on the project's **Proposals** tab.

## Make the quotation (project Won)

1. Mark the project Won (the customer signing a proposal does this, or set the scope's outcome).
2. Open the proposal the customer agreed to and choose **Make quotation** from the actions menu.
   It only shows on a sent proposal of a Won project that has no quotation yet.
3. Pick the revision (newest first) and click **Make quotation**.
4. The quotation opens. It carries that revision's party, letter, terms and lines; lost scopes are
   left out. Its header shows **From** with a link back to the proposal revision, and the proposal
   shows **Quotation** with a link to it.
5. Sign it and send it like a proposal. The customer can sign it on the same kind of link.

A project has one quotation. If you picked the wrong revision, delete the quotation before it is
sent and make it again.

### A further discount needs approval

On the quotation, a line priced **below** the same product's price on the proposal revision it came
from needs a manager's approval before you can send it (*One line is priced below the proposal*).
The same **Send for approval** flow as the minimum price applies. A higher price, or a quantity
change, needs nothing.

## PO quantity above the quotation

When the POs of a project together order more of a product than the quotation quotes, saving or
confirming the PO opens **More than quoted**, one line per product (for example *32MM TAIL PIECE
COUPLING: 13 ordered, 10 quoted.*). Type a reason (for example *Variation order VO-3*) and click
**Save**. The PO saves, shows a **Qty over quote** badge (hover for the reason), and management is
told. You are asked once per PO.

Once a project has a quotation, a new PO cannot be checked against a proposal.

## Fill the cover page

Every quotation sent from now on starts with a cover page: page 1 of the PDF (portrait) and the
first card on the customer's sign link. It replaces the separate Excel cover sheet. It shows, in
this order: **Reference No.**, **Date**, **Attn**, **Company**, **Contact**, **Add**, **Email**,
**Proposal Purpose** (**Quotation Purpose** on the quotation), **Terms & Conditions**, **Payment
Terms**, **Validity**, **Prepared By**.

* **Reference No.** is the proposal or quotation number with its revision and the project name
  (for example `PRJQ-2026-0042-B SERI MUTIARA RESIDENCES`). The same reference shows on the price pages and
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
  is quoted from (hover: *Outside the series this scope is quoted from*). That is allowed.

### Minimum price, while you type

* Under a line's rate, **Minimum price RM x** appears as soon as the price you type is below the
  lowest price allowed for that item. It shows on a new quotation too, before the first save.
* **Non-standard** also appears while you pick, on a new quotation as on a saved one.
* A quotation with a line below the minimum price says *One line is priced below minimum price*
  (or *N lines are priced below minimum price*) and needs a manager's approval before it can be
  sent.

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

## Quote in a grid (unit types or levels across, areas or rooms below)

A project bill of quantities often lists the products down the side and the unit types or levels
across the top, each split into areas or rooms, with a quantity in every box. Any section (scope)
of a quotation can be laid out that way. A section with no grid stays exactly as before.

### Set up the columns

On the section's **Lines** tab, while the revision is still a draft:

1. Click **Add a column header** (the narrow column at the far right of the table) and type its
   name, for example *TYPE A - 1 BH* or *LEVEL 9*. Your lines' current quantities move into the
   new column, so no total changes.
2. Click **+** (*Add a column*) after a header to add the columns under it, for example *1 BH*,
   *KITCHEN*, *YARD*, *BALCONY* or *SURAU M*, *JANITOR*. A header with no columns under it is one
   quantity column on its own (for example *BREAK TANK*).
3. Click any header or column name to rename it. Drag the grip to reorder. Click **Remove** (the
   x) to take one away: it counts down with **Undo** in the header, and its quantities leave the
   totals when the countdown ends.
4. **Copy columns from** on the table's toolbar copies another section's headers and columns (not
   its quantities), so the second LEVEL sheet takes seconds.

Every column you already use stays: photo, drawing, product code, description, brand, UOM, rate,
complete set, rate only, and the section headings (*Bathroom*, *Kitchen and yard*). Only the
single Qty column is replaced by the grid.

### Fill in the quantities

Type the real quantity in each box (blank means none). The line's quantity is the sum of its
boxes, and everything that reads a quantity (totals, approval, PO check, SO draft, spec sheet)
uses that sum. To bring numbers over from the customer's spreadsheet, copy the block of quantities
there, click the first box here and paste: it fills right and down; *-* and blanks paste as blank.

The table adds up for you:

* after each header with two or more columns: that header's **Qty** and **RM** for the line;
* at the end of the line: **Total qty** and the amount;
* at the bottom: **Total qty** under every column and **Total (RM)** under every header.

The same product can sit on more than one line (an angle valve for the WC and again for the
sink); the PO check adds them up.

The PDF and the Excel export print the same two-row header (repeated on every page) with today's
columns around it; a wide sheet prints its column names upright to fit. The customer's link shows
the grid when they open the section.

## The customer leaves feedback

Instead of signing, or as well as signing, the customer can leave feedback on the sign page. They
tap the feedback button beside an item, or tap one box of a grid, to open **Leave a note**: they
write **Your note** and can add a hint: a suggested quantity, a suggested price, **Remove this
item**, or another model (**Model name or code**) with its price. They click **Send feedback**.
They can send feedback as many times as they like, and it never stops them signing.

Nothing the customer sends changes the quotation. You read it and decide what to do.

### How you hear about it

The project owner (or management, if the project has no owner) gets an in-app notice, an email and
a WhatsApp: *{customer} left feedback on {n} lines on {quotation}*. The project's activity log
records it too.

### Read and act on it

1. Open the quotation's **Customer feedback** tab. The number on the tab is how many notes are
   still open. Each note shows the item, the section and, for a grid box, the column (*TYPE C - 3
   BH / KITCHEN*), what the customer wrote and their hint next to today's value (*Suggested
   quantity 140 (now 133)*).
2. Click **Show in Lines** to jump to that line. Open notes are marked on the Lines tab: an amber
   corner on a grid box, a dot on an item.
3. Change what you see fit in a new revision (revise, edit, send), exactly as for any change.
4. Tick **Handled** on a note once you have dealt with it. Unticking opens it again.

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
