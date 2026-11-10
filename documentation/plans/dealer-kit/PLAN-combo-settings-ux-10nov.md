# PLAN: combo settings UX (one accessory add, preview with choices, description variables)

Status: Plan, behaviour card + mock v1 filed for owner approval (no build yet). Track: LEAD, size M,
frontend only (no migration, no backend change, no auth/RBAC change; expected diff ~400 lines incl.
tests).
Lane: COMBO-SETTINGS-UX. Mock: `documentation/plans/dealer-kit/mocks/combo-settings-ux-v1.html`.

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
