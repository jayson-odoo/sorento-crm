# UAC: PS-QUOTE-MATRIX (quotation grid scopes)

Plan: `PLAN-ps-quote-matrix-02nov.md`. Card rules R1-R22: `CARD-ps-quote-matrix-02nov.md`.

- AC-1 A scope with no columns (every existing quotation) shows, prints, exports and totals exactly as before; no data
  is converted.
- AC-2 A salesperson can add column headers and shoulders to a scope's draft version, rename, reorder, delete
  (deferred action), and copy them from another scope of the same document.
- AC-3 Adding the first column keeps every line's quantity (moved into it); deleting the last column keeps each line's
  summed quantity.
- AC-4 Each cell takes a quantity (blank = 0, no negatives); the line quantity = sum of its cells and every total,
  approval, PO and SO check reads it.
- AC-5 A row shows Qty + RM per header that has 2+ shoulders (when the scope has 2+ headers), and always Total qty +
  Amount; a header pair with no quantity shows "-".
- AC-6 Footer shows Total qty under every quantity and per-header Qty column, Total (RM) per header, and the scope
  total.
- AC-7 Pasting a block of numbers copied from Excel fills cells right and down; a non-number refuses the paste with
  one message.
- AC-8 The same product may sit on several rows; the PO quantity check sums them.
- AC-9 Revise and make-quotation copy columns and cells; editing a draft's columns never changes an issued version.
- AC-10 PDF: 2-row header repeated per page, vertical headings when wide; Excel: merged 2-row header, numbers, live
  SUM formulas.
- AC-11 Sign page: a scope with columns expands to a read-only grid; the customer can suggest a cell quantity, a row
  total, a price or removal.
- AC-12 Accepting a row total on a multi-cell row requires a split that adds up to it; accepting a row total and a cell
  suggestion on the same row is refused.
- AC-13 Usable and unclipped at 375 px and 1280 px.
