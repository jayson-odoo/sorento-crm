# UAC - Product Sets

> Given/When/Then contract for product sets: a Sorento-owned code that names a two-piece
> assembly and resolves to the real SKUs it is made of.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.
> Plan: `PLAN-product-sets.md`.

**Slug:** `product-sets` · **Domain:** master-data
**Classification:** CORE, schema `public`, normal FKs. Products and how they are named are a
base-platform capability; the WhatsApp resolver and the external linking API are always on and
are not module-gated, so a set cannot live behind a module guard.
**Status:** ACCEPTED - captain sign-off 2026-08-23 via Lavish review. This file is the contract.
Implementation progress is tracked in the plan's Status line, not here.

## Problem

A two-piece water closet is sold as one thing and stocked as three. The flyer prints
`SRTWC8608-RL`. The catalogue holds only the parts:

```
SRTWCX8608-RL   SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)   1180.00
SRTWCY8608      SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)        0.00
SRTWC8608-SC    SORENTO SRTWC8608-SC SEAT COVER ONLY               85.00
```

No `SRTWC8608-RL` row exists. Two things break as a result:

1. A customer asks `check stock SRTWC8608-RL` on WhatsApp. `entity_resolver._probe_product`
   is an exact match on `product_code`, so it finds nothing and the bot answers that the
   product does not exist.
2. n8n reads that flyer and calls the external product-attachment and promotion link APIs with
   the same code. Neither resolves it, so the document is never linked to anything.

Measured on the live catalogue copy: 47 two-piece families, 23 of them with no bare code at
all, across roughly 338 role-bearing SKUs (X 164, Y 105, SC 45, FT 21, PS 3). Both companies,
SRT and MOCHA, carry the same codes.

## Journey

**Actor: the product executive who owns master data.** Arrives because the flyer for
`SRTWC8608-RL` exists, customers ask for that code, and the system answers nothing.

1. Opens **Master Data Management > Product Sets**. The empty state says none exist yet and
   offers two ways in.
2. Clicks **Propose from catalogue**. The system scans for role-infix families and shows
   candidates already filled in: set code, members, each member's current list price. Nothing
   is typed.
3. Reviews a candidate. Three decisions only: keep or discard, adjust membership, tick which
   members set the price. Everything else is derived from what the catalogue already holds.
4. Saves. The set is live immediately.
5. The manual path exists for the odd one out: type a code, pick members, and the system still
   pre-fills candidates by matching the number.

Downstream, nobody decides anything:

- **A customer on WhatsApp** asks `check stock SRTWC8608-RL`. It resolves as one product set
  carrying its three members, each with its own stock, plus a complete-sets figure.
- **A flyer upload** goes to resources, n8n reads it and calls the external link API with
  `SRTWC8608-RL`. The link fans out to all three members and records that the set created it.
- **A promotion** posted by n8n naming the same code expands the same way.

The executive never types a member code, never types a price. Both are derived.

## Settled decisions

Every one of these came out of the grill and is binding on the plan.

| id | decision |
| --- | --- |
| D1 | A **Product Set** is a new core concept, NOT the dealer-kit `Bundle`. A Bundle has no code and *is* an authored price; a set is a code first and its price is derived. The existing `product_set_service.py` (a spec predicate filter, misnamed) is renamed to free the name. |
| D2 | A set is **not orderable**. No order-line explosion, no overlap with the Project Sales set-explosion engine (`project_so_draft_service.py`, D10 there). |
| D3 | A set code resolves to **one entity**, `entity_type: "product_set"`, carrying its members inside its display block. Not a fan-out of member products. This is an additive change to the frozen `/references/resolve` contract and must be coordinated with `sorento-crm-n8n-60`. |
| D4 | Members carry **no role column**. A member is a product, a quantity, a contributes-to-price tick and a sort order. Role earned nothing: price basis is the tick, complete-sets needs quantity, FT inclusion is just membership, labels come free from the product description. |
| D5 | Set price is **computed**: `SUM(member.list_price * qty) WHERE contributes_to_price`. A nullable override wins when set and renders as an override. |
| D6 | Stock answers **per member first**, plus a derived complete-sets figure and the name of the member that limits it. Never a bare zero while stock sits in the warehouse. |
| D7 | Price never appears in a stock answer. A price question is answered by the price path, which returns the set price and does not fan out. |
| D8 | A discontinued member does **not** end the set. The member is flagged, complete sets reads 0, the reason is named. |
| D9 | Sets are **company-scoped** (`CompanyScopedMixin`). Roughly 94 rows for 47 families across SRT and MOCHA. |
| D10 | Link fan-out records provenance: `linked_via_set_id` on the link row, so a link created by a set can be found and cleaned up when membership changes. |
| D11 | `product_attachments` and `promotions` resolve codes through **one shared helper**. They diverge today (substring versus exact) and that is a live defect independent of sets. |
| D12 | Sets get their own listing and detail page, and a **Sets** section on product detail linking by code. They do NOT appear in the products DataGrid, and no new MCP tool is added. |
| D13 | Resolving a member code alone does **not** name its parent sets. A dealer asking for a cistern wants the cistern. |
| D14 | Seeding runs through the existing proposal-and-review shape (stored batches, grouped review, tick to apply), never an unattended script. |

## Out of scope

- Ordering a set, quoting a set, or exploding a set onto an order line (D2).
- `FT` fitting membership. The model permits it; no set ships with one.
- Backfilling `item_packages`. That table stays the AutoCount mirror it is, read-only and
  owned by ingest.
- Any change to the Project Sales set-explosion engine.

---

# Phase 1 - frontend against mocks

## Group A - authoring

- **AC-A.1** `[FE]` Given no sets exist, when the executive opens Master Data Management >
  Product Sets, then the empty state names what a set is in one line and offers both **Add
  set** and **Propose from catalogue**.
- **AC-A.2** `[FE]` Given the listing has rows, when it renders, then it is a DataGrid with
  `tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`,
  explicit `size` per column, and long text truncated with a `title`.
- **AC-A.3** `[FE]` Given the executive clicks **Add set**, when the modal opens, then it asks
  for a set code and a name, and every optional select is clearable and searchable.
- **AC-A.4** `[FE]` Given a set is open for edit, when members are added, then each member row
  shows product code, description, list price, a quantity input defaulting to 1, a
  contributes-to-price tick, and a drag handle for sort order.
- **AC-A.5** `[FE]` Given the executive removes a member, then a confirmation dialog appears
  first (`ConfirmDeleteDialog`, never `confirm()`), because detaching is a destructive action.
- **AC-A.6** `[FE]` Given a set is deleted, when the executive confirms, then it is a hard
  delete behind an `AlertDialog`, and member products are untouched.
- **AC-A.7** `[FE]` Given the set detail page, when it renders in view mode and then in edit
  mode, then both show the same sections in the same order and editing swaps a read-only value
  for an input in place. Read-only metadata (code, company, created) lives in the header.
- **AC-A.8** `[FE]` Given the set detail page, when viewed at 375px and at 1280px, then no
  section clips and no horizontal page scroll appears.
- **AC-A.9** `[FE]` Given a set with no members, when the detail page renders, then the members
  section shows an explicit empty state with a next-step CTA, not a blank panel.
- **AC-A.10** `[FE]` Given the set detail page, when it renders, then it carries prev/next
  record navigation (`components/common/RecordNavigation`).

## Group B - price, on the mock

- **AC-B.1** `[FE]` Given two members are ticked as contributing, when their prices are 1180
  and 85, then the header shows a computed set price of 1265.
- **AC-B.2** `[FE]` Given an override is set to 1180, when the header renders, then it shows
  1180 with an explicit override badge naming who set it, and the computed figure remains
  visible for comparison.
- **AC-B.3** `[FE]` Given the override is cleared, when the header re-renders, then it falls
  back to the computed figure and the badge disappears.
- **AC-B.4** `[FE]` Given no member is ticked, when the header renders, then the price reads as
  absent with a reason, never as 0.00. A price of zero and a missing price are different facts.

---

# Phase 2 - backend, test first

## Group C - model and scope

- **AC-C.1** `[BE][T]` Given the migration runs on a database built by `create_all`, then
  `product_sets` and `product_set_members` exist with explicit `op.create_table`, because
  new-module tables are absent on legacy create_all databases.
- **AC-C.2** `[BE][T]` Given a set code already exists for SRT, when the same code is created
  for MOCHA, then it succeeds. Uniqueness is per company, not global.
- **AC-C.3** `[BE][T]` Given a user scoped to MOCHA, when they list sets, then SRT's sets are
  absent, and the filter is fail-closed rather than absent.
- **AC-C.4** `[BE][T]` Given a set member points at a product, when that product is deleted,
  then the delete is refused (`RESTRICT`). A set must never hold a dangling member.
- **AC-C.5** `[BE][T]` Given a set is deleted, then its member rows go with it (`CASCADE`) and
  no product is affected.
- **AC-C.6** `[BE][T]` Given a product appears in two sets, when both are read, then both list
  it. Membership is many-to-many; `SRTWCY8608` belongs to both the S-trap and P-trap sets.
- **AC-C.7** `[BE][T]` Given a member quantity of 2, when it is stored, then it round-trips as
  `Numeric`, never coerced to an integer.

## Group D - price

- **AC-D.1** `[BE][T]` Given members priced 1180, 0 and 85 with only the first ticked, when the
  set price is computed, then it is 1180.
- **AC-D.2** `[BE][T]` Given the cistern and the seat cover are ticked instead, when the set
  price is computed, then it is the sum of those two, and the pedestal's 1180 is excluded.
- **AC-D.3** `[BE][T]` Given a ticked member with quantity 2, when the set price is computed,
  then that member contributes twice its list price.
- **AC-D.4** `[BE][T]` Given an override is set, when the set is read, then the override is the
  price and the computed figure is still returned alongside it, so the FE can show both.
- **AC-D.5** `[BE][T]` Given a member's `list_price` changes, when the set is read again, then
  the computed price has followed it. The price is derived at read time, never stored.
- **AC-D.6** `[BE][T]` Given a set is serialised for the API, when the response is built, then
  the computed price, the override and the resolved price are all present. Assert each field
  explicitly, because `response_model` silently drops undeclared fields.

## Group E - resolve and stock

- **AC-E.1** `[BE][T]` Given the set `SRTWC8608-RL` exists, when `/references/resolve` is
  called with that token, then exactly one entity comes back with
  `entity_type: "product_set"`, `canonical_code: "SRTWC8608-RL"`, and its three members inside
  the display block. Not three top-level entities.
- **AC-E.2** `[BE][T]` Given a set token, when the response is built, then each member carries
  its product code, description, quantity and its own stock figure.
- **AC-E.3** `[BE][T]` Given member stock of 40, 12 and 0, when the set is resolved, then
  complete sets reads 0 and the limiting member is named.
- **AC-E.4** `[BE][T]` Given member stock of 40, 12 and 7 with all quantities 1, then complete
  sets reads 7.
- **AC-E.5** `[BE][T]` Given a member with quantity 2 and stock 7, when complete sets is
  derived, then that member contributes `floor(7 / 2) = 3`.
- **AC-E.6** `[BE][T]` Given a member is discontinued, when the set is resolved, then the set
  still resolves, the member is flagged discontinued, complete sets reads 0, and the reason
  names the member.
- **AC-E.7** `[BE][T]` Given the member code `SRTWCY8608` alone, when it is resolved, then it
  resolves as an ordinary product and the response does NOT name its parent sets (D13).
- **AC-E.8** `[BE][T]` Given a user scoped to MOCHA, when they resolve `SRTWC8608-RL`, then
  they get MOCHA's set and MOCHA's members, never SRT's.
- **AC-E.9** `[BE][T]` Given a stock question, when the set resolves, then no price appears in
  the response (D7).
- **AC-E.10** `[BE][T]` Given the resolver probes run ORM-only, when a set leg executes, then
  it goes through the ORM so `do_orm_execute` injects company isolation. Raw `text()` bypasses
  the listener entirely and is forbidden here.

## Group F - shared code resolution and link fan-out

- **AC-F.1** `[BE][T]` Given the shared helper, when `product_attachments` and `promotions`
  both resolve the same code, then they return the same product ids. One helper, one
  behaviour.
- **AC-F.2** `[BE][T]` Given the set code `SRTWC8608-RL`, when an attachment is linked through
  the external API, then rows are created for all three members.
- **AC-F.3** `[BE][T]` Given that fan-out, when each link row is written, then it carries
  `linked_via_set_id` naming the set that created it.
- **AC-F.4** `[BE][T]` Given a link created manually rather than by a set, then
  `linked_via_set_id` is null. Provenance distinguishes the two.
- **AC-F.5** `[BE][T]` Given a promotion payload naming a set code, when it is created, then it
  links every member, where today it links nothing.
- **AC-F.6** `[BE][T]` Given a code that names no set and no product, when it is resolved, then
  it is reported as unmatched rather than silently dropped.
- **AC-F.7** `[BE][T]` Given a plain product code that is not a set, when either path resolves
  it, then behaviour is unchanged from today for attachments, and promotions gain substring
  matching. This is a deliberate behaviour change and ships with its own evidence run.
- **AC-F.8** `[BE][T]` Given an attachment pinned to one company, when a set code resolves,
  then only that company's members are linked. A same-coded set in the other company never
  resolves.

## Group G - product detail surface

- **AC-G.1** `[BE][T]` Given a product belongs to sets, when the product detail response is
  built, then it carries those sets by code and name. Assert the field explicitly.
- **AC-G.2** `[FE]` Given `SRTWCY8608`, which belongs to two sets, when its detail page
  renders, then a **Sets** section lists both, each a link to the set, addressed by code and
  never by UUID.
- **AC-G.3** `[FE]` Given a product in no set, when its detail page renders, then the Sets
  section shows an explicit empty state rather than being hidden.

## Group H - seeding

- **AC-H.1** `[BE][T]` Given the catalogue, when the proposal pass runs, then it groups
  role-infix families and proposes one set per trap variant, and it writes nothing.
- **AC-H.2** `[FE]` Given proposals exist, when the executive reviews them, then each shows the
  proposed code, its members with current prices, and a tick to accept, matching the flyer-spec
  proposal shape already in the repo.
- **AC-H.3** `[BE][T]` Given a proposal is accepted, when it is applied, then the set and its
  members are created for that company only, and re-running the proposal pass does not
  re-propose it.
- **AC-H.4** `[BE][T]` Given the seeding pass, when it runs against both companies, then it
  produces a set per company and never mixes members across them.

---

# Phase 3 - evidence

- **AC-I.1** `[E2E]` A recorded agent-browser run, navigating by sidebar clicks from `/`, never
  a deep URL: create a set, add three members, tick the price basis, save, open the product
  detail of a member and follow the Sets link back. Console and errors clean.
- **AC-I.2** `[E2E]` The same run repeated at 375px, confirming AC-A.8.
- **AC-I.3** `[T]` A live resolve of `SRTWC8608-RL` against the running stack returning the set
  with three members and a complete-sets figure, captured before the n8n contract conversation.
- **AC-I.4** No new Playwright spec is added, per the standing order. The recorded
  agent-browser evidence run stands in.

## Definition of Done

1. Mock swapped for the real call, verified showing real data.
2. Existing rows backfilled: the 47 families proposed and reviewed, both companies.
3. New permissions granted to provisioned roles.
4. Every new column reaching the FE is present in **both** manual dict builders.
5. Verified from the executive's own path: real sidebar clicks, real data, 375px and 1280px.
6. `sorento-crm-n8n-60` has the `product_set` contract in writing, and has confirmed, before
   S3 deploys.
