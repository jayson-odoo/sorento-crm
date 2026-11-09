# UAC - COMBO-COPY-TO-PRODUCTS

Written from the owner's answers of 9 Nov 2026 (~16:35, recorded in `PLAN-combo-copy-to-products-09nov.md`)
and #2280's picker rulings.

- AC-1: A user with `master_data.products.edit` sees "Copy to other products" in each combo's header on product
  detail > Combos, next to the delete icon. A user without it sees no button. At 375px the button shows its icon
  only (accessible name "Copy combo <name> to other products") so the combo name keeps its width.
- AC-2: The button opens a picker of products: search, Category and Brand multi-select filters, row ticks with
  shift-click and drag, and "Select all" over every product the search and filters match. The product being edited
  cannot be ticked. A discontinued product stays pickable with a grey "Discontinued" hint. The footer counts the
  picks; more than 500 picks blocks Next and says one copy takes at most 500.
- AC-3: Next runs a dry run (no write) and shows the confirm step: how many products get the combo as a new one, any
  picked product skipped because it is a part of this combo, the 500 cap, and, only when the source combo has price
  tag template links and the user cannot manage tag templates, that the templates are not copied.
- AC-4: Every picked product that already has a combo with the same name (letter case ignored) is listed with Skip /
  Overwrite, default Skip, plus an "Overwrite all" toggle. Copy is disabled while nothing would be written.
- AC-5: Copy writes everything in one call, all or nothing. Each new combo has the same name, the target as host,
  every part (fixed, choice groups, sell price if picked, upgrade and top-up), list and sell price, description with
  its formatting, legacy free-items text, accessories included (with overrides and pictures, minus the target
  itself), box style and the same cover picture (shared, with a gallery link on the target).
- AC-6: Overwrite keeps the target combo's row (request lines naming it stay linked) and replaces its fields, parts,
  accessories included, box style, prices, description, picture and template links with the source's.
- AC-7: Price tag template links (with the LP / SP defaults) copy only for a user holding
  `dealer_kit.tag_templates.manage`; otherwise none are written and an overwritten combo keeps its own.
- AC-8: A picture is deleted from storage only after the commit and only when nothing at all still points at it
  (another combo, a gallery link, a quotation line, an accessory, a dealer kit asset or any other reference).
- AC-9: A target outside the user's company scope, or in another company than the source host, fails the whole call
  with "Product not found"; the source host itself is dropped from the targets.
- AC-10: The dialog title clears the close X at 375px; the dialog is usable at 375px and 1280px.
