# CONTEXT - Sorento CRM glossary

Ubiquitous language for this codebase. Glossary only - no implementation detail, no specs.
When a term here conflicts with how you're about to use a word, the glossary wins or the
glossary changes. Nothing in between.

---

## Project Sales (module: `projects`)

### Project
A **pursuit of a single property development** by one company, from registration through to
a won purchase order. Not a delivery/execution container - nothing is built or scheduled
against it. A Project exists from the moment a salesperson claims the development, long
before any money moves.

> ⚠ **Conflicts with `ecohub-nextjs`.** There, `Project` is a *post-sale execution container*
> (tasks, gantt, handover checklist, expenses, service jobs) that sits downstream of
> `Lead → Quotation → SalesOrder`. The structural analogue of a Sorento **Project** is an
> ecohub **`Lead`**. Do not port ecohub's project tabs.

Company-scoped: a Project belongs to exactly one company (SRT or MOCHA). The same physical
development pursued by both entities is two Projects.

### Project Type
A configurable category of Project - property development, hotel, commercial fitout,
renovation, institutional. Not every Project is a property development; roughly half the
project names already in the system are fitouts and renovations. Type decides which fields
are required and how delivery timing is derived: developments infer it from launch date plus
a lag, everything else states an explicit delivery window.

### Project Template
A reusable preset belonging to a Project Type. It owns the configurable defaults: the
Stakeholder roles available, and optionally its own status graph. A Project is created *from*
a template. Same concept as `dreamz_ems`'s `project_templates` - where an **Event** is simply
a Project of a different type, and the UI renames it via terminology. This module is shaped
so EMS and Sorento can share it.

### Project Task
A unit of work on one Project, carrying an assignee and a due date. A Project Template ships a
default checklist of them, so registering a development lays out the work rather than leaving a
blank page.

Two **independent** axes, which must not be collapsed into one field:

- **Task phase** - `pursuit` (the sales actions needed to win: visit the architect, submit the
  quotation, deliver the sample, chase the PO) or `delivery` (post-win execution).
- **Task category** - the work-stream a task belongs to (Spec-in, Sampling, Commercial,
  Logistics), supplied by the template. This is what the Tasks board **groups by**, in
  collapsible sections, with each task showing its own status. Same meaning as ecohub's
  `category`.

**Escalate** and **Stuck** are statuses that cannot be set without their context: escalating
requires naming the person escalated to, and going stuck requires a reason. Both then render on
the task itself - a status without its reason is useless to whoever reads it next.

A Project's **next action** is the due date of its earliest open Task - derived, never stored.
There is no separate committed-follow-up field; two records of the same promise would drift.

### Status graph inheritance
The `project` entity carries a **default** status graph. A Template may **override** it, at
which point that template gets its own forked graph; templates that never override keep
inheriting the default. Cross-template reporting groups by a status's `category`, never by
status id - so `category` is mandatory on every status.

### Lead
An **unqualified sighting** of a possible project - a salesperson hears about a development
from an architect, an info provider, or a WhatsApp thread. Cheap to record and deliberately
**not exclusive**: several people may hear the same rumour, and racing to lodge hearsay would
be worse than racing to register. A Lead is tied to a **Customer** (the dealer or account it
came through) and may name a developer before one is confirmed.

Qualifying a Lead runs the fuzzy clash check and creates a **Project** - that conversion is
the moment ownership locks. A Lead may produce more than one Project. Leads carry their own
qualified / disqualified outcome, which is what makes "we hear about 40 and pursue 12"
measurable - the top of the funnel that today lives only in WhatsApp.

> Not the same as ecohub's `Lead`, which is a B2C enquiry from a homeowner about one property,
> carrying budget range and an assigned designer.

### Registration
The act of claiming a Project. Exclusive: within a company, one development = one Project.
Identity is **Developer + fuzzy-matched title**, with Location as tiebreak. A second
salesperson attempting to register a colliding development is **blocked**, shown the
incumbent (owner, stage, last activity), and offered *request to join* or *dispute*.

### Developer
The parent property group pursuing the development - SP Setia, Gamuda, Pavilion. A
**Project Party**. Usually never buys anything; the money arrives from a Main Contractor
or Trading House.

### Registered company (SPV)
The legal entity actually registered for one specific development - typically a
project-specific special-purpose vehicle, distinct from the Developer parent. Usually
unknown at Registration and surfaces around PO time.

### Project Party
An **organisation master record**, reusable across many Projects, typed as one of
developer / architect / main contractor / trading house / consultant. Reusable identity is
the point: it is what makes "which architects should we prioritise visiting" and "which
developers convert best" answerable. Optionally bridged to a `customers` row once that
party actually issues a purchase order - until then it is not a customer.

### The cast, and which way value flows

Two different flows run through every project, and confusing them is the classic mistake:
**influence** decides *whose product gets specified*, **money** decides *who we invoice*. The
party who approves the brand is almost never the party who pays for it.

| Party | What they do | Do they pay us? |
|---|---|---|
| **Us** (the principal) | Supply the sanitary ware, across all brands carried | - |
| **Developer** | Owns the development (SP Setia, Gamuda, Pavilion). Approves the specification, usually on consultants' advice. Requests **Sponsorship** into their showroom | Almost never |
| **Registered company (SPV)** | The legal entity for one specific development, typically project-specific | No - an identity, not a buyer |
| **Architect / consultant** | **Specifies** the product. The entire "spec-in" effort targets them. Pure influence, zero money - which is exactly why they must not live in `customers` | Never |
| **Main contractor** | Wins the construction tender and buys materials to build. **May issue the PO directly** | Sometimes |
| **Trading house** | An appointed intermediary trading company: it buys from us and resells to the main contractor | **Usually - and preferred** |
| **Dealer / customer** | An existing trading account business is routed through (1 Living Depot, DBI Concept Design) | Yes |

### Trading house
An intermediary appointed to sit between us and the main contractor: **we invoice the trading
house, the trading house invoices the contractor.** We prefer it, for two reasons the client
states directly - it *"keeps the principal out of direct contractor dealings"* (no chasing
site progress claims, retentions or variation disputes) and it *"reduces finance
exposure"* (construction contractors are a long-payment, higher-default counterparty; the
trading house absorbs that credit risk).

So the same physical product can be specified by an architect, approved by a developer, built
in by a contractor, and paid for by a trading house - four parties, one project. This is why
`po_source` is `contractor direct | trading house`, why the issuing party is recorded
separately from whoever was quoted, and why **PO source need not tally with the quotation**:
we quote whoever will listen and invoice whoever is appointed.

### Project Stakeholder
A **person on one Project**, with the role they play *on that Project*: decision maker,
influencer, info provider, architect. The same person is a decision maker on one tender and
an influencer on the next, so the role belongs to the pairing, never to the person. There is
no global person master - stakeholders are recorded per Project. Optionally linked to a
Project Party (their firm); a stakeholder with no firm is valid.

### Info provider
A Project Stakeholder role. Someone inside the developer or contractor feeding tender
intelligence to the salesperson. Carries no special visibility rules - visible to anyone who
can see the Project.

### Brand
One of the manufacturer brands the company carries (Sorento, Mocha, Cabana, Iborn, Bravat,
…). The existing `brands` reference data, company-scoped. A Project records which brands are
being pushed into it. Note: **Mocha is both a Brand carried by the SRT company and a separate
Company** - the two are unrelated uses of the name.

### Quotation
A priced scope of supply offered into one Project - House Units, Common Area / Facilities,
Showroom. A Project has many. Spec-in and pricing are the same act: specs are submitted with
prices, so there is no separate "spec" artifact.

Outcome lives here, not on the Project: each Quotation is open, won, or lost, and a lost one
carries a loss reason. **The Project's outcome is derived** - Won if any Quotation is won,
Lost only when all are lost, otherwise Open. Winning the house units while losing the common
area is the normal case, not an edge case.

### Outcome vs Status
Two different axes, never to be conflated. **Status** is a funnel position describing what has
happened - its terminal rung is **"PO Received"**, deliberately *not* "Won", because a project
can receive a PO for one scope while another scope is still being quoted. **Outcome** is the
commercial result, derived from Quotations. Every metric - conversion rate, win/loss, loss
reasons - reads outcome. Nothing reads status.

### Quotation Version
A numbered revision of a Quotation. The current version is the highest-numbered one - there is
no "current" flag and no "frozen" flag, because a second record of the same fact drifts. The
current version is editable and every save is audit-trailed; **Revise** freezes it as it stands
and opens the next one.
Superseded versions are immutable, which is what makes "this is what we actually showed the
developer" provable. Sample Submissions and Project POs bind to a version, never to the
Quotation as a whole.

### Project PO
An **incoming** purchase order from a main contractor or trading house - the moment a
Quotation is won. Real money arriving.

> ⚠ Not the same thing as `purchase_orders`, which is the **outgoing** SCM supply PO issued
> to a supplier and is wired into on-order supply maths. A Project PO lives in
> `projects.purchase_orders`. The UI says "PO" for both because that is the client's word;
> the tables must never merge. Same bare name, two schemas, two different things
> (ADR-0002, ADR-0011).

Validation against the bound Quotation Version: model must match, unit price must match the
initial quotation, quantity may differ freely, and the issuing party need not be whoever was
quoted. Mismatches are **flagged, not blocked**.

### Sample Submission
Physical product sent to the developer for approval, bound to a Quotation Version. No
sample, no realistic chance of winning. The Quotation is the source of truth: the quotation
is updated (and revised) first, then the matching samples go out.

### Sponsorship
Product given free into a developer's showroom or a mockup - a real cost, recorded against
the Project, repeatable, and not a pipeline step. Already exists in the system as a portal
form (`purchase_requests` with `request_type='sponsorship_form'`) submitted by Sorento's own
salespeople. Gains a link to a Project; the picker is enabled per contact so UAT and live
cohorts run on one form.

### Order Inquiry
One artefact seen twice. The **derived rows** are what purchasing is told to do, computed
from a published project sales order or an amendment to one. Never a second source of
demand: committed quantity stays on the sales order lines. **The sheet** is the Excel export
of those rows, which Joey edits and re-imports; it is that import, not the publish, which
creates core `sales_orders` rows carrying `demand_origin = 'scm_order_inquiry'`.

The loop is owned end to end by the Project Sales module (ADR 0010), despite the `scm_`
prefix on that stamp.

### Project Series
The set of `product_categories` nominated as standard for project sales. A Quotation line
outside it raises a **non-standard SKU** alert - the control on SKU proliferation. Coarse by
construction: a premium one-off inside a nominated category will not flag.

### Price Floor
The lowest acceptable unit price for a Quotation line. Configurable as either a percentage
of list price or an absolute amount, at **system, category, or product** level; the most
specific wins. Breaching it warns the salesperson and alerts management. The floor in force
at quote time is recorded on the line, so changing the policy never retro-flags old
quotations.

---

## Company vs Tenant

### Company
A legal selling entity - SRT (Sorento) or MOCHA. A partition *below* the tenant. Owned
business records carry `company_id` and are auto-filtered.

### Tenant
The install boundary for modules. Currently stubbed to a single default tenant.

---

## Core vs Module

### Core
A base-platform capability every install needs (auth, users, products, stock, orders).
Always present, never toggleable.

### Module
A capability a tenant installs and can turn off - an `app_modules_catalog` entry, a
`tenant_modules` enablement row, and a route guard. Enablement is the entire definition;
schema location is a separate decision.

---

## Dealer Sales Kit

### Dealer Sales Kit (the Kit)
The set of capabilities Sorento sells to its dealers. Nine **Packages** in the
vision: Brochure Generator, Stock Check, AI Design, Order Management, Warranty,
Display Rack, Product Knowledge, Extra Discount, Exhibition Request. The Kit is
one installable capability, not nine.

### Package
One sellable capability inside the Kit. A **Dealer** may hold some Packages and
not others. Distinct from a *module* (what a tenant installs) - the Kit is one
module; Packages are what a Dealer is entitled to within it.

### Dealer
A business that buys from Sorento and sells on to Consumers. A Dealer is a
**Customer** of Sorento - it is **not** a Company. Dealer staff reach the Kit as
Contacts, not as Users.

### Consumer (end user)
The Dealer's customer. Never buys from Sorento directly. Distinct from
**Customer**, which in this system always means Sorento's counterparty.

### Company
An operating entity Sorento runs (Sorento, Mocha) - an isolated data partition
with its own products, stock and customers. **A Dealer is never a Company.**
See ADR-0007.

### Designer
Whoever may build and publish **Pages**, **Tile Templates** and library
**Collections**. A capability, not a job title or an account type - grantable to
Sorento marketing staff today and to a Dealer later.

### Approver
Whoever may accept or reject a finished **Edition** before it goes live. Held by
someone other than the **Designer** who built it - an Edition nobody else has
looked at cannot go live. Approval is about the offer (products, combinations,
prices), not the layout.

### Assembler
Whoever may produce a **Brochure** from an existing Page without touching its
layout. The Dealer's normal role.

---

## Authoring

### Page
One publishable document: an ordered list of **Sections** plus a layout for each
breakpoint. A Page is *viewer-agnostic* - what a given reader sees (which
prices, which products) is resolved when it is read, not when it is written.
The same Page serves staff, Dealers and Consumers.

### Section
A full-width horizontal band of a Page, with its own background and padding, and
a grid inside it. Called a **zone** in earlier meeting notes - "Section" is the
term.

### Block
One placed thing inside a Section's grid: text, image, artboard, or a bound
product grid. Blocks occupy grid cells; they are never positioned in absolute
pixels.

### Tile Template
The design of a single product's card - image, name, code, price, badges,
certification icons, call to action. Authored once, reused by every bound
product grid. Called an **item** in earlier meeting notes.

### Artboard
A fixed-aspect Block inside which things *may* be freely positioned. The one
exception to grid placement, for hero and feature imagery.

### Asset
A reusable piece of artwork - logo, icon, decorative element - uploaded for use
in designs. Belongs to no product. Referenced by identity, never by filename, so
renaming a file cannot break a published Page.

### Badge
A mark rendered on a Tile from the **product's own data** - never placed by
hand. A product carries a certification because it holds a document of that
type; the artwork comes from the type. A Badge is therefore a claim about the
product, and showing the wrong one is a compliance failure, not a layout bug.

### Print Preview
The Page rendered at true paper geometry, showing where each page begins. It is
the same render that becomes the PDF - which is what makes its page breaks
trustworthy. The editing canvas never shows page breaks, because it is not at
paper width and would be guessing.

### Edition
The catalogue as published for a period - "2024", "2026 bathroom". An Edition is
produced by duplicating the previous one and revising it, so it accumulates
**Versions** as it is worked on, and goes live once. Editions succeed each other;
Versions accumulate inside one.

### Proposal
A change generated by the system that a person must accept before it takes
effect. AI re-spacing produces a Proposal; wall detection produces a Trace to
confirm. The system never rearranges a Designer's work silently - **the system
suggests, a person decides**, everywhere.

### Version / Label
A published Page is an immutable **Version**; going live moves a **Label** to
point at one. Same pattern as AI prompt versions and labels. Publishing moves a
pointer; it never edits a Version.

---

## Products and selling

### Collection
A curated, ordered set of products, defined by a rule plus manual pins and
exclusions. **Library** Collections are named and reusable; **page-scoped**
Collections are the ad-hoc set someone picked inside one editor session. A
page-scoped Collection can be promoted to a library one.

### Selection
The running list of products a person has chosen, carried across the whole
journey - browsing, designing, summarising, ordering. One Selection spans
brochure, design and checkout; it is never re-picked per step. An abandoned
Selection is a lead with a product list attached.

### Bundle
A named set of products sold together at its own price - "buy this set for RM X".
A Bundle is part of the catalogue, chosen like a product, but it **is not a
product**: it is never stocked, never costed and never sent to accounting. What
is ordered is always its components; the Bundle is the price and the name they
are shown under. It is available only while every component is, so losing one
component ends the Bundle rather than shrinking it.

A Bundle is **not** a **Discount Rule**: it has no code to enter, no usage limit
and no validity window. Where a Discount Rule reduces a price at checkout, a
Bundle *is* a price.

### Product Set
A code that names an assembly Sorento sells as one thing and stocks as several.
`SRTWC8608-RL` is printed on a flyer and asked for on WhatsApp, but the catalogue
holds only its parts: a pedestal, a cistern and a seat cover, each its own SKU.
The Set is that missing code.

Like a Bundle it is not a product, is never stocked or costed, and derives its
availability from its members. It differs from a Bundle on the two things that
matter: a Bundle **has no code** and *is* an authored price, while a Set is a
**code first** and its price is **derived** from whichever members are ticked as
contributing. A Set is also not orderable at all, where a Bundle is ordered
through its components.

Distinct again from an **item package** (the read-only AutoCount `PackageDTL`
mirror), which is what Project Sales explodes a PO SET line with. AutoCount owns
that one; Sorento owns this one.

### Brochure
One Assembler-produced instance: a Page, a page-scoped Collection, and cover
details. Shareable and exportable. Renders against the Page Version it was made
from, so a Brochure sent last month still looks the way it did.

### Quote
The priced document between a Dealer and a Consumer. Owned by the Dealer.
Carries the Dealer's own retail pricing - which is the Dealer's commercial
information, not Sorento's.

### Draft Order
A Dealer-to-Sorento order awaiting the Dealer's submission. This - not the
Quote - is what enters Sorento's order pipeline.

---

### Discount Rule (voucher)
A configured rule that reduces a price when its conditions hold - percentage,
fixed amount, or percentage with a cap - bounded by a validity window and a
usage limit. Distinct from a **Promotion**, which in this system means marketing
collateral and carries no pricing maths. Every redemption is recorded, never
counted.

### Warranty Registration
A Consumer's record that they bought a specific product on a specific date. Its
expiry is fixed when it is created - a later change to a product's warranty
period must never shorten a warranty someone already holds. A claim against it
becomes a **Complaint**; warranty does not run a parallel service pipeline.

Registering is never a precondition of being covered. Cover runs from the date of
purchase whether or not anyone registered, so lodging a Complaint creates the
Registration if it is missing. Registering early is worth doing because it is
proof and because a few products grant longer cover to those who do - not because
the unregistered are turned away.

### Warranty Term
**One promise Sorento makes about one part of one kind of product** - how long it
lasts, which defects it covers, and whether labour is included.

Cover attaches to the **part**, never the whole product: a water closet's ceramic
body, its flushing fittings and its seat-cover mechanism carry three different
promises that expire on three different dates. A term may run for a period or for
the product's lifetime, and may cover only certain defects (a lifetime ceramic
body covers cracking and leaking, nothing else).

Terms name a **kind** of product - a category, a named series, or a specific list
of models - never one product at a time.

Whether **installation is included** is part of the promise, and it is what
decides who pays for the visit. A part still under cover whose term excludes
installation means the part is free and the callout is not.

Replacing a part under warranty transfers the **remaining** cover to the new part.
It never starts a fresh one.

Terms are **versioned and dated**. A Complaint is always judged against the terms
in force on its date of purchase, so republishing the policy never changes what
someone already bought.

### Request
A dealer-submitted ask that a person decides on - an exhibition, a display rack,
support. Requests are **configured, not built**: they share one submission,
approval and SLA pipeline, and differ only by definition.

---

## After-sales

### Complaint
**One customer issue, start to finish** - the after-sales case. Raised once, no
matter how many visits, collections or replacements it takes to settle. It owns
the SLA clock, the conversation thread, the notifications and the one
satisfaction survey.

A Complaint is never subdivided into more Complaints. Work done to settle it
lives in its children (product lines, **Service Jobs**, linked delivery orders) - 
so one issue is always one row, one clock, one card on the submitter's portal,
one survey. A **Warranty Registration** claimed against becomes a Complaint; it
does not start a parallel pipeline.

Broader than the English word: a Complaint covers a chargeable out-of-warranty
service call and a dealer's wrong-model delivery just as much as a genuine
grievance.

### Submitter
**Whoever lodged the Complaint** - and the only party the system converses with
about it. Usually a salesperson or Customer Service transcribing what someone
else reported; sometimes the Dealer; sometimes the Consumer. The Submitter owns
the portal thread and receives every status update.

Distinct from the parties the Complaint is *about*. A Consumer is notified only
when they are themselves the Submitter.

### Service Job
**One scheduled attendance on one Complaint** - a technician, a time window, a
site, and photographic proof of what was done. A Complaint needing two visits has
two Service Jobs; a Complaint settled by shipping a replacement has none.

Deliberately free of after-sales vocabulary so it can be attached to whatever
requested it - a Complaint here, something else in another system.

### Site
**Where the work physically happens** - an address, and the person to call on
arrival. Belongs to the Complaint, not to a party: one Consumer may have several,
and the Dealer's shop is a Site as readily as a home.

### Technician
**Whoever attends a Service Job.** Not a system user and never given one - a
technician holds no CRM account, sees no listings, and reaches their own work
through the portal on their phone like any other outside party. Identified by the
phone they already message from.

### Warranty Product Kind
**The kind of thing the warranty policy talks about** - a water closet, a wash
basin, a sensor tap - which is not the same as the category a product is filed
under for selling. Selling categories split by brand and by buying pattern; the
policy splits by what the thing is and what can go wrong with it. **Warranty Terms
scope to a Kind**, so the same promise covers every model of that kind without
being restated per product.

A Kind is what a Consumer recognises. It is the level at which cover can be
decided even when the exact model is still unknown - which is why a claim can be
answered from a photograph before anyone has pinned down the variant.

---

## Space and design

### Space
The Consumer's actual room, as captured in the system. Arrives as a floor plan
image, a photo, or a drawn outline.

### Trace
The editable outline of walls, doors and windows over a Space. Automatic
detection *seeds* a Trace; a person always confirms it. Detection is never the
final word.

### Scale calibration
Binding pixels to real-world millimetres. Mandatory before a Space can be used - 
without it every downstream dimension, and therefore every Quote, is fiction.

### Proxy model
A dimensionally-correct box standing in for a product that has no 3D model,
sized from the product's real dimensions. Not a placeholder to be tolerated - 
the accurate thing, until a real model exists.

### Render
The saleable image. Produced by AI from the scene, not by the 3D engine. The 3D
scene carries *layout truth*; the Render carries *beauty*.
