# PLAN — Seed a Dealer Kit catalogue from the printed flyer (S7)

**Status:** Pre-code. Phase 0 written, decisions locked, awaiting the plan grill.
**Companion UAC:** `flyer-seeding-acceptance-criteria.md`
**Input artefact:** `_SORENTO A3 FLYER 2025-2026_compressed.pdf` (36 pages, A3 portrait, 20MB, vector).
**Depends on:** S1 builder core, S2 collections. Ships into the same `dealer_kit` schema.

---

## Why this exists

Sorento already has the catalogue. It is 36 A3 pages of finished design that somebody
spent weeks laying out. Rebuilding it block by block in the builder is the single
biggest reason the Kit would sit unused: nobody starts a 36 page rebuild on a Tuesday.

Seeding turns that from weeks into an afternoon of corrections.

## What the flyer actually is (measured, not assumed)

Probed with PyMuPDF against the real file:

| Fact | Value |
|---|---|
| Pages | 36, A3 portrait (841.89 x 1190.55 pt) |
| Type | Vector. Text, positions, fonts, colours and image boxes all extractable. Not scans. |
| Distinct product codes | 1,000 |
| Codes matching `products.product_code` exactly | 960 (961 after dash-normalising) |
| Codes with a price in the flyer | 984 |
| Codes with `L x W x H` in the flyer | 367 |
| Codes with a Product Photos image in the system | 535 |
| Codes with any attachment | 703 |

Layout is regular: product cards sit on repeating grid baselines, the code at a fixed
`y` per row, name / price / dimensions in a column band directly under it, the product
image directly above. Clustering by column band reproduced the cards cleanly on every
page sampled.

Each code resolves to two `products` rows, one per company (Sorento and Mocha). Company
scope decides which, and the seed must run inside a company scope like everything else.

## Phase 0 — the journey

**Actor:** a Sorento marketing Designer. Arrives from Dealer Kit → Pages → **Seed from a
flyer**.

**What the system already knows:** the product master, every product photo, which company
they are working in, and what a Dealer Kit page is made of. None of that is asked for.

1. **Drop the PDF.** One decision: which file. Nothing else. The system reads it and
   reports what it found, per page: the section heading it detected, how many product
   cards, how many of those it matched to real products.
2. **Look at the misses.** One list, not 36. Every code the master does not have, each
   with the closest existing code as a suggestion. Per row, one decision: map it to the
   suggestion, or leave it out. Leaving it out is the default, and it is recorded, so a
   product missing from the catalogue is never a silent hole.
3. **Choose the pages.** Every page ticked by default. Untick the ones that are not
   catalogue (order form, dealer list, back cover).
4. **Seed.** One page is created, with one section per flyer page, saved as version 1 and
   **not published**. The designer lands in the builder looking at it.
5. **Correct and publish.** The machine got the structure; the designer fixes what it got
   wrong and publishes. That is the existing publish flow, unchanged.

**What they hold at the end:** a live digital catalogue whose prices, photos and stock
resolve per viewer, and a 36 page PDF export that still reads like the flyer.

**What else the seed hands over, without being asked:** the three by-product reports
below. Every one is a review queue. Nothing is written to the product master by the seed.

## Decisions

**D1 — Structure-faithful, live bindings. Not a pixel facsimile.** *(user decision)*
The seeded doc stores bindings: heading blocks, spacer blocks, and collection blocks bound
to product ids. It never stores a price, a photo URL or a product snapshot. Baking
`LP: RM 2,200` into a text block would freeze one price for every audience and break AC-G1,
which is the rule that lets one published page serve staff, dealers and consumers at the
price each is allowed to see. Exact millimetre positions are the thing being traded away,
deliberately.

**D2 — One page, thirty six sections. Not thirty six pages.**
A reader should scroll one catalogue, not click through 36 URLs. Sections already carry
`printMode`, so each flyer page becomes a section with `printMode: breakBefore`, which
gives the faithful 36 page PDF back at export time. One page also means one publish, one
label, one rollback.

**D3 — Page-scoped collections, pinned and ordered.**
Each detected card grid becomes a `Collection` with `scope='page'`, its cards in
`pinned_product_ids`, and the flyer's left-to-right order in `manual_order`. No rule
engine conditions: the flyer is a hand-picked set, and inventing a rule that happens to
select the same products today would silently change the page tomorrow.

**D4 — Unknown codes are reported, never guessed.**
A code the master does not have is left out of the collection and listed in the seed
report. The suggestion shown is a trigram nearest match, and applying it is always the
designer's click. A seeded page that silently swapped `SRTKS7850` for `SRTKS7851` would
be worse than one with a gap.

**D5 — The seed writes nothing to the product master.**
Dimensions, prices and photos found in the flyer become three reports, not three
migrations. See below.

**D6 — Re-seeding the same flyer makes a new version, never edits one.**
Same page, `max(version)+1`, published label untouched. Which means a designer who has
already corrected version 3 does not lose that work when somebody re-runs the seed: they
diff and cherry-pick, or they roll back.

## By-product reports (this is where the real value hides)

The extraction reads three things the system is short of. None is applied automatically.

**R1 — Dimensions.** Only **3,331 of 22,805** products carry length and height. The flyer
carries `L x W x H` for 367 codes. This matters far beyond the catalogue: the room
designer sizes a product from `dimensions_length/width/height`, and a product without them
renders as the orange estimated box. `SRTWC286-SH` has 31 photos and no dimensions, which
is exactly why it looks like a placeholder in 3D today.

**R2 — Price drift.** 984 codes carry LP and SP in print. Comparing them to the system's
own prices is a free audit of what was actually promised to dealers in a document that is
already in their hands.

**R3 — Photo gaps.** 465 of the 1,000 codes have no Product Photos image. Those are the
tiles that will render empty, and the list is the marketing shot list.

## Slices

**S7.1 — Extraction engine (backend, pure, test-first).**
`app/services/dealer_kit/flyer_extraction.py`. In: PDF bytes. Out: a `FlyerReading`
dataclass: pages, each with a heading, dividers, card grids, cards (code, name lines,
price strings, dimension string, image bbox), and unmatched codes. No DB, no HTTP, no
writes. Golden-set tests against committed page fixtures cut from the real flyer, per the
"E2E uses real user samples" rule. Pure geometry and text, so it is unit-testable in full.

**S7.2 — Match and report (backend).**
Resolve codes to products inside the active company scope. Trigram suggestions for misses.
Produce the seed report and the three by-product reports. Endpoint:
`POST /api/v1/dealer-kit/flyer-readings` (upload, returns a reading id + report),
`GET .../flyer-readings/{id}`.

**S7.3 — Review and seed (FE prototype first, then wiring).**
The three-step screen from the journey. `POST .../flyer-readings/{id}/seed` builds the doc
and calls the existing `save_version`. Draft by construction: no label is moved.

**S7.4 — By-product review queues.**
Dimensions and price drift as accept/reject lists that write to `products` only on an
explicit click, by a user with the master-data permission. The photo gap list exports.

**S7.5 — Decorative artwork (optional, last).**
Hero panels and banners lifted from the PDF into `Asset` rows so a seeded section is not
text-only. Left last because a section that reads correctly without its banner is already
useful, and image extraction from a compressed PDF is the fiddliest part of the job.

## Risks

- **Heading detection is a heuristic.** Largest non-card text in the top band. It will be
  wrong on the pages that are pure artwork. The review step exists so that is a correction,
  not a defect.
- **A "card" is inferred, not declared.** Two products sharing one image (`SRTBF11404 + SRTWT5841-RG.jpg`
  exists in the master) are a real pattern in this flyer. The extractor emits both codes into
  the grid; it does not try to work out which one owns the picture.
- **Column count is guessed from the row.** Six across on A3 print is not six across on a
  phone. The derived-layout machinery already handles the smaller breakpoints, but the
  desktop count comes from the flyer and may need a nudge.
- **The 40 unmatched codes may be real products that were never imported.** The report says
  so; it does not create them.
