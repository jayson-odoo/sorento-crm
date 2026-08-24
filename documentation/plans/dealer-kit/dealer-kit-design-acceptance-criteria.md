# UAC - Dealer Kit S4: Selection and the room designer

**Status:** drafted 2026-07-26, pre-code. Companion to
`dealer-kit-builder-acceptance-criteria.md` (S1-S3, all approved).

**In scope:** the Selection spine, the room designer (2D trace -> 3D proxy boxes), and the
handoff to a quote. **Out of scope:** photoreal rendering, real 3D models, AI furniture
placement (S4.5), checkout itself (S5).

---

## Journey

The journey is written first and every AC below traces to a step in it. A plan whose first
section is a schema is rejected in review.

### Who arrives, and from where

Two actors reach the same canvas, and the canvas does not change shape between them:

- **A dealer**, in their showroom, customer beside them. They are a CRM user, signed in.
- **A consumer**, at home, following a link from a published catalogue. They hold a portal
  token, not a login.

**What the system already knows.** A dealer brings their company, their price list and their
customer record. A consumer brings whatever the catalogue link carried and, if they have used
the portal before, their contact. Neither is asked to type a product dimension, a price, or
anything the catalogue already holds.

### The steps, and the one decision each

1. **"Which products?"** They arrive from a catalogue page with products already chosen, or
   they open the designer cold and pick from the same collections the catalogue uses. Either
   way this becomes a **Selection** - the spine everything else hangs off. *Decision: which
   products.*
2. **"What shape is the room?"** They upload a floor plan and the system traces the walls, or
   they drag walls on a grid. Upload is offered first; drawing is always there, because a
   detection that fails must never be a dead end. *Decision: confirm or correct the outline.*
3. **"Does this look right?"** The room appears in 3D with their selected products in it as
   correctly-sized boxes, placed on a first guess. They drag, rotate, add and remove.
   *Decision: where things go.*
4. **"Is this what you want?"** A summary lists everything in the room with quantities and
   prices resolved for whoever is looking, plus the room itself as a picture.
   *Decision: confirm.*
5. **They hold** a saved design they can reopen and a quote request. **Everyone else is told
   automatically**: the dealer sees it in their pipeline, and Sorento sees the demand.

### What is derived, never asked

Product dimensions, prices, availability, the dealer's company, the customer's contact
details, the room's area and the total. If a user is typing something the catalogue already
knows, that is a defect.

---

## Group S - Selection (the spine)

- **AC-S1** `[BE]` Given `dealer_kit.selection`, Then it carries a nullable `user_id` AND a
  nullable `contact_id`, exactly one of which is set, enforced by a CHECK constraint - a
  Selection always has exactly one owner and it is either a CRM user or a contact.
- **AC-S2** `[BE]` Given a Selection, Then its lines reference `products.id` with a quantity,
  and NEVER a price - price is resolved per viewer at read time, as everywhere else (AC-G1).
- **AC-S3** `[E2E]` Given a dealer adds products from a catalogue page, Then a Selection is
  created silently and is visible only to them.
- **AC-S4** `[E2E]` Given a consumer with a portal token does the same, Then the Selection is
  owned by their contact and survives closing the browser.
- **AC-S5** `[BE]` Given a Selection is read by its owner, Then prices resolve for THAT owner:
  a dealer sees dealer pricing, a consumer sees consumer pricing, from one row.
- **AC-S6** `[BE]` Given a Selection references a product that is later discontinued, Then
  reading it flags that line as unavailable rather than dropping it silently - the user chose
  it and must be told, not quietly corrected.
- **AC-S7** `[E2E]` Given a Selection, Then it can be reopened, renamed, and deleted with a
  confirmation naming what is lost.

## Group R - The room

- **AC-R1** `[FE]` Given the designer opens with no room, Then the user can drag walls on a 2D
  grid and see live dimensions in millimetres.
- **AC-R2** `[FE]` Given a drawn outline, Then it is stored as an ordered list of points in
  millimetres - a polygon, not a bitmap - so it can be re-edited and re-rendered forever.
- **AC-R3** `[E2E]` Given a user uploads a floor plan image, Then the system proposes a traced
  outline which the user can drag to correct before accepting. The proposal is a **Proposal**
  in the glossary sense: it is never applied without confirmation.
- **AC-R4** `[E2E]` Given detection fails or produces nonsense, Then the user is dropped into
  hand-drawing with the image behind the grid as a tracing guide - never a dead end.
- **AC-R5** `[BE]` Given a room, Then its area is DERIVED from the polygon and never stored.

## Group V - The 3D view

- **AC-V1** `[FE]` Given a Selection and a room, Then every product renders as a box at its
  real `dimensions_length/width/height`, to scale with the room.
- **AC-V2** `[FE]` Given a product with no dimensions, Then it renders at a clearly-marked
  default size with a warning naming the product - a silently wrong-sized box is worse than an
  obvious placeholder.
- **AC-V3** `[FE]` Given a box, Then it carries the product's name and photo on a face, so the
  scene is readable without clicking anything.
- **AC-V4** `[FE]` Given the user drags a box, Then it moves on the floor plane only and
  cannot leave the room outline or intersect another box.
- **AC-V5** `[FE]` Given the scene, Then it runs at 30fps or better with 50 boxes on a
  mid-range laptop, and degrades to the 2D plan view rather than freezing.
- **AC-V6** `[FE]` Given a phone, Then the designer is usable at 375px - the plan view and the
  summary at minimum, even if 3D manipulation is coarse.

## Group Q - The handoff

- **AC-Q1** `[E2E]` Given a finished design, Then the summary lists every product with
  quantity and a price resolved for the viewer, plus the derived room area and a total.
- **AC-Q2** `[E2E]` Given a dealer confirms, Then a Quote is created that they own, per the
  grill decision (C2), and it appears in their pipeline.
- **AC-Q3** `[E2E]` Given a consumer confirms, Then a request reaches the dealer rather than
  becoming an order - a consumer cannot place an order directly.
- **AC-Q4** `[BE]` Given a Quote from a design, Then it links back to the Selection and the
  room, so "what did they actually design" is answerable later.

## Group D - Dependencies this slice must clear first

- **AC-D1** `[BE]` Given `respond_contacts` and `customers`, Then a link between them exists -
  the plan's dependency table names its absence as the thing blocking S4.
- **AC-D2** `[BE]` Given the link, Then a contact reaching the designer resolves to a customer
  when one exists, and does not invent one when it does not.

## Group T - Tests

- **AC-T1** Room geometry (area, containment, wall snapping) has a golden set written BEFORE
  the implementation.
- **AC-T2** Box packing and collision have a golden set written BEFORE the implementation.
- **AC-T3** Every price assertion is made against the SERVER response, never the DOM.
