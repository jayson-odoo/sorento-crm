# PLAN: combo settings UX (one accessory add, preview with choices, description variables)

Status: Review (owner approved mock v2 + own Combos tab, 10 Nov ~16:40; reviewer round 1 fixed).
Track: LEAD, size M, one additive migration (`combo_0001_part_labels`), no auth/RBAC change.
Lane: COMBO-SETTINGS-UX. Mocks: `documentation/plans/dealer-kit/mocks/combo-settings-ux-v1.html`, `...-v2.html` (dev rows).

Owner ask (10 Nov ~15:45 MYT, on SRTKS7061-BL's Combos tab): three controls per accessories block
is too much; the tag preview cannot be seen with a choice made; the combo Description should take
variables (fixed parts, their price tag description, dimensions) so it is dynamic.

## Scout (file:line)

| What | Where |
| --- | --- |
| Combos tab, one block per combo | `sorento_crm_frontend/app/(protected)/master-data-management/products/[id]/components/ProductCombosSection.tsx:590` (`ComboBlock`) |
| Description editor + preview side by side | same file `:138` (`DescriptionField`, blur-save, preview follows the draft) |
| Part row ("Sell price if picked", Upgrade) | same file `:311` (`PartRow`) |
| Accessories block (Box style / Add accessory / Add product) | `.../[id]/components/AccessoryListField.tsx:308-354` (3 `SearchableSelect`s) |
| The "second" accessories block the owner saw | `.../[id]/components/ProductAccessoriesSection.tsx` (the PRODUCT's own list, mounted under Combos at `ProductDetail.tsx:611`), same `AccessoryListField` |
| Tag preview | `.../[id]/components/ComboTagPreview.tsx:70-84`: the line is sent with `parts: []`, so nothing can be picked |
| Preview endpoint already takes picks | BE `app/services/dealer_kit/product_tag_template_service.py:961-974` builds transient line parts from `{product_id, role}` / `{role, candidates}`; `tag_data_service.py:1053` `_line_slots` places them (fixed / per-group picks / chosen upgrade, role `Upgrade`); `_combo_with_picks` `:1331` marks `picked` |
| Merge fields | `sorento_crm_frontend/lib/dealer-kit/merge-fields.ts`: `{{...}}` tokens; `slot.fixed.N.*`, `slot.pick.G.I.*`, `slot.upgrade.N.*` positions `:116-176`; fields today `code, name, list_price, price_tag_description, sell_price (pick only)`; `combo.description` resolved `:303` |
| Rich description tokens already resolve per text run | `lib/dealer-kit/product-block.ts:709` `layerRichBlocks`, `:844` `richBlocksWithFields` (so a `{{slot.fixed.1.code}}` typed into the rich combo description already prints) |
| Insert field picker to reuse | `app/(protected)/dealer-kit/tag-templates/components/InsertFieldDialog.tsx`; used in a rich editor at `ProductSpecificationsTab.tsx:278` (`insertAtCaret` via `onEditorReady`) |
| Picker groups | `components/common/SearchableSelect.tsx:48` (`group` on an option) |

Finding: the machinery for rules 2 and 3 exists; what is missing is the UI to reach it, plus two
tokens and one plain-text gap. No backend change is needed.

## Behaviour card

### Rule 1: one add control per accessories block
- Each accessories block (combo's and product's, same `AccessoryListField`) has ONE picker,
  placeholder "Add accessory or product". Typing searches both: results grouped "Accessories"
  (library, incl. `Create "<text>"`) then "Products" (paged, server-searched, host and already
  listed ones excluded, as today).
- Box style leaves the block: a small settings icon (aria-label "Box style") beside the
  "Accessories included" label opens a popover holding the same clearable Box style select.
  When a style is set, the label reads "Accessories included · <style name>" so it is not hidden
  knowledge. Read-only readers see the same text, no icon.
- Unchanged: drag to reorder, pencil = own text for this list, X = remove, instant save.

### Rule 2: preview with choices
- Under the preview's template switcher, one compact picker per pick-one group ("TAP") listing
  its options by code, plus "No pick" (default). One "Upgrade" picker the same way when the combo
  has upgrades.
- Picking sends the preview line as a real request line would: fixed parts `{product_id}`, a
  picked group `{product_id, role}`, an unpicked group `{role, candidates}`, a picked upgrade
  `{product_id, role: "Upgrade"}`. The server draws it (price incl. "Sell price if picked" /
  top-up) exactly as the proof and PDF would. Nothing is saved; picks reset on reload.
- A pick whose part was removed or regrouped falls back to "No pick".

### Rule 3: description variables
- An "Insert field" button under the combo Description opens the existing Insert field dialog,
  limited to the Combo and Combo positions groups, with positions named by this combo's real
  codes ("Fixed 1 code: SRTWB2380"). The field goes in at the caret, as the price tag description
  editor does today.
- New tokens (existing syntax, `{{...}}`):
  - `{{slot.fixed.N.dimensions}}` / `{{slot.pick.G.I.dimensions}}` / `{{slot.upgrade.N.dimensions}}`
    (dimensions added to the position fields).
  - `{{combo.fixed_parts}}` "All fixed parts as a list": one line per fixed part,
    `- <code> (<price tag description>)` (the flyer's shape; description blank = `- <code>`).
- The chosen option of a pick-one group is the existing `{{slot.pick.G.1.*}}`: on a real line
  only the chosen option is placed there.
- Gap fixed: a plain (non-rich) combo description read through `{{combo.description}}` gets its
  own tokens resolved too (today only the rich path does). A description cannot include itself
  (`{{combo.description}}` inside it resolves empty).
- Rendered on the tag preview (draft, unsaved) and on the printed tag (same renderer).

### Real examples (from the owner's screenshot and flyer; dev rows requested below)
1. SRTKS7061-BL, combo "1 KITCHEN SINK + 1 KITCHEN TAP": preview picker TAP = SRTKT1634SS-BL ->
   tag shows that tap's code/description and the combo sell price with that tap's "Sell price if
   picked". TAP = No pick -> the tag lists all 5 options, as an open request line prints today.
2. Same combo, Description `1 KITCHEN SINK + 1 KITCHEN TAP / {{slot.fixed.1.dimensions}} - Matt
   Black / Tap: {{slot.pick.1.1.code}}` -> with TAP picked "Tap: SRTKT1634SS-BL"; no pick "Tap: ".
3. SRTBF11829 "5 IN 1 BATHROOM FURNITURE", Description `{{combo.name}}` + `{{combo.fixed_parts}}`
   -> `- SRTBF11829 (S/STEEL 304 CABINET L780xW480xH400mm)`, `- SRTWB2380 (BASIN)`,
   `- SRTMCB8083-BL (MIRROR CABINET)`, `- SRTWT6203-GM (BASIN COLD TAP)`, `- SRTW2600 (POP UP WASTE)`.
4. SRTKS7061-BL accessories: BK002 drainer + SRTBK7005 basket added from the one picker; box style
   set from the settings popover.

`crew-data-request:` rows (to confirm the examples on the dev copy):
- `SELECT c.id, c.name, c.description, p.product_code FROM product_combos c JOIN products p ON p.id = c.host_product_id WHERE p.product_code IN ('SRTKS7061-BL','SRTBF11829');`
- parts of those combos with `choice_group, is_upgrade, sell_price, topup_amount` and each part's `price_tag_description`, `dimensions`.

### Edge cases
- Pick-one group with no choice made: its `slot.pick.*` tokens print empty; preview shows the
  open state (all options listed), exactly as an unanswered request line.
- A variable whose part was removed: positions are by order, so a removed fixed part shifts later
  positions up and a position past the end prints empty. The editor shows, under the description,
  what each position token currently reads ("Fixed 3 = SRTMCB8083-BL") and flags a position the
  combo no longer has. (See Q4.)
- Long lists on a small tag: no new fitting rule; the description layer behaves as today (its
  template's wrap / clip), and the preview shows it before printing so the overflow is visible.
- Discontinued parts / accessories: unchanged (still pickable with the grey hint).
- Copy combo to other products: tokens are positional, so they keep working on the copies.

### Questions (each with a recommendation)
1. Preview default when nothing is picked: (a) "No pick" = open line, all options listed;
   (b) first option pre-picked. Rec (a): it is what an unanswered request actually prints.
2. `{{combo.fixed_parts}}` line shape: (a) `- CODE (price tag description)`; (b)
   `- CODE price tag description dimensions`. Rec (a), the flyer's shape; dimensions stay their own
   token so a description that already holds them is not doubled.
3. Box style home: (a) settings icon + popover beside the label, style name shown in the label;
   (b) inside the Tag Template designer only. Rec (a): per-list setting stays per list.
4. Part variables: (a) positional (existing `slot.fixed.N`, survives copy to colour siblings,
   shifts on removal, editor warns); (b) code-keyed new path `part.<CODE>.*` (survives
   removal/reorder, breaks on copy to a sibling with different codes). Rec (a): existing mechanism,
   and copies are common.
5. Upgrade in the preview picker: (a) yes, "Upgrade: none / <code>"; (b) choice groups only.
   Rec (a): the top-up price is otherwise never seen before print.

## Build (after approval)
- Phase 1 FE (mock data from the real hooks): `AccessoryListField` one picker + box style popover;
  `ComboTagPreview` pick state + parts; `DescriptionField` Insert field; `merge-fields.ts` tokens.
- Tests red first (vitest): one picker offers both groups and adds each kind; box style popover
  saves; preview sends the right `parts` for no pick / pick / upgrade; `combo.fixed_parts` and
  `slot.*.dimensions` resolve; plain combo description resolves tokens and cannot include itself.
- Reviewer, cloud browser pass at 375 and 1280, hand-test script.

## Owner answers and dev data (10 Nov)

- Placement: stays in the existing Combos card on the product page, no new tab (owner asked; answered (a)).
- Q1 (a): with nothing picked the preview shows all options. Q5 yes: Upgrade picker in the preview.
- Q2, Q4: owner asked "wdym", crew explaining. Q3: owner asked "why we need box style"; answered with
  (a) remove entirely / (b) designer only, rec (a) pending the dev usage count.
- Dev rows (sorento_prod_1104): SRTKS7061-BL combo LP 880, no sell price; TAP options sell 899 / 899 /
  929 / 929 / 1099, no price tag description, no dimensions, no upgrades. With no pick the tag prints
  LP and each option's own price, no single sell figure (`pricing.py:694`, AC-2.5); a pick prints that
  option's price. SRTBF11829 combo "SRTBF11829 + SRTMCB8083-BL", LP 2715 SP 2099, description typed by
  hand part by part; 4 fixed parts, only SRTWT6203-GM and SRTW2600 have a price tag description (multi
  line), only SRTMCB8083-BL has dimensions, SRTWB2380 has neither.
- Consequences for the card: the parts list token includes the main product first (the flyer and the
  typed description both list SRTBF11829), so it is `{{combo.parts}}`, not `combo.fixed_parts`; an
  empty description prints no "( )", an empty dimension prints no line, a multi-line description is
  joined onto one line. Dimensions print in the shared tag format `800 x 130 x 700 mm`
  (`tag_data_service.py:98` `format_dimensions_mm`), not the flyer's `L800xW130xH700mm`: one format
  for every tag, by that function's own rule.

## Approved build (10 Nov ~16:25 to 16:40)

- Box style: REMOVED (owner (a)). The control is gone, and the canvas, print page and drop counter
  no longer apply it; every tag draws its template's own box. Dev had 2 products / 0 combos with a
  value; they fall back. Columns `products.accessory_box_preset_id` / `product_combos.accessory_box_preset_id`
  and the BE plumbing (`box_style_for`, payload `accessory_box_style`, copy-accessories box style) go
  in a later cleanup lane.
- Combos: its own product tab (`?tab=combos`, badge = combo count), not a card on Overview.
- Q2 (owner): each part and the main product get a Label; `{{combo.parts}}` repeats the combo's own
  "Each part prints as" line (rich, `{{part.code|label|name|price_tag_description|dimensions_lwh|dimensions}}`),
  default `**{{part.code}} ({{part.label}})**` + `{{part.dimensions_lwh}}`. Label default: empty
  (recommended (a); empty "( )" is dropped, a paragraph whose only field is empty is dropped).
- Q4: position-based (a), crew decided.

| Piece | Where |
| --- | --- |
| One add picker | `AccessoryListField.tsx` (`fetchOptions`, groups Accessories / Products) |
| Box style removed | `accessory-card.ts`, `accessory-drops.ts`, `product-block.ts`, `KonvaTagLayer.tsx`, `TagCanvasEditor.tsx`, `InspectorPanel.tsx`, `TagSheetRenderer.tsx`, `useAccessories.ts`, `accessoryService.ts`, `CopyAccessoriesDialog.tsx` |
| Combos tab | `ProductDetail.tsx` |
| Preview picks | `ComboTagPreview.tsx` (`previewChoices`, `previewParts`), `useTagPreview.ts` (parts in the key) |
| `{{combo.parts}}` | `lib/dealer-kit/combo-parts.ts`, `merge-fields.ts` (plain), `product-block.ts` (rich splice, also inside the description) |
| Labels, Insert field, Each part prints as | `ProductCombosSection.tsx` (`LabelField`, `DescriptionField`, `PartsLineField`) |
| BE | migration `combo_0001_part_labels`; `product_combo.py` model/schema/service; `tag_data_service.py` `_part_row.dimensions_lwh`, `_combo_object` labels + line; `schemas/price_tag.py` |

## Reviewer round 1 (10 Nov)

- B1 fixed: a label / name / description holding `{{...}}` prints as text (`combo-parts.ts`
  `fieldValue` drops the braces), so `{{combo.parts}}` typed into a label cannot recurse.
- S1: test for the parts list spliced inside a description among other text.
- S2: each preview picker is named on screen; N4: pickers only while a published template draws.
- S3: the Insert field picker names this combo's positions by code ("Fixed 1 code: SRTWB2380").
  The mock's "Fields read" readout under the description is dropped: the picker already names
  each position's current part, and `{{combo.parts}}` (the owner's chosen tool) has no positions.
- S4: an inserted field saves at once; S5: the description's picker omits `{{combo.description}}`.
- Not changed (nits): N1 brackets with markup inside, N2 editor `mergeFields` token protection,
  N3 `previewParts` mirrors `price-tag-draft-lines.ts` `partsFromCombo` (same output; kept local
  to avoid widening the lane).
