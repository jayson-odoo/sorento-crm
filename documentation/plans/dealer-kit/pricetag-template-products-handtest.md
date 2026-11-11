## URL
crew test copy

## Setup
- Sign in as a user with `dealer_kit.tag_templates.manage` (marketing or admin).
- Pick one published price tag template (not a spec sheet page) that already prints on at least two
  products, and note one of those products, called P1 below. Note one product that does NOT use the
  template yet and has no price tag template at all, called P3.
- For step 15 (AC-7): a DIY-Tag product other than CB2151-DIY (crew's earlier run already emptied that
  one's Default SP), called D below, that uses DIY Tag and Small Price Tag LP and whose card shows
  Default SP = DIY Tag. Note what its card shows for Default LP and Default SP.
- For steps 16 to 18 (combos): a product with at least one combo, called H (its combos are on its
  product page, Combos tab), and a plain price tag template (no combo part positions), called T.
- The countdowns below read "Removing in 1s" because the dev DB's deferred_action_seconds is 1 (dev
  setting; prod uses its own window).
- No migration and no SQL is needed.

## Steps
1. From the home page, open Dealer Kit > Room Designer > Tag Templates in the sidebar.
2. Open the template you picked.
3. In the canvas toolbar, click the box icon next to Versions (its tooltip reads "Products (N)").
4. Type a code prefix the ticked products share into "Search products..." (for example DIY) and look at
   the ticked rows.
5. Clear the search, then type the code prefix of a product family (for example SRTKS).
6. Click Filters, pick a Category, then click outside the popover.
7. Tick the header checkbox, then click "Select all N records" in the banner.
8. Click "Clear" twice: the first undoes Select all, the second returns to what the dialog opened with.
9. Tick P3 by hand, and untick P1 by hand.
10. Click Save.
11. Wait for the countdown to finish.
12. Click the box icon again, open Filters, set "Show" to "Uses this template".
13. Open P1's product page and look at its "Price tag templates" card, then do the same for P3.
14. Open the template's designer again, click the box icon, untick any product, click Save, then click
    Cancel on the countdown.
15. Open the template "Small Price Tag SP" in the designer, click the box icon, search D's code, tick D,
    click Save, then open D's product page and look at its "Price tag templates" card.

16. Open T in the designer, click the box icon, open Filters, set "Type" to "Combos", then click outside
    the popover. Search H's code.
17. Tick one of H's combos that does not use T yet, called K, click Save, then open H's product page,
    Combos tab, and look at K's "Price tag templates" field.
18. Back in T's designer, click the box icon, set "Type" to "Combos", untick K, click Save and wait
    for the countdown, then look at K's field on H's Combos tab again.

## Expected
- Step 3: one dialog titled "Products for <template name>", no tabs. The products that use the
  template are already ticked, the footer reads "N use this template", Save is greyed out.
- Step 4: the rows that use the template show ticked.
- Step 6: the Filters button stays visible while rows are ticked and shows "Filters 1".
- Step 7: the footer reads "<N + added> use this template after Save: <added> added, 0 removed". No
  product that was ticked before is unticked.
- Step 8: after the first Clear the Select all additions are gone (the page you ticked in step 7 stays
  ticked); after the second the ticks are exactly what the dialog opened with, footer
  "N use this template". Never nothing ticked.
- Step 9: the footer reads "N use this template after Save: 1 added, 1 removed".
- Step 10: a green toast "Linked 1 product" appears at once. The Save button becomes "Removing in 1s"
  with a Cancel (dev setting; prod uses its own window), and the dialog cannot be closed while it
  counts down. No confirm dialog.
- Step 11: the dialog closes. The box icon's tooltip reads "Products (N)" with the same N as before
  (one added, one removed).
- Step 12: only the products that use the template are listed. P3 is there and ticked, P1 is not.
- Step 13: P1's card no longer lists the template. Whatever default the removed template held is
  cleared; if P1 is left with one template, that one becomes its saved default for the price types it
  fits (for example, a DIY-Tag product unticked from DIY Tag is left with Small Price Tag LP as its
  saved Default LP). P3's card lists the template, and it is P3's default because it is its only
  template. Products that already showed a default keep it.
- Step 14: Cancel ("Removing in 1s") keeps every link; reopening shows the same ticks as before step 14.
- Step 15: D's card now also lists Small Price Tag SP, and its Default LP and Default SP read exactly
  as you noted in Setup (Default SP is still DIY Tag). Small Price Tag SP is not a default.
- At 375px wide: the box icon is under the toolbar's "More actions" menu as "Products (N)", the dialog
  is full width, and the product grid scrolls sideways inside its border without the page scrolling
  sideways.
- A user without `dealer_kit.tag_templates.manage`, and any spec sheet page, shows no Products button.
- Step 16: the same dialog, no tabs, now lists combos: H's code, the combo name, H's category and
  brand, and a grey "Combo" hint after the code. Combos that use T are ticked. The footer count
  includes them. A combo a template with combo part positions cannot print is greyed out and its
  checkbox tooltip says why (for example "Needs 3 fixed parts; this combo has 2"); with plain T
  every combo can be ticked.
- Step 17: toast "Linked 1 combo". K's "Price tag templates" field lists T; if K had no template, T is
  its default. The designer's box icon tooltip reads one more in "Products (N)".
- Step 18: "Removing in 1s" with Cancel, then the dialog closes; K's field no longer lists T, and K's
  other defaults are unchanged.
