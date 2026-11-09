# PLAN: show each spec value's price-tag icons on the product Specifications tab (SPEC-VALUE-ICONS, 9 Nov)

Status: owner answered 9 Nov ~14:25; building (PR #2279). Track: small fix track (expected diff
well under 300 lines, no migration, no auth/RBAC change, no new ingest surface).

Owner, 9 Nov ~13:55 MYT, on product detail > Specifications: "think it will be good if I can view
the icon here ... like for Mixer, there are icons tied to this spec value, if I can view here then
it will be good".

## What exists today (measured)

- **The rule lives on the spec VALUE, not on the Dealer Kit icon.** Owner ruling 5 Nov 20:35
  moved it: `product_spec_registry.value_icons` is `value -> [icon asset id, ...]` in the admin's
  order, plus `icon_order` for the key's place in the tag's one sequence
  (`sorento_crm_backend/app/models/product_spec.py:162-168`). It is set on Master Data > Product
  Specifications > a key > Values and words, Icons column
  (`sorento_crm_frontend/app/(protected)/master-data-management/product-specifications/components/record/ValuesAndWordsTab.tsx:398-486`),
  gated by `dealer_kit.library.manage` (`ValuesAndWordsTab.tsx:102`).
- **The tag's resolver.** Backend flattens the rules into one ordered list of
  `{id, name, spec_key, values}` keeping only live, non-deleted `kind = icon` assets
  (`app/services/dealer_kit/asset_service.py:470-532`), served with signed URLs by
  `GET /api/v1/dealer-kit/feature-icons` behind `dealer_kit.tag_templates.view`
  (`app/api/v1/dealer_kit/tag_data.py:46,152-167`). The ONE matching function used by canvas,
  request preview and print is `featureIconsFor(specs, icons)`
  (`sorento_crm_frontend/lib/dealer-kit/feature-icons.ts:35-53`): it matches on the RAW stored value
  (`true`/`false` for a bool, `str()` otherwise, `app/services/dealer_kit/tag_data_service.py:304,310-314`).
- **The tag reads the same values the tab shows.** `product_specs` reads the product's
  `product_specifications.values` row (`tag_data_service.py:266-308`); the tab builds its rows from
  the same row (`ProductSpecificationsTab.tsx:439-505`, `components/spec-table/types.ts:39-68`).
- **Static icons are not spec data.** Warranty / anti-bacteria are fixed `badge` layers on the
  template (owner 5 Nov), so no spec row maps to them.

## Proposed behaviour

R1. Each row of the Specifications table shows the icons its CURRENT saved value carries, using
    `featureIconsFor([{key, raw}], icons)` over the same `GET /dealer-kit/feature-icons` list the
    print page reads, so the tab can never disagree with the tag about which icon a value prints.
R2. Shown as small (24px) thumbnails inline after the value text, in the rule's order; tooltip =
    the icon's name. Reuses the existing `<img>` thumbnail markup from the Values and words tab
    (one image component, owner 3 Nov); no new rendition.
R3. A row whose value carries no icon shows nothing (no placeholder, no "No icons" text).
R4. Clicking an icon opens that spec key's record (Master Data > Product Specifications > key),
    where the icon is actually set, for a user holding `dealer_kit.library.manage`; others get the
    tooltip only.
R5. While a row is in edit its icons are hidden (the editor needs the width); after save they
    follow the new saved value.
R6. Only a user holding `dealer_kit.tag_templates.view` sees icons; for anyone else the list is
    never fetched and the table is exactly as before.

### Examples (illustrative: the dev DB is not reachable from this cloud sandbox)

| Product row | Value | Shows |
| --- | --- | --- |
| Water supply | Mixer (`mixer`) | the hot + cold icons set on `water_supply = mixer`, in that order |
| Water supply | Cold only (`cold_only`) | the cold icon, if one is set |
| Steel grade | 304 | the SUS 304 icon, if one is set on `steel_grade = 304` |
| Colour | Black | nothing (no icon set on that value) |
| (any) | warranty / anti-bac | never on a row: static template badges |

### Edge cases

- Several icons on one value: all shown, in the admin's order.
- The same icon on two rows: shown on both rows (the tag prints it once; the tab answers "what does
  THIS value carry").
- Icon deleted from the library, or removed from the value: gone (the backend list drops it).
- Spec key deactivated: no icons (`active_registry`).
- Value typed by hand (`human` source): matched on its stored value like any other.
- Conflict row (rules propose another value, authored one holding): icons of the HOLDING value,
  which is what prints.
- Unknown key (no longer in the registry): no icons.
- Template without a feature_icons layer: the tab still shows the value's icons; whether a given
  template draws them is the template's choice.

## Owner rulings (9 Nov ~14:25)

1a inline after the value. 2a click opens the spec key's record, for `dealer_kit.library.manage`
holders; others get the tooltip only. 3a only `dealer_kit.tag_templates.view` holders see icons (no
RBAC change). 4a static warranty / anti-bac not shown. 5a nothing when a value has no icon.

## Questions for the owner (answered above)

1. Placement: inline after the value (rec) or a narrow Icons column? Rec: inline, keeps the table
   at 3 columns and fits 375px.
2. Click target: the spec key's record where icons are set (rec), not the Dealer Kit icon, since the
   rule lives on the value since 5 Nov.
3. Who sees them: the list sits behind `dealer_kit.tag_templates.view`. (a) users without it see no
   icons (rec: no RBAC change), or (b) widen the endpoint to `master_data.products.view` too.
4. Static warranty / anti-bac icons: not shown (rec), since they are not tied to any spec value.
5. Product with no icons at all: nothing extra (rec), not an "icons: none" line.

## Tests (after answers)

- vitest: row with `mixer` shows two icons in order with names; row with no icon shows none; bool
  value matches `true`; conflict row uses the holding value; no permission -> no fetch, no icons.
- Kill test: swap `raw` for the display label in the matcher and the mixer test must go red.
