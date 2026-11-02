# UAC: Stock position totals follow the visible columns

Plan: `PLAN-stock-pos-dynamic-total-02nov.md`.

- AC-1: With every column shown, Total stock = every warehouse column + Incoming BRW (unchanged).
- AC-2: Hiding a warehouse column (Columns chooser) takes it out of Total stock on every row at once; showing it
  again puts it back.
- AC-3: Hiding Incoming BRW takes it out of Total stock and Total incoming; hiding Incoming (Project) takes it
  out of Total incoming.
- AC-4: Every warehouse column hidden: Total stock = Incoming BRW (0 if that is hidden too).
- AC-5: Sorting by Total stock / Total incoming orders the whole result (server) by the visible-columns total.
- AC-6: A saved column layout that hides columns gives the same totals when it is applied (the page has no saved-views menu).
- AC-7: Export to Excel writes the shown warehouse and incoming columns and the visible-columns totals.
- AC-8: The Total stock / Total incoming header carries a tooltip naming the columns it adds up.
- AC-9: Usable at 375px and 1280px.
