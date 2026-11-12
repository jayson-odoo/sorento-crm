# UAC: Certification tab UX (CERT-TAB-UX)

Plan: `PLAN-cert-tab-ux-11nov.md`. Owner feedback 11 Nov 2026.

## List (Certification tab of a quotation)

- UX-1 A warm list of a 34-certificate quote reads no certificate file and runs a fixed number of
  SQL statements (<= 40, measured 13), not one or two per certificate; under 1 s.
- UX-2 The list route does not queue behind PDF work (`@heavy` off the list only); a cold list holds
  at most one file's bytes at a time.
- UX-3 Every row is one line: certificate number (title and "Also filed as" in its tooltip), scheme,
  valid-until date with its validity badge inline, quoted products, rows marked, source, menu.
- UX-4 Search box matches certificate number, scheme, title, issuer, other filings and quoted
  product codes. "Nothing matches" with a hint when search/filters hide every row.
- UX-5 Filters (multi-select, chips with clear): Scheme, Validity (Valid/Expiring/Expired), Rows
  marked (exactly Marked, Edited, Code not found, Code needed, No text, No file), Source (Auto/Added).
- UX-6 Every data column sorts by a header click (client-side).
- UX-7 No "Suggested" wording anywhere on the tab, the box editor or the register.

## Box editor

- UX-8 No "Remove box" button; "Draw box" stays.
- UX-9 Select a box, Delete/Backspace removes it. Right-click a box: menu with Delete removes it.
  A Delete key pressed inside the open menu removes nothing.
- UX-10 Opening a certificate lands the viewer on its first box (reading order) and outlines it.
- UX-11 Each product with a box has a "Go to box" button that scrolls the viewer (not the page) to
  that box and outlines it for ~1.6 s, no animation.
- UX-12 "Save boxes" is the primary button in the page header, disabled until something changes;
  the header shows "Unsaved changes" after an edit and "Saved" after a save.
- UX-13 Product state reads "Marked" for a found box, whether the code was typed or read.

## Crew browser pass fixes (11 Nov 2026)

- UX-14 A certificate whose file is missing from storage is remembered as missing for its revision:
  a warm list does not call storage for it (34 missing files: 5.2 s before, ~50 ms after). The miss
  is retried after 1 h, and the box editor and issuing always read the file themselves, so a file that is back is
  seen at once and the miss forgotten.
- UX-15 A product's state follows the boxes in force: a product marked by its code whose box was
  deleted (this quote only, or as default) reads "Not marked" (`unmarked`). A box drawn for this
  quote names no product, so while one exists no product is unmarked.
- UX-16 A quote-only save keeps each merged box's `product_ids`, so a box shared by two products
  keeps both marked.
