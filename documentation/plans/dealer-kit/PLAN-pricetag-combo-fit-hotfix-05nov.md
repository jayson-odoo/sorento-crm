# PLAN: PRICETAG-COMBO-FIT-HOTFIX (5 Nov 2026)

Status: implemented, awaiting merge (small fix track: no migration, no auth change, diff well under 300 lines)

## Problem

#2172 made every template that reads fewer combo fixed parts than the combo has "Does not fit"
(`fit_reason`: "Prints 0 of this combo's 4 fixed parts"). No production template has any combo
position field yet, so EVERY real template was greyed out and refused for every combo with fixed parts.

## Rule (owner, option a)

A template with NO combo position field at all (`template_needs` = fixed 0, no group read, upgrades 0)
is a plain template. It fits any combo and prints the combo as one product (host code and name,
the combo's stored prices), exactly as a combo line printed before #2172. The fit check and its
refusal apply only to a template that reads SOME position.

## Change

One place per side, so every caller follows:

- BE `app/services/dealer_kit/template_needs.py` `fit_reason`: None for a plain template. Callers:
  `product_tag_template_service.py` `_require_fit` (422 TAG_TEMPLATE_DOES_NOT_FIT on save),
  `fitting` (read-time filter of links), template lists' `needs` (unchanged numbers).
- BE `missing_positions` already owes nothing for a plain template (no group, `fixed[:0]`), so
  `require_template_positions` (TEMPLATE_POSITIONS_MISSING) never fires; pinned by a test.
- FE `lib/dealer-kit/combo-slots.ts` `fitReason`: same rule. Callers: `ComboTemplatesPicker`,
  `price-tag-draft-lines.ts` `lineTemplateState`.

## Tests

- pytest: plain template fits S1..S4 shapes; links save; approve passes; partial template still refused.
- vitest: combo-slots plain fits; picker enables a plain template; partial still disabled.
