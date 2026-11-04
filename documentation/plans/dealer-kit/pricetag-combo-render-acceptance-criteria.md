# UAC: price tags render every combo shape (PRICETAG-COMBO-RENDER, 4 Nov)

Behaviour card: `CARD-pricetag-combo-render-04nov.md` (owner-approved mock v5, 4 Nov 21:31 MYT).
Plan: `PLAN-pricetag-combo-render-04nov.md`. Mock: `pricetag-combo-render-mock.html`.

Every combo shape in the reference PDF has a test (S1 to S5 below). Codes are exact system codes.
Code paths carry no product-type words: "group", "fixed part", "upgrade", "main product" only.

Shapes:
- **S1** main + one choice group, 1..5 picks, + one upgrade (kitchen sink SRTKS7061 + group
  "Kitchen tap" of 5 + upgrade SRTKT71SS top-up RM 150).
- **S2** main + one fixed part + a free item drawn as a template picture (basin SRTWB1419-BL +
  SRTWT7449-BL).
- **S3** main + one choice group of 2 finishes, 1 or 2 shown (SRTWB1419-BL + group "Tap colour":
  SRTWT7449-BL / SRTWT7449-RG).
- **S4** main + two fixed parts, nothing to pick (SRTBF11829 + SRTMCB8083-BL + SRTWT6203-GM).
- **S5** S1 with the upgrade picked.

## A. Template positions (designer + renderer)

- AC-A1. A text, image, product slot, price badge or barcode layer may carry `subjectSlot`:
  `{kind:'main'}`, `{kind:'fixed', index}`, `{kind:'pick', group, index}`, `{kind:'upgrade', index}`
  (0-based). It wins over the older `subjectPart`; a layer without it prints exactly as today.
- AC-A2. On a combo line, `main` reads the main product; `fixed n` the line's n-th fixed part;
  `pick g,k` the k-th product the line picked from the combo's g-th choice group (pick order);
  `upgrade n` the combo's n-th upgrade. Each prints that product's own picture, code, tag
  description and own list price.
- AC-A3. A position the line has not filled (fewer picks, fewer fixed parts, no such group)
  prints an empty product: no picture, no code, no price. Never the main product.
- AC-A4. The canvas, the request preview and the PDF print page resolve positions through the
  same `subjectOf`; a test proves the print page's text for each shape equals the canvas's.
- AC-A5. The designer's "Product" select also shows in the template editor. With no combo
  previewed it lists "Main product", "Fixed part 1..4", "Choice group 1..3, pick 1..5",
  "Upgrade 1..2". With a combo previewed it lists that combo's own positions with its own names
  and codes, grouped ("Kitchen tap" > "Kitchen tap, pick 2", SRTKT1863SS). Choosing one writes
  `subjectSlot` and clears `subjectPart`.
- AC-A6. With a combo previewed, every group's picks are filled with the group's options in
  combo order, so pick k shows the k-th option.
- AC-A7. The Layers panel suffix names the position ("Kitchen tap, pick 2", or "Choice group 1,
  pick 2" with nothing previewed).

## B. Template needs and fit

- AC-B1. A template's needs are read from its layers: fixed = highest fixed index + 1; per group
  g, highest pick index + 1; upgrades = highest upgrade index + 1. Every template list the app
  reads for linking or choosing carries `needs` (`{fixed, groups: [..], upgrades}`).
- AC-B2. A template fits a combo when the combo has at least that many fixed parts, upgrades,
  choice groups, and options in each needed group. Otherwise the reason names the shortfall in
  the combo's own words: "Needs 3 from choice group 1; Tap colour has 2".
- AC-B3. The combo's "Price tag templates" picker (product page Combos card and Add combo modal)
  shows each template's needs in that combo's names ("105 x 148 mm. Needs 3 from Kitchen tap,
  upgrade") and lists a template that does not fit as a disabled option with the reason.
- AC-B4. A request line's Template select offers only templates that fit the line's combo, with
  the same needs text in the description.

## C. Request line

- AC-C1. One row per choice group, labelled with the group's name, as today. A group the chosen
  template needs 0 or 1 from keeps today's single select.
- AC-C2. A group the template needs k >= 2 from shows the existing `SearchableMultiSelect` with
  `max={k}`: no "Select all" row, the remaining options disabled once k are picked, chips in
  pick order, placeholder "Pick k".
- AC-C3. Picks save as resolved line parts sharing the group's role, in pick order, and reopen
  (draft, edit) into the same row with the same order.
- AC-C4. Switching to a template that needs fewer keeps the first picks and drops the rest.
- AC-C5. Under a group with fewer than k picks: "<group>: pick n more." Approve is disabled and
  the reason beside it says "Line i: <group>: pick n more."
- AC-C6. A discontinued option (`products.is_discontinued`) is listed disabled with
  "Discontinued" (multi: `badgeText`; single: description). A line that already holds a
  discontinued pick keeps it; Approve is disabled with "<code> is discontinued. Pick another or
  escalate it to marketing."
- AC-C7. Fixed-part rows and the Upgrade row behave as today.

## D. Combo price (never calculated)

- AC-D1. On a combo line, the list price is the combo's stored LP or nothing; the selling price
  is the combo's stored / option price, else the typed SP, else nothing. The sum of the parts is
  never used, on the tag data and on the line-pricing lookup alike. Ala carte and set lines are
  unchanged.
- AC-D2. An LP line on a combo with no stored LP shows "-" in List price, prints no price, and
  Approve is disabled with "No combo list price for line i. Escalate it to marketing."
  Escalate stays available.
- AC-D3. An SP line on a combo with no stored SP shows today's "Type a price" box (no sum in its
  placeholder); typed, it prints.

## E. Flyer re-seed (script, owner-approved before any write)

- AC-E1. `scripts/flyer_combo_read.py` reads flyer PDFs page by page through the app's LLM
  provider and writes a seed in the format `import_product_combos.py` loads: main, fixed parts,
  choice groups with names from the flyer's wording, upgrades with top-up, prices, flyer page,
  and an "unsure" note. The model's answer is data: codes are only kept as read, never invented.
- AC-E2. The import's dry run (default) writes a report with one row per combo: shape, status
  `new` / `matches` / `differs` (what differs) / `unsure` (why), flyer page, discontinued
  products named. Nothing is written.
- AC-E3. `--apply` loads prices (combo LP/SP, option SP, top-up) and, for a combo that differs,
  updates it to the flyer (adds, removes, regroups parts). A combo the flyer no longer shows is
  untouched.
- AC-E4. Cabana and every no-selling-price brand: no combo SP, option SP or top-up is written;
  the report says "price not loaded: no selling price brand".
- AC-E5. A code that does not resolve in the chosen company, or resolves to a discontinued
  product, is not loaded and is listed; the combo is `unsure`.
- AC-E6. `--link-templates` links every published template that fits the combo (AC-B2).
- AC-E7. Starter templates: `--templates` creates one 105 x 148 template per PDF shape, built by
  one generic position layout (no per-type code).
