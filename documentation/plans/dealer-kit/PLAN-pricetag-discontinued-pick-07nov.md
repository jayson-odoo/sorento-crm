# PLAN: price tag request, discontinued combo options stay selectable

Status: in progress (small fix track: no migration, no auth/RBAC, FE-only diff expected)

Lane: PRICETAG-DISCONTINUED-PICK. UAC: `pricetag-discontinued-pick-acceptance-criteria.md`.

## Journey

Owner, 7 Nov: on the price tag request form (Dealer Kit), line SRTKS7061-BL with template
KS_1TAP_SP, the "Not sure, any of 5" picker shows SRTWT5831-BL greyed "Discontinued" and it cannot
be picked. "discontineud should still be able to choose".

## Cause (measured)

- `sorento_crm_frontend/components/dealer-kit/PriceTagLinesTable.tsx:311` (multi pick) and `:340`
  (single pick) pass `disabled: discontinued(candidate)` to the option. This is AC-C6 of
  `pricetag-combo-render-acceptance-criteria.md:68`, which the owner now overrides.
- `sorento_crm_frontend/lib/dealer-kit/price-tag-draft-lines.ts:663` (`lineProblemsOf`) blocks
  Approve with "<code> is discontinued." for any held part whose product is discontinued, so a
  pick that is now allowed would still stop the request at Approve.
- Backend: nothing rejects a discontinued part on save / submit / print. Save checks only that a
  part or candidate is a UUID the request's company can see
  (`sorento_crm_backend/app/services/price_tag_request_service.py:802`, `_visible_product_ids`); tag
  data reads `Product.is_active` only (`app/services/dealer_kit/tag_data_service.py:160`).

## Change

1. The two option builders keep the grey "Discontinued" hint (description on the single select,
   `badgeText` on the multi select) but drop `disabled`.
2. `lineProblemsOf` no longer names a discontinued product held in a choice-group row (a row with
   a `role`). A fixed part (role null) that is discontinued still blocks Approve: it is not a
   choice, and the owner's rule is about the picker; crew asks the owner about it separately.
3. Backend: a pytest pinning that save accepts a discontinued candidate pick, so a future reject
   cannot land silently.

## Out of scope

Every other place in the price tag / Dealer Kit flow that blocks a discontinued product is listed
in the PR's crew-note for the owner to rule on; none changes here.
