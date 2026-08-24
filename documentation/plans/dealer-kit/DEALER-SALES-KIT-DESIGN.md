# Dealer Sales Kit - Design and Build Plan

**Audience:** product, commercial, and engineering leadership
**Status:** S1, S2, S3 delivered and signed off internally. S4 part-delivered. Nothing deployed.
**Branch:** `feat/promo-expiry-rule-engine` (Dealer Kit worktree) - cannot merge before the
multi-company work lands. See *Risks*.
**Last updated:** 2026-07-27

---

## 1. What this is, in one paragraph

Sorento sells through dealers. Today a dealer sells from a printed catalogue, phones or messages
the office to check stock, and the customer imagines what the product will look like in their
room. The Dealer Sales Kit replaces that with one continuous flow: a digital catalogue Sorento
controls centrally, a room the customer can actually see their chosen products standing in, and
a quote that comes out the other end already priced correctly for whoever is looking at it. The
catalogue, the room and the quote are the same piece of work, not three tools bolted together.

The commercial point is that this is something Sorento **sells to its dealers**, not an internal
admin screen. It has to be good enough that a dealer would miss it if it were taken away.

---

## 2. The nine packages, and where we are

The full Dealer Kit vision has nine parts. This programme delivers them in dependency order,
not in wish order.

| # | Package | State |
|---|---------|-------|
| 1 | **Brochure / catalogue generator** | **Delivered** (S1-S3) |
| 2 | **Stock check** | Already exists in the CRM; needs surfacing in the kit |
| 3 | **AI design** (room designer) | **Part-delivered** (S4) |
| 4 | Order management | Exists in the CRM; the quote handoff is the missing link |
| 5 | Warranty system | Separate programme, already grilled and specced |
| 6 | Display rack | Not started |
| 7 | Product knowledge | Not started |
| 8 | Extra discount | Not started |
| 9 | Exhibition request | Not started |

Packages 1 and 3 were chosen first deliberately: they are the two the dealer touches every day,
and everything else hangs off the catalogue being real.

---

## 3. The journey, written before the schema

Every part of this was designed from the user's journey first. A plan whose first section is a
database diagram gets rejected in our review, because the schema then dictates the experience
instead of serving it.

### 3.1 Who arrives, and from where

Four people touch this, and the system already knows something about each:

- **A Sorento marketing designer** builds the catalogue. Signed in, sees everything.
- **A Sorento office user** exports a PDF for a dealer or a customer. Signed in.
- **A dealer**, in their showroom with a customer beside them. Signed in; brings their company
  and their price list.
- **A consumer**, at home, following a link. Holds a portal token, not a login. Brings whatever
  the link carried, plus their contact record if they have used the portal before.

### 3.2 The steps

1. **"Which products?"** They arrive from a catalogue page with products already chosen, or open
   the designer cold and pick from the same collections the catalogue uses. *One decision: which
   products.*
2. **"What shape is the room?"** They upload a floor plan and the system traces the walls, or
   they drag walls on a grid. Upload is offered first; drawing is always available, because a
   failed detection must never be a dead end. *One decision: confirm or correct the outline.*
3. **"Does this look right?"** The room appears in 3D with their products in it at real size,
   placed on a first guess. They drag, rotate, add, remove. *One decision: where things go.*
4. **"Is this what you want?"** A summary lists everything with quantities and prices resolved
   for whoever is looking, plus the room area and a total. *One decision: confirm.*
5. **They hold** a saved design they can reopen and a quote request. Everyone else is told
   automatically: the dealer sees it in their pipeline, Sorento sees the demand.

### 3.3 What is derived, never asked

Product dimensions, prices, availability, the dealer's company, the customer's contact details,
the room's area, the total. **If a user is typing something the catalogue already knows, that is
a defect.**

---

## 4. The three decisions that shape everything

These were the genuinely contested calls. Each has a cost we accepted knowingly.

### 4.1 Build the 3D ourselves rather than embed Coohom / Aihom

Coohom is a professional interior-design tool. It is excellent at what it does, and what it does
is give a trained interior designer deep control. Our users are a dealer with a customer waiting
and a consumer on a phone. They need **one room, a handful of products, and an answer in two
minutes**.

We render each product as a correctly-sized box rather than a photoreal model. That sounds like
a downgrade and is not:

- **Every product works on day one.** Products already carry length, width and height, so a box
  is free and exact for the entire catalogue. A model pipeline would cover the few SKUs somebody
  modelled and leave the rest missing - worse than a room of honest boxes.
- **A box cannot lie.** It claims to be a volume and a name, nothing more. A half-finished
  photoreal model quietly misrepresents the product.
- **It runs on a phone.**

The cost: it does not look like a magazine. If photoreal becomes a sales requirement, the room
data we store (a polygon plus placements, all in millimetres) feeds a better renderer later
without redesign.

### 4.2 Build inside the CRM, not as an embedded shared service

The catalogue needs live products, live prices, live stock, the dealer's company, and the
customer's contact. All of that is in the CRM. An iframe-embedded service would need a copy of
each, and copies drift. Prices drifting is the specific failure that produces a quote the
company cannot honour.

The cost: the Dealer Kit is a CRM module, so a dealer needs a CRM identity. That is already true
of the portal, so it is not new ground.

### 4.3 Prices are never stored - they are resolved for whoever is looking

This is the single most important rule in the build, and it is enforced in several places at
once.

A saved catalogue page stores **bindings** ("show this collection here"), never resolved values.
A selection line stores a product and a quantity, never a price. When anyone reads either, the
price is worked out at that moment, for that viewer.

That is what lets **one** published document serve staff, dealers and consumers with the price
each is allowed to see, instead of three copies drifting apart. Two independent gates decide
whether an internal price appears: the document must be set to show it **and** the viewer must
be entitled to it. When the answer is no, the number is **absent from the response**, not hidden
in the page where it can be recovered by inspecting it.

A test asserts that a selection line has no `price`, `unit_price`, `list_price`, `invoice_price`
or `total` column, so the rule cannot be quietly relaxed later.

---

## 5. The slices

Each slice runs three phases in order: **prototype the screens against mock data → build the
backend and wire it up with tests → review**. A slice is not "done" until its gate is recorded.
This is what stops us building a backend for a UI that gets rejected.

### S1 - The page builder *(delivered)*

A Sorento designer builds catalogue pages from blocks: heading, text, image, product grid,
bundle, artboard. Four preview modes (desktop, tablet, mobile, paper) because the same page has
to work on a phone and on A4.

- **Versions are immutable, labels move.** Publishing does not overwrite anything; it points the
  `published` label at a version. Rollback is the same operation pointed backwards. There is
  also a `staging` label so a designer can preview without publishing to every dealer.
- The public address is company-qualified - `/c/{company}/{page}` - because two companies may
  legitimately use the same page name.

### S2 - Collections, tile designs and bundles *(delivered)*

- **Collections** are how a page says "show these products". A collection can be a **rule**
  ("everything in this category under this price"), a **hand-picked list**, or both, with
  exclusions. Exclusions always win. The rule engine is the same one the marketing automation
  already uses, so a rule behaves identically in both places and the existing rule-builder UI
  works unchanged.
- A collection can be **saved to a library** and bound to several pages - edit it once, every
  page that uses it follows.
- **Tile designs** control what a product tile shows (photo, name, code, price, and so on) from
  a whitelist. Internal cost fields are not on that whitelist and cannot be added through the UI.
- **Bundles** sell several products under one price. The single price is split back across the
  components in whole cents, with the remainder going to the largest line, so the parts always
  add up to the price the customer was shown. A bundle's availability is derived from its
  components on every read: a bundle whose part was discontinued this morning reads as
  unavailable without anyone editing it.

### S3 - Publishing and PDF export *(delivered)*

- A published page is a real public web page.
- **PDF export** renders the actual page in a headless browser, so the PDF and the screen cannot
  disagree - there is one renderer, not two.
- The export snapshots **who it is for** at the moment it is requested. A staff export and a
  dealer export of the same page carry different prices, and the worker can never fall back to
  a default identity and quietly print internal pricing into a customer's document.
- The version is pinned when the export is queued, so publishing again while a PDF is in the
  queue does not change what that PDF contains.

### S4 - The room designer and the selection spine *(part-delivered)*

**Delivered:**

- **The room.** Drawn as a polygon on a grid, in millimetres, snapping to 50mm. Every wall shows
  its length live while you drag it. The area is calculated from the shape every time it is read
  and never stored, so it can never disagree with the drawing.
- **The 3D view.** Same room, same products, one shared state - dragging in the plan moves the
  box in 3D because there is only one model underneath. Products with no dimensions in the
  catalogue render at an obvious default size **and say so, by name**. A wrong-sized box that
  looks right is worse than one that admits it is a guess.
- **The Selection** - the spine everything hangs off. It belongs to exactly one owner, either a
  CRM user or a contact, enforced by the database rather than by convention. Lines carry a
  product and a quantity. A product that is later discontinued **stays on the selection, flagged,
  and is left out of the total** - dropping it would edit somebody's basket behind their back;
  including it in the total would be a promise we cannot keep.
- **Designs persist.** A design reopens after a reload, and "New design" starts a fresh one
  without deleting the saved work.
- **The contact-to-customer link.** Previously missing, and named in the plan as the thing
  blocking S4: nothing connected a WhatsApp contact to the customer account they buy under. Now
  it exists, per company, and it **refuses to guess** - if a contact is linked to two accounts
  with no primary chosen, the system returns nothing and asks a human rather than inventing an
  answer that looks like data. Phone-number matching only ever **proposes**; a person confirms.

**Not delivered, deliberately:**

- **The quote handoff.** There is no Quote entity anywhere in the CRM today, and no pipeline for
  one to appear in. Creating one means deciding numbering, ownership, expiry, approval and how
  it converts to an order - a real commercial design conversation, not something to invent at
  the end of another slice. **This is the top item for product to weigh in on.** The Selection is
  built so that once the shape is agreed, generating a quote is reading one record.
- **Floor-plan upload with wall detection.** Drawing works today, which is the path that must
  always exist. Upload is an accelerator on top.

---

## 6. What a PM should know about quality

- **Tests are written before the code** for anything with rules in it - room geometry, price
  splitting, collection membership, the selection rules. Twenty-four of those were written and
  confirmed **failing** before the feature existed.
- Current state: **1,323 frontend unit tests**, **26 browser tests** driving the real
  application against the real API, **230 backend tests** for this area. All green.
- Every browser test navigates **through the sidebar**, never straight to a URL, so a broken or
  mis-permissioned menu entry fails the test instead of hiding.
- Price assertions are made against the **server response**, never against what the screen shows,
  because a screen can be right for the wrong reason.
- The test suite now **deletes the data it creates**. It previously did not, and had left 213
  rows of test litter in the shared development database.

---

## 7. Open risks and decisions needed

| # | Item | Who decides | Impact if unresolved |
|---|------|-------------|----------------------|
| 1 | **Quote shape** - numbering, ownership, expiry, approval, conversion to order | Product + commercial | S4 cannot finish; the journey stops one step before the payoff |
| 2 | **Consumer cannot order directly** - a consumer confirming sends a request to the dealer, never an order. Assumed, needs confirming | Commercial | Rework if wrong |
| 3 | **Merge is blocked** behind the multi-company work | Engineering | Delivered work sits unmerged and drifts |
| 4 | **PDF export has never run in a production container** - verified on a developer machine only | Engineering | Export could fail on first real deploy |
| 5 | **Library collections cannot be edited from the library list** - only created from inside a page, which undercuts the "edit once, every page follows" promise | Product priority call | Feature is weaker than advertised |
| 6 | **Photoreal rendering** - boxes today. Is that sellable? | Product + sales | Determines whether a model pipeline gets funded |

---

## 8. What a dealer will see on day one

1. Open the catalogue from the sidebar; it is the pages Sorento's marketing team published, at
   their prices.
2. Pick products, or start the room designer cold.
3. Draw the room by dragging four corners into shape, wall lengths updating as they drag.
4. Watch the chosen products appear as correctly-sized boxes and move them around, in plan or in
   3D.
5. Read a summary with quantities, prices at **their** price level, room area, and a total.
6. Save it, reopen it tomorrow, or export the catalogue as a PDF to send on.

Step 7 - turning it into a quote - is the piece awaiting the decision in §7.1.

---

## 9. Glossary

| Term | Means |
|------|-------|
| **Page** | A catalogue document built from blocks. Has versions; one may be published. |
| **Version** | An immutable snapshot of a page. Never edited, never overwritten. |
| **Label** | A movable pointer (`published`, `staging`) at a version. Publishing moves a label. |
| **Collection** | A named set of products, defined by a rule, by hand, or both. |
| **Bundle** | Several products sold under one price, split back across the parts. |
| **Tile design** | What a product tile displays, chosen from a safe whitelist. |
| **Selection** | What one person chose: products and quantities. Never prices. |
| **Room** | An outline in millimetres plus where each product stands. |
| **Proposal** | Something the system suggests and a human confirms. Never applied on its own. |
| **Viewer** | Who is reading right now. Decides which prices exist in the response. |
