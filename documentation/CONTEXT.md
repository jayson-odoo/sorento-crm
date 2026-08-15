# CONTEXT — Sorento CRM glossary

Ubiquitous language for this codebase. Glossary only — no implementation detail, no specs.
When a term here conflicts with how you're about to use a word, the glossary wins or the
glossary changes. Nothing in between.

---

## Project Sales (module: `projects`)

### Project
A **pursuit of a single property development** by one company, from registration through to
a won purchase order. Not a delivery/execution container — nothing is built or scheduled
against it. A Project exists from the moment a salesperson claims the development, long
before any money moves.

> ⚠ **Conflicts with `ecohub-nextjs`.** There, `Project` is a *post-sale execution container*
> (tasks, gantt, handover checklist, expenses, service jobs) that sits downstream of
> `Lead → Quotation → SalesOrder`. The structural analogue of a Sorento **Project** is an
> ecohub **`Lead`**. Do not port ecohub's project tabs.

Company-scoped: a Project belongs to exactly one company (SRT or MOCHA). The same physical
development pursued by both entities is two Projects.

### Project Type
A configurable category of Project — property development, hotel, commercial fitout,
renovation, institutional. Not every Project is a property development; roughly half the
project names already in the system are fitouts and renovations. Type decides which fields
are required and how delivery timing is derived: developments infer it from launch date plus
a lag, everything else states an explicit delivery window.

### Project Template
A reusable preset belonging to a Project Type. It owns the configurable defaults: the
Stakeholder roles available, and optionally its own status graph. A Project is created *from*
a template. Same concept as `dreamz_ems`'s `project_templates` — where an **Event** is simply
a Project of a different type, and the UI renames it via terminology. This module is shaped
so EMS and Sorento can share it.

### Project Task
A unit of work on one Project, carrying an assignee and a due date. Two categories:
**pursuit** (the sales actions needed to win — visit the architect, submit the quotation,
deliver the sample, chase the PO) and **delivery** (post-win execution). A Project Template
ships a default checklist of them, so registering a development lays out the work rather than
leaving a blank page.

A Project's **next action** is the due date of its earliest open Task — derived, never stored.
There is no separate committed-follow-up field; two records of the same promise would drift.

### Status graph inheritance
The `project` entity carries a **default** status graph. A Template may **override** it, at
which point that template gets its own forked graph; templates that never override keep
inheriting the default. Cross-template reporting groups by a status's `category`, never by
status id — so `category` is mandatory on every status.

### Lead
An **unqualified sighting** of a possible project — a salesperson hears about a development
from an architect, an info provider, or a WhatsApp thread. Cheap to record and deliberately
**not exclusive**: several people may hear the same rumour, and racing to lodge hearsay would
be worse than racing to register. A Lead is tied to a **Customer** (the dealer or account it
came through) and may name a developer before one is confirmed.

Qualifying a Lead runs the fuzzy clash check and creates a **Project** — that conversion is
the moment ownership locks. A Lead may produce more than one Project. Leads carry their own
qualified / disqualified outcome, which is what makes "we hear about 40 and pursue 12"
measurable — the top of the funnel that today lives only in WhatsApp.

> Not the same as ecohub's `Lead`, which is a B2C enquiry from a homeowner about one property,
> carrying budget range and an assigned designer.

### Registration
The act of claiming a Project. Exclusive: within a company, one development = one Project.
Identity is **Developer + fuzzy-matched title**, with Location as tiebreak. A second
salesperson attempting to register a colliding development is **blocked**, shown the
incumbent (owner, stage, last activity), and offered *request to join* or *dispute*.

### Developer
The parent property group pursuing the development — SP Setia, Gamuda, Pavilion. A
**Project Party**. Usually never buys anything; the money arrives from a Main Contractor
or Trading House.

### Registered company (SPV)
The legal entity actually registered for one specific development — typically a
project-specific special-purpose vehicle, distinct from the Developer parent. Usually
unknown at Registration and surfaces around PO time.

### Project Party
An **organisation master record**, reusable across many Projects, typed as one of
developer / architect / main contractor / trading house / consultant. Reusable identity is
the point: it is what makes "which architects should we prioritise visiting" and "which
developers convert best" answerable. Optionally bridged to a `customers` row once that
party actually issues a purchase order — until then it is not a customer.

### The cast, and which way value flows

Two different flows run through every project, and confusing them is the classic mistake:
**influence** decides *whose product gets specified*, **money** decides *who we invoice*. The
party who approves the brand is almost never the party who pays for it.

| Party | What they do | Do they pay us? |
|---|---|---|
| **Us** (the principal) | Supply the sanitary ware, across all brands carried | — |
| **Developer** | Owns the development (SP Setia, Gamuda, Pavilion). Approves the specification, usually on consultants' advice. Requests **Sponsorship** into their showroom | Almost never |
| **Registered company (SPV)** | The legal entity for one specific development, typically project-specific | No — an identity, not a buyer |
| **Architect / consultant** | **Specifies** the product. The entire "spec-in" effort targets them. Pure influence, zero money — which is exactly why they must not live in `customers` | Never |
| **Main contractor** | Wins the construction tender and buys materials to build. **May issue the PO directly** | Sometimes |
| **Trading house** | An appointed intermediary trading company: it buys from us and resells to the main contractor | **Usually — and preferred** |
| **Dealer / customer** | An existing trading account business is routed through (1 Living Depot, DBI Concept Design) | Yes |

### Trading house
An intermediary appointed to sit between us and the main contractor: **we invoice the trading
house, the trading house invoices the contractor.** We prefer it, for two reasons the client
states directly — it *"keeps the principal out of direct contractor dealings"* (no chasing
site progress claims, retentions or variation disputes) and it *"reduces finance
exposure"* (construction contractors are a long-payment, higher-default counterparty; the
trading house absorbs that credit risk).

So the same physical product can be specified by an architect, approved by a developer, built
in by a contractor, and paid for by a trading house — four parties, one project. This is why
`po_source` is `contractor direct | trading house`, why the issuing party is recorded
separately from whoever was quoted, and why **PO source need not tally with the quotation**:
we quote whoever will listen and invoice whoever is appointed.

### Project Stakeholder
A **person on one Project**, with the role they play *on that Project*: decision maker,
influencer, info provider, architect. The same person is a decision maker on one tender and
an influencer on the next, so the role belongs to the pairing, never to the person. There is
no global person master — stakeholders are recorded per Project. Optionally linked to a
Project Party (their firm); a stakeholder with no firm is valid.

### Info provider
A Project Stakeholder role. Someone inside the developer or contractor feeding tender
intelligence to the salesperson. Carries no special visibility rules — visible to anyone who
can see the Project.

### Brand
One of the manufacturer brands the company carries (Sorento, Mocha, Cabana, Iborn, Bravat,
…). The existing `brands` reference data, company-scoped. A Project records which brands are
being pushed into it. Note: **Mocha is both a Brand carried by the SRT company and a separate
Company** — the two are unrelated uses of the name.

### Quotation
A priced scope of supply offered into one Project — House Units, Common Area / Facilities,
Showroom. A Project has many. Spec-in and pricing are the same act: specs are submitted with
prices, so there is no separate "spec" artifact.

Outcome lives here, not on the Project: each Quotation is open, won, or lost, and a lost one
carries a loss reason. **The Project's outcome is derived** — Won if any Quotation is won,
Lost only when all are lost, otherwise Open. Winning the house units while losing the common
area is the normal case, not an edge case.

### Outcome vs Status
Two different axes, never to be conflated. **Status** is a funnel position describing what has
happened — its terminal rung is **"PO Received"**, deliberately *not* "Won", because a project
can receive a PO for one scope while another scope is still being quoted. **Outcome** is the
commercial result, derived from Quotations. Every metric — conversion rate, win/loss, loss
reasons — reads outcome. Nothing reads status.

### Quotation Version
A numbered revision of a Quotation. The current version is the highest-numbered one — there is
no "current" flag and no "frozen" flag, because a second record of the same fact drifts. The
current version is editable and every save is audit-trailed; **Revise** freezes it as it stands
and opens the next one.
Superseded versions are immutable, which is what makes "this is what we actually showed the
developer" provable. Sample Submissions and Project POs bind to a version, never to the
Quotation as a whole.

### Project PO
An **incoming** purchase order from a main contractor or trading house — the moment a
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
Product given free into a developer's showroom or a mockup — a real cost, recorded against
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
outside it raises a **non-standard SKU** alert — the control on SKU proliferation. Coarse by
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
A legal selling entity — SRT (Sorento) or MOCHA. A partition *below* the tenant. Owned
business records carry `company_id` and are auto-filtered.

### Tenant
The install boundary for modules. Currently stubbed to a single default tenant.

---

## Core vs Module

### Core
A base-platform capability every install needs (auth, users, products, stock, orders).
Always present, never toggleable.

### Module
A capability a tenant installs and can turn off — an `app_modules_catalog` entry, a
`tenant_modules` enablement row, and a route guard. Enablement is the entire definition;
schema location is a separate decision.
