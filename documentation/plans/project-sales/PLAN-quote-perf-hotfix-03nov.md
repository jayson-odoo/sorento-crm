# PLAN: quotation spec sheet + sign page performance hotfix (3 Nov)

Status: in review, PR #2126 (small fix track: no migration, no auth/RBAC change, no new ingest surface)

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
3. Sign page: inline only when the photo/drawing column is shown, thumbnail first (crew ruling
   (b), 3 Nov: an attachment with no thumbnail has one made from the original ONCE, stored as its
   thumbnail, and used from then on), failures cached ~10 min, max 60 pictures per page, no
   refetch on window focus, DB connection released before image work.

No worker memory limit was added: the repo's compose files (`sorento_crm/docker-compose.yml`,
`infra/templates/compose.ha.yml`) carry no worker resource settings to extend. Renders are
already one at a time: `catalogue_render` drains only on the single `batch` worker role
(`worker.py` QUEUES), and RQ runs one job per worker process; a test pins that.

## Tests (red first)

- BE: preview payload signs thumbnails; export payload caps resolution; sign page skips images for
  hidden columns, caps pictures, caches failures.
- FE: `useQuotationSign` has `refetchOnWindowFocus: false`; spec sheet thumbnails render lazily.
