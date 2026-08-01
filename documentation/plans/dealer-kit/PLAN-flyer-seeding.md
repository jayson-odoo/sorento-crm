# PLAN — Seed a Dealer Kit catalogue from the printed flyer (S7)

**Status:** Grilled 2026-07-31. Decisions below are settled; S7.1 is built and green.
**Companion UAC:** `flyer-seeding-acceptance-criteria.md`
**Input artefact:** `_SORENTO A3 FLYER 2025-2026_compressed.pdf` (36 pages, A3 portrait, vector).
**Depends on:** S1 builder core, S2 collections.

---

## Why this exists

Sorento already has the catalogue: 36 A3 pages somebody spent weeks laying out.
Rebuilding it block by block in the builder is the single biggest reason the Kit would
sit unused, because nobody starts a 36 page rebuild on a Tuesday. Seeding turns that
into an afternoon of corrections.

## What the flyer actually is (measured against the real file)

| Fact | Value |
|---|---|
| Pages | 36, A3 portrait, vector. Not scans. |
| Distinct product codes | 998 |
| Matching `products.product_code` exactly | 960 |
| Printed card rows detected | 347 |
| Cards carrying `L x W x H` | 425 |
| Codes with a product photo linked | 535 |
| Codes with a photo somebody has CHOSEN | **0** |
| Codes already in this flyer's promotion | 785 |

Cards sit on repeating baselines: the code at a fixed `y` per row, its copy in a narrow
column below, its photo above. Each code resolves to two `products` rows, one per
company, so the seed runs inside a company scope like everything else.

## The three things the grill changed

**1. The flyer is a promotion, and the promotion already exists.**
`promotions` holds a row called `_SORENTO A3 FLYER 2025-2026_compressed`, dated
2025-12-01 to 2026-05-31, with **883 promotion_products** carrying `promo_selling_price`,
across 7 access levels. Promotions in this system ARE flyers: their descriptions are PDF
filenames, and audience variants exist as separate rows (`...KITCHEN SINK PROMO DEALER.pdf`,
`... END USER.pdf`, `... OFFICE.pdf`) with different end dates.

So the seed must not invent prices. It must not even audit them: reading prices off a
page is lossy, and provably so. `SRTWC286-SH` prints "SP RM 599" where the extractor's
column band cannot reach, so it reads no offer price at all. Across the flyer, 1,081
cards yield a list price and only 660 an offer price. A drift report built on that would
be mostly the extractor's own misses. **Price extraction survives only as a reading aid on
the review screen. R2 (price drift) is cancelled.**

**2. Nobody has ever chosen a product's brochure photo.**
`product_attachments.is_primary` exists, `product_images.py` already orders by it, and it
is `false` on every one of the 1,087 photo rows behind the flyer's products. So the tile
today shows whichever row was linked first. `SRTWC286-SH` has 31 linked images including
`98. BLANK PAGE_PG93.jpg`, `SRT93-BL.jpg` and `SRTBF11620.png` - other products' pictures
and a blank page.

Filenames could identify the right one for 509 of 535, but **inference is rejected as too
dangerous** (user decision): a wrong photo on a brochure is a wrong product in front of a
customer. A human sets the flag. This is a prerequisite for the seed being worth looking
at, and it also unblocks the 3D slice, which needs the same answer.

**3. Section headers and dividers are artwork, not vector rules.**
Flyer page 4 contains exactly ONE horizontal rule. What reads as a header band or a
divider is a full-width image with the heading typeset on top. Artwork therefore moves out
of the last slice, because it IS the headers and dividers. Two constraints ride along: the
banners are **CMYK JPEGs**, which browsers do not render reliably and which we already
know break WhatsApp media, so extraction must convert to RGB; and some backgrounds are
oversized and bleed off the page (one is 1.17x page width anchored at y=-662), so they need
cropping to the page box.

## Decisions

**D1 — Structure-faithful, live bindings.** The doc stores bindings: heading blocks,
collection blocks bound to product ids, artwork by asset id. Never a price, never a photo
URL. Exact millimetre positions are the deliberate trade.

**D2 — One page, thirty six sections.** A reader scrolls one catalogue, not 36 URLs.
Each flyer page becomes a section with `printMode: breakBefore`, so the PDF export still
comes out as 36 pages. One page also means one publish, one label, one rollback.

**D3 — A printed row is a pinned collection.** `scope='page'`, cards in
`pinned_product_ids`, print order in `manual_order`. Not a rule, and **not a promotion
group**: only 193 of 347 printed rows sit wholly inside one promotion group, and "Faucet
Series" alone is spread across 27 printed rows. The printed row is the layout unit; the
promotion is a pricing binding, not a membership one.

**D4 — Colourways stay flat, one tile per code.** 518 of 998 codes carry a colour-looking
suffix but only 155 are linked by `variant_of_id`, and the Kit's collection and tile model
has no variant concept. Collapsing some rows and not others would produce an inconsistent
page, which is worse than a long one.

**D5 — A brochure links to exactly ONE promotion, explicitly and optionally.**
Nullable `promotion_id` on `page`. Set by a human, never inferred, though the seed may
SUGGEST it when a promotion's description matches the uploaded filename. No link means
list prices only. An audience-split flyer is separate brochures, which is how Sorento
already produces them: separate PDFs per audience.

**D6 — Tile pricing falls back to the list price, and says nothing false.**
Linked promotion has a row for this product and this viewer's access level, and today is
inside its dates, then the offer price. Otherwise the list price with no offer styling.
An expired promotion is simply a promotion with no applicable rows. The seed reports the
213 codes printed in the flyer but absent from the promotion, so marketing closes the gap
deliberately.

**D7 — The brochure photo is a flag a human sets, on two surfaces.**
`product_attachments.is_primary`, reachable from a dedicated picker screen AND from the
product's own attachments tab (user decision: both). One endpoint, two surfaces.

**D8 — Unknown codes are reported, never guessed.** A code the master does not have is
left out of the collection and listed, with a trigram nearest match shown as a suggestion
that only a click applies. Silently swapping `SRTKS7850` for `SRTKS7851` would be worse
than a gap.

**D9 — The seed writes nothing to the product master.** Dimensions become a review queue.

**D10 — Re-seeding makes a new version, and new collections.** Same page,
`max(version)+1`, published label untouched, and always fresh page-scoped collections:
reusing one would mutate what an older version renders, which is the one thing versioning
exists to prevent.

## Slices, in dependency order

**S7.0 — The brochure image flag.** `PATCH` on a product attachment to set it as the
brochure image (exactly one per product per company), a picker screen filterable by
promotion so "everything in the A3 flyer" is one sitting, and the same control on the
product attachments tab. Prerequisite for every tile that shows a photo, and for S8.

**S7.1 — Extraction engine.** DONE. Pure: bytes in, a reading out. 25 tests against three
pages cut from the real flyer.

**S7.2 — Promotion link and promo price resolution.** `page.promotion_id`, and the
resolver the Kit does not have: today `product_facts` knows `list_price` and nothing else,
so every tile would show LP. This is the slice that makes a seeded page tell the truth.

**S7.3 — Match and report.** Codes to products in company scope, trigram suggestions for
the 38 misses, the not-promoted list, the dimensions candidates. `POST /flyer-readings`,
`GET /flyer-readings/{id}`.

**S7.4 — Review and seed.** The three-step screen, then `POST /flyer-readings/{id}/seed`
building the doc through the existing `save_version`. Draft by construction: no label moves.

**S7.5 — Artwork.** Extract, convert CMYK to RGB, crop bleeds to the page box, store as
`Asset`, and set it as the Section background with the heading as a text block over it.
Needs `SectionStyle` to accept an asset id, which it does not today.

**S7.6 — Dimensions review queue.** 425 candidates, applied only on an explicit click by
someone with the master-data permission.

## Risks

- **Heading detection is a heuristic** (largest non-card text in the top band) and is
  already wrong on flyer page 3, where it reads "Transforming Your" instead of "BATHTUB
  COLLECTION". The review step is what makes that a correction rather than a defect.
- **Row detection splits some printed rows.** 80 of 347 detected rows hold a single card.
  Some are genuinely featured products; some are a row the 24pt tolerance cut in half.
- **Two products under one photo** is a real pattern here. The extractor emits both codes
  and does not try to decide which owns the picture.
- **The 38 unmatched codes may be real products never imported.** The report says so; it
  does not create them.
- **Column count comes from the paper.** Six across on A3 is not six across on a phone;
  the derived-layout machinery handles smaller breakpoints, but the desktop count may need
  a nudge.

---

## S7.0 outcome (2026-08-01)

Shipped and gated. Two surfaces, one flag (`product_attachments.is_primary`), enforced in
the service AND by a partial unique index so no write path can produce two.

Verified end to end in a browser, which is the only check that mattered: choosing
`CBF31049.jpg` in the picker moved the catalogue tile for `SRTWC286-SH` off
`SRTWC286_SH_2.jpg`, confirmed independently at the API. No renderer change was needed,
exactly as predicted.

**Defects found and fixed that were not in the plan:**

- Deleted photos were offered as candidates: 611 of 2,924 image links, 20%. Worse than it
  reads, because choosing one returned 200 while the tile silently did not change, so a
  human decision was discarded without a word.
- The new unique index turned two older write paths (the attachment PUT and the n8n link
  POST) into 500s carrying raw constraint text. Both now funnel through the one service.
- The default listing read all 22,805 products into Python on every debounced keystroke.
  Now 17-147ms.
- A failed save left the tile looking chosen, so a user moved on believing a product was
  answered when it was not.
- The screen shipped with no sidebar entry, reachable only by typing the URL.
- `resolve_signed_url` fails open, so an unsignable image reached the browser and came back
  403 as a broken tile. Image paths now sign strictly; 181 of 2,472 links are affected on
  one environment.

**Known and deliberately left, for the next slice or for marketing:**

- Two candidates on one product can be indistinguishable, because the filename is the only
  label shown and some products carry two files with the same name. A human cannot tell
  them apart either.
- In a company with no product attachments at all, the screen reads "11390 of 11390 still
  to choose" with every row empty. Correct, but it is that company's default landing state
  and looks broken.
- Under the default "only unanswered" filter the answered row leaves the list on the next
  fetch, so the mark is only ever seen optimistically.
