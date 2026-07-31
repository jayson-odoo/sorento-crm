# PLAN — Real product models in 3D, generated from product photos (S8)

**Status:** Pre-code. Phase 0 written, approach chosen, awaiting the plan grill.
**Companion UAC:** `product-3d-models-acceptance-criteria.md`
**Depends on:** S4 room designer (the renderer that currently draws boxes).

---

## The problem, stated honestly

Every product in the room designer is a grey box with its code printed on the front. That
was the right first move: dimensions are free, exact, and available for the whole
catalogue, whereas a model pipeline covers whatever somebody has modelled and leaves the
rest missing. But a customer asking "what will my bathroom look like" is not answered by
seven grey boxes.

Two separate gaps sit underneath this, and only one of them is about models:

1. **Shape.** A box does not look like a water closet.
2. **Size.** Only **3,331 of 22,805** products have length and height. `SRTWC286-SH` has
   **31 photos and no dimensions**. So even a perfect mesh has nothing to scale to.

A mesh with no dimensions is a shape floating at an invented size, which is a worse lie
than an honest box. The flyer seeding slice (S7) recovers dimensions for 367 codes and is
the natural companion to this work.

## Decision

**AI image-to-3D per SKU.** *(user decision, taken with the cost and quality caveats on the
table.)* A hosted image-to-3D API turns the primary product photo into a glTF mesh. No
manual modelling, no GPU to run.

The caveats stand and are designed around rather than argued with:

- **Cost is per generation.** Mitigated by generating **on demand and once**, never as a
  bulk sweep over 22,805 products. The 535 flyer SKUs that actually have a photo are the
  realistic working set.
- **Quality on glossy ceramics and chrome is unreliable.** Mitigated by a **draft state**:
  a generated model is not visible to dealers until a human approves it. Same shape as the
  page publish flow, for the same reason.
- **A provider will change or die.** Mitigated by putting one interface in front of it.

## Phase 0 — the journey

Two actors, two entry points.

**Marketing, curating.** From a product's detail page, or from a collection in bulk:
**Generate 3D model**. The system already knows which photo is primary. One decision:
generate, or not. It returns to a queue: models come back minutes later, and the queue
shows each one turning on a turntable next to its photo. One decision per model: **approve**
or **reject and try another photo**. An approved model is what dealers see. A rejected one
never was.

**The dealer or consumer, designing.** Nothing new to learn. They place a product in the
room and it looks like the product. Where there is no approved model, they get the box they
get today, which still carries the real dimensions and the real code. The room never
refuses to show a product because nobody has modelled it.

## Design

**Storage.** Models are files, so they go where files go: `attachments`, through the storage
router, with a new `3D Model` attachment type (`glb`). No second file store.

**`dealer_kit.product_model`** (one row per attempt, not per product, so a rejected
generation stays on the record):

| column | why |
|---|---|
| `product_id` | the SKU |
| `source_attachment_id` | the photo it was generated FROM, so a re-run against a better photo is a different row |
| `model_attachment_id` | the GLB, null until it lands |
| `provider`, `provider_job_id` | which service, which job |
| `status` | `queued` / `generating` / `ready` / `approved` / `rejected` / `failed` |
| `failure_reason` | the provider's own message, kept verbatim |
| `reviewed_by`, `reviewed_at` | who approved it |
| `scale_source` | `product_dimensions` or `unscaled`, see below |

Company-scoped via `CompanyScopedMixin` like every other owned table.

**Generation is a job, never a request.** RQ on a `models` queue, mirroring the imports
queue. The API enqueues and returns; the worker calls the provider, polls, downloads the
GLB, stores it, flips the status. The worker is already a required part of the dev stack.

**One interface, one provider behind it.** `Image3DProvider` with `submit(image) -> job_id`
and `poll(job_id) -> ready|generating|failed`. A stub provider returns a committed GLB
fixture, so no test ever touches the network and the whole pipeline is testable offline.

**Scaling is the part that goes wrong.** A generated mesh has no idea how big the thing is.
So:

- Product has dimensions → the mesh is scaled to that bounding box. `scale_source =
  product_dimensions`.
- Product has none → the mesh is scaled to the same placeholder volume the box uses today,
  and **is marked estimated in exactly the same way the box already is** (the orange
  treatment). It must not quietly look authoritative because it now has a nice shape.

**Renderer preference.** Approved model → box. Two states, not three: an unapproved model
does not render for anyone except the reviewer.

**Loading cost is real.** A GLB per product, in a scene that may hold a dozen, on a dealer's
phone. So: models are loaded lazily per placed product, cached by attachment id for the
session, and a product still renders as its box while its model is in flight. The room is
never blocked on a download.

## Slices

**S8.1 — Schema, attachment type, permission.** Migration, `product_model`, `3D Model`
type, `dealer_kit.model.generate` and `dealer_kit.model.approve` slugs with the grant
sweep.

**S8.2 — Provider interface plus stub, and the job.** Test-first: the whole pipeline
queued → generating → ready, driven by the stub, with the failure and timeout paths
covered before a real provider is wired.

**S8.3 — Real provider.** One implementation. Key in env, absent key means the feature is
off rather than broken.

**S8.4 — Review queue (FE).** The turntable next to the source photo, approve or reject.

**S8.5 — Renderer.** Load an approved GLB, scale it, fall back to the box, keep the room
interactive while it loads. The existing scene is already built once and synced
incrementally, so a model arriving mid-session is a mesh swap, not a rebuild.

## What this does not do

- It does not model a room's fittings (taps on a basin, a mirror on a wall). One SKU, one
  mesh.
- It does not give a product materials or finishes. The generated mesh brings its own
  texture from the photo, which is exactly as accurate as the photo was.
- It does not fix the dimensions gap. S7's dimension report does, for 367 SKUs, and the
  rest stay honest placeholders until somebody types them.
