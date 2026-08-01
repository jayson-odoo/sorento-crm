# PLAN — Real product models in 3D, generated from product photos (S8)

**Status:** Grilled 2026-08-01. Blocked on S7.0 (a chosen image) and materially helped by S7.6 (dimensions).
**Companion UAC:** `product-3d-models-acceptance-criteria.md`
**Not a Dealer Kit feature.** A 3D model is a property of a PRODUCT, like its photo
and its dimensions. It lives in master data, is triggered from the product, and is used by
whatever wants it: the room designer today, tiles or AR later.

---

## The problem, stated honestly

Every product in the room designer is a grey box with its code on the front. That was the
right first move, because dimensions are free and exact for the whole catalogue while a
model pipeline covers only what somebody has modelled. But a customer asking "what will my
bathroom look like" is not answered by seven grey boxes.

Three gaps sit underneath, and only one of them is about models.

| | Count | Of |
|---|---|---|
| Products | 22,805 | |
| Active, not discontinued | 17,402 | |
| **With any image at all** | **1,541** | 6.8% |
| With length, width and height | 3,331 | 14.6% |
| **With BOTH an image and dimensions** | **473** | 2.1% |

So the addressable set today is **473 products**, not 22,805. For this flyer's 998 codes it
is **229**. S7.6, which recovers dimensions for 425 flyer cards, roughly doubles that,
which is why it belongs before this slice rather than after it.

And a fourth gap, found while grilling S7: **nobody has ever said which photo is the
product.** `product_attachments.is_primary` is false on every row. `SRTWC286-SH` has 31
linked images including `98. BLANK PAGE_PG93.jpg` and two other products' photographs.
Filenames would identify the right image for 509 of 535, and inference is rejected: a
generator fed the wrong picture produces a confident, expensive model of the wrong product.
S8 consumes the flag a human sets in S7.0 and generates nothing without it.

## Decisions

**D1 — AI image-to-3D, one interface, provider chosen by benchmark.** *(user)*
Before committing, generate the same five products on two or three providers and judge them
at real size in the room designer, not on a turntable. The set is chosen to be the
catalogue's hard cases, because the failure mode everyone reports is glossy and reflective
surfaces and this catalogue is mostly glossy and reflective:

| SKU | Why it is in the set |
|---|---|
| `SRTWC286-SH` | glossy white ceramic, the archetypal case |
| `SRTWT51012` | chrome and rose gold, the worst case for reconstruction |
| `SRTJC8041` | acrylic bathtub, 1700mm, a large concave form |
| `SRTMRL707` | frameless LED mirror, nearly flat and reflective |
| `SRTBF11102` | timber-front vanity, a box with real material detail |

**Needs from you:** API keys for the shortlisted providers and a small spend, perhaps 15
generations. Nothing else in the plan is blocked while that is arranged.

**D2 — Per product, never per brochure.** *(user)* Triggered from the product detail page
and in bulk from the products grid. Stored in `public`, alongside products. Not in the
`dealer_kit` schema: uninstalling the module drops that schema, and it must not take the
product models with it.

**D3 — A product with no dimensions still gets a model, marked estimated.** *(user)*
1,068 of the 1,541 products with an image have no dimensions. Refusing them would mean
almost nothing ever gets modelled. The mesh is scaled to the same placeholder volume the box
uses today and carries the identical estimated treatment, so it is honest about the one thing
it does not know. Typing dimensions later rescales it with no regeneration.

**D4 — Staff see it immediately, dealers only after approval.** *(user)*
The moment a model lands it renders for staff, including in a real room, so it is judged at
size and beside other products, which is where a bad mesh actually shows. Dealers and
consumers keep the box until somebody approves it. Rejection keeps its reason and returns the
product to a box.

**D5 — GLB is the master; whatever else the job returns is kept beside it.** *(user)*
GLB is what the app loads: web-native, an open Khronos standard, and imported natively by
Blender, 3ds Max, Rhino, Unreal, Unity and SketchUp. Any OBJ, FBX or USDZ the same job
produces is stored as an attachment and offered on a Download menu, because asking for them
at job time is free while converting later is a pipeline to build and host. USDZ is what
makes "view it in your bathroom" work on an iPhone, which is worth having for free.

STL is deliberately not a target: it carries geometry with no colour or texture, so it
answers 3D printing rather than visualisation.

**D6 — A permission plus a configurable monthly cap.** A dedicated
`product_model.generate` permission decides who may spend; a cap in Settings decides how
much per month. Past the cap generation refuses with a plain message and the month's count,
rather than silently queueing. Both DB-configurable, so a big push is a settings change.

**D7 — Claude vets, it does not model.** Claude produces no geometry. It is used where
judgement is the work and it directly protects the spend:

- before a job, check the chosen photo really is one product, photographic, and not a line
  drawing or a blank page;
- after a job, compare a render of the mesh against the source photo and flag the obvious
  failures, so a human reviews a short list instead of 229 turntables;
- read dimensions off technical drawings, extending what S7.6 recovers from the flyer.

## Design

**Storage.** Models are files, so they go where files go: `attachments`, through the storage
router, under a new `3D Model` attachment type. No second file store.

**`product_model`** (one row per attempt, so a rejected generation stays on the record):

| column | why |
|---|---|
| `product_id` | the SKU |
| `source_attachment_id` | the photo it came FROM, so a re-run on a better photo is a new row |
| `model_attachment_id` | the GLB, null until it lands |
| `extra_attachment_ids` | OBJ, FBX, USDZ from the same job |
| `provider`, `provider_job_id` | which service, which job |
| `status` | `queued` / `generating` / `ready` / `approved` / `rejected` / `failed` |
| `failure_reason` | the provider's own message, kept verbatim |
| `reviewed_by`, `reviewed_at`, `rejection_reason` | who decided and why |
| `scale_source` | `product_dimensions` or `estimated` |

Company-scoped via `CompanyScopedMixin` like every other owned table.

**Generation is a job, never a request.** RQ on a `models` queue, mirroring imports. The API
enqueues and returns; the worker submits, polls, downloads, stores, flips the status.

**One interface, providers behind it.** `Image3DProvider` with `submit(image) -> job_id` and
`poll(job_id) -> ready | generating | failed`. A stub returns a committed GLB fixture, so the
whole pipeline is testable offline and no test touches the network.

**Renderer preference.** Approved model, then box. For staff, ready model, then box. A model
is loaded lazily per placed product and cached by attachment id for the session, and the
product renders as its box while its model is in flight: a room on a showroom's wifi must
never block on a download.

## Slices

**S8.0 — Blocked on S7.0.** Nothing is built until a human can say which image is the product.

**S8.1 — Benchmark.** Five SKUs, two or three providers, judged at real size. Produces the
provider decision and the first honest quality read. Needs keys and a small spend.

**S8.2 — Schema, attachment type, permissions, cap.** Migration, `product_model`, the
`3D Model` type, `product_model.generate` and `product_model.approve`, the settings cap, and
the grant sweep.

**S8.3 — Provider interface, stub, and the job.** Test-first: queued to generating to ready,
plus the failure and timeout paths, all driven by the stub before a real provider is wired.

**S8.4 — Real provider**, the one the benchmark chose. Absent key means the feature is off
rather than broken.

**S8.5 — Product surfaces.** Generate and approve on the product detail page, bulk generate
from the products grid, the Download menu, and the estimated-size warning.

**S8.6 — Renderer.** Load an approved GLB, scale it, fall back to the box, keep the room
interactive while it loads. The scene is already built once and synced incrementally, so a
model arriving mid-session is a mesh swap rather than a rebuild.

**S8.7 — Claude vetting.** Pre-flight photo check and post-flight comparison, both as
advisory flags on the review, never as an automatic reject.

## What this does not do

- It does not model a product's fittings separately. One SKU, one mesh.
- It does not give a product materials or finishes beyond what the photo carried.
- It does not fix the dimensions gap. S7.6 does, for 425 flyer cards; the rest stay honest
  placeholders until somebody types the number, model or no model.
