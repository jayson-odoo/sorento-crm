# UAC: IMAGE-UNIFY

Plan: `PLAN-image-unify-03nov.md`. Each criterion names its phase.

## P1 backend

- AC-1 One resize routine: every downscale in `sorento_crm_backend/app` goes through
  `image_thumbnailer.downscale`. A BE guard test fails on `Image.open(` in any other module that is
  not on its reasoned allow-list.
- AC-2 A new image upload, through any of the 7 upload paths, stores `<key>.thumb.jpg` (320 px) and
  `<key>.medium.jpg` (1024 px), both upright and white-backed, both with
  `Cache-Control: public, max-age=31536000, immutable`.
- AC-3 A failed rendition never fails the upload.
- AC-4 An image with no medium gets one made on first request, once; the next request does not read
  the original. An undecodable image is not retried for 10 minutes.
- AC-5 All picture URLs are signed through `storage_router.resolve_signed_url`; no module keeps its
  own signed-URL or picture cache (the three in the plan's table are gone).
- AC-6 Overwriting an original (promotion re-upload, CMYK fix script) regenerates its renditions;
  new promotion uploads no longer share a key with an earlier upload of the same filename.
- AC-7 Backfill script: dry run writes nothing; resumable with `--after`; throttled with `--sleep`;
  re-running it does no work for rows already done; a broken file is counted and skipped. Dev-copy
  run numbers (rows, made, skipped, failed, minutes, bytes written) posted on the P1 PR.
- AC-8 No screen changes in P1: every existing spec sheet, sign page, attachment and price tag test
  stays green unchanged.

## P2 Price Tag

- AC-9 The designer canvas and preview load medium renditions; opening a template with 20 product
  photos downloads under 5 MB of images (crew perf pass, prod-clone copy).
- AC-10 The tag-sheet PDF prints pictures capped per Q1; a picture already within the cap prints
  from its original; a missing copy prints the original (never a blank).
- AC-11 Printed tag sharpness signed off by the owner on a real print (hand test).

## P3 rest

- AC-12 `<AttachmentImage size>` is the only way a stored image is rendered in `app/` and
  `components/`; a FE guard (eslint + vitest) fails on a new raw `<img>` outside the allow-list.
- AC-13 Attachment preview opens the medium; zoom or download reaches the original (per Q3).
- AC-14 Sign page and catalogue grid render through `AttachmentImage`, lazy (sign page per Q5).
- AC-15 Usable at 375 px and 1280 px on every switched screen.

## P4 chatbot

- AC-16 Per Q2. With the recommended answer (a), nothing changes and this phase closes with no PR.
