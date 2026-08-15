# PLAN - Products that look real in 3D (S8)

**Status:** REWRITTEN 2026-08-03, and NOT yet grilled. The 2026-08-01 version of
this plan generated one AI mesh per SKU; that design is replaced below and the
reasoning for replacing it is in "Why the per-SKU design was wrong". Needs a
grill before any code, per the three-phase loop.
**Companion UAC:** none. The 2026-08-01 plan cited
`product-3d-models-acceptance-criteria.md` as its companion and that file was
never written - the directory holds a UAC for the builder, the design canvas and
flyer seeding, and nothing for this. So there are no ACs to update, and writing
them is part of the grill rather than a rewrite of something existing.
**Depends on:** S7.0 (a chosen image) for the texture work, S7.6 (dimensions)
for scale. Both are done.

---

## The problem, stated honestly

Every product in the room designer is a grey box with its code on the front.
That was the right first move, because dimensions are free and exact while a
model pipeline covers only what somebody has modelled. But a customer asking
"what will my bathroom look like" is not answered by seven grey boxes.

| | Count | Of |
|---|---|---|
| Products | 22,805 | |
| Active, not discontinued | 17,402 | |
| **With any image at all** | **1,541** | 6.8% |
| With length, width and height | 3,331 | 14.6% |
| **With BOTH an image and dimensions** | **473** | 2.1% |

## Why the per-SKU design was wrong

The previous plan chose AI image-to-3D, one generated mesh per SKU, provider
picked by benchmark. Three things kill it as the spine of this feature.

**1. It cannot reach the catalogue.** The addressable set is 473 products, 2.1%.
S7.6 roughly doubles it for the flyer's codes and it is still a rounding error
against 22,805. A design whose best case leaves 95% of products as grey boxes is
not a design for this catalogue.

**2. Generated meshes bake the photo's lighting into the albedo.** The texture
that comes back carries the studio's highlights and shadows painted into the
colour. Dropped into a room with its own lights, that double-lights and reads
worse than a clean mesh under correct lighting. This directly damages the render
quality the feature exists to produce.

**3. Glossy ceramic and chrome are the documented worst case** for single-image
reconstruction, and that is most of what Sorento sells.

Underneath all three: **sanitaryware repeats**. The flyer's 998 codes are
perhaps 25 to 40 distinct SHAPES - one-piece WC, two-piece WC, wall-hung WC,
pedestal basin, countertop basin, undermount basin, single-bowl sink,
double-bowl sink, mixer tap, rain shower, bathtub, mirror, vanity, cabinet. Once
that is seen, generating 998 meshes to represent 30 shapes is obviously the
wrong unit of work.

## The design: archetype, dimensions, material

A product's appearance in 3D is **an archetype scaled to its real dimensions and
finished with its real material**. Not a mesh of its own.

- **100% coverage**, including the 21,000 products with no photo. An archetype
  needs no photograph.
- **More accurate in space** than a generated mesh, which guesses proportions.
  Ours are scaled to the L x W x H the master holds.
- **Renders correctly** - clean topology, real PBR materials, no baked lighting.
- **Fixed one-time cost.** No per-SKU bill and no per-SKU approval queue.

### The ladder, cheapest first

Each rung stands alone and ships value on its own. Nothing below depends on the
rung above being perfect.

**Rung 0 - Lighting and materials. Half a day. Do it regardless of the rest.**
Most of "looks fake" is not mesh detail. `RoomScene.tsx` today is
`AmbientLight(1.4)` plus `DirectionalLight(1.4)` over
`MeshStandardMaterial({ roughness: 0.75 })`, with no environment map and no
shadows - which is why everything reads flat and plastic. Add `RoomEnvironment`
(ships inside three.js, no asset to download), `ACESFilmicToneMapping`, shadow
maps, and per-material PBR values. Grey boxes look dramatically better and every
rung above inherits it.

**Rung 1 - Texture the box with the product's own photo. ~1 day.**
Replace the code-label canvas texture with the brochure image S7.0 already
chose. For flat and boxy products - mirrors, vanities, cabinets, counters - this
is close to finished, because a mirror IS a plane and a vanity IS a box. Zero
new dependencies, zero per-SKU cost, covers all 1,541 products with a photo.

**Rung 2 - Cut-out billboard. ~2 days. Optional.**
Background-removed PNG on a camera-facing plane. `rembg` runs locally in the
worker, no API and no per-image cost. Convincing head-on, breaks past roughly 40
degrees of orbit. Worth it only if rung 3 is delayed.

**Rung 3 - The archetype library. The real answer.**
`product.archetype_id` plus the dimensions the master already holds. Roughly 30
meshes, authored once.

### Where the 30 meshes come from

Cheapest first. This is a procurement question, not an engineering one, and it
does not block rungs 0 to 2.

- **Buy packs** - CGTrader, TurboSquid bathroom fixture sets, roughly $10-50
  each and cheaper in bundles. **Check the licence permits serving the GLB to a
  browser** - that is redistribution, and some licences forbid it.
- **CC0** - Sketchfab filtered to CC0, ambientCG for the PBR ceramic, chrome and
  timber materials. The materials matter more than the meshes.
- **Freelancer in Blender** - a WC is a couple of hours for somebody competent.
  Thirty archetypes is about a week of contract work, once.
- **Use an image-to-3D service 30 times, not 998 times.** Generate one mesh per
  archetype, clean it in Blender, ship it. Roughly $15 of credits rather than an
  ongoing per-SKU bill, and every mesh gets human cleanup so quality is
  controlled rather than sampled. This is the honest role for the AI service:
  an asset-authoring shortcut, not a production pipeline.

## Decisions carried over from the 2026-08-01 grill

These survive the rewrite unchanged.

**D2 - A model is a property of a PRODUCT, not of a brochure.** Stored in
`public` alongside products, never in the `dealer_kit` schema: uninstalling the
module drops that schema and it must not take the product appearance with it.

**D3 - A product with no dimensions still renders, marked estimated.** 1,068 of
the 1,541 products with an image have no dimensions. The archetype is scaled to
the same placeholder volume the box uses today and carries the identical
estimated treatment. Typing dimensions later rescales it with no regeneration -
which under this design is free, where under the old one it was not.

**D5 - GLB is the master format.** Web-native, an open Khronos standard,
imported natively by Blender, 3ds Max, Rhino, Unreal, Unity and SketchUp. STL is
deliberately not a target: geometry with no colour or texture answers 3D
printing rather than visualisation.

**D7 - Claude vets, it does not model.** It produces no geometry; that is a
different model class entirely. It is used where judgement is the work: checking
a chosen photo really is one product and not a line drawing or a blank page
(there is a `98. BLANK PAGE_PG93.jpg` linked to a product right now), and
reading dimensions off technical drawings to extend what S7.6 recovered.

**D4 is materially weakened and mostly drops out.** Staff-see-it-first existed
because a generated mesh might be garbage and needed a human gate before a
dealer saw it. A hand-checked archetype does not: it was correct when it was
authored, and it is correct for every product mapped to it. What remains is
review of the MAPPING - is this SKU really a wall-hung WC - which is ordinary
master data, not an approval workflow.

**D6 (permission plus monthly spend cap) drops out entirely.** There is no
per-SKU spend to cap.

## Schema

Much smaller than the old design, which needed `product_model` with job states,
provider ids, failure reasons and a review trail.

**`product_archetype`** - the library. Roughly 30 rows.

| column | why |
|---|---|
| `code`, `name` | `WC_ONE_PIECE`, "One piece water closet" |
| `model_attachment_id` | the GLB, through the storage router like every file |
| `anchor` | how it sits: floor, wall, counter, ceiling |
| `default_length_mm`, `default_width_mm`, `default_height_mm` | the mesh's own size, so scaling is a ratio |

**On `products`:** `archetype_id`, nullable. Null renders the box exactly as
today, so nothing regresses and the rollout is per-product.

No new file store: GLBs are files and go in `attachments` under a `3D Model`
attachment type.

## Slices

**S8.0 - Rung 0, lighting and materials.** No schema, no API. Independent of
everything else and worth doing first because it improves what exists today.

**S8.1 - Rung 1, photo-textured boxes.** Reads the brochure image from S7.0.
Still no schema.

**S8.2 - Archetype schema and admin.** Migration, `product_archetype`,
`products.archetype_id`, a small CRUD screen, the `3D Model` attachment type.

**S8.3 - Renderer loads an archetype.** GLB by archetype, scaled to the
product's dimensions, box as the fallback, room stays interactive while it
loads. The scene is already built once and synced incrementally, so a model
arriving mid-session is a mesh swap rather than a rebuild.

**S8.4 - Assign archetypes at scale.** Bulk assign from the products grid;
propose by category with a human confirming, never auto-applied. This is the
slice that decides whether the feature covers the catalogue or 30 products.

**S8.5 - Author the library.** Procurement and Blender, not application code.
Runs in parallel with S8.2 to S8.4 against a handful of placeholder meshes.

## What this does not do

- It does not give a product a mesh of its own. Two SKUs of the same shape and
  size render identically, differing by material and dimensions. For
  sanitaryware that is nearly always right, and where it is wrong the escape
  hatch below covers it.
- It does not fix the dimensions gap. S7.6 recovered 425 flyer cards; the rest
  stay honest placeholders until somebody types the number.

## The escape hatch, kept deliberately

Some products genuinely need their own mesh - a flagship suite, a distinctive
basin. `products.model_attachment_id` overriding the archetype covers that in
one nullable column, and the mesh can come from anywhere including an AI
service. It is a per-product exception, not a pipeline, and it is explicitly out
of scope until somebody names a product that needs it.

## Open questions for the grill

- Is 30 archetypes right? Someone who knows the catalogue should sort the
  flyer's 998 codes into shapes and count them. That number decides the budget.
- Who authors the mapping, and does it belong on the product form or in a
  dedicated screen like the brochure image picker?
- Does an archetype vary by finish, or is finish purely a material swap? A
  chrome and a rose gold tap are the same shape; a wall-hung and floor-standing
  WC are not.
- Rung 2 at all, or straight from rung 1 to rung 3?
