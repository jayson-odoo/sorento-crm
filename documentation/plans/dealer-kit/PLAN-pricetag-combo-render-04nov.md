# PLAN: price tags render every combo shape (PRICETAG-COMBO-RENDER, 4 Nov)

Status: Build (Phase 2 tester-first; owner approved mock v5 4 Nov 21:31 MYT). Track: full (re-seed
import is an external-ingest surface; no migration).

Card: `CARD-pricetag-combo-render-04nov.md`. UAC: `pricetag-combo-render-acceptance-criteria.md`.
Mock: `pricetag-combo-render-mock.html`.

Owner (4 Nov): "make sure we can cater every combo scenario while reusing as many components as
possible and make our solution simple and straightforward and general". No product-type words in
code paths. No new component; one new prop (`max` on `SearchableMultiSelect`).

## No migration (measured)

- Position on a layer: a new optional key in the template document JSON (`dealer_kit.tag_template`
  doc), like `subjectPart` before it.
- Several picks from one group: `price_tag_request_line_parts` already takes several resolved rows
  sharing a `role` (`app/models/price_tag.py:299-351`; `price_tag_request_service.py:732-790`
  writes them in order, no uniqueness on role).
- Discontinued: `products.is_discontinued` exists (`app/models/product.py:354`).
- Combo prices / option SP / top-up / upgrade flag exist (`app/models/product_combo.py:71-76,
  129-133`).

## Contracts

### K1. Layer position (FE `lib/dealer-kit/tag-template-types.ts`)

```ts
export type SubjectSlot =
  | { kind: 'main' }
  | { kind: 'fixed'; index: number }               // 0-based, the line's fixed parts
  | { kind: 'pick'; group: number; index: number }  // 0-based group in combo order, 0-based pick
  | { kind: 'upgrade'; index: number };             // 0-based, the combo's upgrades
```
`subjectSlot?: SubjectSlot` beside every `subjectPart?: number` (text, image, product_slot,
price_badge, barcode props; `tag-template-types.ts:115,167,189,278,293`). Present = wins over
`subjectPart`.

### K2. Tag data: `slots` (BE `app/services/dealer_kit/tag_data_service.py`, FE `LineTagData`)

Each tag row (`resolve_tags_live`, `tag_data_service.py:773-990`) gains
```
"slots": {
  "fixed":    [part_row, ...],                         # line's resolved parts with empty role, sort order
  "groups":   [{"role": str, "size": int, "picks": [part_row, ...]}, ...],
  "upgrades": [part_row, ...]                          # combo's upgrade parts, combo order
} | None
```
- `groups`: with a combo on the line, the combo's choice groups in combo part order (role = the
  group name, size = number of options). Picks = the line's RESOLVED parts with that role in
  sort order, then the tag's `choices[role]` when that group's row is open. Without a combo, the
  distinct roles of the line's parts in order (excluding the upgrade row's role).
- `upgrades`: the combo's `is_upgrade` parts as part rows, each with `chosen: true` when the line
  picked it.
- `part_row` = today's `_part_row` (`tag_data_service.py:671-722`).
- `None` for a line with no parts and no combo, and for set lines.
- Template-editor preview (`with_preview_combo`, `tag_data_service.py:1127-1150`): the product
  data gains `slots` with fixed = combo fixed parts, each group's picks = ALL its options in combo
  order, upgrades = all upgrades (AC-A6).
- Schemas: add `slots` to the tag row / preview response models (`app/schemas/price_tag.py`
  ResolvedLineData and the preview product shape; `response_model` drops undeclared fields,
  assert it in a route test).

FE: `LineTagData.slots?` and `ProductTagData.slots?` of type
`{ fixed: TagPartData[]; groups: { role: string; size: number; picks: TagPartData[] }[]; upgrades: TagPartData[] } | null`.

### K3. `subjectOf` (FE `lib/dealer-kit/product-block.ts:200-227`)

`subjectSlot` present on the layer and the binding carries `slots` (line or preview product):
- main: line -> `productFromLineParent`; product -> the product itself.
- fixed / pick / upgrade: `productFromPart(item)`; missing item -> `EMPTY_PART_PRODUCT` (AC-A3).
Absent `subjectSlot`: today's behaviour unchanged. Helper `slotLabel(slot, slots | null)`:
"Main product", "Fixed part 2", "<role>, pick 2" / "Choice group 1, pick 2", "Upgrade 1".
`layerSubjectSuffix` (`:1158-1166`) uses it.

### K4. Needs and fit

- BE `app/services/dealer_kit/template_needs.py` (new module, pure):
  `template_needs(doc: dict) -> {"fixed": int, "groups": list[int], "upgrades": int}` (walks
  every layer, including group children, reading `props.subjectSlot`);
  `combo_shape(combo: ProductCombo) -> {"fixed": int, "groups": [{"role","size"}], "upgrades": int}`;
  `fit_reason(needs, shape) -> str | None`.
- `needs` is added to `ProductTagTemplateItem` (`app/schemas/price_tag.py:1635`) and to the tag
  template list item the FE's `listTemplates()` reads (`usePriceTagTemplateOptions`,
  `app/(protected)/dealer-kit/hooks/useProductTagTemplates.ts:100`), computed from the template's
  PUBLISHED doc.
- FE `lib/dealer-kit/combo-slots.ts` (new, pure): `comboShape(parts: ComboPartOption[])`,
  `fitReason(needs, shape)`, `needsText(needs, shape | null)` -> "Needs 3 from Kitchen tap,
  upgrade" / "Needs the main product only"; `groupIndexOf(role, shape)`.
- Reason text (both sides, same words): `Needs {k} from choice group {g+1}; {role} has {size}`,
  `Needs {n} fixed part(s); this combo has {m}`, `Needs choice group {g+1}; this combo has {n}`,
  `Needs {n} upgrade(s); this combo has {m}`.

### K5. Request line (FE)

- `ComboPartOption` gains `is_discontinued: boolean` (BE portal lookup
  `app/api/v1/public/portal_price_tag.py:886-910` and the CRM twin of that lookup, if any).
- `DraftPart` gains `product_ids?: string[]` (ordered picks for a group the template needs >= 2
  from). `draftLinesPayload` expands it into one resolved part per id, same role, in order.
  Loading a saved line folds two or more resolved parts sharing a role back into one DraftPart.
- `PartRow` (`components/dealer-kit/PriceTagLinesTable.tsx:235-331`): k = the chosen template's
  `needs.groups[groupIndexOf(part.role)]`; k >= 2 -> `SearchableMultiSelect` with `max={k}`;
  else today's `SearchableSelect`. Options: disabled + "Discontinued" when `is_discontinued`.
- Template sub-row (`:652-676`): description = size + `needsText`; options filtered to those
  whose `fitReason` is null for the line's combo.
- Hint row (`:711-723`): "<role>: pick n more." while picks < k.
- `lib/dealer-kit/price-tag-draft-lines.ts`: `linePickProblems(lines, pricingByKey)` returns the
  reasons for AC-C5, AC-C6, AC-D2 in line order; `PriceTagRequestForm.tsx`
  `approveBlockedReason` (`:1485-1494`) appends them (joined with a space) when the preview
  checks pass.
- `SearchableMultiSelect` (`components/common/SearchableMultiSelect.tsx`): `max?: number`; when
  set, no "Select all" row, and every unselected option is disabled once `value.length >= max`.

### K6. Combo template picker (FE)

`ComboTemplatesPicker.tsx` gains `parts?: ComboPartOption[]` (callers: `AddComboModal.tsx`
draft parts, `ComboTemplatesField.tsx` the saved combo's parts via `ProductCombosSection.tsx`).
With parts: option description = size + `needsText(needs, shape)`; a non-fitting template =
`disabled: true`, `badgeText: 'Does not fit'`, description = the reason.

### K7. Designer (FE `InspectorPanel.tsx`)

`SubjectInspector` (`:1485-1547`) also renders in the template editor (gate `:319-333` accepts a
missing `subjectParts` when the layer kind is subject-aware). Options per AC-A5, value encoded
`slot:main`, `slot:fixed:0`, `slot:pick:0:1`, `slot:upgrade:0`; legacy part values unchanged.
Choosing a `slot:` value writes `subjectSlot` and `subjectPart: undefined`.

### K8. Price (BE)

- `tag_data_service.py:853-903`: when the line has a combo (`combo_row is not None`), list =
  `combo_list` (may be None), sell = `combo_sell` if `sell_decided` else None; then the manual
  price and the marketing override as today. The part sum stays for lines without a combo.
- `pricing.py:537-610` (line pricing lookup): same rule.

### K9. Re-seed

- `scripts/flyer_combo_read.py` (new): `--flyer PDF [...] --company SRT --out seed.json`.
  Per page: page text (PyMuPDF, as `flyer_extraction.py`) -> one LLM call through
  `app.services.llm_provider.get_provider` with a JSON schema answer -> entries in the
  `import_product_combos.py` seed format, plus `page`, `flyer`, `unsure` (text) and the price
  fields. Bounded: max pages, max PDF bytes (reuse `MAX_SEED_BYTES` idea), answer validated with
  pydantic; codes kept only as read (stripped, upper-cased), never generated.
- `scripts/import_product_combos.py`: prices loaded (combo `lp`/`sp`, option `sp`, upgrade
  `topup`), except for hosts of a no-selling-price brand (reuse `pricing._no_selling_price_product_ids`);
  `--update` brings a `differs` combo to the seed (adds, removes, regroups, re-flags parts);
  dry-run report columns: `id, flyer, page, host, combo, shape, status, differences, dropped_parts,
  discontinued, price_note, unsure`; `--link-templates` links published templates whose needs fit;
  `--templates` builds the starter templates from one generic `position_template(name, fixed,
  groups, upgrades, free_asset)` layout (replaces `STARTER_TEMPLATES`).

## Tester rulings (4 Nov, captain)

1. `LinePricingRow.list_price` (`app/schemas/price_tag.py:1181`) becomes `Optional[float]`; any
   `sell < list` compare in `pricing.py` guards None.
2. Existing tests that pin the part sum on a combo line (`tests/test_price_tag_combo_tag_data.py`
   `test_ac_2_4_*`) or "no price loaded" / `would_create` / `unchanged` / the two fixed starter
   templates (`tests/test_import_product_combos.py`) are updated to the new owner-ruled contract.
3. A differing combo is brought to the flyer only by `--apply --update`.
4. A picked upgrade is a resolved part with role "Upgrade"; it appears only in `slots.upgrades`
   (`chosen: true`). `slots.fixed` excludes role "Upgrade" and any product that is one of the
   combo's upgrade parts.
5. `needs` is on both `ProductTagTemplateItem` and `TagTemplateResponse` (`price_tag.py:818`).
6. Only the portal combos lookup exists (`portal_price_tag.py:839`); it carries `is_discontinued`.
7. The coder also wires `approveBlockedReason` (`PriceTagRequestForm.tsx:1485`) to
   `linePickProblems` and passes the Add combo modal's draft parts to `ComboTemplatesPicker`.
   Test-file header comments record the remaining names (`resolvePicks`, `trimPicksToTemplate`,
   `linePickProblems(lines, pricingByKey, priceMode)`, `layerSubjectSuffix(layer, parts, slots?)`,
   `subjectSlots` prop, `flyer_combo_read.main(argv, *, provider=None, out=None)`).

## Slices (one lane, one PR)

1. Tests first (tester): the list below, red.
2. Coder: K1-K8 (FE + BE), then K9.
3. Reviewer + security reviewer (K9 + portal lookup change), browser pass per shape, hand test.

## Test list (tester writes these red, before any code)

Backend (`sorento_crm_backend/tests/`, Postgres via `tests/_pg_fixture.py`, own seed chain):
- `test_template_needs.py`: needs from a doc with main/fixed/pick/upgrade layers incl. a group
  child; fit + reason texts; one case per shape S1-S5 (S1 needs 3 from group 1 vs 5 options fits;
  S3 needs 3 vs 2 options -> reason "Needs 3 from choice group 1; Tap colour has 2"; S4 needs 2
  fixed fits, needs 3 fixed -> reason).
- `test_tag_data_slots.py`: tag rows carry `slots` for S1 (3 picks in pick order, upgrade listed
  unpicked), S2 (fixed 1, no groups), S3 (2 picks), S4 (fixed 2), S5 (upgrade chosen); preview
  combo fills picks with all options; route test that the response model keeps `slots`.
- `test_combo_price_no_sum.py`: combo line with no combo LP/SP -> list None, sell None (LP and SP
  lines), typed SP prints, stored combo SP prints, option SP still decides; non-combo line with
  parts still sums; same through the line-pricing lookup.
- `test_portal_combo_lookup_discontinued.py`: `is_discontinued` in the portal combos lookup.
- `test_template_needs_in_lists.py`: `needs` on `ProductTagTemplateItem` and on the template list.
- `test_flyer_combo_read.py`: stub provider answer -> seed entries per shape; codes not invented;
  oversize / too many pages refused; malformed model answer -> page reported, nothing crashes.
- `test_import_product_combos_reseed.py`: dry run statuses new / matches / differs (with the
  difference) / unsure (unresolved, discontinued); nothing written in dry run; `--apply` loads
  prices; `--update` regroups a differing combo; no SP/option SP/top-up for a no-selling-price
  brand host; `--link-templates` links only fitting templates; `--templates` builds one starter
  per shape.

Frontend (vitest, `sorento_crm_frontend`):
- `lib/dealer-kit/product-block.slots.test.ts`: `subjectOf` / `resolveSlotText` /
  `slotImageAttachmentId` per shape S1-S5 for main, fixed, pick, upgrade; missing position ->
  empty, never parent; layer without `subjectSlot` unchanged; `layerSubjectSuffix` words.
- `lib/dealer-kit/combo-slots.test.ts`: `comboShape`, `fitReason`, `needsText` per shape.
- `lib/dealer-kit/price-tag-draft-lines.picks.test.ts`: payload expands `product_ids` in order;
  load folds them back; template change trims; `linePickProblems` reasons (pick n more,
  discontinued, no combo list price on an LP line).
- `components/common/SearchableMultiSelect.max.test.tsx`: no Select all with `max`; options
  disabled at max; deselect re-enables.
- `components/dealer-kit/PriceTagLinesTable.picks.test.tsx`: k >= 2 renders the multi-select with
  the group name and "Pick k"; k <= 1 renders the single select; discontinued option disabled with
  "Discontinued"; hint text.
- `ComboTemplatesPicker.fit.test.tsx`: needs text in the combo's words, non-fitting disabled with
  the reason.
- `InspectorPanel.slots.test.tsx`: Product select shows in the template editor with the generic
  list; with a previewed combo shows its names; choosing writes `subjectSlot` and clears
  `subjectPart`.
- `TagSheetRenderer` parity: the print page text for a `pick` layer equals the canvas's
  (`layerText`) for S1.

Kill tests (reviewer): flip `subjectOf`'s missing-position branch to the parent -> a test fails;
re-enable the part sum on a combo line -> a test fails; drop `max` -> a test fails.
