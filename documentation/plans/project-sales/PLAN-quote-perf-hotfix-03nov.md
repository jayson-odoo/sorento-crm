# PLAN: quotation spec sheet + sign page performance hotfix (3 Nov)

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Why

Prod 3 Nov: opening a quotation tab hung the app. Heavy paths shipped the same day:

1. Spec sheet tab (#2103) preview signs FULL-SIZE originals and draws a full renderer per page
   thumbnail.
2. Spec sheet Export PDF renders full-size images into 420x297 mm pages.
3. Customer sign page (#2106) downloads/decodes/inlines every line photo and drawing per request
   while holding a DB connection; failures are never cached; refetch on every window focus.

## Fix (no visible behaviour change beyond speed)

1. Preview / thumbnails sign thumbnails (`full=False`); page thumbnails render lazily (only the
   visible ones). Full size only in the Export PDF payload.
2. Export images capped at what the page needs at ~200 dpi; one render at a time.
3. Sign page: inline only when the photo/drawing column is shown, thumbnails only, failures cached
   ~10 min, max 60 pictures per page, no refetch on window focus, DB connection released before
   image work.

## Tests (red first)

- BE: preview payload signs thumbnails; export payload caps resolution; sign page skips images for
  hidden columns, caps pictures, caches failures.
- FE: `useQuotationSign` has `refetchOnWindowFocus: false`; spec sheet thumbnails render lazily.
