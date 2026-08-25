# Side-by-side verification of the eight seeded tag templates (AC-L.10)

Run 2026-08-25 against the local prod-copy database, company `SRT`, on the
worktree dev stack (FE `:3030`, BE `:8030`). Each PNG in this folder is the
matching page of `Sorento Pricetag Template.pdf` rendered at 150 dpi and cropped
to its tag box on the LEFT, and the seeded template opened in the tag editor
with a real product bound on the RIGHT.

How the evidence was produced, so it can be re-walked:

1. `PYTHONPATH=. venv/bin/python scripts/seed_tag_templates.py --company-code SRT`
   (28 assets uploaded, 8 templates inserted; a second run reports
   `assets: 0 created, 28 already present | templates: 0 created, 8 already present`).
2. agent-browser session `ptag-seed`: log in, then `Dealer Kit -> Room Designer ->
   Tag Templates` from the sidebar. All eight rows render with the right family
   label and print size; a ninth row, `Kitchen Sink Combo A4`, is the empty
   placeholder template from an earlier slice and is not part of this seed.
3. Open each template, select its product block in the Layers panel, `Change
   product`, pick the code below, `Rebind`, screenshot.
4. `scratchpad/sidebyside.py` crops both halves and joins them.

The tag box crops are the filled white (or brand-green) rectangle
`pdf-geometry.json` reports for that page, so the two halves are the same
physical tag at the same scale.

## What was bound, per family

| Family | Template | Bound to | Note |
| --- | --- | --- | --- |
| `sink_combo` | Kitchen Sink - Combo | `SRTKS2435` | The PDF's own sink. Alternatives left unbound on purpose - see gap 4. |
| `ala_carte` | Kitchen Sink - Ala Carte | `SRTKS2409` | PDF page 2 prints `SRTKS2020`, which is not in this database. |
| `art_basin` | Art Basin | `SRTWB8001` | PDF page 3 prints `SRTWB1543-BL`, absent here. `SRTWB8001` is a pedestal basin, the nearest of the family. |
| `mirror_cabinet` | Mirror Cabinet | `SRTLMCB902-BL` | The PDF's own code. |
| `shower` | Exposed Shower Set | `SRTWT7633` | PDF page 7 prints `SRTWT9616-BL`, absent here. |
| `wc` | Water Closet | `SRTWC8036-SH-250` | **Substitution.** The PDF prints `SRTWC8036-SH-UF`; the `-UF` variant is not in this database, the `-250` trap variant of the same model is. |
| `urinal` | Urinal | `SRTUB6503` | The PDF's own code. |
| `furniture_set` | Bathroom Furniture Set | product set `SRTWC8608-RL-WEPLS` | **Substitution.** `SRTBF11826` does not exist; the database holds exactly two product sets and both are WC sets. This one has 3 members, so the `set_members` slot is exercised. |

## What matches

Every element on each PDF page has a layer in its template, and every bound slot
resolved from live data with no figure stored in the document (ADR 0008):

- **Brand band** - the green `#445235` header at the PDF's own height, with the
  Sorento wordmark right-aligned on it.
- **Badge rows** - the four kitchen badges (SUS304, ultrasonic nano, 25-year,
  anti-bacteria) on both sink tags; the three WC warranty badges; the single
  lifetime-ceramic badge on the urinal. All seeded as `badge` layers bound to
  the uploaded assets by name.
- **Product block** - image slot, code, dimensions, name, spec lines, list-price
  line and price badge, grouped so the whole block re-binds in one action.
  Binding `SRTKS2435` filled `SRTKS2435 / 800 x 535 x 250 mm / Sorento kitchen
  sink. Nanograin. / LP: RM 1,550 / RM 1,550`.
- **Price badge** - a `price_badge` layer, `promo` on the tags whose PDF shows an
  SP block and `list_only` on the WC and urinal, which the PDF prices at list.
  With no promotion active a `promo` badge degrades to the list price rather
  than blanking, which is what the screenshots show.
- **WC specifics** - the trap badges (6", 8", 10", P-trap, UF seat cover), the
  Twister Flush logo, the flushing-technology line, the six smart-feature icons
  with their captions, and the remote-control diagram with its label.
- **Shower specifics** - the grey diagram panel, the water inlet/outlet diagram
  as a `badge` layer bound to `Diagram Water Inlet Outlet`, its three-line
  heading and the two labels beneath it, plus the stainless-body badge.
- **Mirror cabinet specifics** - the inside-view secondary image slot with its
  label, the dim-light label, and the two light-colour swatches with captions.
- **Furniture set specifics** - the green surround with a white inner card at
  85.9 x 107 mm, the wordmark above the card, the composed image slot, the
  `N IN 1 BATHROOM FURNITURE` heading, the `set_members` slot (which resolved to
  the three members of `SRTWC8608-RL-WEPLS`), the `Label Pull Out` asset, the
  circle-masked honeycomb callout with a rotated caption, the LP line and the
  promo badge.
- **Sink combo specifics** - the circle-masked NANO GRAIN callout over the hero
  photo, the accessories strip with four captioned image slots, and an
  alternatives row of three unbound product blocks with a leading `+` and two
  `OR` connectors.

## What the template cannot yet express

Specific and reproducible, in the order a reviewer would hit them.

1. **The caption around the honeycomb disc is straight, not curved.** The flyer
   sets `HONEYCOMB` on an arc following the top of the circle. A text layer has a
   single `rotation_deg`, so the seed rotates the whole caption 8 degrees, which
   reads as a tilted label rather than text on a path. Needs text-on-path in the
   layer model - v2.

2. **The Sorento wordmark is set in Jost, not the real logotype.** It is vector
   artwork in the PDF (neither a text span nor an embedded image), so it could
   not be cropped into `manifest.json`. Marketing uploads the logo as an asset
   and swaps the text layer for an image layer over the same box; nothing else
   changes.

3. **Codes and prices are set in Bebas Neue, body text in Jost.** The originals
   are Century Gothic and Myriad Pro, both licensed. The templates name the
   family, so uploading the real faces as `Asset.kind='font'` and renaming is the
   whole migration. Letterfit therefore differs from the PDF - Bebas Neue is
   narrower and taller than Century Gothic Bold, which is why the seeded `LP:`
   label is a separate layer sized for the stand-in rather than for the original.

4. **An alternatives block cannot be bound per-tag on a SHEET, only in the
   template editor.** `TagSheetDesigner` resolves every layer of a placed tag
   against the ONE request line it was dropped from, so on a tag sheet the three
   alternatives collapse to the line's own product. In the template editor each
   block is its own group and binds independently, which is what the screenshots
   show. Per-block binding on a placed tag needs the designer to resolve per
   group the way the editor does.

5. **The alternatives row is one row of three, not the PDF's two rows of six.**
   Six blocks do not fit the 125.9 x 88.6 mm tag at the size the seed uses, and
   duplicating a row is one action for a designer. The flyer's connectors are
   solid red and dark discs; the seed draws an outlined ellipse plus a text
   layer, per D28, so both are editable.

6. **`lineFamily` in `TagSheetDesigner` never selects `art_basin` or `urinal`.**
   It is a code-substring heuristic (`wc`, `sh`, `mr`, `mc`, `sk`) with an
   `ala_carte` fallback, so a request line for a basin or a urinal is dropped
   onto the ala carte template. The two new families exist and are pickable in
   the template dialog; only the automatic per-line choice is behind. Out of
   scope for this slice, named here because it is the first thing a reviewer
   will notice on a sheet.

7. **Two products in the sample have no photo the tag can show.** `SRTKS2435`
   and `SRTLMCB902-BL` have zero gated attachments, so their image slots draw
   the "No image" state. That is a product-master data gap, not a template gap -
   `SRTKS2409`, `SRTWB8001` and `SRTWC8036-SH-250` all render their photos.

8. **Dimensions on some products are partial.** `SRTWC8036-SH-250` resolves to
   `250 x - x - mm` and `SRTWT7633` to an empty string, because the master data
   carries only one of the three measurements. The slot is correct; the source
   rows are incomplete.

9. **The WC template is the union of the two WC tags on page 8.** Page 8 prints a
   standard WC (badges, traps, twister logo) and a smart WC (icon row, remote
   diagram) as separate tags. The seed carries both sets of elements on one
   template so a designer deletes rather than rebuilds; the tag is
   correspondingly busier than either PDF tag on its own.

## Defects found and fixed during this run

Recorded here because each was invisible until a seeded template was opened.

- **Every library image on a tag sat on "Loading" forever.**
  `KonvaTagLayer.useHtmlImage` set `crossOrigin = 'anonymous'`, and the R2 bucket
  serving `dealer_kit_asset/` returns no `Access-Control-Allow-Origin`, so the
  browser discarded all 28 pieces of artwork. Nothing in `dealer-kit/` calls
  `toDataURL`, so an untainted canvas buys nothing here; the attribute is gone
  and the badges render.
- **A block about a SET could only be offered a PRODUCT picker.**
  `handleRebind` chose the picker mode from the binding alone, which is empty on
  a template by design, so the bathroom-furniture tag could never be bound to the
  one kind of thing it is about. It now also reads the block's `set_members`
  slot.
- **A text layer bound to `list_price` / `sell_price` never resolved.**
  `resolveSlotText` handled code/name/dimensions/spec lines/set members only, so
  the flyer's `LP: RM 1,550` line kept its seeded placeholder - an invented
  figure on a real tag. Both price slots now resolve through the same formatter
  the price badge uses.
- **The seed wrote `company_id = NULL`.** A script gets neither the scope filter
  nor the insert auto-stamp, which the API startup and `worker.py` install, so
  the eight templates and 28 assets landed unowned and were invisible from the
  company that owns them. `seed_tag_templates.run` now calls
  `register_company_scope_listeners()` the way `worker.py` does.

## Known noise, not fixed

`DialogContent` logs `Missing 'Description' or 'aria-describedby={undefined}'` on
every dialog open. It is the shared ReUI dialog, unrelated to this slice, and
appears throughout the app. No page errors were logged on any of the eight
templates.
