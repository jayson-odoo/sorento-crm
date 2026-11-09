# UAC: price tag upgrade items + family tag with variant icons (PRICETAG-UPGRADE-VARIANTS)

Status: DRAFT; card fully answered 09/11/2026 (Q1 a, Q2 a, Q3 whole tree + per-line chooser, Q4 a, Q5 a). Final after the mock is approved.
Card: `CARD-pricetag-upgrade-variants-09nov.md`. Plan: `PLAN-pricetag-upgrade-variants-09nov.md`.

## Upgrades box

- AC-U1. A saved Accessories box with no `lists` setting prints exactly as before (byte-for-byte layout).
- AC-U2. Setting "Lists: Upgrades" on a box makes it read the combo's upgrades on offer, in combo order;
  the header defaults to "UPGRADE".
- AC-U3. On SRTKS2432 with upgrade SRTKT71SS (top-up RM 150): one card with its photo, "SRTKT71SS", its
  description, "LP: RM 440", "TOPUP RM 150", and SRTKT71SS's own feature icons; tag SP stays RM 949.
- AC-U4. Picking the upgrade on the request line: SP reads RM 1,099 and the Upgrades box prints nothing.
- AC-U5. A combo with no upgrades: the box (frame, header, badge) prints nothing, and the template still fits
  that combo (no "Needs 1 upgrade").
- AC-U6. Three upgrades in a box sized for one: one whole card prints, and the drop warning reads
  "2 of 3 ... do not fit this box".
- AC-U7. The "SP with upgrade" field is not on the default card; placed by hand it prints combo SP + top-up
  ("RM 1,099"); it hides when the combo has no SP or the upgrade has no top-up.
- AC-U8. Text slots "Upgrade top-up" and "SP with upgrade" on an "Upgrade 1" position print the same words as
  the card.
- AC-U9. Canvas, request preview and print draw the same cards (one layout function, tested on all three).
- AC-U10. A pinned tag keeps its upgrade figures after the top-up is edited, until re-pinned.

## Family tag

- AC-F1. A feature icons layer offers "Reads from: All variants".
- AC-F2. On a line for SRTWC8354-SH, "All variants" = SRTWC8354-SH and every product under it in the variant graph
  (whole tree), all ticked by default; the layer shows the union of their icons, each once, in registry icon order.
- AC-F2b. The request line has "Variants on this tag" (SearchableMultiSelect) listing every member; the line's own
  product is always on. Unticking SRTWC8354-SH-UF-300 removes the 12" S-trap 300mm icon and leaves 6" / 8" / 10"
  S-trap, P-trap 180mm and UF seat cover. The template is not changed by it.
- AC-F2c. The line stores the unticked members: a variant created later appears ticked; a pinned tag keeps the
  members it printed until re-pinned.
- AC-F3. On Master Data > Product Specifications, `trap_length` offers the values products have (150, 200, 250,
  ...) and each can carry icons; raw 150 / 150.0 / "150" all match the value "150".
- AC-F4. A discontinued or inactive variant adds no icon; a variant with no stock still does.
- AC-F5. A line naming a leaf variant (SRTWC8354-SH-150) shows only that product's icons on "All variants".
- AC-F6. Code, name, photo and price layers on the family tag keep reading the line's own product.
- AC-F7. Ticked members with different list prices: the request line shows "Variants price differently: RM x to RM y";
  the tag prints the line product's own price.
- AC-F8. Existing templates (no layer on "All variants") print unchanged.
