# UAC: PRICETAG-MULTI-ADD (draft, pending owner answers Q1-Q5 on PR #2366)

Written against the recommended answers. Re-cut once the owner replies.

## AC-1 Tick and stay open
Given row 1's Item picker is open with search "DIY", when the user clicks a result's tick box (or presses Space on it),
the result shows ticked, the list stays open, the search text stays "DIY", and a footer shows "1 ticked" and a filled
button "Add 1".

## AC-2 Single pick unchanged
Clicking a result's text (or pressing Enter on it) with nothing ticked fills the row and closes the list, as today.

## AC-3 Add N fills the origin row, inserts the rest below
With rows [A, B] and the picker opened from row A's position (row 1), ticking X, Y, Z (list order) and pressing "Add 3"
gives rows [X, Y, Z, B]. No blank row is left behind. Each of X, Y, Z goes through the same pick path as a single pick
(qty 1, remarks empty, combos/templates/pricing looked up as for one pick).

## AC-4 Already added
A set or product already on another row shows ticked-grey with "Already added", cannot be ticked, and is skipped by
Select all. Nothing ever creates a duplicate row.

## AC-5 Select all
"Select all N" ticks every shown, tickable result; N counts only those. When the search hit its cap, the label reads
"Select all N shown" and a line "More match. Type more of the code to see them." shows.

## AC-6 Ticks across searches
Ticking in "DIY-BS" then typing "DIY-MR" keeps the earlier ticks; the footer shows the total. Add N adds all of them
in the order they were ticked within list order per search.

## AC-7 Esc / close
Esc or clicking outside closes the list and drops the ticks; the row is unchanged.

## AC-8 Keyboard
Arrow keys move, Space ticks, Enter = single pick of the highlighted result, Ctrl/Cmd+Enter = Add N.

## AC-9 Discontinued (Q4 a)
A discontinued product in the Item picker shows a grey "Discontinued" hint and can still be ticked and added.

## AC-10 Everywhere
CRM create, CRM edit, portal create, portal edit behave identically (one component). Upload a file, Save Draft,
Escalate to marketing and Preview are unchanged.

## AC-11 Phone
At 375 px the list fits the screen width and "Add N" stays visible at the bottom without horizontal page scroll.

## Test list (for the tester)
- vitest `PriceTagLinesTable.multiAdd.test.tsx`: AC-1, AC-2, AC-3 (row order and no blank row), AC-4, AC-5, AC-6, AC-7, AC-8.
- vitest `usePriceTagLineEditor` multi pick: inserting after the origin row, each item gets the single-pick patch,
  duplicates skipped.
- pytest `lookup_tag_items`: returns `is_discontinued` for products (AC-9) and honours the raised limit (Q3 b).
- existing `PriceTagLinesTable.*.test.tsx` and `SearchableSelect` tests stay green (single pick unchanged).
