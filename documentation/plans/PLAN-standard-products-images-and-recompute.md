# PLAN - Standard products by list, quotation images, recompute, and stranded extractions

> **Table names in this document predate the schema move.** On 2026-08-15 the projects
> module's 47 tables moved into a dedicated `projects` Postgres schema and the 34 that
> carried a `project_` prefix dropped it: `project_leads` is now `projects.leads`,
> `project_quotation_lines` is `projects.quotation_lines`, and so on. The 13 unprefixed
> ones only changed schema. Nothing else in this document changes. See
> [ADR-0011](../adr/0011-project-sales-tables-live-in-the-projects-schema.md) and
> `documentation/plans/PLAN-projects-schema-move.md` for the full mapping.

**Status:** written 2026-08-08. **All four slices implemented.** S18 and S19 on 2026-08-08
(migration `331_project_series_products`, applied to the shared dev DB via an Operations
context). S21 on 2026-08-08. S20 on 2026-08-08 (migration `332_extraction_job_tracking`),
with the decoupling **demonstrated** on 2026-08-09 - see "What S20 shipped" below. That
demonstration found and fixed a defect that had disabled the whole slice.
Still outstanding for the whole plan: DoD 6 (verified at 375px and 1280px on a prod build).
**Parent:** `PLAN-project-quotation-document.md`, `PLAN-quotation-approval-and-revision-request.md`
**Slug:** standard-products-images-and-recompute

## Why

Four things from the 2026-08-08 client review, plus the reference documents they supplied:

- `products template( sanitaryware).xlsx` - what "standard" actually means to them.
- `Cabana Elmina- nadi cergas R2.xlsx` - what a real issued quotation looks like.

## The finding that shapes S18

The client's template is **an explicit list of product codes**, not a set of categories.
Three sheets (`wares` 40, `fittings` 97, `shower` 14) share one shape:

```
ITEM | PRODUCT IMAGE | TECHNICAL SPEC | DESCRIPTION | BRAND | PRODUCT CODE | DEVELOPERS | DISTRIBUTORS | CENTRAL | NORTHEN
```

151 code cells, **142 unique**, matching **167 product rows** in the catalogue.

Today a `ProjectSeries` nominates CATEGORIES (`project_series_categories`), and
`is_in_series` asks whether the line's product sits in one of them. Measured against this
template:

| | |
|---|---|
| Products the client calls standard | ~167 |
| Categories those products span | 31 |
| Products in those 31 categories | **15,048** |

So expressing this template by nominating categories would call 15,048 products standard to
capture 167 - about ninety times too many, and it would never flag the sibling product that is
the exact thing the alert exists to catch. **Category nomination cannot express this
requirement.** A series needs product-level membership.

Categories stay. They are the right tool for "everything under Basins is fair game", and the
client may still want that for other scopes. The two combine: a product is in the series if it
is nominated directly OR sits in a nominated category.

Note for whoever builds it: the sheets also carry per-audience pricing columns (DEVELOPERS,
DISTRIBUTORS, CENTRAL, NORTHEN) and a PRODUCT IMAGE column. Those are NOT in scope here -
pricing floors already have their own model, and images are S21. Do not quietly import them.

## Slices

| # | Slice | Ships |
|---|---|---|
| **S18** | Standard products by list | `project_series_products` (series_id, product_id, unique together). `is_in_series` answers on direct membership OR category membership, with the same `covered` pre-expansion trick so a whole version costs one walk. A way to load a list of product codes onto a series from the UI, reporting every code it could not match rather than silently dropping it - an unmatched code is the client's data telling us something. Load the 142 codes as the first series. |
| **S19** | Recompute | The client's words: "I need to have a recompute button rather than you go and bulk write the data, like, a refresh button that recompute this, in case someone change at the master data (product or any configuration), then the quotation can refresh to repull this". A button on the quotation that re-runs `_apply_guardrails` over the current version's lines against today's master data, and reports what changed. This is also the migration path for the stale flags rather than a one-off backfill script. |
| **S20** | Stranded extractions | A document extraction whose work-horse dies leaves `extraction_state='running'` forever: the failure is written in an `except` block, and that never runs when the process is killed. Detect the death and mark the row failed with a readable reason plus a way to retry. **BUILT** - `app/services/project_extraction_recovery_service.py`, migration `332_extraction_job_tracking`, reconcile-on-read on both document types, `POST .../retry-extraction` on both. Demonstrated against a real killed work-horse 2026-08-09. |
| **S21** | Quotation product images | The client's issued quotation has a PRODUCT IMAGE column, 24 images, anchored in column B beside each line. Source it from `product_attachments.is_primary` - the SAME flag the brochure uses - and render it on the line table, the PDF and the Excel export. **BUILT** - UAC at `quotation-product-images-acceptance-criteria.md`. Resolver: `app/services/product_image_service.py` (one decision, three consumers); quotation glue + freeze-at-issue: `project_quotation_image_service.py`. Measured: 52-line PDF 863 KB, 52-line workbook 419 KB (52 originals would be 119.5 MB). |

## Decisions taken from the client's message

- **Standard = on the sheet.** "any product that is not in the sheet that I provided you are
  flagged as non standard". Explicit membership, not inference.
- **No bulk write.** The stale flags are corrected by pressing recompute, not by a migration.
  They asked for this directly and the reason is good: master data moves, so the fix has to be a
  repeatable action rather than a one-time correction.
- **Extraction stays queued and decoupled.** "make sure the processing is by a queue in the
  backend so refreshing the page doesn't kill it, the processing is going to be high loading so
  we must decouple it else it will lag the system." It already is (RQ, `project_docs`), and a
  page refresh has never affected it. S20 does not change that; it fixes the reporting of a
  death. Whoever builds S20 must confirm the decoupling holds rather than assuming it.
- **One image decision, not two.** `brochure_image_service.py` (dealer-kit branch) says it
  outright: "This is product master data, not a Dealer Kit concept. The Kit is one consumer; 3D
  model generation is another, and it reads the same flag." The quotation becomes the third
  consumer of `product_attachments.is_primary`. It must NOT invent its own choice, and must not
  fall back to "whichever photo was linked first" - that is the exact defect that flag exists to
  remove.

## What S18 and S19 actually shipped (2026-08-08)

**S18.** `project_series_products (series_id, product_id)`, composite PK, both FKs
`ON DELETE CASCADE`, plus `ix_project_series_products_product` for the reverse question.
`project_pricing_service.SeriesMembership` carries the two expanded sets and
`series_membership()` builds it once per version; `is_in_series(..., membership=...)`
answers on direct membership OR category membership, direct first (so a product whose
category is not covered is still standard when it is named). Codes resolve through
`variant_link_service.normalize_code` and its SQL twin, in ONE query for the whole list.
Two routes, one service: `POST /config/series/{id}/products` for a paste, and
`.../products/upload` for a sheet, both answering the same report. The series listing gained
`product_count` + `product_codes` (codes, not ids).

**The 142 codes are loaded.** Series `Sanitaryware template (client, 2026-08)`, created and
filled through those endpoints over HTTP against the dev database:

| | |
|---|---|
| Code cells read | 153 (151 cells, two of which carry two codes on two lines) |
| Unique after normalising | 141 |
| Matched a Sorento product | 92 |
| Products nominated | 92 |
| **Unmatched, reported to the user** | **49** |

The 49 are not a bug. The client's sheet quotes BASE codes the catalogue only stocks as
suffixed variants (`CWC1009-RL` against a stocked `CWC1009-SC`, `SRTWC8036` against
`SRTWC8036-RL` / `-SH-150` / `-SH-200` ...). Reported verbatim, copyable, for the client to
reconcile. Nothing fuzzy-matched: guessing which of six suffixed variants they meant would
call the wrong products standard and nobody would ever find out.

Not imported, as instructed: the DEVELOPERS / DISTRIBUTORS / CENTRAL / NORTHEN price columns
(price floors have their own model) and the PRODUCT IMAGE column (S21, `is_primary`).

**S19.** `POST /quotation-versions/{id}/recompute`, synchronous, **the version named in the
URL and only while it is editable** (`assert_editable`, so frozen and issued refuse with the
usual 422). Not "every editable version on the document": recomputing a scope somebody else
has open is a surprise, and the screen already knows which version is being read. The series
is expanded once and the version's products read in one query, so the per-line cost is the
floor resolution alone; if a document ever carried hundreds of lines, the thing to move is
`resolve_floor` re-reading the company's rules per line, and then the whole pass belongs on
the `project_docs` queue with the report delivered through My Downloads. Breach events stay
transition-only, so re-confirming forty lines notifies nobody.

**The 46 "stale" flags were not stale.** All 46 lines on the open version of
`QT-004188 Tuju Residences` name products belonging to a DIFFERENT company that happen to
carry the same codes as Sorento's own rows (233 quotation lines across the database are in
this state). Under the acting company's scope those products do not resolve, so each line
reads as off-catalog and stays non-standard - which is exactly what a re-SAVE computes, so
recompute agrees with save and correctly reports that nothing changed. To stop that reading
as a no-op, the report carries `unresolved_products` and the screen says so: "46 lines name
products this company's catalogue does not carry". **Repointing those lines is a separate
data fix and is not part of this slice.**

## What S20 shipped, and what the demonstration caught (2026-08-09)

The plan asked for the decoupling to be **demonstrated rather than assumed**. Doing that is
what turned S20 from "written and green" into "actually working": the slice had a defect
that disabled it completely, and every unit test passed anyway.

**The defect.** `look_up_job` turned RQ's answer into our own vocabulary with
`str(job.get_status())`. RQ's `JobStatus` is a `(str, Enum)`, so `__str__` is Enum's:
`str(JobStatus.FAILED)` is `"JobStatus.FAILED"`, and lowercased that is
`"jobstatus.failed"` - in neither `_ALIVE` nor `_DEAD`. So `_verdict` took its "an
unrecognised status is not evidence of death" branch and returned `None` for **every**
killed read. RQ would log `moving job to FailedJobRegistry (signal 15)` and the row would
still say `running` a minute later: the exact stranding the slice exists to remove, with a
whole module of correct code sitting behind one bad conversion.

**Why the tests could not see it.** All 21 of them replace `look_up_job` - the documented
seam that lets the decision table run without a Redis. No real `JobStatus` ever reached the
line that was wrong. Two tests now cover the seam itself: one feeds a real `JobStatus.FAILED`
through a stubbed `Job.fetch` and requires `"failed"`, and one asserts that **every** value
RQ's enum can report is in our vocabulary, so a new RQ status becomes a test failure instead
of a silently stranded row. That second test immediately found `created` missing, now listed
in `_ALIVE`.

**The demonstration**, against the real dev database, real Redis and a real worker, on a
cloned version so no real document was touched:

| What was done | What happened |
|---|---|
| `retry()` on a version | job enqueued and its id recorded on the row, in 36ms |
| worker picked it up | row `running`, `extraction_started_at` stamped, read executing in forked pid 43347 - a different process from the caller |
| `kill -15` the work-horse | RQ logged `moving job to FailedJobRegistry ... signal 15`; **row still said `running` 10s later**, reproducing the bug exactly |
| reconcile on read | row -> `failed`, reason: *"The read was interrupted: the background worker was terminated (signal 15), so nothing was recorded from this document. It is still stored. Read it again."* |
| `retry()` again | fresh job id, worker picked it up, row `running` again |

**The decoupling, demonstrated at the level the client asked about.** A page refresh only
drops a TCP connection, so surviving one proves little. The harder test was run instead:
start the read through the real `POST /project-sales/purchase-order-versions/{id}/retry-extraction`,
then `SIGKILL` the entire uvicorn process three seconds in and confirm `:8010` was dead and
unreachable. The read ran to completion with no web tier at all - `done`, 45 lines,
305 seconds. Nothing about a document read depends on the process that requested it, so no
page refresh can affect one.

(That run also exercised the partial-read path incidentally: page 5 came back unreadable and
the row still ended terminal, with *"Pages 5 could not be read; everything else on the
document stands."* - a different sentence from the interruption one, which is the point.)

**Not covered:** the two screens that show this were not driven in a browser. The endpoints,
the reconcile-on-read and the retry are demonstrated end to end; the FE rendering of them is
part of DoD 6, still outstanding.

## Open engineering questions

- **Only 30 products currently have a primary photo**, against 535 with candidates. So most
  quotation lines will have no image on day one. The empty state has to read as "nobody has
  chosen this product's photo yet" with a way to go and choose it, not as a broken image.
- Whether recompute acts on the open version only (safe, obvious) or every editable version on
  the document. Lean to the open version: recomputing a version somebody else is editing is a
  surprise.
- Whether recompute is synchronous. A version is tens of lines, so probably yes - but it must
  not become a second heavy path if a document ever carries hundreds.
- S18's importer and the existing product-code resolution used elsewhere (imports, PO matching)
  should share a normaliser. The template has codes with trailing and internal double spaces
  (`CWB 242`, `SRTPW0035 `, ` TPE 9203`) and 9 duplicates across sheets.

## Definition of done

1. A product not on the client's sheet is flagged non-standard; one on it is not.
2. The 142 codes are loaded, and every code that did not match a product is reported to the user.
3. Recompute exists on the quotation, corrects the stale flags, and says what it changed.
4. A killed extraction shows as failed with a reason and can be retried; the queue decoupling is
   demonstrated, not assumed. **DONE 2026-08-09** - real work-horse killed with signal 15 and
   recovered; read survived a `SIGKILL` of the whole API process. See "What S20 shipped".
5. The quotation shows each line's product image, identical to the brochure's, on screen, in the
   PDF and in the Excel export.
6. Verified at 375px and 1280px on a prod build, against real data.
