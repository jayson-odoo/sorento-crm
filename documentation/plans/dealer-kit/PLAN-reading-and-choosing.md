# PLAN - S9: reading it, and choosing what goes in it

**Status:** DONE. Every section below shipped and was verified in a browser
against live data. Four commits: perf, tile design + overlap gate, UI
corrections, brochure images, picker, collections + tile dialog.

Two things were found rather than built, and both outlived this slice:
`DataGridTable` rows ARE testable under jsdom (one unmocked preferences fetch,
not a limitation), and `SortableItemHandle` was dropping every `aria-label` in
the codebase.
**UAC:** `dealer-kit-reading-and-choosing-acceptance-criteria.md`

---

## The through-line

Every item traces to one of two complaints, and it is worth keeping them apart
because they need different medicine.

**"It is slow and it fights me."** A brochure of 341 rows is not a big page, it
is a page that was built by code assuming ten rows. The fixes are all "do the
thing once instead of per row": one bulk resolve instead of 341, one cached
payload instead of one per reader, one page-level tile design instead of 341
per-block ones. That last one is filed as a UX item and is really the same bug.

**"I cannot see what I am doing."** Choosing four products out of seventeen
thousand, arranging a room, or picking photos are all LOOKING tasks that were
built as reading tasks. Cards, categories, footprints, a visible basket.

---

## Order, and why

Sequenced so each step is independently testable and the riskiest thing is not
last.

### 1. AC-P Performance - DONE

| Change | Where |
|---|---|
| `resolve_tiles_bulk`, union-priced in 3 queries | `collection_service.py` |
| `_shared_candidates`: full scan only when a rule needs it | `collection_service.py` |
| TTL + ETag payload cache, busted on publish | `public_cache.py`, `catalogue.py`, `page_service.py` |
| In-flight dedupe, `no-store` removed | `publicCatalogueService.ts` |

Measured: 13.1s -> 1.30s cold, 3.7ms warm, 304 on revalidate, ~1,020 queries -> 3.

**Deliberate call: TTL, not a pin on the version id.** Tempting, and wrong. The
live page is a version PLUS two mutable joins (collections resolve at read time,
the promotion lives on the page). Pinning would keep quoting an offer that had
ended. One number, `TTL_SECONDS = 60`, bounds the server entry and the browser's
`max-age` together, and publishing clears it outright.

### 2. AC-T21/T22 Page-level tile design

The highest-value item on the list, and it is a two-line schema change.

- `dealer_kit.page.tile_template_id`, nullable. Migration.
- `_tile_templates_for` includes the page default; `bindingFor` falls back to it.
- Inspector shows "Using the page's design (Compact)" with an override control.
- Editor header gets one control that sets it for the document.
- Seeding sets it, so a seeded brochure arrives with a design instead of 340
  unbound blocks.

### 3. AC-R Scroll snap

CSS, on the render container, not the editor. `scroll-snap-type: y proximity`
(not `mandatory` - mandatory on a section taller than the viewport traps a
reader mid-section, which is AC-R2). Off under `prefers-reduced-motion`.

### 4. AC-D Room plan: selection and the overlap gate

The only item with real algorithmic content.

- Footprint = plan-view rectangle from product dimensions, with a stated default
  where dimensions are missing (AC-D9). The dimensions gap is already known and
  recorded against S8.
- **Drag:** the candidate position is tested before it is committed, so an
  illegal drag never lands. Refuse, do not revert.
- **Populate:** shelf placement over free rectangles; place what fits and REPORT
  the remainder rather than silently dropping or stacking it.
- Selection, rotate, duplicate, delete; delete behind a confirmation.

### 5. AC-S Product picker

Card grid with photos, grouped by category, a persistent chosen-list on the
right with remove. Paged server-side - AC-S14 is the constraint that decides the
design, and it is why this is not a client-side filter over everything.

### 6. AC-I Brochure images

List + pagination + a per-row picker that walks next/previous. **AC-I26 is the
one to get right:** one candidate means no decision, so take it and show what
was taken. Anything else is asking somebody to press OK 800 times.

### 7. AC-C Collections as a record, AC-T18/19/20 the design dialog

Standard CRUD list + form; drag-to-reorder fields; undo. Last because they are
the most mechanical and the least likely to surprise.

---

## Testing

Per phase, not deferred: pytest for the resolver, the cache and the page
default; vitest for the picker, the image list and the tile dialog; Playwright
for the reader journey (land, snap, tick, room) and the maker journey (seed,
apply a design, fill a row).

The overlap gate gets property-style tests: no pair of placed footprints may
intersect, for any input, including more picks than the room can hold.

---

## Known risk

**Product dimensions are sparse.** AC-D9 hangs on them, and the room plan is
only as honest as they are. The default footprint keeps it functional; it does
not make it right. Recorded against S8's dimensions gap rather than solved here.
