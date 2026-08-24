# PLAN - Seed a Dealer Kit catalogue from the printed flyer (S7)

**Status:** Grilled 2026-07-31. Decisions below are settled; S7.1 is built and green.
S7.2 is built and green: `page.promotion_id` (migration 315), `resolve_prices` (ADR 0008),
and all four money surfaces migrated onto it - tile, quote line, bundle allocation, public
and print payloads.
S7.3 is DONE: `match_reading` (`app/services/dealer_kit/flyer_matching.py`) is green on 47
tests covering group D, and the four `/flyer-readings` routes are green on 27 more
(`tests/test_dealer_kit_flyer_readings.py`). A reading is PERSISTED
(`dealer_kit.flyer_reading`, migration 316); the report is DERIVED from it on every read and
deliberately never stored - see the S7.3 outcome note at the foot of this file.
S7.4 BACKEND is DONE: `POST /flyer-readings/{id}/seed` builds a draft brochure through the
existing `save_version`, green on 34 tests (`tests/test_dealer_kit_flyer_seed.py`) covering
AC-E1 to AC-E4. No migration: the seed writes only `page`, `page_version` and `collection`
rows that already exist. See the S7.4 outcome note at the foot of this file.
S7.4 FRONTEND is DONE: the three step review screen at `/dealer-kit/flyer-readings`, wired
to the real API, green on 80 vitest cases and 3 playwright specs
(`e2e/dealer-kit-flyer-seeding.spec.ts`). The E2E half of AC-E5 - the seed produces a
version no reader can reach - is covered there. The dealer-vs-consumer half was recorded
here as "already pinned by `e2e/dealer-kit-offer-pricing.spec.ts`", which was WRONG: that
spec grants its promotion to `['end_user', 'dealer']`, so both audiences see the same
offer and it never shows the two differing. AC-E5 is now closed in
`tests/test_dealer_kit_pdf_render.py` - see the AC-E5 outcome note at the foot.
See also the S7.4 FE outcome note at the foot.
LINK B of the fidelity gate is DONE: `score_seed` in
`app/services/dealer_kit/flyer_fidelity.py` scores the seeded document against the reading
it was built from, green on 23 tests (`tests/test_dealer_kit_flyer_seed_fidelity.py`)
covering AC-Z3 to AC-Z7. Link B is **1.000** on the committed three page fixture and
**1.000** on the whole 36 page flyer (1,252 cards, 347 printed rows, 341 collections),
including a run with 40 codes deliberately withheld from the master: 44 unplaceable card
occurrences, all reconciled against the seed result's `skipped` list, 0 lost, 0 invented.
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

**D1 - Structure-faithful, live bindings.** The doc stores bindings: heading blocks,
collection blocks bound to product ids, artwork by asset id. Never a price, never a photo
URL. Exact millimetre positions are the deliberate trade.

**D2 - One page, thirty six sections.** A reader scrolls one catalogue, not 36 URLs.
Each flyer page becomes a section with `printMode: breakBefore`, so the PDF export still
comes out as 36 pages. One page also means one publish, one label, one rollback.

**D3 - A printed row is a pinned collection.** `scope='page'`, cards in
`pinned_product_ids`, print order in `manual_order`. Not a rule, and **not a promotion
group**: only 193 of 347 printed rows sit wholly inside one promotion group, and "Faucet
Series" alone is spread across 27 printed rows. The printed row is the layout unit; the
promotion is a pricing binding, not a membership one.

**D4 - Colourways stay flat, one tile per code.** 518 of 998 codes carry a colour-looking
suffix but only 155 are linked by `variant_of_id`, and the Kit's collection and tile model
has no variant concept. Collapsing some rows and not others would produce an inconsistent
page, which is worse than a long one.

**D5 - A brochure links to exactly ONE promotion, explicitly and optionally.**
Nullable `promotion_id` on `page`. Set by a human, never inferred, though the seed may
SUGGEST it when a promotion's description matches the uploaded filename. No link means
list prices only. An audience-split flyer is separate brochures, which is how Sorento
already produces them: separate PDFs per audience.

**D6 - Tile pricing falls back to the list price, and says nothing false.**
Linked promotion has a row for this product and this viewer's access level, and today is
inside its dates, then the offer price. Otherwise the list price with no offer styling.
An expired promotion is simply a promotion with no applicable rows. The seed reports the
213 codes printed in the flyer but absent from the promotion, so marketing closes the gap
deliberately.

**D7 - The brochure photo is a flag a human sets, on two surfaces.**
`product_attachments.is_primary`, reachable from a dedicated picker screen AND from the
product's own attachments tab (user decision: both). One endpoint, two surfaces.

**D8 - Unknown codes are reported, never guessed.** A code the master does not have is
left out of the collection and listed, with a trigram nearest match shown as a suggestion
that only a click applies. Silently swapping `SRTKS7850` for `SRTKS7851` would be worse
than a gap.

**D9 - The seed writes nothing to the product master.** Dimensions become a review queue.

**D10 - Re-seeding makes a new version, and new collections.** Same page,
`max(version)+1`, published label untouched, and always fresh page-scoped collections:
reusing one would mutate what an older version renders, which is the one thing versioning
exists to prevent.

## Slices, in dependency order

**S7.0 - The brochure image flag.** `PATCH` on a product attachment to set it as the
brochure image (exactly one per product per company), a picker screen filterable by
promotion so "everything in the A3 flyer" is one sitting, and the same control on the
product attachments tab. Prerequisite for every tile that shows a photo, and for S8.

**S7.1 - Extraction engine.** DONE. Pure: bytes in, a reading out. 25 tests against three
pages cut from the real flyer.

**S7.2 - Promotion link and promo price resolution.** `page.promotion_id`, and the
resolver the Kit does not have: today `product_facts` knows `list_price` and nothing else,
so every tile would show LP. This is the slice that makes a seeded page tell the truth.

**S7.3 - Match and report.** DONE. Codes to products in company scope, trigram suggestions
for the 38 misses, the not-promoted list, the dimensions candidates. `POST /flyer-readings`,
`GET /flyer-readings/{id}`, plus the list and a hard `DELETE`.

**S7.4 - Review and seed.** The three-step screen, then `POST /flyer-readings/{id}/seed`
building the doc through the existing `save_version`. Draft by construction: no label moves.

**S7.5 - Artwork.** Extract, convert CMYK to RGB, crop bleeds to the page box, store as
`Asset`, and set it as the Section background with the heading as a text block over it.
Needs `SectionStyle` to accept an asset id, which it does not today.

**S7.6 - Dimensions review queue.** 425 candidates, applied only on an explicit click by
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

---

## S7.3 outcome (2026-08-01)

Four routes on the existing dealer-kit router, all behind the page permissions already in
use: `page.edit` to upload or delete, `page.view` to read or list. No new slug, because a
fourth one would need a grant sweep before any existing role held it, and everybody who can
build a page can already do everything a reading leads to. (A fifth route, `POST
/flyer-readings/from-attachment`, landed later under the same `page.edit` slug - see
`PLAN-flyer-read-hardening.md`.)

**The reading is stored; the report is not.** `dealer_kit.flyer_reading` keeps what the
extractor read - pages, cards, printed rows, artwork, headings - and the match report is
recomputed against the master on every read. A stored report is only true for the master it
was computed against, and it goes stale in the direction that costs money: it keeps telling
marketing to close gaps that were closed last week, with nothing on the screen to say the
number is old. Recomputing 998 codes costs 0.4s and three statements. The regression test
for this changes the master between two GETs of the same reading and expects the answer to
move.

**Extraction no longer runs inside the request.** The "36 A3 pages take about a second" figure
recorded here was never measured, and it was wrong: the real flyer takes 17 to 18 seconds in
`extract_flyer`. It is now an RQ job on the `flyer_read` queue and the POST answers 202. The
measurements, the gateway timeout that forced it and the whole design live in
`PLAN-flyer-read-background-job.md` and in the `flyer_reading_service` module docstring, which
own it. Do not re-derive anything from this paragraph.

Decisions worth keeping:

- **The wrong file is a 400 in words.** `extract_flyer` already refuses a non-PDF; the route
  maps it. A 500 tells a designer the system is broken when their file is, and a 201 with an
  empty report tells them their flyer has no products on it.
- **50 MB ceiling, 413, and the message names the limit.** The real flyer is 20 MB, and the
  same document exported without compression can double that. The upload is read in chunks
  so the check fires before the whole file is held.
- **`promotionId` is typed as a UUID at the edge**, so a malformed one is a 422 and never
  reaches a WHERE clause. It is asked on the READ as well as the upload, because "what does
  this promotion not carry" is a question about the report rather than a property of the
  file. An unknown-but-well-formed id is NOT a 404: it reports everything as not promoted,
  which is how a reviewer discovers the brochure points at a promotion somebody deleted.
- **Another company's reading is 404, never 403.** 403 confirms the id exists.
- **The list carries no reports.** One report per row is one match run per row, on a screen
  whose only job is to say which flyers have been read.

Migration 316 was applied to the shared dev database by hand and NOT stamped (that database
sits at another worktree's revision), so its DDL is idempotent throughout.

---

## S7.4 outcome, backend half (2026-08-01)

One route on the existing dealer-kit router, `POST /flyer-readings/{id}/seed`, behind
`dealer_kit.page.edit` and deliberately NOT `page.publish`. No new slug and no new table:
the seed writes a `page`, one `page_version` through the existing `save_version`, and one
`collection` per printed row.

**Draft by construction.** No draft flag exists and none was added. A version with no label
pointing at it is unreachable by every reader (`published_doc` refuses to fall back to the
latest version), so the absence of a label IS the draft and approving it is the publish that
already exists. A flag would be a second way to say the same thing, and the two would
disagree the first time one was forgotten.

Decisions the ACs did not settle, and the reasoning:

- **Unmatched codes are dropped from the document and named in the response.** A collection
  pins product ids, so a code the master does not have cannot be pinned, and inventing a
  product for one would put a SKU nobody stocks in front of a customer (D8). The response
  carries a `skipped` list in the SAME shape as the match report - code, pages, trigram
  suggestion - so the reviewer sees exactly what did not make it and where to look for it
  on the paper. It is deliberately NOT written into the document as a note: the document is
  what a customer eventually reads, and internal QA text there is one careless publish away
  from a customer. The recomputed report on the reading keeps answering the same question
  afterwards, and keeps answering it truthfully as products are created.
- **A row where nothing matched produces no collection at all.** An empty pinned collection
  renders a blank grid a designer can do nothing with, inside a page that otherwise looks
  complete. The section still exists, so the draft still lines up against the flyer page by
  page.
- **Two products under one photo both get a tile**, in printed order, in the same
  collection. The extractor emits both codes and does not decide which owns the picture;
  neither does the seed. Collapsing them would drop a product from the catalogue on a guess,
  and the Kit's tile model has no variant concept to collapse them into (D4).
- **A misread heading is carried through verbatim.** Fixture page 2 reads "Transforming
  Your" where the paper says "BATHTUB COLLECTION". The seed does not repair it, because a
  draft that quietly invents a heading is a draft nobody can check against the flyer. It is
  a five second correction on the review screen, which is exactly why heading carries the
  smallest fidelity weight.
- **The promotion is a parameter, applied on the seed.** D5 says a brochure links to one
  promotion explicitly and never by inference. The review screen is where a human is already
  answering that question - it is the screen that reports what the promotion does not carry -
  so the click that approves the seed IS the explicit act. It is typed as a UUID at the edge
  (422 on a malformed one), validated before anything is written (404 on an unknown one, and
  no half-made page left behind), and an omitted value on a re-seed means "leave it alone",
  never "unlink": silently dropping a live brochure's offer is the worse failure, and
  clearing is the page's own PUT, which says so out loud.
- **A seed says where it is going.** `pageId` re-seeds; `name` plus `slug` create. Exactly
  one, 422 otherwise. Nothing links a reading to a page it seeded earlier, on purpose: one
  flyer legitimately seeds a dealer brochure and a consumer one, so the target is a decision
  the review screen makes rather than a column.
- **The paper comes from the flyer.** The fixture measures A3 portrait, and the PDF export
  reads the PAGE row's profile, so a seed left on the A4 default would print an A3 layout
  onto A4 and overflow every section. `cover` is set false: the flyer's own first page IS
  the cover. Applied on creation ONLY - the profile is shared by every version of a page, so
  overwriting it on a re-seed would re-paginate an already-published edition.
- **Company scope.** Another company's reading is a 404 before anything is written (never a
  403, which would confirm the id exists). The seed then lands in the scope that reading was
  reachable in, which IS its company; a scope holding more than one company cannot stamp an
  owned row at all, so it fails closed rather than guessing.

**AC-E4 was proved by mutation, not by assertion alone.** With the seed changed to reuse an
existing page-scoped collection, `test_an_older_version_still_renders_exactly_what_it_did`
fails on version 1's collection having gained a third product it was never approved with,
and `test_reseeding_writes_a_new_version_and_brand_new_collections` fails on the id sets
overlapping. Reverted, both pass. The membership assertion is deliberately ordered before
the id assertion so a future reuse fails on the damage it does rather than on bookkeeping.

**Left open at the time:** AC-E5 (`[E2E]`, dealer and consumer prices from one published
document) needs the review screen and a browser, and is not faked with a backend test. The
review screen itself, the FE half of S7.4, is next. **Closed on 2026-08-09, see below.**

---

## S7.4 outcome, frontend half (2026-08-02)

Three steps on two routes: `/dealer-kit/flyer-readings` (which flyers have been read, plus
the upload) and `/dealer-kit/flyer-readings/{id}` (review, then seed). A sidebar entry
called **Flyers** under Dealer Kit, added with the screen rather than after it: the
brochure image picker shipped reachable only by typing the URL and that is not a defect
worth repeating.

**The review screen is written to be unflattering.** It opens with four figures - printed,
matched, missing, printed twice - and if anything is missing it says, above the fold, that
those products will NOT be in the brochure. The same list is repeated on the seed form
before the button, and again in the result afterwards, because the result screen is the
last moment anybody is still thinking about the flyer. Sizes are labelled a report in the
section subtitle and there is no control anywhere that could write one, which is the rule
S7.6 will inherit. A standing "what the draft will not have right" card names the guessed
headings, the blank product photos and the rows the baseline tolerance split - none of
which are in the report, so none of which would ever appear on their own.

Decisions worth keeping:

- **The promotion is asked on the REVIEW, not on the seed form.** It is a question about
  the report first ("what does this offer not carry") and only afterwards a property of
  the brochure, and asking it twice would let a reviewer report against one promotion and
  seed with another. The detail query is keyed on it, and `placeholderData` keeps the
  previous answer on screen while the recompute runs - a skeleton there would throw away a
  half-filled seed form and the section somebody was reading.
- **Every report table is a `ReportGrid` with `listingKey=""`.** Column personalisation is
  off deliberately: unset, the grid keys saved widths on the URL, which here carries a
  reading id - a config row per user per flyer, four per screen, never read again. It also
  leaves the grid in its skeleton state until something else re-renders it, which showed up
  in the browser as ten blank rows where an empty section should have said it was empty.
  `useListingColumnPreferences` settles a ref rather than state, so a grid with no data
  query of its own never gets the render that clears it.
- **The seed result replaces the form rather than navigating.** Going straight to the
  builder would put the skipped codes behind a back button.

**Contract gap found, not worked around:** the section HEADINGS the extractor read are
stored on the reading but are NOT on `FlyerReadingOut`, so the review screen can say
headings are guessed but cannot show WHICH ones are wrong - the reviewer still has to open
the builder and compare against the paper. Surfacing them is an additive field on the
detail response (`headings: [{page, text}]`), deliberately left for a slice that can also
test it on the backend.

Verified in a browser against the real stack (login, sidebar, upload, review, seed,
re-seed, delete, 375px) on the committed 3 page fixture: 41 codes printed, 36 matched, 5
absent from the master with trigram suggestions from 72% to 100%, 27 dimension candidates
of which 1 conflicts, 2 codes printed on two pages. The seed produced 3 sections, 17
printed rows and 36 products, with no label on the version and a 4xx from the public
catalogue - which is AC-E2 observed rather than asserted.

---

## AC-E5 outcome (2026-08-09)

**Proved in `tests/test_dealer_kit_pdf_render.py`, not in a Playwright spec**, because that
file is where the property is observable: real headless Chromium against the prod frontend
build, against a real FastAPI process, against Postgres. The public catalogue route
(`app/api/v1/public/catalogue.py`) renders with a hardcoded `ANONYMOUS` viewer and there is
no signed-in dealer view of a page, so the export AUDIENCE is the only surface today on
which a dealer and a consumer read the same published document.

One page, one published version, one linked promotion, rendered twice. The document stores
no figure at all (AC-G1), so the two files are the only place the difference exists.

**Distinct from the neighbouring gate item.** `test_a_staff_export_and_a_consumer_export_of_one_page_differ`
moves `is_staff`, which decides the INVOICE price. This one moves `access_codes`, which is
what `pricing._may_see_offer` reads to decide an OFFER. Different columns, different
function: the invoice test passes unchanged with offer gating entirely broken.

**Both parametrised rows earn their runtime, and which fault each catches was measured.**

| Mutation | dealer row | mirror row |
|---|---|---|
| `_AUDIENCE_ACCESS_CODES` dealer/consumer transposed | FAILS | FAILS |
| `_may_see_offer` given an early `if "dealer" in viewer.access_codes: return True` | passes | FAILS |

The mirror row is therefore not symmetry: it is the only row that catches a gate letting one
audience past whatever the promotion says. An earlier draft of its comment claimed it existed
to catch the transposition, which the measurement above disproves, and the comment was
corrected to what the runs actually show.

**Read narrowly on one point, deliberately.** The AC says "given the real flyer". The seed is
exercised against the committed excerpt of the real flyer in `test_dealer_kit_flyer_seed.py`
(AC-E1..E4); it cannot be exercised here. This file commits to the real database so a
separate backend process and a separate browser can read the rows, and locally that database
is a copy of production, while the seeder matches the codes actually printed on the paper.
Seeding here would hang a promotion off REAL product rows at prices nobody set, on a document
whose figures come from live master data (46% of which is `list_price = 0.00`), leaving no
distinctive figure to assert. So the seed is proved where the seed lives, and what E5
uniquely adds - two audiences, one document, two sets of money - is proved on a page where
both figures are chosen.

**Two defects fixed on the way, neither part of the AC:**

- `committed_db` leaked rows into the production copy. A test dying between `flush()` and
  `commit()` left pending rows on the session; teardown's own `commit()` then re-INSERTed
  them AFTER deleting the products they referenced, the FK failed, and the whole teardown
  transaction rolled back, so everything the test created survived. Reproduced, then fixed
  with a `session.rollback()` as teardown's first statement. Promotions are now tracked and
  deleted children-first.
- The frontend port was wrong in two places. `.env` and this test file both said `:3020`,
  which is the `spec-search` worktree's frontend and has no `/c/print` route at all. Renders
  went next door and died on a print-ready timeout a minute later, which reads like a broken
  print page rather than a wrong address. This worktree is **3040 / 8040**.
