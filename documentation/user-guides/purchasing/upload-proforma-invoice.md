# 1.7-Purchasing - Upload a proforma invoice (and its packing list)

Use this flow when a supplier emails you their proforma invoice, their packing list, or both. This
is where every supplier document starts now: the Packing Lists page no longer reads a supplier's
file for you (its own **Upload** files an attachment as-is, and **Create Packing List** builds one
by hand) - a packing list that came from a supplier's own workbook is read here, on **Proforma
Invoices**, and our packing list is born later, when you convert.

## Steps

1. Open **[Procurement → Supply Chain → Proforma Invoices](/scm/proforma-invoices)**.
2. Click **Start**, then **Upload proforma invoice**.
3. The **Upload supplier documents** dialog opens: *"A proforma invoice, a packing list, or both -
   each file is read on its own and classified automatically."*
4. Choose the **Supplier** (type to search).
5. Drag in or browse to the file or files - a proforma invoice alone, a packing list alone (only
   when its invoice is already in the CRM), or both together, and a single sheet that carries both
   is fine too. (**Currency** only needs filling in when none of the files states one.)
6. Choosing files reads nothing yet. Click **Test**. Each file comes back labelled **Proforma
   invoice**, **Packing list**, or **Combined**, with its blocks, lines, and header read out. A
   packing-list file also shows **Attaches to** - the invoice it will attach to, already picked
   when the file states the invoice number or shares its date; change it yourself only if that
   guess is wrong.
7. If a header on the file could not be placed, it appears under **Unmapped headers** as a chip.
   Click **Map to...** on the chip, pick the system field, and the file is read again with that
   mapping - the mapping is then remembered for every later file (see
   [System Management - Import column mappings](../system-management/import-column-mappings.md)).
8. Click **Confirm**.

Re-uploading the same supplier's invoice (same supplier and the same invoice number written on
it) updates the existing proforma invoice in place and keeps its number; it does not create a
duplicate. Uploading a fresh copy of a file that states no invoice number always creates a new
proforma invoice.

## Our PI number and the supplier's own reference

Every proforma invoice gets **our** number, `PI-YYMM-NNN` (year, month, a running count that
resets each month) - the same numbering-rule engine behind every other document number in the
CRM, listed on **[System Management → Running Numbers](/system-management/numbering-rules)**.
Alongside it is the supplier's own reference, read straight off their document (blank when the
file states none). The **Proforma Invoices** list carries both - **PI number** and **Supplier
ref** - and its search box matches either one.

## The Packing tab

Open a proforma invoice and its **Packing** tab holds the supplier's packing list exactly as they
sent it, one row per row of their file, each matched to the invoice line it belongs to by product.
On the **Lines** tab, a **Packed** column shows the packed quantity from those rows next to the
invoiced quantity; when the two disagree the cell is flagged with the invoiced and packed figures
side by side.

* **No packing list yet:** the tab reads **No packing list attached yet** with an **Attach packing
  list** button - the same upload dialog opens with the supplier and this invoice already chosen.
  This is the normal case for a supplier (Kailu, in the sample set) who sends the invoice first and
  the packing list days later.
* **Replacing a packing list:** once one is attached, the tab's gear menu offers **Replace packing
  list** - a re-upload replaces the rows rather than adding to them, for when the supplier sends a
  corrected file.
* **A row the catalogue doesn't know** (a spare part, a customs sample, a note about a shared
  container) reads **Not in catalogue**, with **Match** (pick the product it actually is) and
  **Dismiss** (a 5-second countdown you can cancel) beside it. Dismissing a code is remembered:
  the same code from the same supplier lands dismissed automatically on every later upload,
  without asking again.

A packing list uploaded with no matching proforma invoice for that supplier is refused, naming the
supplier and the date on the file - upload it together with its invoice, or upload the invoice
first and attach the packing list to it afterwards.

## Convert to packing list

Our own packing list is never created by this upload - it is born by converting proforma invoices,
or by hand with **Create Packing List** on the Packing Lists page.

1. On **Proforma Invoices**, tick the invoices going into one container.
2. Click **Start**, then **Convert N to packing list**.
3. The **Convert to a packing list** dialog shows what carries onto the draft: the container
   number, seal number and bill of lading, when every selected invoice's packing rows (or their
   own container reference) agree on one container. When they don't agree, those fields are left
   blank and you're told so once you convert.
4. Each supplier packing row goes onto the draft whole or stays behind for a later container - it
   is never split by typing a smaller quantity. If a supplier packed one product as two cartons of
   different sizes (Kailu's 50-carton batch and 35-carton batch of the same item, for example),
   the draft carries both as two lines, and the printed packing list shows it the same way.
5. Click **Convert**.

## Source files

A proforma invoice's **General** tab has a **Source files** section listing the file(s) it was
read from - the invoice workbook and, once attached, the packing-list workbook - each with its
kind and the date it was uploaded.

## Chinese wording and its English reading

A supplier document written in Chinese shows a **Translations - English beside the Chinese**
panel at Test time, and once an invoice is created, its **Lines** and **Packing** tabs carry a
**Description (EN)** column beside **Description**. See [Translating supplier
wording](translating-supplier-wording.md) for how to read, add or correct it, and where the
English travels to from there.

## What's captured

From the proforma invoice: our PI number, the supplier's reference, the supplier, currency, and
every line as the document states it (product, quantity, price, and - when the document carries
them - cartons, pieces per carton, carton dimensions, CBM, net and gross weight).

From the packing list: every row as the supplier sent it, matched to a line by product, rolled up
onto that line's cartons, CBM, and weights. A row with no invoice line to match reads Not in
catalogue until it's matched or dismissed.

## What gets created

Confirming files the uploaded workbook(s), mints or updates the proforma invoice, and writes its
packing rows. Nothing about our own packing list is created at this step - that only happens when
you convert (or create one by hand).

## How you'll be notified

* **Immediately:** the Test and Confirm results appear in the dialog itself - there is nothing to
  wait for.
* Uploading, attaching, replacing, matching, and dismissing all happen synchronously; no
  background job or notification is involved.

## Bulk import

Drop several files into the same upload - an invoice and its packing list together, or several
suppliers' files across separate uploads - and Test reads each one on its own. There is no
spreadsheet-of-many-invoices import; each supplier document is its own file.

## See also

* [Upload packing list](upload-packing-list.md) - the Packing Lists page's own upload (files the
  workbook as an attachment, unread) and creating one by hand
* [Upload SPO](upload-spo.md)
* [Translating supplier wording](translating-supplier-wording.md)
* [System Management - Import column mappings](../system-management/import-column-mappings.md)
