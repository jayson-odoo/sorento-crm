# 1.8-Purchasing - Translating supplier wording

Many suppliers write their proforma invoice and packing list in Chinese. This is where their
wording gets an English reading: once, on the upload preview or on the invoice itself, and it is
remembered for every proforma invoice on file, this one and every later one, forever.

## Where the English comes from

1. On the **Upload supplier documents** dialog (see [Upload a proforma
   invoice](upload-proforma-invoice.md)), click **Test**. Any block, line or note written in
   Chinese shows a **Translations - English beside the Chinese** panel: the supplier's text on
   the left, an editable English box on the right, and a **manual** or **ai** badge once
   something has filled it in.
2. A phrase already known (from an earlier correction, on this document or any other) fills in
   on its own. A phrase seen for the first time is sent to the AI model for a first guess,
   badged **ai**.
3. Type over any box before **Confirm** - the badge switches to **manual** the moment you edit
   it. What you confirm here is what every later document carrying the same Chinese text will
   read from that point on.

## On the proforma invoice: the Description (EN) column

Open a proforma invoice and both its **Lines** tab and its **Packing** tab carry a
**Description (EN)** column right beside **Description**. **Description** always stays the
supplier's own wording; **Description (EN)** is the English reading.

* A dash means nobody has told the system the English for that wording yet.
* An already-English description also shows a dash - it is still editable, but nothing is
  guessed or auto-filled for it, on purpose.
* Click the dash (or the English text, to correct it), type the English, and press **Enter** to
  save. **Escape** cancels without saving.
* Saving updates every row on file that carries that exact Chinese wording - not just the row
  you clicked. That means this proforma invoice's other lines or packing rows with the same
  wording, and every other proforma invoice's lines and packing rows with the same wording, all
  read the new English immediately. A toast names how many rows updated.
* This column appears the same way whether the invoice is in view mode or in Edit mode, and
  editing it does not put the invoice's own Edit form into an unsaved state.
* Only the people who can **Match** or **Dismiss** a packing row (see [Upload a proforma
  invoice](upload-proforma-invoice.md)) can edit this column. A row with nothing in
  **Description** has nothing to translate.

## System Management > Translations

**[System → Configuration → Translations](/system-management/translations)** lists every word
the system has learned, across every supplier document: the supplier's text (**Source**), the
English (**English**), whether it came from a person or the AI model (**Source kind**), who
last set it and when, and how many times it has been reused (**Hits**).

* **Correct** a word by editing its **English** cell in place - the correction reaches every
  proforma invoice line and packing row on file that carries that Chinese text, the same as
  editing it on the invoice itself.
* **Forget** a word with the row's delete button. This clears the English back to a dash on
  every row that had it - it does not delete the Chinese wording from any document, only the
  English reading of it.

## Where the English goes next

Once a proforma invoice's line carries an English reading, it travels with the description
wherever that line is copied onward, in place of the Chinese:

* The packing list line created when you **Convert** the proforma invoice (see [Upload a
  proforma invoice](upload-proforma-invoice.md)).
* The workbook produced by **Export adjusted PI** on the proforma invoice's own gear menu.
* The notes on the packing list, for a supplier row that was dismissed or never matched to a
  product - its wording is still named there in English once the glossary knows it.

A line whose wording has no English yet still carries its original Chinese through all three;
nothing is blocked on a translation being filled in.

## What's captured

The English reading of a piece of supplier wording, keyed to that exact wording - not to any one
document, line or row.

## What gets created

Nothing new to open or manage separately: your correction is stored the moment you press Enter
or the panel is confirmed, and every current and future proforma invoice reading that same
wording shows it.

## How you'll be notified

Everything here is immediate. Saving a translation shows a toast naming how many rows updated;
there is no background job and nothing to wait for.

## Bulk import

Not applicable - translations are added and corrected one phrase at a time, either on the upload
preview, on a proforma invoice's own tabs, or on the Translations page.

## See also

* [Upload a proforma invoice (and its packing list)](upload-proforma-invoice.md)
* [System Management - Import column mappings](../system-management/import-column-mappings.md)
