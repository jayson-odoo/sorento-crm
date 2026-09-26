# UAC: PanelDataGrid keeps its page across a save

- AC-1 On fulfilment planning list view page 2+, saving a line decision (draft save) leaves the grid on the same page, same rows, same scroll position.
- AC-2 Confirm (refetch of the same selection) also leaves the grid on the same page.
- AC-3 If the saved change removes rows so the current page no longer exists, the grid shows the last page that does, never an empty page.
- AC-4 Typing in a PanelDataGrid search box still returns to page 1.
- AC-5 No other PanelDataGrid caller changes behaviour beyond keeping its page across a data update.
- AC-6 A parent-side filter change (the board's page search, a kind card, the breakdown dialog's own search) returns the grid to page 1; a data update under the same filter keeps the page.
