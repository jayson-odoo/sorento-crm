# UAC: pick a template's products inside the Tag Template designer

Plan: `PLAN-pricetag-template-products-10nov.md` (Design v3). Mock: `pricetag-template-products-mock-v3.html`
(owner approved 10 Nov 23:43).

- AC-1 A user with `dealer_kit.tag_templates.manage` sees a "Products (N)" button in the designer
  toolbar of a price tag template; N = products that use it. Without manage, or on a spec sheet page,
  there is no button.
- AC-2 The button opens ONE view (no tabs): the shared product grid of "Copy to other products"
  (search, Category / Brand filters, ticks, Select all, paging, discontinued grey hint), with every
  product that uses the template already ticked.
- AC-3 The Filters popover also carries "Show: Uses this template" (clearable), which lists only the
  products that use it.
- AC-4 Ticking adds, unticking removes; the footer reads "N use this template" and, once changed,
  "N use this template after Save: a added, r removed". Save is off while nothing changed.
- AC-5 "Select all N records" adds the matching products to the ticks; it never unticks a product
  outside the search. "Clear selection" goes back to the ticks before it.
- AC-6 Save links the added products at once. If any were removed, the Save button becomes the
  standard countdown with Cancel (no confirm dialog); once it lapses the removals commit and the
  dialog closes. Cancel keeps every link.
- AC-7 A bulk link never changes an existing default: a product with no template gets this one as
  Default LP / SP (for the types it fits); a product with one template keeps that one as default; a
  product with stored defaults keeps them and gains none.
- AC-8 A removal that leaves a product with one template makes that one its default.
- AC-9 The product page "Price tag templates" card shows the same links at once, both directions.
- AC-10 Products of another company are never listed, seeded, linked or unlinked; a non-uuid id is
  ignored; more than 500 ids in one call is refused.
- AC-11 Usable at 375px and 1280px: the modal is full width on a phone and the grid scrolls sideways
  inside its border.
