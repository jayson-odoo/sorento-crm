# UAC — Flyer seeding, and the fidelity gate (S7)

**Companion to:** `PLAN-flyer-seeding.md`
**Status:** Pre-code except S7.1, which is built and green.
**Legend:** `[BE]` backend/pytest · `[FE]` frontend/vitest+playwright · `[E2E]` full FE→BE→DB · `[MIG]` migration · `[T]` CI guard.

Convention: **Given / When / Then**. An AC passes only when the Then is observed against the
real stack for the side marked.

---

## Group Z — The fidelity gate

> **The requirement:** the seeded catalogue must be at least **90% alike** the printed
> document it came from.

### Z.0 What "alike" can and cannot mean here

It cannot mean a picture diff. The seed is deliberately **structure-faithful, not
pixel-faithful** (PLAN D1): exact millimetre positions were traded away so that prices,
photos and stock resolve per viewer. A rendered-page-against-flyer-page image comparison
would score low on a seed that is working exactly as designed, and high on one that had
baked in a single frozen price for every audience. It would measure the wrong thing and
punish the right answer.

So fidelity is measured on **what the page says and how it is grouped**, in six components
defined below.

### Z.1 The ground truth must not be the extractor

Scoring the seeded page against the extractor's own reading tests only the seeder. The
extractor could misread the flyer completely and still score 100%.

So the chain is measured in two independent links, and the headline number is their product:

```
  PRINTED DOCUMENT  --(A)-->  READING  --(B)-->  SEEDED PAGE
                     |                  |
                     |                  +-- mechanical, exact, must be 100%
                     +-- vs a HAND-VERIFIED transcript, must be >= 90%
```

- **Link A, extraction fidelity.** The reading is scored against `flyer_golden.json`, a
  transcript of what is actually printed on the fixture pages, verified by a human against
  the document itself and committed. This is the only honest ground truth, and it is the
  link that can genuinely fail.
- **Link B, seed fidelity.** The seeded document is scored against the reading it was built
  from. This link is mechanical, so its bar is exact equality, not 90%.

- **AC-Z1** `[BE][T]` Given `tests/fixtures/dealer_kit/flyer_golden.json`, Then it is a
  hand-verified transcript of the committed fixture pages, and the test suite fails if the
  fixture PDF changes without the golden being re-verified (checksum pinned in the golden).
- **AC-Z2** `[BE]` Given the golden, When `extract_flyer` reads the fixture, Then the
  composite score is **>= 0.90** and each component is reported separately so a regression
  names which one moved.
- **AC-Z3** `[BE]` Given a reading, When the seeder builds a document from it, Then link B
  scores **1.00**: every card in the reading appears in the document, in the same section,
  in the same grid, in the same order. Anything less is a seeder defect, not a tolerance.

### Z.2 The six components

Each is a ratio in `[0, 1]`, measured per page and averaged over pages weighted by card
count, so a dense spread counts for more than a cover.

| # | Component | Weight | Measures |
|---|---|---|---|
| C1 | **Code coverage** | 0.30 | printed product codes that reached the page, over printed codes |
| C2 | **Placement** | 0.20 | codes landing in the section for the flyer page they were printed on |
| C3 | **Grouping** | 0.20 | mean Jaccard of each card's row-mates in the seed against its printed row-mates |
| C4 | **Order** | 0.10 | within a grid, the fraction of adjacent pairs in the printed left-to-right order |
| C5 | **Heading** | 0.10 | section headings matching the printed heading, normalised for case and spacing |
| C6 | **Artwork** | 0.10 | printed full-width bands that became a section background |

`score = 0.30*C1 + 0.20*C2 + 0.20*C3 + 0.10*C4 + 0.10*C5 + 0.10*C6`

Weights say what matters: a product missing from the catalogue is the worst outcome, so
coverage carries the most; a heading that reads "Transforming Your" instead of "BATHTUB
COLLECTION" is a five-second correction, so it carries little.

### Z.3 Invention is not scored, it is forbidden

A tolerance on the way IN is not a tolerance on the way OUT.

- **AC-Z4** `[BE]` Given the seeded document, Then **every** product code in it appears in
  the printed document. A code the seed invented scores zero on the whole run regardless of
  the other components, because a catalogue offering a product the flyer never advertised
  is a different kind of wrong from one missing a product.
- **AC-Z5** `[BE]` Given the seeded document, Then it contains **no price, no photo URL and
  no product snapshot**. Present as a test because it is the rule a well-meaning change
  breaks first.

### Z.4 Where the missing 10% is allowed to be

Stated up front so the gate cannot be met by tightening a metric until it passes.

- Codes the master does not have (38 of 998) count as MISSED on C1. They cannot be seeded
  and the report lists them, but the score is not forgiven for them.
- Headings on pages that are pure artwork.
- Rows the 24pt tolerance split (80 of 347 detected rows hold a single card).
- Free-gift codes and non-catalogue pages.

- **AC-Z6** `[BE]` Given a scoring run, Then it prints a per-component breakdown and the
  specific codes and pages that lost points, so "90%" is never a number without a list
  behind it.

### Z.5 The full document, not only the fixture

- **AC-Z7** `[BE]` Given the whole 36 page flyer at `FLYER_FIXTURE_PDF`, When the scorer
  runs, Then it reports the composite score for all 36 pages. Skipped when the variable is
  unset, because a 20MB PDF does not belong in the repository, and the committed 3 page
  fixture is what CI guards.

---

## Group A — Extraction (S7.1, built)

- **AC-A1** `[BE]` Given a flyer PDF, Then `extract_flyer` returns pages, cards, grids,
  artwork and headings, and touches no database.
- **AC-A2** `[BE]` Given a card, Then it carries the code, the lines printed around it, its
  position, and any `L x W x H` printed with it.
- **AC-A3** `[BE]` Given cards sharing a printed baseline, Then they are one grid, ordered
  left to right as printed.
- **AC-A4** `[BE]` Given a code the typesetter punctuated (`FG-CW13:`), Then the SKU is read
  without the punctuation. A card lost to a colon is a product missing from the catalogue.
- **AC-A5** `[BE]` Given something that is not a PDF, Then it raises rather than returning an
  empty reading: a designer who uploaded the wrong file must be told.
- **AC-A6** `[BE]` Given `SRTWC286-SH`, Then `offset_price` is None, because the flyer prints
  it outside the card's column band. Pinned as evidence that prices come from the promotion.

## Group B — The brochure image (S7.0)

- **AC-B1** `[BE]` Given a product and one of its image attachments, When it is set as the
  brochure image, Then exactly one attachment carries the flag for that product in that
  company, and the previous one is cleared in the same transaction.
- **AC-B2** `[BE]` Given a product outside the caller's company scope, Then the request 404s.
  Never 403: a non-owner must not learn the row exists.
- **AC-B3** `[BE]` Given an attachment not linked to that product, Then the request 404s.
- **AC-B4** `[BE]` Given the candidate list, Then it contains images only. `product_attachments`
  links 532 PDFs in the live data and a spec sheet offered as a photo is noise.
- **AC-B5** `[FE]` Given a product with one candidate, Then it still takes a click. Nothing is
  chosen on the user's behalf, however obvious it looks.
- **AC-B6** `[FE]` Given a product with no candidates, Then it says so and offers no control:
  the answer is a photo shoot, not a click.
- **AC-B7** `[FE]` Given the picker, Then each thumbnail shows its filename, because that is
  the only thing distinguishing two thumbnails when one is a different product entirely.
- **AC-B8** `[E2E]` Given a chosen image, When a catalogue tile for that product renders,
  Then it shows that image, with no renderer change: `product_images.py` already orders by
  the flag.
- **AC-B9** `[FE]` Given the product attachments tab, Then the same control is present there,
  writing through the same endpoint.

## Group C — Promotion link and pricing (S7.2)

- **AC-C1** `[BE][MIG]` Given `page`, Then it carries a nullable `promotion_id`, set
  explicitly. The seed may SUGGEST one when a promotion description matches the uploaded
  filename; only a click applies it.
- **AC-C2** `[BE]` Given a brochure with no linked promotion, Then every tile resolves the
  list price and no offer styling.
- **AC-C3** `[BE]` Given a linked promotion that is live and has a row for the product, and a
  viewer whose access level is in its `access_levels`, Then the tile resolves
  `promo_selling_price` against the list price.
- **AC-C4** `[BE]` Given today is past the promotion's `end_date`, Then every tile resolves
  the list price. Nothing quotes a dead offer.
- **AC-C5** `[BE]` Given a product with no row in the linked promotion (213 of 998), Then the
  tile resolves the list price with no offer styling.
- **AC-C6** `[BE]` Given a viewer whose access level is not in the promotion's, Then they get
  the list price, and the promotional figure is **absent from the payload**, not hidden.

## Group D — Match and report (S7.3)

- **AC-D1** `[BE]` Given a reading, Then codes resolve to products **within the active company
  scope**; the same code under another company is never matched.
- **AC-D2** `[BE]` Given a code the master does not have, Then it is reported with a trigram
  nearest match as a suggestion, and is not seeded.
- **AC-D3** `[BE]` Given the flyer and its linked promotion, Then the report lists codes
  printed but absent from the promotion.
- **AC-D4** `[BE]` Given cards printing `L x W x H`, Then they are reported as dimension
  candidates and **nothing is written to `products`**.

## Group E — Seed (S7.4)

- **AC-E1** `[BE]` Given a seed, Then one page is created with one section per flyer page,
  each `printMode: breakBefore`.
- **AC-E2** `[BE]` Given a seed, Then a version is written and **no label is moved**: a draft
  is a draft by construction, and approving it is the existing publish.
- **AC-E3** `[BE]` Given a printed row, Then it becomes one page-scoped collection with the
  cards in `pinned_product_ids` and the printed order in `manual_order`.
- **AC-E4** `[BE]` Given a re-seed of the same flyer, Then a new version and **new**
  collections are created; no existing collection is mutated, or an older version would
  silently start rendering something else.
- **AC-E5** `[E2E]` Given the real flyer, When it is seeded and published, Then a dealer sees
  promotional prices and a consumer sees their own, from one document.

## Group F — Artwork (S7.5)

- **AC-F1** `[BE]` Given a CMYK JPEG banner, Then it is converted to RGB before storage.
  Browsers do not render CMYK JPEG reliably, and it is the same defect that breaks WhatsApp
  media.
- **AC-F2** `[BE]` Given artwork extending past the page box (one is 1.17x page width at
  `y=-662`), Then it is cropped to the page.
- **AC-F3** `[FE]` Given a section with a banner, Then the banner is the section background
  and the heading is a text block over it: editable, searchable, translatable.
- **AC-F4** `[BE]` Given a picture sitting directly above a product code, Then it is NOT
  extracted as artwork. That is the product's photo and it comes from the master.
