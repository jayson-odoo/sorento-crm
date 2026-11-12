# UAC: PRICETAG-MULTI-ADD

Answers (crew, 12/11/2026, owner may overrule): Q1 (a), Q2 (a), Q3 (b), Q4 (a), Q5 (a); rules 1-7 as written.

## AC-1 Tick and stay open
Given row 1's Item picker is open with search "DIY", when the user clicks a result's tick box (or presses Space on the
highlighted result), the result shows ticked, the list stays open, the search text stays "DIY", and a footer shows
"1 ticked" and a button "Add 1". With nothing ticked there is no footer.

## AC-2 Single pick unchanged
Clicking a result's text (or pressing Enter on the highlighted result) fills the row and closes the list, exactly as
today. Existing single-pick tests stay green.

## AC-3 Add N fills the origin row, inserts the rest below
With rows [A, B] and the picker opened from row 1, ticking X, Y, Z and pressing "Add 3" gives rows [X, Y, Z, B]
(the ticked items in the order the list shows them; across searches, in the order they were ticked). No blank row is
left behind. Each of X, Y, Z gets exactly the patch a single pick gives (qty 1, remarks empty, line_type/product id,
name, code, combos/templates/pricing reset so the existing effects look them up). The list closes after Add N.

## AC-4 Already added
A set or product already on another row of the request shows ticked, disabled, with the hint "Already added"; it
cannot be ticked and Select all skips it. Add N never creates a duplicate row (also not when the same item is ticked
twice through two searches).

## AC-5 Select all
A "Select all N" row sits above the results; N counts the shown results that can be ticked. Clicking it ticks them
all; clicking again (all ticked) unticks them. When the search hit its cap (50 sets or 50 products returned) the label
reads "Select all N shown" and a line under the list reads "More match. Type more of the code to see them."

## AC-6 Ticks across searches
Ticking in "DIY-BS", then typing "DIY-MR" keeps the earlier ticks; the footer shows the total.

## AC-7 Esc / close
Esc or clicking outside closes the list and drops the ticks; the row is unchanged.

## AC-8 Keyboard
Arrow keys move the highlight. Space ticks the highlighted result once the user has moved the highlight with an arrow
key since their last typed character (the search text is then unchanged); before that, Space types a space, so a name
search such as "basin cabinet" still works. Enter = single pick; Ctrl+Enter or Cmd+Enter = Add N.

## AC-9 Discontinued
The item search returns `is_discontinued` for each product (sets: false). A discontinued product in the Item picker
shows a grey "Discontinued" hint and can still be picked, ticked and added.

## AC-10 Search cap raised
`GET .../lookups/price-tag-items` defaults to 50 sets + 50 products (max stays 50 per kind).

## AC-11 Everywhere
CRM create, CRM edit, portal create, portal edit behave identically (one component). Upload a file, Save Draft,
Escalate to marketing and Preview are unchanged.

## AC-12 Phone
At 375 px the list fits the screen width and "Add N" stays visible at the bottom without horizontal page scroll.

## Contract (tester and coder both build to this)

Frontend, `components/common/SearchableSelect.tsx` (opt-in; every other caller unchanged):
- `SearchableSelectOption.badgeText?: string` renders a small grey badge after the label (same look as
  `SearchableMultiSelect`'s badgeText).
- New prop `multiAdd?: { onAddMany: (options: SearchableSelectOption[]) => void; isAdded?: (option: SearchableSelectOption) => boolean; capped?: (options: SearchableSelectOption[]) => boolean }`.
  - Each option renders a tick box: `role="checkbox"`, `aria-label="Tick <option.label>"`, `aria-checked`.
  - Already added (`isAdded` true): option disabled, tick box checked + `aria-disabled="true"`, badge "Already added".
  - Select all row: text "Select all N" / "Select all N shown" (when `capped(options)`).
  - Footer when >= 1 ticked: text "N ticked" and a `button` named "Add N"; clicking it calls `onAddMany(ticked)` once
    and closes the list.
  - Cap line text: "More match. Type more of the code to see them."

Frontend, `hooks/usePriceTagLineEditor.ts`:
- New `handleItemsAdd(key: string, options: SearchableSelectOption[])`: the first non-duplicate option is applied to
  row `key` with the same patch `handleItemSelect` applies; each further one becomes a new line (`emptyDraftLine()` +
  that patch) inserted directly after `key`, in order, in ONE state update. Options already on another line, or
  repeated within the batch, are skipped.
- `tagItemOption` sets `badgeText: 'Discontinued'` when `item.is_discontinued`.
- `TagItemOption.is_discontinued?: boolean` (`app/(auth)/portal/lib/price-tag-request-service.ts`).

Frontend, `components/dealer-kit/PriceTagLinesTable.tsx`: the Item `SearchableSelect` passes `multiAdd` with
`onAddMany = (opts) => editor.handleItemsAdd(line.key, opts)`, `isAdded` = on another line of `lines`, `capped` = 50
sets or 50 products among the options.

Backend: `TagItemLookupItem.is_discontinued: bool = False`; `lookup_tag_items` fills it from `Product.is_discontinued`
(sets False); the portal route's `limit` default becomes 50 (`le=50` unchanged); `lookup_tag_items` default limit 50.

## Test list (tester)
- vitest `components/common/SearchableSelect.multiAdd.test.tsx`: AC-1, AC-2, AC-4, AC-5, AC-6, AC-7, AC-8 on the
  component with a fake `fetchOptions`.
- vitest `components/dealer-kit/PriceTagLinesTable.multiAdd.test.tsx` (or a hook test): AC-3 row order + no blank row +
  single-pick patch per row, AC-4 no duplicates, AC-9 Discontinued badge.
- pytest (`tests/test_price_tag_request.py` style, Postgres): AC-9 `is_discontinued` in `lookup_tag_items` rows,
  AC-10 default limit 50 on the route.
