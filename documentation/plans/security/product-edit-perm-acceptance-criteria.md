# UAC: permission gates on the product write routes

Plan: `PLAN-product-edit-perm-30oct.md`. Lane: PRODUCT-EDIT-PERM.

- **UAC1.** For each of the ten routes in the plan's table, a signed-in caller holding every
  `master_data.products.*` slug except the one the route needs gets 403 naming that slug, and
  nothing changes (no product created, edited, linked, deleted or imported).
- **UAC2.** For each of those routes, a caller holding only the route's slug succeeds as before.
- **UAC3.** Every non-GET route on the products router carries `require_permission` on a
  `master_data.products.*` slug; a new ungated write fails the structural test.
- **UAC4.** Product list: Create product shows only with `.add`; Import and Download template
  only with `.import`; bulk Chat search only with `.edit`; bulk Delete only with `.delete`.
- **UAC5.** Product record: the Edit button shows only with `.edit`; the Variants tab's write
  buttons (family Edit / Reset, Set or Change parent, Unlink, Reset to auto, Add variant, Remove
  variant) show only with `.edit`, and the links still render read-only without it.
- **UAC6.** The create page needs `.add` and the edit page needs `.edit`; without it a typed URL
  shows Access Denied, not the form.
- **UAC7.** The promotion line PUT changing a product's list price needs `.edit` (403 naming it
  otherwise, price unchanged); sending the unchanged list price back saves without it.
- **UAC8.** No migration and no new slug.

Tests: `sorento_crm_backend/tests/test_product_write_gates.py` (UAC1-3),
`ProductsList.uploadCostPrice.test.tsx` (UAC4), `ProductDetail.editGate.test.tsx` and
`ProductVariantsTab.test.tsx` (UAC5), `products/new/page.test.tsx` (UAC6); UAC7 is in the
backend gates file.
