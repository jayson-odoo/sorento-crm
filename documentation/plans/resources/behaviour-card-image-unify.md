# Behaviour card: IMAGE-UNIFY, one way to size and show stored photos

Lane IMAGE-UNIFY, 3 Nov 2026. Facts cite file:line at #2126 head 2875866ce6 / main 36bd6e6909.
Plan: `PLAN-image-unify-03nov.md`.

## In one paragraph

Every stored photo gets three sizes: a 320 px thumbnail (lists, grids, table cells), a 1024 px
medium (any screen that shows one picture big: price tag designer, preview, attachment preview,
spec sheet page) and the original (download, zoom, and the source for printing). Printing makes a
copy capped to what the paper can show. Screens get exactly one way to draw a stored photo, which
picks the right size and loads lazily, and a test stops new code drawing an original into a small
box. This is what #2126 did for the spec sheet, made the rule for every screen.

## What staff, dealers and customers will notice

| Who | Where | Today | After | Phase |
| --- | --- | --- | --- | --- |
| Staff | Price Tag designer / preview | Loads every original (3000-4500 px, often 2-8 MB each); a template with many photos can freeze the tab like the spec sheet did | Loads the 1024 px medium; opens fast. On a 4K screen zoomed past 200 % a photo looks slightly softer | P2 |
| Dealers | Printed price tags (PDF) | Chromium prints originals, uncapped | Prints a copy capped by Q1. At the recommended cap nobody can see a difference on paper | P2 |
| Staff | Attachment preview (Files) | Opens the original | Opens the medium; "Open original" / zoom / download still get the original (Q3) | P3 |
| Customers | Quotation sign page | 240 px pictures inlined, first 60 only; cells past 60 blank | Same 320 px thumbnails, all of them, loaded as the customer scrolls (Q5) | P3 |
| Staff | Catalogue photos grid, line photos, shipment photos, pickers | Mostly thumbnails already, some not lazy | Same thumbnails, all lazy | P3 |
| Customers | WhatsApp / chatbot photos | Originals | Unchanged under the recommendation (Q2) | P4 |
| Nobody | Storage | Thumbs only, made at upload; old rows via a manual script | Thumb + medium at upload; a throttled, resumable backfill for old files; long cache headers on renditions | P1 |

## Worked examples (the arithmetic; real dev-data numbers pending, see below)

- Print cap formula (from #2126, `project_spec_sheet_service.py:679`): long edge in mm / 25.4 x DPI.
  - Spec sheet, A4 page at 200 DPI (today): 297 / 25.4 x 200 = **2339 px**.
  - A4 page at 300 DPI: **3508 px**. Most phone photos are 3000-4500 px, so this cap barely
    shrinks anything.
  - A price tag measured by the TAG, not the A4 sheet, at 300 DPI: a 100 x 60 mm tag gives
    **1182 px**; a 150 x 100 mm tag gives **1772 px**; an A5 tag gives **2481 px**. A photo slot is
    smaller than its tag, so these never cut visible detail.
- Decoded memory (what froze the browser): a 4000 x 3000 photo decodes to ~48 MB of bitmap; the
  1024 px medium (1024 x 768) to ~3 MB. A designer page with 20 photos: ~960 MB vs ~63 MB.
- #2126's case: 165 MB of originals for one spec sheet tab.

Real examples from the dev copy: this sandbox cannot reach the dev database or storage (crew
contract: no shared DB). Crew, please run these on the prod-clone copy and paste the result as a
`crew-note` on PR #2133; I fold them into this card:

```sql
-- image attachments, how many lack a thumbnail (backfill size)
SELECT count(*) AS images,
       count(*) FILTER (WHERE thumbnail_path IS NULL) AS no_thumb,
       pg_size_pretty(sum(file_size_bytes)) AS original_bytes
FROM attachments WHERE is_deleted IS FALSE AND mime_type ILIKE 'image/%';
-- price tag templates by print size (Q1)
SELECT print_size, count(*) FROM dealer_kit.tag_template GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
-- biggest product photos linked to price tags (designer load)
SELECT a.original_filename, a.file_size_bytes FROM attachments a
JOIN product_attachments pa ON pa.attachment_id = a.id
WHERE a.mime_type ILIKE 'image/%' ORDER BY a.file_size_bytes DESC NULLS LAST LIMIT 10;
```


## Questions for the owner (at most 5)

**Q1. Printed price tag sharpness: how big may a printed photo be?**
(a) 300 DPI measured on the TAG's own size (100 x 60 mm tag -> 1182 px copy);
(b) 200 DPI on the A4 sheet, the same number as the spec sheet (2339 px);
(c) keep printing originals.
**Recommendation: (a).** Tags are read up close on a shelf, so 300 DPI is the print-shop standard;
measuring the tag instead of the sheet makes the copy small enough to matter. Same formula as the
spec sheet, only the DPI and the measured unit differ by document. Spec sheet stays at 200 DPI on
its page, which #2126 just shipped.

**Q2. Photos the chatbot sends customers on WhatsApp: which size?**
(a) unchanged, the original; (b) the 1024 px medium; (c) a new ~1600 px copy.
**Recommendation: (a).** No browser draws these, so they cannot freeze anything; WhatsApp already
recompresses photos it delivers as images; customers zoom into product photos for detail.
Changing it is a customer-visible change with no problem behind it. P4 then closes with no PR.

**Q3. Attachment preview in Files: what opens first?**
(a) the 1024 px medium, with zoom / "Open original" / download fetching the original;
(b) always the original, as today.
**Recommendation: (a).** Opening is fast and light; anyone who needs the full detail is one click
away, and download is untouched.

**Q4. Making the medium size for photos already stored: when on production?**
(a) run the backfill once on prod, off-hours, after the dev-copy run's numbers are posted;
(b) never; make each medium the first time someone opens it.
**Recommendation: (a).** With (b) the first person to open each old template waits while the
server makes its pictures. The run is throttled, resumable and skips anything done, and on-demand
stays as the safety net for anything it misses.

**Q5. Customer sign page: show every picture, not just the first 60?**
(a) all pictures as 320 px thumbnails loaded as the customer scrolls;
(b) keep #2126's cap of 60 with blanks after it.
**Recommendation: (a).** The cap exists because every picture was packed into the page up front;
lazy thumbnails remove that reason, and a customer signing a quote should see every line's photo.
The page then carries 1-hour signed picture links instead of inlined pictures; the security review
in P3 checks that.
