# UAC: PRICETAG-ALA-CARTE

Owner answers 13 Nov ~11:00 MYT (relayed by crew): Q1 (b) empty Package = ala carte, placeholder "Ala carte";
Q3 (b) bare code from Upload a file = ala carte; Q5 (a) package in the revision snapshot. Q2 assumed (crew): a
re-added product takes the next package not yet used. Q4 pending (nothing built). Crew technical: version-independent
COALESCE unique index; combo delete collision = merge (rec (a), no objection).

Terms: "package" of a product line = its combo_id; null = ala carte. Set lines have no package.

## Editor (shared PriceTagLinesTable + usePriceTagLineEditor, portal and CRM create/edit)
- AC-1 A product line whose product has 1+ combos shows the Package select (today 2+ only). A product with no combo
  and a set line show none.
- AC-2 Options = each combo by name. The select is clearable; empty shows the placeholder "Ala carte".
  No extra "Ala carte" option.
- AC-3 A product picked by hand with exactly one combo starts on that combo with its parts (unchanged). 2+ combos
  start empty = ala carte (unchanged).
- AC-4 Clearing the Package sets combo_id null and parts []; choosing a combo sets it and its parts (choosePackage).
- AC-5 A line that arrives with combo_id null and is NOT a fresh hand pick (saved draft reopen, duplicate, revise,
  Upload a file) keeps combo_id null after the combos lookup: the auto-pick runs only right after a hand pick.
- AC-6 Same product on two lines with different packages: no guard_error. Same product + same package on two lines:
  the later line gets guard_error "<code> is already on this request." (also when the Package is changed to one an
  earlier line of that product already holds; clears when it no longer collides).
- AC-7 (Q2 assumed) Picking a product already on the request: the new line takes the first package not yet used on
  the request, in the order [the product's default (its single combo, else ala carte), then ala carte, then combos
  in their order]. Every package used -> refused with "<code> is already on this request." (today's text).
- AC-8 Multi-add calls the same single-pick function per item (AC-7 applies per item, in tick order). The picker
  does not grey/skip a product that still has an unused package.
- AC-9 A combo with zero parts is still a package (combo_id set), distinct from ala carte.

## Upload a file (AI read, portal handleAIExtractApply)
- AC-10 A bare product row (no "+" parts) starts ala carte (combo_id null, no auto-pick - AC-5). A "+" row that
  matches a stored combo starts on that combo (unchanged).
- AC-11 A row merges into an existing line only when product AND package match; otherwise it becomes its own line.

## Backend
- AC-12 _raise_on_duplicate_line keys product lines on (product_id, combo_id or none): same pair twice -> 422
  DUPLICATE_LINE naming the code (create, update/replace_lines, portal revise); different combo or one ala carte ->
  accepted. Set lines unchanged.
- AC-13 replace_lines carry_tags and portal revise old_by_key match on (product_id, product_set_id, combo_id): two
  lines of one product re-save / revise without error and each keeps its own tags, overrides and template pick.
- AC-14 An ala carte line of a product that has combos renders the product's own list price, template and
  accessories, never the combo's (regression).
- AC-15 DB: unique index uq_ptag_line_request_product_package over (request_id, product_id,
  COALESCE(combo_id, '00000000-0000-0000-0000-000000000000'::uuid)), created CONCURRENTLY, replaces constraint
  uq_ptag_line_request_product (dropped after the index exists). uq_ptag_line_request_set unchanged. Model
  __table_args__ match. Migration up / down / up; down fails clearly when a request holds two lines of one product.
- AC-16 Deleting a combo: lines on it become ala carte (unchanged), except a line whose request already has an ala
  carte line of that product - it is merged into that line (quantities added, its tags dropped), no 500.
- AC-17 (Q5) Price tag revision snapshot carries item_code (product or set code) and package (combo name or "Ala
  carte"); a package change shows in History as "Product line N package: <old> -> <new>".
