## URL
crew test copy

## Setup
- Sign in as a user with `dealer_kit.tag_templates.manage` (marketing or admin).
- Pick one published price tag template (not a spec sheet page) that already prints on at least two
  products, and note one of those products, called P1 below. Note one product that does NOT use the
  template yet and has no price tag template at all, called P3.
- No migration and no SQL is needed.

## Steps
1. From the home page, open Dealer Kit > Room Designer > Tag Templates in the sidebar.
2. Open the template you picked.
3. In the canvas toolbar, next to Versions, click "Products (N)".
4. Look at the dialog without changing anything.
5. Type the code prefix of a product family into "Search products..." (for example SRTKS).
6. Click Filters, pick a Category, then click outside the popover.
7. Tick the header checkbox, then click "Select all N records" in the banner.
8. Click the small "Clear" next to "N selected" above the grid.
9. Tick P3 by hand, and untick P1 by hand.
10. Click Save.
11. Wait for the countdown to finish.
12. Click "Products (N)" again, open Filters, set "Show" to "Uses this template".
13. Open P1's product page and look at its "Price tag templates" card, then do the same for P3.
14. Open the template's designer again, click Products, untick any product, click Save, then click
    Cancel on the countdown.

## Expected
- Step 3: one dialog titled "Products for <template name>", no tabs. The products that use the
  template are already ticked, the footer reads "N use this template", Save is greyed out.
- Step 6: the Filters button stays visible while rows are ticked and shows "Filters 1".
- Step 7: the footer reads "<N + added> use this template after Save: <added> added, 0 removed". No
  product that was ticked before is unticked.
- Step 8: the ticks go back to exactly what the dialog opened with (never to nothing), footer
  "N use this template".
- Step 9: the footer reads "N use this template after Save: 1 added, 1 removed".
- Step 10: a green toast "Linked 1 product" appears at once. The Save button becomes "Removing in 5s"
  with a Cancel, and the dialog cannot be closed while it counts down. No confirm dialog.
- Step 11: the dialog closes. The toolbar button now reads "Products (N)" with the same N as before
  (one added, one removed).
- Step 12: only the products that use the template are listed. P3 is there and ticked, P1 is not.
- Step 13: P1's card no longer lists the template; if P1 had one other template left, that one is now
  its default. P3's card lists the template, and it is P3's default because it is its only template.
  Products that already had a default keep it.
- Step 14: Cancel keeps every link; reopening Products shows the same ticks as before step 14.
- At 375px wide: Products is under the toolbar's "More actions" menu, the dialog is full width, and
  the product grid scrolls sideways inside its border without the page scrolling sideways.
- A user without `dealer_kit.tag_templates.manage`, and any spec sheet page, shows no Products button.
