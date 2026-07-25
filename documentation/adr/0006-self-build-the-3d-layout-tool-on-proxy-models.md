# The AI Design 3D layout tool is self-built on proxy models, not Coohom or Roomle

Sorento partners with Coohom, `coohom_test/` holds working OpenAPI credentials and a
signed-request harness for uploading models via OSS, and Coohom sells exactly this: an
embeddable floor planner where customers design with your products. We are still building
our own. A future reader will ask why, so:

**Near-zero Sorento SKUs have 3D models.** What a vendor sells is a 3D asset library plus a
renderer. Neither is what we need — the models have to be *Sorento's*, so their library is
irrelevant, and the saleable image does not come from their renderer either (below). We would
be paying for the part we can't use while supplying the part they normally provide.

**We already have dimensional truth for free.** `products.dimensions_length / _width /
_height` exists for every SKU. A proxy box built from those numbers is dimensionally accurate
today, and dimensional accuracy is the entire job of the 3D layer — whether the 1200 vanity
fits the wall. Texture the box with the existing `product_attachments` image and it is
recognisable too. Proxies are not a stopgap; they are the correct primitive until real models
exist, at which point a `model_asset` on the product swaps in per SKU.

**3D carries layout truth; AI carries beauty.** The scene never has to look good — it has to
be spatially correct. The image a customer is sold comes from an AI render conditioned on
that scene plus product reference photos. That deletes materials, lighting, PBR and render
quality from the 3D scope, which is most of what makes a 3D editor expensive, and it removes
the last reason to rent someone else's renderer.

**UX simplicity was the original objection, and an iframe permanently forfeits it.** Coohom's
tool is designer-grade; a dealer or a walk-in consumer needs a 2D-plan-first placer with a 3D
preview. Inside a vendor iframe we cannot simplify anything. Roomle is the closer fit — it
ships price calculation and order lists — and is worth a quote to de-risk the BOM half, but
its 6,000-product library contains no Sorento SKUs either.

Photogrammetry from dealer photos was rejected as a launch dependency: white glossy ceramic
is featureless and chrome tapware is specular — the two worst cases for feature matching.
Single-image AI-to-3D copes better but is dimensionally unreliable, and a wrong scale on a
quotable layout is worse than a box. It becomes an opt-in per-SKU upgrade path with a QC
gate, never a promise.

The reversal cost is the scene document model. It is ours, so a later decision to embed a
vendor means abandoning it — which is precisely the lock-in we are declining now.
