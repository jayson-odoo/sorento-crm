# UAC: project quote line tools

Plan: `PLAN-project-quote-line-tools-11nov.md`.

- AC-1 In edit mode, the row ⋯ menu and the right-click menu of a priced line offer "Duplicate line".
  It is absent in view mode and on a section heading row, and disabled on a line staged for removal.
- AC-2 Duplicate line inserts one new line directly below the source with the same product or set,
  rate, every quantity cell, description, brand, UOM, notes and picks; the source is unchanged; the
  scope total grows by the source's line total.
- AC-3 After Duplicate line the new line's product picker has focus.
- AC-4 Changing the product on a copy fills rate (series price, else blank), description, brand and
  UOM exactly as a pick on a new line does.
- AC-5 A saved line with `is_discounted` true and `is_below_floor` false shows "Below default price"
  under the product code, in view and edit modes. A line with `is_below_floor` true shows no
  "Below default price" pill.
- AC-6 Typing a rate below the default price on any line (saved, new, or on a new unsaved scope)
  shows "Below default price" once the live verdict answers; typing it back to the default removes it.
- AC-7 The live verdict returns `is_discounted` by the same rule as the save: below the series price
  where the series names the product or set, else below the list price; false when neither exists.
- AC-8 The lines toolbar has a multi-select "Flags" filter with "Non-standard" and
  "Below default price"; choosing options shows only lines matching any of them, AND-ed with the
  search; numbering and totals do not change; each option shows its count on the tab.
- AC-9 On a saved, unedited quotation, the number of "Below default price" pills across all tabs
  equals the banner's "N lines are priced below the default price".
- AC-10 Usable at 375px and 1280px.
