# UAC: access-sheet follow-up fixes (ACCESS-SHEET-FIXES)

Plan: `PLAN-access-sheet-fixes-27oct.md`.

- F1.1 A dealer whose rows tag SRT only: its Sorento exact account is ticked; a Mocha exact account with
  the same name is listed, unticked. (`test_u8_u10_exact_accounts_span_every_company_but_only_row_companies_are_proposed`)
- F1.2 Rows tagging SRT and MCH: both exacts ticked. F1.3 MCH-only rows, only an SRT exact: nothing ticked.
- F2.1 Opening the pick card search runs one customer search and shows the results.
  (`AccessSheetImportPage.pickerFetch.test.tsx`)
- F3.1 Viewer in Sorento granted Mocha: a contact linked only to Mocha `300-1001` shows `300-1001 (MCH)`.
- F3.2 Not granted Mocha: the code is not shown and the Customer filter does not match it.
- F3.3 Customer filter options read "Mocha · 300-1001 - NAME"; a restored id keeps that label.
- F4.1 A contact holding MCH keeps every brand on import; a narrowed one goes back to every brand.
- F4.2 SRT-only contact without MCH still narrows to the Sorento dealer brands.
- F4.3 The script lists (dry run) and resets (`--apply`) only contacts the import narrowed from every
  brand that hold MCH and still carry a list, with an audit row each.
- F5.1 Every Internal Users column header sorts; asc and desc order the rows by that column on the server;
  an empty Customers cell sorts last both ways; "All" brands sorts first ascending.
