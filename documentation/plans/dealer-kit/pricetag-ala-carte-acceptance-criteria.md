# UAC: PRICETAG-ALA-CARTE (draft, written against the card's recommendations; final after owner answers)

## Editor (portal / CRM request form, shared PriceTagLinesTable + usePriceTagLineEditor)
- AC-1 A product line whose product has 1+ combos shows the Package select; a product with no combo shows none; a set line shows none.
- AC-2 Options = each combo (by name) + "Ala carte (product only)" (Q1 pending).
- AC-3 A freshly picked product with exactly one combo starts on that combo with its parts (unchanged); 2+ combos start with no package (unchanged).
- AC-4 Picking ala carte sets combo_id null and parts []; picking a combo sets that combo and its parts.
- AC-5 A line loaded from a saved draft / duplicate / revise with combo_id null keeps combo_id null after the combos lookup (no auto-pick on reopen).
- AC-6 Same product on two lines with different packages: no guard_error. Same product + same package: guard_error "<code> is already on this request." on the later line, including when the package is changed to one another line of that product already holds.
- AC-7 Picking a product already on the request starts the new line on the first unused package (Q2 pending); every package used -> refused.
- AC-8 Multi-add uses the same single-pick function per item; the picker's "already added" state does not block a product that still has an unused package (Q2 pending).

## Backend
- AC-9 _raise_on_duplicate_line keys on (product, combo) for product lines; same product + same combo -> 422 DUPLICATE_LINE; different combo / one ala carte -> accepted (create, update, portal revise).
- AC-10 replace_lines and portal revise carry tags / picks by (product, set, combo): two lines of one product re-save without error and each keeps its own tags.
- AC-11 Ala carte line renders the product's own list price, template and accessories (existing path; regression test).
- AC-12 DB (crew decision 13 Nov): unique index over (request_id, product_id, COALESCE(combo_id, zero uuid)) built CONCURRENTLY replaces uq_ptag_line_request_product (dropped only after the index exists); uq_ptag_line_request_set unchanged (sets carry no combo). Migration up/down/up; down fails clearly if two lines of one product exist.
- AC-12b Deleting a combo whose line would collide with an ala carte line of the same product on the same request merges the combo line into the ala carte line (quantities add) instead of a 500 (pending crew answer, rec (a)).
- AC-13 Revision snapshot includes combo_id so a package change shows old -> new in History (Q5 pending).

## Upload a file (AI read)
- AC-14 handleAIExtractApply merges a row into an existing line only when product AND package match; else adds a new line.
