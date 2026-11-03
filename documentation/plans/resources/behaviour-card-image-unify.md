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
| Staff | Price Tag designer / preview | Loads every product photo's original (product photos run up to 29 MB; 96 stored images are 5 MB or more); a few big ones can freeze the tab like the spec sheet did | Loads the 1024 px medium; opens fast. On a 4K screen zoomed past 200 % a photo looks slightly softer | P2 |
| Dealers | Printed price tags (PDF) | Chromium prints originals, uncapped | Prints a copy capped by Q1. At the recommended cap nobody can see a difference on paper | P2 |
| Staff | Attachment preview (Files) | Opens the original | Opens the medium; "Open original" / zoom / download still get the original (Q3) | P3 |
| Customers | Quotation sign page | 240 px pictures inlined, first 60 only; cells past 60 blank | Same 320 px thumbnails, all of them, loaded as the customer scrolls (Q5) | P3 |
| Staff | Catalogue photos grid, line photos, shipment photos, pickers | Mostly thumbnails already, some not lazy | Same thumbnails, all lazy | P3 |
| Customers | WhatsApp / chatbot photos | Originals | Unchanged under the recommendation (Q2) | P4 |
| Nobody | Storage | Thumbs only, made at upload; old rows via a manual script | Thumb + medium at upload; a throttled, resumable backfill for old files; long cache headers on renditions | P1 |

## Real examples (prod clone `sorento_prod_1020`: prod copy of 20 Oct plus dev uploads since; crew ran the queries read-only, 3 Nov)

**Stored images today.** 6343 live images, 3404 MB of originals. Median 62 kB, largest 29 MB,
96 images are 5 MB or more. 859 have no thumbnail (754 of them under 0.5 MB, 5 over 10 MB).
(1670 deleted images, 1446 MB, are left out of every number here and of the backfill. 1026 of the
6343 are dev uploads made after 20 Oct.)

**Product photos, where the freeze risk actually is.** 4378 product photos, 3193 MB, 312 without a
thumbnail. The biggest: SRTBF11833 _2.png 29 MB (linked to 5 products), SRTBF31416-02.png 20 MB
(no thumbnail), SRTBT1872.jpg 18 MB, MWC7632-SH-UF-MKH-S10.jpg 17 MB. Any screen that pulls
originals for a handful of these (the Price Tag designer and preview do, `dealer_kit/product_images.py:182`)
downloads 80+ MB and decodes several hundred MB, which is the #2126 freeze.

**Photos inside tag designs are not the problem.** 9 templates carry image layers, 1-2 pictures
each, all under 0.9 MB, all with thumbnails. Only 2 products are linked to a template today
(SRTKS7061 with 5 photos, 9.3 MB; CB1178A-DIY with none). So the risk grows with use: every
product linked to a template brings its own product photos into the designer and preview.

**Tag sizes in use (13 templates), and the Q1 print cap at 300 DPI measured on the tag:**

| Tag size | Templates | Cap at 300 DPI |
| --- | --- | --- |
| 95 x 44.5 mm | 4 | **1122 px** |
| 98 x 140 / 140 x 98 mm | 7 between these two rows (split not reported) | **1654 px** |
| A5 148 x 210 mm | (in the 7 above) | **2480 px** |

(2 more templates named "Crew perf 2126", 338.7 x 190.5 mm, are crew test data and ignored.)
Against the A4 sheet the cap would be 2339 px at 200 DPI or 3508 px at 300 DPI; most product
photos are 3000-4500 px wide, so a sheet-based cap barely shrinks them. The 29 MB photo printed on
a 95 x 44.5 mm tag goes into a copy at most 1122 px wide.

**Decoded memory** (what froze the browser): a 4000 x 3000 photo is ~48 MB of bitmap; its 1024 px
medium (1024 x 768) is ~3 MB. #2126's spec sheet tab pulled 165 MB of originals.

**Backfill size for Q4:** a medium for all 6343 live images plus the 859 missing thumbnails, from
3404 MB of originals. Most are small (median 62 kB), so most of the run time is the 96 files of
5 MB or more; the dev-copy run in P1 reports the actual minutes.

Queries (read-only, for re-running after P1):

```sql
-- live image attachments, how many lack a thumbnail (backfill size)
SELECT count(*) AS images,
       count(*) FILTER (WHERE thumbnail_path IS NULL) AS no_thumb,
       pg_size_pretty(sum(file_size_bytes)) AS original_bytes
FROM attachments WHERE is_deleted IS FALSE AND mime_type ILIKE 'image/%';
-- price tag templates by print size (Q1)
SELECT print_size, count(*) FROM dealer_kit.tag_template GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
-- biggest live PRODUCT photos (all product photos, not only tag-linked), each file once
SELECT a.original_filename, a.file_size_bytes, (a.thumbnail_path IS NULL) AS no_thumb,
       count(pa.product_id) AS products
FROM attachments a JOIN product_attachments pa ON pa.attachment_id = a.id
WHERE a.is_deleted IS FALSE AND a.mime_type ILIKE 'image/%'
GROUP BY a.id ORDER BY a.file_size_bytes DESC NULLS LAST LIMIT 10;
```


## Questions for the owner (at most 5)

**Q1. Printed price tag sharpness: how big may a printed photo be?**
(a) 300 DPI measured on the TAG's own size (the 95 x 44.5 mm tag, 4 templates, -> 1122 px copy; A5 -> 2480 px);
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
