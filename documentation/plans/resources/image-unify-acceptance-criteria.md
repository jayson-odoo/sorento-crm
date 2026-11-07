# UAC: IMAGE-UNIFY

Plan: `PLAN-image-unify-03nov.md`. Owner rulings Q1-Q5 of 3 Nov 14:35 are recorded there. Each
criterion names its phase.

## P1 backend

- AC-1 One resize routine: every downscale in `sorento_crm_backend/app` goes through
  `image_thumbnailer.downscale`. A BE guard test fails on `Image.open(` in any other module that is
  not on its reasoned allow-list.
- AC-2 A new image upload, through any of the 7 upload paths, stores `<key>.thumb.jpg` (320 px) and
  `<key>.medium.jpg` (1024 px) from one decode, both upright and white-backed, both with
  `Cache-Control: public, max-age=31536000, immutable`.
- AC-3 A failed rendition never fails the upload.
- AC-4 No backfill runs (Q4). An old photo gets its medium (and a missing thumb) the first time a
  screen asks for it; after that, asking again touches neither the original nor storage's
  existence check.
- AC-5 One generation per file under concurrency (Q4): many requests, in one process or several,
  asking for the same missing rendition at once cause exactly one download of the original and one
  write per size. If Redis is down the picture is still made.
- AC-6 A request never waits more than 8 s for renditions in total; anything not ready comes back
  as its thumb and is ready on the next open.
- AC-7 An undecodable or over-40 MP photo is not retried for 10 minutes and shows its thumb or a
  placeholder, never the original.
- AC-8 All picture URLs are signed through `storage_router.resolve_signed_url`; no module keeps its
  own signed-URL or picture cache.
- AC-9 Overwriting an original (promotion re-upload, CMYK fix script) regenerates its renditions;
  new promotion uploads no longer share a key with an earlier upload of the same filename.
- AC-10 No screen changes in P1: every existing spec sheet, sign page, attachment and price tag
  test stays green unchanged.

## P2 Price Tag and printed PDFs

- AC-11 The designer canvas, the CRM design preview and the portal design preview draw product
  photos and library assets from medium renditions, never originals. Opening a design whose products
  carry the 17-29 MB photos downloads under 5 MB of images once renditions exist (crew perf pass,
  prod-clone copy).
- AC-12 Q1: in the tag-sheet PDF and the spec sheet PDF each photo prints from a copy sized to its
  image layer's designed box at 300 DPI, fitted the way the layer draws (cover / contain / stretch,
  crop kept), never upscaled, aspect kept. A photo used by several layers gets the largest size any
  of them needs.
- AC-13 A photo already within its box, or whose copy fails, prints from the original; no blank box.
- AC-14 Owner hand test: a printed tag looks as sharp as today.

## P3 sign page, grids, shared component

- AC-15 Q3: Resource Attachments behaves exactly as today: grid shows the thumbnail, opening a file
  shows the original, download gives the original.
- AC-16 Q5: the customer sign page shows every line's picture as a 320 px thumbnail, loaded as the
  customer scrolls; no cap of 60 and no blank cells. The quotation PDF is unchanged.
- AC-17 The sign page's picture route answers only for a valid token and a picture that belongs to
  that quotation issue, never serves an original, and its links expire (security review).
- AC-18 `<AttachmentImage>` renders every stored image in `app/` and `components/`; a FE guard
  (eslint + vitest) fails on a new raw `<img>` outside the allow-list.
- AC-19 Usable at 375 px and 1280 px on every switched screen.

## P4 chatbot

- AC-20 Q2: chatbot and WhatsApp keep sending originals. Closed with no PR.
