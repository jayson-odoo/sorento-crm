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
6. Once a file lands, a **Columns for** *\<file name\>* panel appears for it: two sample values
   from the sheet, the column's own header text exactly as written (line breaks kept), and a
   field picker for each column, with an **Ignore** entry for columns that don't matter. Required
   fields are marked, and **Test** stays disabled - naming what's still needed - until every one
   has a field. A header written on two lines, or split by a merged cell (shown as `外箱/木托尺寸
   [2]`), is picked the same way as any other column. If the guessed **Header row N** is wrong,
   the stepper beside it nudges the row up or down and the columns re-read.

   The first time this supplier's layout is seen, the panel is open. On a later upload of the
   same layout it is folded to "N of N columns mapped from saved layout" with a **Review** link,
   and it opens again only when a column this supplier has never had before turns up - already-
   mapped columns, and any you marked **Ignore**, don't reopen it.
7. Below the column grid, when the sheet packs more than one label into a single header cell -
   a supplier's B/L, container and seal often sit together like that, in one cell - a **Header
   fields** section lists every `label：value` pair found above the table (and in the footer
   rows below it), the value as its sample and the label exactly as the supplier wrote it. Pick a
   field for each: **PI number**, **Invoice date**, **BL**, **Container**, **Seal**,
   **Currency**, or **Ignore** for a label that isn't one of ours - an address, a phone number.
   Map a label once and it splits out of the shared cell from then on: DAFUYUAN's
   `提单号 ：OOLU2339207730 柜号 ：FSCU9304169 封条号：OOLLGZ7182` reads as one blob until 柜号 is
   mapped to **Container** and 封条号 to **Seal**, then splits into its three values on every
   later upload from that supplier. The section folds the same way the column grid above it does,
   into "N of N header fields mapped from saved layout" with its own **Review** link, and reopens
   only for a label this supplier has never had before.
8. Click **Test**. Test saves the column and header-field choices for this supplier together and
   reads the file in the same click. Each file comes back labelled **Proforma invoice**,
   **Packing list**, or **Combined**, with its blocks, lines, and header read out. A packing-list
   file also shows **Attaches to** - the invoice it will attach to, already picked when the file
   states the invoice number or shares its date; change it yourself only if that guess is wrong.
   A sheet that names itself 装箱单 (packing list) but also carries prices, cartons and CBM
   together reads as **Combined**: Test shows one proforma-invoice block and one draft
   packing-list block from the same file.
9. Click **Confirm**. A **Combined** file's Confirm creates the proforma invoice and its packing
   list together, from that one upload.

Re-uploading the same supplier's invoice (same supplier and the same invoice number written on
it) updates the existing proforma invoice in place and keeps its number; it does not create a
duplicate. Uploading a fresh copy of a file that states no invoice number always creates a new
proforma invoice.

Column mappings you save here are remembered per supplier and apply the next time that supplier
sends a file, on this dialog or on **Plan a container**. See [System Management - Import column
mappings](../system-management/import-column-mappings.md) for where saved layouts live and how
to remove one.

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

## The Lines tab

For lines with an item code, the **Product** column holds a dropdown (labeled **Search a product or set**)
that works in both read and edit mode. Picking a product or set writes the supplier-code alias immediately
with no Edit or Save step needed - a toast reports how many other lines on file were re-pointed to the
same alias. Clearing the dropdown on a line with a remembered code starts a 5-second reversible countdown
in the cell with a **Cancel** button; when the countdown lapses the alias is deleted and the line shows
the placeholder again.

A line with a blank item code (added manually before or after saving the invoice) keeps the old draft
behaviour: picking a product in edit mode patches the draft, and Save persists it.

**Access:** the **Product** column control is offered only to a user who holds both the proforma invoice upload
and reorder permissions. A user lacking either permission sees the item code as read-only text.

## General tab - Container, Seal, BL, Consignee

A proforma invoice's **General** tab shows **Container**, **Seal**, **BL**, and **Consignee**, in
that order, read off the header fields above (a field the sheet never stated, or that isn't
mapped yet, shows "-"). **Consignee** always reads your own company - it's never read off the
supplier's sheet.

## General tab - Source files

A proforma invoice's **General** tab also has a **Source files** section listing the file(s) it was read from:
the invoice workbook and, once attached, the packing-list workbook. Each file appears as a card showing
its name, type (e.g. "Proforma invoice workbook" or "Packing list workbook"), and file size. Icons above
the name offer **Preview** (to open the file in your browser) and **Download** (to save it).

## Convert to packing list

Our own packing list is never created by this upload - it is born by converting proforma invoices,
or by hand with **Create Packing List** on the Packing Lists page.

1. On **Proforma Invoices**, tick the invoices going into one container, click **Start**, then
   **Convert N to packing list** - or open a single invoice and press its own **Convert to
   packing list** button (the header's primary action; it reads **Convert the rest** once part of
   the invoice is already on a packing list). That header button is the only way to start a
   convert from an invoice's own page now; its **Packing Lists** tab no longer has a Convert
   button of its own.
2. The **Convert to a packing list** dialog opens on a **Container size** picker and, for a
   single invoice, a search box that filters the line table by code or product - useful once a
   PI runs to dozens of lines. Every invoice line appears once in that table, even when the same
   product repeats across several lines or packing rows - nothing doubles up and nothing is left
   out.
3. A **Carried onto the draft:** line states exactly what the packing list is about to receive -
   only the parts that actually have a value: **Container**, **Seal**, **SO** (the invoice's BL
   number), and **Consignee** (always your own company). A part the sheet never stated is left out
   of the line rather than shown as a dash.
4. Each supplier packing row goes onto the draft whole or stays behind for a later container - it
   is never split by typing a smaller quantity. If a supplier packed one product as two cartons of
   different sizes (Kailu's 50-carton batch and 35-carton batch of the same item, for example),
   the draft carries both as two lines, and the printed packing list shows it the same way.
5. Click **Convert**.

The packing list this creates shows **Container no**, **Seal no**, **SO** and **Consignee** filled
in on its own **Container** card; **Shipper** stays "-" (nothing on a supplier's sheet states it).
To get the workbook itself afterwards, see [Download a packing
list](upload-packing-list.md#download-a-packing-list).

**For an invoice uploaded before this fix:** if the same product sat on more than one line and its
packing rows had all landed on just one of them, a rebind script the administrator runs after
deploy corrects it; a packing list already converted from that invoice is left as it is.

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
* Downloading the packing list a convert produces runs in the background - see [Download a
  packing list](upload-packing-list.md#download-a-packing-list).

## Bulk import

Drop several files into the same upload - an invoice and its packing list together, or several
suppliers' files across separate uploads - and Test reads each one on its own. There is no
spreadsheet-of-many-invoices import; each supplier document is its own file. Each file gets its
own **Columns for** panel, named by the file.

## See also

* [Upload packing list](upload-packing-list.md) - the Packing Lists page's own upload (files the
  workbook as an attachment, unread), creating one by hand, and [downloading a packing
  list](upload-packing-list.md#download-a-packing-list)
* [Upload SPO](upload-spo.md)
* [Translating supplier wording](translating-supplier-wording.md)
* [System Management - Import column mappings](../system-management/import-column-mappings.md)
