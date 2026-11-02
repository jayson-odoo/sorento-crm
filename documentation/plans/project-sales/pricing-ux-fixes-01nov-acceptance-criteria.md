# UAC: Pricing UX fixes (01 Nov)

Plan: `PLAN-pricing-ux-fixes-01nov.md`. Owner rulings 1 Nov: Q1 (a), Q2 (a), Part C added.

## A. Quotation editor
- A1 On a NEW quotation scope (not saved yet) quoted from a series, typing a price below the
  series floor shows **Minimum price RM x** under the rate within a second, without saving.
  (tests/test_pricing_ux_fixes.py::test_a1, QuotationLineFlags.test.tsx "asks the series verdict
  live on a NEW scope", QuotationVersionEditor.test.tsx AC-QF073)
- A2 On a new scope, a product outside the series shows **Non-standard** while picking. (test_a2)
- A3 With no series, nothing is non-standard; a half-typed price is not an error. (test_a3, a3b)
- A4 The new verdict route needs projects.projects.view or view_own; a view_own holder may ask it
  (no record behind it). (test_a4, test_a5)
- A5 A saved scope still judges against its own series exactly as before. (test_a6)
- A6 The approval panel reads *One line is priced below minimum price* / *N lines are priced
  below minimum price*. (QuotationApprovalPanel.test.tsx)
- A7 No "Set on ..." line is printed under the rate; **Minimum price RM x** stays.
  (QuotationLineFlags.test.tsx, QuotationVersionEditor.test.tsx)

## B. Series page
- B1 (Q1 a) The bin on ANY row, in-scope included, removes the product: the row disappears, a
  quotation line with it reads Non-standard, the series no longer prices it, the series listing
  no longer names it. (test_q1_*, SeriesProductsTable.test.tsx Q1)
- B2 A removed product comes back by pricing it (Add a product) or by code import; an import that
  does not name it leaves it removed. (test_q1_*_added_back_*, test_q1_an_import_does_not_undo_*)
- B3 (Q2 a) A selling price with no max discount gives floor = selling price, on products and sets,
  shown in the Floor column and enforced live and on save. (test_q2_*, updated floor tests)
- B4 A saved row's product cell is text, with no clear X. A new row with no product says
  **Pick a product to save this row** inline and is not saved. (SeriesProductsTable.test.tsx)
- B5 Search or page change saves edited rows first; a row that cannot save keeps the list where it
  is and a warning names it (never dropped). Reload/close with an unsaved edit asks first.
- B6 Every row save shows **Saved**.

## C. Standard quotation terms
- C1 Project Sales > Configuration > **Quotation Templates**: list, add/edit in a modal with bold
  and numbered list, **Activate**; gated projects.types.view (edit: projects.types.edit).
- C2 New quotations copy the active template; existing quotations are unchanged.
- C3 The quotation PDF keeps bold, and an `<ol>` clause list prints each number once.
  (tests/test_project_quotation_pdf_text_blocks.py)
