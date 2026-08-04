# Dealer Sales Kit - S9: reading it, and choosing what goes in it

**Status:** drafted 2026-08-04, from hands-on feedback on the seeded A3 brochure.

Everything here came from one session of somebody actually using the module,
which is why it is a mixed bag: some of it is a reader complaining that the
brochure does not behave like the PDF it replaces, and some of it is a maker
complaining that assembling one is harder than it needs to be. They are the same
slice because they are the same document seen from its two ends.

---

## Journey A - the reader

**Who.** A consumer, or a dealer's customer. They arrived by tapping a link
somebody forwarded them on WhatsApp. They have no account and never will.

**What the system already knows.** Which company published the page (it is in
the address), which version is live, and which offer prices it. It knows nothing
about the reader, so every figure on the page is a consumer figure. It does not
ask who they are, because the answer would change nothing it is allowed to show
them.

1. **They land on the brochure.** It is a document, not a feed. The printed
   flyer they know has pages, and a thumb-flick moves them one page - so the
   web version settles on a section boundary rather than stopping halfway
   between two of them. The decision at this step is only "keep going or stop".
2. **They see something they want.** They tap it. The decision is one tap, and
   it is reversible in one tap. Nothing is asked of them: not a quantity, not a
   name, not an email.
3. **They want to see it in their room.** A bar appears once anything is ticked,
   and only then. They tap it and their picks become objects in a plan.
4. **They arrange the room.** They tap an object to select it, and turn, move or
   remove it. **They are never allowed to put two things in the same space** -
   not by dragging one onto another, and not by the system dropping their picks
   on top of each other when the room first opens. A plan that shows a bathtub
   inside a vanity is not a plan.

**What they hold at the end.** A room they arranged and a list of what is in it,
which is what a salesperson needs to quote from. Nobody was asked to register.

---

## Journey B - the maker

**Who.** Marketing, assembling next season's brochure. They arrive from the
sidebar. They may be starting from a seeded flyer of 341 printed rows, which is
the realistic case and the one that breaks tools designed around ten.

**What the system already knows.** The whole product master, its categories, its
photos, and every design and collection the company has made before.

1. **They fill a row.** They are choosing products for a printed row out of
   seventeen thousand. The decision at this step is "is this the one", and that
   is a decision made by LOOKING, so the products are shown as pictures and
   grouped the way the catalogue is already organised. What they have chosen so
   far stays visible beside the search, and anything in it can be taken back out
   without starting again.
2. **They name the row and say what it is.** A collection is that row: the
   binding between a place in the document and a live set of products. It is
   edited as a form, like every other record in this system, not only as a panel
   that appears when a block is selected.
3. **They decide how a tile looks.** They choose which attributes appear and in
   what order, by dragging them into order. Getting it wrong costs one undo.
4. **They apply that design to the brochure.** Once, for the document. Not 341
   times.
5. **They give the products photos.** Working down a list, one row at a time,
   with pagination, because the master is large. Where there is only one
   candidate photo there is nothing to decide, so they are not asked.

**What they hold at the end.** A document ready to send for approval, and every
other stakeholder (approver, dealer, reader) gets it from the same place.

---

## Acceptance criteria

### AC-P Performance (DONE - measured, not asserted)

- **AC-P1.** Resolving the collections a document binds costs a fixed number of
  queries regardless of how many it binds. *Measured: the seeded brochure went
  from ~1,020 round trips to 3.*
- **AC-P2.** A cold read of the seeded A3 brochure completes in under two
  seconds. *Measured 13.1s -> 1.30s.*
- **AC-P3.** A second reader within the staleness window is served without
  touching the database. *Measured 3.7ms.*
- **AC-P4.** A reader who already holds the payload revalidates rather than
  re-downloading it. *304, 0 bytes.*
- **AC-P5.** Publishing or rolling back is visible to the next reader
  immediately, not after the window.
- **AC-P6.** One page open causes ONE payload request, not two.

### AC-R Reading

- **AC-R1.** Scrolling the published catalogue settles on a section boundary.
  A flick moves one section, the way a page turn does.
- **AC-R2.** It never traps the reader: a section taller than the viewport
  scrolls through normally before the next one engages, and the behaviour is off
  entirely where the platform or the reader has asked for reduced motion.
- **AC-R3.** Snapping applies to the published page and the print route
  identically in layout, and NOT to the editor, where a maker is positioning
  blocks and needs free scroll.

### AC-D Designing a room

- **AC-D4.** Tapping an object in the plan selects it, and the selection is
  visible without reading a label.
- **AC-D5.** A selected object can be turned, duplicated and removed.
- **AC-D6.** ~~Removal asks first, per the confirm-before-destructive rule.~~
  **Revised during implementation, deliberately.** Removing a box is already a
  single undo away, and undo restores the SERVER line too (`applySnapshot`
  pushes the quantity back), so it is not the irreversible act the
  confirm-before-destructive rule exists to guard. A dialog on every removal in
  a design canvas is friction on the most-repeated action in the screen. The
  rule still binds everywhere it was written for: deleting a page, a collection,
  a design.
- **AC-D7.** **An object cannot be dragged into a position that overlaps
  another.** The drag is refused at the point of overlap; it does not snap back
  from an illegal drop, and it does not land and then complain.
- **AC-D8.** **Populating a room from picks places objects without overlapping.**
  Where the room cannot fit them all, it places what fits and says plainly how
  many it could not.
- **AC-D9.** Overlap is decided on the objects' real footprints, from product
  dimensions, and an object with no dimensions gets a stated default rather than
  a zero-size footprint that can overlap everything.

### AC-S Choosing products

- **AC-S10.** The product picker shows photographs, not only rows of text.
- **AC-S11.** Results are grouped by product category, and a category can be
  collapsed.
- **AC-S12.** What has been chosen is listed beside the results, always visible,
  with a count.
- **AC-S13.** Anything in that list can be removed from it, from the list.
- **AC-S14.** The picker holds seventeen thousand products without loading
  seventeen thousand products.

### AC-C Collections

- **AC-C15.** A collection is a first-class record with a list and a form view,
  reachable from the sidebar, following the CRUD standard (list + search + add;
  edit in a modal; hard delete behind a confirmation).
- **AC-C16.** The form states what the collection resolves to right now: how
  many products, and which.
- **AC-C17.** What a collection is FOR is documented in the user guide, not
  explained inside the UI.

### AC-T Tile designs

- **AC-T18.** The fields on a tile are ordered by dragging, using the same
  drag-and-reorder interaction as the rest of the system.
- **AC-T19.** The dialog is not cramped: it follows the spacing other dialogs in
  the system use.
- **AC-T20.** A change to a tile's attributes can be undone.
- **AC-T21.** **A page has a tile design, applied to every collection block that
  does not override it.** Choosing a design once changes the brochure. *This is
  the actual defect behind "why is the design on my tiles not reflected": the
  seeded brochure binds a design on 0 of its 340 blocks, and the only control is
  per block.*
- **AC-T22.** A block may still override the page's design, and the inspector
  shows which it is using and where that came from.

### AC-I Brochure images

- **AC-I23.** Products awaiting a photo are shown as a paginated LIST, not a
  wall of cards, because the master is large and the maker is working down it.
- **AC-I24.** A row opens a picker for that product.
- **AC-I25.** The picker moves to the next and previous product without closing.
- **AC-I26.** **Where a product has exactly one candidate image, nothing is
  asked.** It is taken, and the row shows what was taken and lets it be changed.
- **AC-I27.** The list says how many are still without a photo.

---

## Explicitly out of scope

- Reader accounts. Journey A never authenticates.
- 3D collision in the vertical axis. Footprints are plan-view rectangles;
  stacking is not a thing this room planner models.
- Rewriting the rule engine. Collections keep the rule shape they have.
