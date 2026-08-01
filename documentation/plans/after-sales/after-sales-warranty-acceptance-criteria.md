# UAC - After-Sales, Warranty & Service Scheduling

**Companion to:** `PLAN-after-sales-warranty.md` (to be written)
**Status:** Pre-code. Every AC must be self-verified on the stated side(s) end-to-end before handoff.
**BRD:** Cluster D, Requirements #5 to #13 (`documentation/Sorento_Phase2_BRD.md`).
**Decisions:** `adr/0008` (one Complaint per issue) - `adr/0009` (Service Job is requester-agnostic) - `adr/0010` (Warranty Terms scope to Kind) - `adr/0001` (status engine is core) - `adr/0007` (a Dealer is a Customer). Vocabulary in root `CONTEXT.md`.
**Legend:** `[BE]` backend/pytest - `[FE]` frontend/vitest+playwright - `[E2E]` full FE->BE->DB - `[MIG]` migration/data - `[AI]` LLM behaviour - `[T]` CI guard.

Convention: **Given / When / Then**. An AC passes only when the Then is observed against the **real stack** (not mocks) for the side marked, per the three-phase loop.

---

## Journey (Phase 0 - governing; every AC below traces to a step here)

### Why this module exists commercially

**To capture consumer data by bypassing the dealer.** Sorento sells through dealers and therefore has no
idea who actually owns its products. Every complaint is a moment when a consumer voluntarily hands over
their identity, their address, their purchase and their receipt. That data is the strategic prize; the
complaint is the occasion for collecting it.

So a Complaint is never the end record. Every lodgement must leave behind, permanently and queryably:
**who the consumer is** (a profile that persists across complaints), **which Dealer they bought from**,
**that dealer's own invoice or order number**, **the value if the receipt shows it**, **the product and
quantity**, **the purchase date**, and **the receipt document itself**. The BRD says the same thing more
quietly: *"the added value of warranty registration to Sorento is to have the sales data from the
dealership indirectly."*

This reframes the design: the warranty engine and the service dispatch are the visible value exchanged
with the consumer, and the purchase ledger is what Sorento keeps.

### The guided experience

The system's job is to remove decisions, not to collect fields. Two WhatsApp groups are being
retired: `Maintenace & Services` (consumer site visits) and `Sorento Exchange & Replacement 2025`
(dealer goods swaps). Neither group contains a customer. Every message in them is Sorento staff
hand-transcribing what someone told them, into a template they keep re-pasting, which the office
then chases for missing fields.

### Actor 1 - the Consumer (a homeowner with a faulty product)

Arrives from a WhatsApp link. Enters a phone number, receives an OTP. **No question is asked at all** -
dealer staff are already known from their `customer_id` binding, Sorento staff and technicians from
theirs, so anything else is a Consumer by elimination.

They photograph the receipt and the fault. Nothing else is typed yet. The AI reads the shop name,
the purchase date and the model from the receipt, matches the shop to a Dealer, and resolves the
Warranty Product Kind. One screen comes back:

> *A water closet, bought from Total Home DIY on 16 Oct 2025. Did I get this right?*

Every extracted value lands in a **normal, editable field** - not a read-only confirmation. If the AI
misread the shop name or the date, the consumer simply corrects it, the way they would on any form. This
matters more than it sounds: a wrong extraction costs the consumer one edit instead of costing Customer
Service a cleanup.

They pick which item is faulty from a small tiled chooser (toilet / basin / tap / sink / shower /
mirror) - never a SKU, never a dropdown of 11,415 codes. They describe the fault in their own words and
add photos, each checked as it uploads with a plain-language nudge if the shot will not do ("*step back
so the pipe joint is visible*"). They submit.

**Two taps and two photos.** They hold a complaint number, a warranty verdict, and a thread that
will keep telling them what is happening. The Dealer and the Dealer's salesperson are told without
anyone asking them to be.

Nothing they were asked for could have been derived. Everything derivable - dealer, product kind,
warranty status, expiry, salesperson, whether a callout is chargeable - was derived. **Including which
journey they are on**: an unbound dealer contact who types an order number instead of uploading a
receipt is recognised from that order and silently re-bound to the dealer track.

### Actor 2 - Sean, reporting on a dealer's behalf (the eight-second message)

He files roughly ten of these a day and today types, into a group:

```
[11/05 11:08:15] <photo>
[11/05 11:08:26] <photo>
[11/05 11:08:55] DILOOMA-USJ. CSS3310BL holder broken. Pls replace to shop
```

He now sends exactly that, unchanged, to the Sorento business number. The AI waits for the burst to
close, reads dealer, model, defect and requested resolution out of one line of shorthand, and
replies with the complaint number. If something is missing it asks for that one thing, immediately -
which is what the office does by hand tomorrow:

> *"this one wat issue? for which dealer? for wat model?"* - Yeoh, three times in four minutes

**His habit does not change. Only the destination changes.** He is never shown a form.

One burst can be two products (`SRTWC8366 x 1 / SRTWC8152 x 1` under eight media spanning two
minutes), so intake accumulates a burst and closes it on topic-switch or idle. One burst, one
Complaint, two product lines.

### Actor 3 - the Technician (a phone, someone's bathroom, poor signal)

Not a system user and never will be. Arrives at the portal from a WhatsApp link, identified by the
phone they already message from. Sees **today's jobs and nothing else** - no listings, no search, no
history but their own.

Taps one job: the site, who to call, what the fault is, the Consumer's own photos. Then
*On my way* -> *Arrived* (location captured silently, never blocking) -> photos, each validated as it
uploads -> diagnosis -> *Complete*.

The diagnosis they record is what settles who pays and what feeds the recurring-defect report.

### What everyone else is told, automatically

The Submitter receives every update. The Dealer hears about goods and outcomes. The Salesperson,
derived from the Dealer and never typed, hears the same. Customer Service sees the clock. The
Consumer is told only when there is something they must know about their own home or must act on -
because on the dealer track they may not know a complaint exists, and a surprise message is worse
than none.

### The five failures this journey is designed to remove

Every one is quoted from the retired groups:

| observed today | removed by |
|---|---|
| `Report No: SV2026/07-4436 - Service Date: TBA` (x3 in one afternoon) | a job cannot leave *Proposed* without a date, and stall time is visible |
| `pls follow up customer didn't receive any call from maintenance` (x2) | *Confirmed* is a distinct state requiring the customer to have agreed |
| `No collect?` / `No arrange??` / `Hi, done replace?` / `Hi?` | the Submitter is told on every transition, so chasing has no purpose |
| `wat is the problem? For which dealer? for wat model?` | the AI asks at intake, in seconds, not the office tomorrow |
| `Warranty over. Pls info service charge first` | entitlement and chargeability are computed and shown before dispatch |

---

## Group A - Prerequisite (S0) and module wiring

**AC-A1 to AC-A3 were rewritten 2026-08-01.** Their original premise was false: the status engine was **not**
absent. It already existed on the project-sales branches (`0ec9875d2`) and was already applied to the shared
dev database. See `../../adr/0012-adopt-the-existing-status-engine-rather-than-porting-it-twice.md`. The
originals are kept below the rewrite so the change of premise is auditable.

- **AC-A1** `[BE][MIG]` Given the status engine already exists as core (`0ec9875d2`: `statuses` +
  `status_transitions` via migration `308_status_engine`, plus service, REST, RBAC and an admin UI), Then
  after-sales **adopts** it rather than porting a second time, its existing tests still pass in this tree, and
  the sibling alembic heads it creates against main are rejoined so `alembic heads` reports exactly one head.
  `workflow_stages` is dropped by the adopted migration. **VERIFIED:** 52 tests green in this tree, single
  head `309_merge_status_engine`.
- **AC-A2** `[BE]` Given the adopted engine, Then all PKs/FKs are `UUID(as_uuid=False)`, never `Column(String)`,
  per the uuid-id principle. **VERIFIED** against the adopted models. Note the boundary found while checking:
  `users.id` is `Column(String)` and 14 model files carry `ForeignKey("users.id")` as String, so FK columns
  pointing at `users` must stay String until the uuid-id PR stack converts `users.id` itself. A `uuid` column
  cannot hold an FK to a `text` column.
- **AC-A3** `[BE]` Given the adopted engine, Then `complaint` is a registered entity type with a default status
  graph, and reporting groups by `key`, never by status id and never by `category`. The graph carries the
  **12** strings live code compares against, verbatim, so registration changes no existing complaint behaviour:
  `draft, new, submitted, updated, responded, approved, rejected, processed_by_cs, fulfilled, closed, voided,
  resolved`. Because `complaints.status` is a bare `VARCHAR(50)` holding the key (no FK, no CHECK, 51 live
  rows) while the engine is id-based, registration goes through a **key-valued adapter** over the existing
  guard - **no `status_id` FK is added and the 51 rows are not migrated.** Edges and flags are specified with a
  file:line citation each in `status-graph-evidence.md`. Two entry points, `draft` (portal) and `new` (column
  default), are both legitimate; no `draft -> new` edge is declared, because nothing performs it.
- **AC-A3a** `[BE]` Given `service_jobs` does not exist yet, Then `service_job` registers **FK-based natively**
  (`status_id`) in the slice that creates its table, not through the adapter complaints need. Moved out of S0.
- **AC-A3b** `[BE]` Given the graph is only advisory unless every write path is guarded, Then the key-valued
  guard covers the dedicated action routes **and** `PUT /api/v1/complaints/{id}`, whose blind `setattr` loop
  (`complaints_service.py:1713`, `ComplaintUpdate.status: Optional[str]`) currently lets any authenticated or
  `X-API-Key` caller set any status from any state. Gated on evidence about real callers, since it is the
  change most likely to break an n8n integration that sets status directly.

<details><summary>Original AC-A1 to AC-A3, superseded (false premise: the engine was already built)</summary>

- **AC-A1** `[BE][MIG]` Given the status engine is not yet in this codebase (`statuses` / `status_transitions` absent; `workflow_stages` is the 0-row orphan), Then it is ported from `foundryx-shared-service` per ADR-0001 as **core** before any after-sales slice merges, and `workflow_stages` is dropped.
- **AC-A2** `[BE]` Given the port, Then all PKs/FKs are `UUID(as_uuid=False)` (never the source's `Column(String)`), per the uuid-id principle.
- **AC-A3** `[BE]` Given the status engine, Then `complaint` and `service_job` are registered entity types each with a default status graph, and reporting groups by `key`, never by status id and never by `category`.

</details>
- **AC-A4** `[BE]` Given `app_modules_catalog`, Then rows `service_jobs` (deps `["base","resources"]`) and `warranty` (deps `["base","product"]`) exist, and `complaints` deps grow to include `order`, `product`, `sla`, `notifications`, `workflow_forms`, `warranty`, `service_jobs`.
- **AC-A5** `[BE]` Given every new router, Then it is wrapped in `Depends(require_module_enabled_with_api_key("<key>"))` for its own module key.
- **AC-A6** `[BE][T]` Given ADR-0009, Then a guard test asserts `service_jobs` tables declare **no FK to `complaints`** and the module's Python package imports nothing from `app.models.complaints`.
- **AC-A7** `[BE][MIG]` Given all new tables, Then they live in `public` with normal FKs (no dedicated schema), and every owned table is registered with `CompanyScopedMixin` with the leak test asserting `UNSET` scope returns 0 rows.
- **AC-A8** `[BE][MIG]` Given new permission slugs (`complaints.*`, `service_jobs.*`, `warranty.*`), Then each is seeded, registered in `permission_module_map`, enforced deny-by-default, **and** an explicit grant sweep runs for already-provisioned roles (PRINCIPLES DoD #3).
- **AC-A9** `[BE][MIG]` Given `document_numbering_rules`, Then `service_job` is seeded as `SV{year}/{month}-` with monthly reset and 4 digits (matching the existing hand-typed `SV2026/07-4436`), and `warranty_registration` as `WR{year}-` yearly. `complaint` keeps `CMP{year}-`.

## Group B - Parties and the portal door

- **AC-B1** `[BE][MIG]` Given `respond_contacts`, Then it gains nullable `customer_id` -> `customers`, `user_id` -> `users`, `technician_id` -> `technicians`. **No `party_kind` column and no `door_answered_at` column exist** - kind is derived, and there is no door question to remember.
- **AC-B2** `[BE]` Given a contact row, Then its kind is **derived**: `customer_id` set means dealer staff, `user_id` set means Sorento staff, `technician_id` set means technician, none set means Consumer. More than one may be set simultaneously.
- **AC-B3** `[E2E]` Given the Sanimart case (a dealer's owner reporting a fault in his own home), When he submits, Then the Dealer resolves to Sanimart, the **Site is his home address**, and the salesperson resolves to Sanimart's account owner. Being a dealer contact never forces the Site to be the shop.
- **AC-B4** `[E2E]` Given a phone with **no** binding, When they land, Then they are treated as a **Consumer by elimination** and **no door question is asked**. Dealer staff are known from `customer_id`, Sorento staff and technicians from `user_id` / `technician_id`; anything else is a Consumer.
- **AC-B5** `[E2E]` Given a bound phone, When they land, Then they go straight to the journey their binding implies, with no question.
- **AC-B5a** `[E2E]` Given an **unbound** dealer contact who was mis-routed to the Consumer journey, When they supply a Sorento **order number** instead of a receipt, Then the order resolves, `respond_contacts.customer_id` is written from that order's customer, and their journey switches to the dealer track. The binding **self-heals** without ever asking a question.
- **AC-B5b** `[FE]` Given the Consumer intake first step, Then it accepts **either** a receipt photo **or** a typed order number, so AC-B5a has a route and a dealer contact is never trapped being asked for a receipt they do not hold.
- **AC-B6** `[BE][MIG]` Given `complaints`, Then a **new** column `reported_by_role` is **added** (values `end_user` / `dealer` / `salesperson` / `cs` / `technician`) and backfilled from `customer_type` via a documented mapping. `customer_type` is **not renamed and not dropped** in this slice - it is left in place, read-only, for one release. Same for the free-text `customer_name` / `salesperson`, superseded by `customer_id` -> `customers` and derivation.
- **AC-B6a** `[BE][T]` Given the legacy columns survive one release, Then a guard test asserts no module code **reads** `customer_type`, `customer_name` or `complaints.salesperson`, so the later drop is a pure deletion with no behaviour change.
- **AC-B7** `[BE][MIG]` Given `customers.account_owner_user_id` is 0 of 3,284 populated, Then a **one-off seed** derives it from `orders.salesman` (most-recent-order-wins), via a `salesman_code` -> `users` map. The 2,191 single-salesman customers resolve automatically. **Sorento creates the `users` rows for salesmen** (they need them for Project Management anyway); the seed script creates stand-in users locally for testing only.
- **AC-B8** `[BE]` Given the 322 customers with multiple salesman codes, Then most-recent-order-wins seeds a value and the field remains editable as **Account Owner** on the Customer form.
- **AC-B9** `[BE]` Given the runtime, Then salesperson resolution reads **only** `customers.account_owner_user_id`. No runtime code path reads `orders.salesman`. Orders are the seed, never the source.
- **AC-B10** `[BE]` Given a Complaint whose dealer has no account owner (~770 dealers with no orders, plus junk codes `0`, `ACT`, `CS01`, `WH02`, `MARKETING`, `SAMPLE`, `FUNITURE`, `TERA`), Then notification routes to the after-sales team lead and the Complaint is flagged **salesperson unresolved** on the dashboard. It is never silently dropped.
- **AC-B11** `[BE]` Given the salesman-code map, Then suffixed codes (`SEAN` / `SEAN I` / `SEAN III` / `SEAN IV`) map many-to-one onto a single user where they are the same person, as configured. The suffix is **not** company: every suffix appears under both Sorento and Mocha in `orders`.
- **AC-B12** `[MIG]` Given testing needs dealer contacts, Then a seed script populates representative `respond_contacts.customer_id` bindings. **Production bindings are configured manually by Sorento**; no bulk import is shipped.

## Group C - Intake

### C.1 WhatsApp AI intake (primary front door)

**Architecture.** Respond.io messages arrive at **n8n**, not at the CRM - n8n is already the message
pump for every WhatsApp flow in this system. So the CRM does not poll or subscribe. The split is:

| owns | responsibility |
|---|---|
| **n8n** | receives each inbound message, debounces the burst (wait node), calls the CRM once when the burst closes |
| **CRM** (via MCP tool) | accumulates the frame, extracts, resolves dealer + product + Kind, creates the Complaint, returns the number and any missing field |

Extraction lives in the CRM, **not** in an n8n LLM node, for two reasons: the prompt must be versioned
and traceable through `ai_prompt_registry`, and the dealer / product / Kind resolvers already exist
CRM-side. Putting the LLM in n8n forks the prompt registry and duplicates the resolvers.

- **AC-C0a** `[BE]` Given intake, Then it is exposed as a **write MCP tool** (`complaint_intake_submit`) so n8n calls it as a tool, not as a bare HTTP endpoint. Registered in `sorento_crm_mcp.catalog.CATALOG`, and the MCP process is restarted so FastMCP re-registers it (adding to the catalog alone is not enough).
- **AC-C0b** `[BE]` Given the tool is write-capable, Then its name matches the `_is_write_tool` convention (`*_submit`) so the AI-assistant prompt dry-run strips it and a test can never persist a real Complaint.
- **AC-C0c** `[BE]` Given the new tool, Then `agent_mcp_tools` linkage is seeded by the startup hook and the `ToolSpec` description carries intent keywords - the implementer owns seeding, never the admin.
- **AC-C0d** `[BE]` Given n8n calls the tool with an accumulated burst, Then the tool is **idempotent** on a burst key: a retry after a timeout returns the same Complaint number and does not create a second Complaint.
- **AC-C1** `[BE][AI]` Given a burst of WhatsApp messages from one contact, Then intake accumulates them into one frame using `conversation_frames` (opened on first turn, closed on topic-switch or idle) and produces **one** Complaint.
- **AC-C2** `[E2E][AI]` Given Sean's real message (`8 media 10:14:18-10:16:05`, then `Unihome. SRTWC8366 x 1 / SRTWC8152 x 1 / Seatcover no soft close. Pls replace to shop` at `10:16:33`), Then one Complaint is created with **two** product lines and all eight media attached.
- **AC-C3** `[E2E][AI]` Given media arrives **before** the text (photos at `11:08:15`, text at `11:08:55`), Then the frame still binds them to the same Complaint.
- **AC-C4** `[E2E][AI]` Given `DILOOMA-USJ. CSS3310BL holder broken. Pls replace to shop`, Then dealer, model, defect and requested resolution are all extracted from that one line without a form.
- **AC-C5** `[E2E][AI]` Given a message missing a required field, Then the AI asks for **only** the missing field, in the same conversation, and does not re-ask anything it already has.
- **AC-C6** `[BE]` Given a created Complaint, Then the AI replies with the complaint number.
- **AC-C7** `[BE][AI]` Given the extraction prompt, Then it resolves through `ai_prompt_registry` (versioned, labelled, publishable without redeploy) and every turn stamps `metadata_json.prompt_versions`.
- **AC-C8** `[BE][AI]` Given generalised extraction, Then the test table uses **paraphrases** of real chat messages, not one canonical sentence, and no keyword-matching branch exists per phrasing.
- **AC-C9** `[E2E]` Given the cutover period, Then a **forwarded** group message is accepted as intake. This path is tagged as cutover-only and removable once both groups are retired.

### C.2 Portal submission (Consumer)

- **AC-C10** `[E2E]` Given a Consumer on the portal, Then the flow is: upload receipt -> **extracted values pre-fill an editable form** -> choose item from a **tiled picture chooser** -> describe fault per item -> upload proof photos -> submit.
- **AC-C10a** `[FE]` Given extraction returned values, Then **every one of them renders in an editable input**, never as read-only text: consumer name, phone, site address, shop name, purchase date, purchase value, quantity, and the chosen Kind. The consumer can correct any of them before submitting.
- **AC-C10b** `[BE]` Given the consumer edits an extracted value, Then **both** are stored - the AI's original extraction and the human-corrected value - so extraction accuracy is measurable in production from real corrections, not only from the S3-pre spike.
- **AC-C10c** `[E2E]` Given the consumer corrects the **shop name**, Then the dealer fuzzy-match re-runs against the corrected text. They are still never shown a dealer picker or a customer code.
- **AC-C11** `[FE]` Given the item chooser, Then **no SKU, product code or UUID is ever displayed to a Consumer**, and no dealer picker is shown.
- **AC-C12** `[E2E][AI]` Given a dealer's own receipt (`KCS-2112-0054`, `CS002629`, `NV20-2-008850`, `IV01029`, `DO10-2-123494`, `CS40964` - **none of which exist in `orders`**), Then extraction pulls shop name, purchase date, model and quantity, and the shop name is **fuzzy-matched to `customers`**. Order-number matching is not attempted on the consumer track.
- **AC-C13** `[E2E]` Given the dealer track, Then a quoted Sorento order number (`202604-0348`) **is** matched to `orders`, and dealer, products and date resolve from the order.
- **AC-C14** `[E2E]` Given a low-confidence or failed dealer match, Then the Complaint still submits, carries the raw extracted shop name, and is flagged for CS to confirm. **The submitter is never blocked.**
- **AC-C15** `[E2E]` Given a Consumer returning later, When they enter their phone, Then they see their own historical Complaints.

### C.3 Product resolution

- **AC-C16** `[BE]` Given an extracted model code, Then `complaint_product_lines` stores **both** the raw claimed text and a nullable resolved `product_id`. An unresolved line is valid and does not block submission.
- **AC-C17** `[BE]` Given `SRTWC8152`, which matches `SRTWC8152-RL-RG`, `SRTWC8152-SH` and `SRTWC8152-300-RL`, Then the line resolves to the **Warranty Product Kind** with confidence, leaves `product_id` null, and is surfaced to CS as a variant choice.
- **AC-C18** `[BE]` Given `WC189-G2` (reporter dropped the `SRT` prefix) and `SRTWC8517-200mm` (size appended as text), Then prefix-strip and dash-strip resolution is attempted before declaring no match.
- **AC-C19** `[E2E]` Given CS opens a Complaint with an unresolved line, Then they can pin the exact variant, and the raw claimed text remains visible as recorded.

## Group D - Warranty

- **AC-D1** `[BE][MIG]` Given `warranty_product_kinds`, Then the 31 kinds from Warranty Policy v15 are seeded (Water Closet, Urinal Bowl, Squatting Pan, Electronic Seat Cover, Intelligent Water Closet, Tankless Water Closet, Wash Basin, LED Mirror, Bathroom Furniture, Mirror Cabinet, Stop Valve, Sensor Taps, ...).
- **AC-D2** `[BE]` Given kind mapping, Then a product resolves to a Kind by **category plus model-code rules** (category, named series such as *Honeycomb*, or explicit model list such as `SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB5060-BL, SRTMCB5061-BL`). It is never a single FK on `products`.
- **AC-D3** `[BE]` Given `warranty_terms`, Then each row carries kind, **part**, duration (months **or** lifetime), covered defect types, `installation_included`, exclusions text, and optional registration bonus.
- **AC-D4** `[BE]` Given a Water Closet, Then three terms resolve simultaneously: Ceramic Body (lifetime, crack + leak only, installation included), Flushing Fittings (5y, installation excluded), Seat Cover Soft Close (2y, installation excluded).
- **AC-D5** `[BE]` Given a lifetime ceramic body and a reported defect that is **not** crack or leak, Then the claim is **not** covered by that term. Defect type is part of entitlement, not just the date.
- **AC-D6** `[BE][MIG]` Given terms are versioned and dated, Then entitlement is judged against the terms **in force on the purchase date**, and republishing the policy never alters an existing Complaint's verdict.
- **AC-D7** `[BE]` Given a part replaced under warranty, Then the new part inherits the **remaining** cover and **no new term starts** (policy clause 6 note).
- **AC-D8** `[E2E]` Given a Complaint is lodged, Then a Warranty Registration is **auto-created if absent**, activated from the purchase date, with registration never a precondition of cover (BRD overrides policy clause 3(b); recorded in ADR-0010).
- **AC-D9** `[BE]` Given the Automatic Water Booster Pump, Then online registration extends cover 2y -> 3y, per clause 26. Registration bonuses are modelled, not ignored.
- **AC-D10** `[E2E]` Given a Complaint with a resolved Kind and purchase date, Then CS sees a computed verdict **before dispatch**: term matched, expiry, time remaining, and whether installation is included, with `[Confirm]` and `[Override with reason]`.
- **AC-D11** `[BE]` Given an override, Then the reason is mandatory and stored; the computed verdict is retained alongside the human decision (never overwritten).
- **AC-D12** `[BE]` Given the purchase date came from OCR of an unverifiable third-party receipt, Then the verdict is a **recommendation** and is never auto-applied as a binding determination.
- **AC-D13** `[BE][MIG]` Given `products.warranty_months` is 0 of 11,415 populated, Then it is abandoned by this engine and no code path reads it.
- **AC-D14** `[E2E][AI]` Given a policy question from a Consumer or Dealer, Then the AI answers **only** from the stored policy text, quoting it, and routes to Customer Service when the situation is ambiguous or outside the document (BRD Req #12).
- **AC-D15** `[BE]` Given clause 17 (residential only, commercial and industrial excluded) and 23 of 50 existing Complaints being `reported_by_role`-adjacent `Project` cases, Then the restriction is **modelled but not enforced**, and the open question is flagged in the plan pending Sorento's ruling.

## Group M - Requirements grilled 2026-08-01

From `REQUIREMENTS-inbox-2026-08-01.md` (R1-R12, all resolved) and the CS discovery study
(`flowcharts/Sorento_Operational_Discovery_Study_CS.pdf`). These sit on the forms platform per `adr/0011`.

### Slotting and prior art - added 2026-08-02, before S1

**Group M arrived after the slice sequence was written and no slice claimed it.** Building S1 without
resolving that would have shipped a Site the very next slice had to migrate. Two corrections follow.

- **AC-M37 moves into S1** `[BE][MIG]`. S1 is the slice that creates the Site, and the plan gave it
  `site_maps_url text` alone. Defining the Site twice - a URL now, then `latitude` / `longitude` /
  `place_id` later - means a second migration on the same concept plus a decision about whether the URL
  survives. S1 now carries all four fields and `site_maps_url` is dropped from its schema before it is ever
  written. AC-M38 (pin optional, geocode at dispatch) and AC-M39 (both kept, neither reconciled) stay with
  the consumer form in S3; AC-M40 (referrer-restricted key) is a deployment gate, not a slice.

- **AC-M8, AC-M9, AC-M10 and AC-M13 are ALREADY BUILT** and must not be built again.
  `workflow_submission_line_disposition.py` (F1a) seeds exactly the option set AC-M8 names - `write_off`,
  `cn_cancellation`, `replacement_same_model`, `replacement_equivalent_value`, `replacement_wrong_model`,
  `repair`, `maintenance` - plus `nothing_to_collect` for AC-M13.
  `workflow_submission_derived_status.py` derives the header from the lines, closing when every line is
  terminal and **reopening** when one stops being decided, which is AC-M10; per-line independence is
  AC-M9. This is ADR-0011 paying off rather than a coincidence: the goods track asked for line-level
  disposition, and the case was already a form submission. S7 inherits these instead of implementing them,
  and its remaining work is the RMA container (AC-M11, AC-M14, AC-M15, AC-M16) and the collection gate
  (AC-M17 to AC-M19).

The rest of group M is slotted in `PLAN-after-sales-warranty.md` under "Slice sequence".

### Waiting attribution - the single design behind R2, R7, R8, R12

- **AC-M1** `[BE][MIG]` Given a case, Then it carries `waiting_on_party` (`cs`/`maintenance`/`plumber`/`customer`/`supplier`/`warehouse`), `waiting_on_reason_id` -> configurable master data, and `waiting_since`. **One shared reason vocabulary** serves both the pending reason and the overdue reason.
- **AC-M2** `[BE]` Given a case is waiting on an external party, Then **the SLA clock is NOT paused**. Time waiting still counts toward resolution.
- **AC-M3** `[E2E]` Given a case is waiting, Then the pending-task row reads "waiting on maintenance since 3 Aug" and **not** "stuck at CS".
- **AC-M4** `[E2E]` Given a case becomes overdue, Then `waiting_on` is **mandatory** before further action.
- **AC-M5** `[FE]` Given the pending-task dashboard, Then rows are coloured by breach risk **and** show the waiting party as a text label - colour is never the only signal.
- **AC-M6** `[E2E]` Given a deadline genuinely must move, Then that is **Extend** (`PLAN-sla-extend-deadline.md`: resolution clock only, reason required, soft limits, audited), not a waiting flag.
- **AC-M7** `[BE]` Given SLA reporting, Then breaches are **attributed** - "of 40 breaches, 26 were waiting on an external party" - rather than hidden.

### Exchange / return request: line-level (R1, R3)

- **AC-M8** `[BE]` Given a request, Then each **line** carries its own status and **disposition**: write-off, CN/cancellation, replacement same model, replacement equivalent value, replacement wrong model, repair, maintenance. Requires forms-platform **F1a**.
- **AC-M9** `[E2E]` Given three lines, Then CS may approve some and reject others independently.
- **AC-M10** `[BE]` Given lines, Then the request's status is **derived** from them, closing when every line reaches a terminal disposition and **reopening** if a line returns - the `complaint_fulfilment_service` recompute shape.
- **AC-M11** `[BE]` Given an RMA, Then it is a **cross-request collection container**: lines from several requests may attach to one RMA, and lines may be added to an existing open RMA.
- **AC-M12** `[BE]` Given a line settled by a **CN alone**, Then it closes with **no RMA** - the RMA link is a line attribute, not a request attribute.
- **AC-M13** `[E2E]` Given nothing can be collected, Then the line takes an explicit **"nothing to collect"** disposition which **requires a reason**. A line never blocks its siblings.
- **AC-M14** `[BE]` Given an RMA, Then it carries its **own lifecycle status, age and owner** - not the outbound order vocabulary. Today all 1,732 RMA rows carry only `NEW`/`DELIVERED` and the truth lives in an Excel file called "RMA summary".
- **AC-M15** `[BE]` Given an RMA, Then it closes against its **REP or CN**.
- **AC-M16** `[E2E]` Given local versus outstation, Then sequencing is expressible per line: local allows REP before RMA; outstation requires RMA first (one trip, not two).

### Collection readiness (R4)

- **AC-M17** `[E2E]` Given collection is arranged, Then the Dealer is notified and must **acknowledge with photos** before collection is scheduled.
- **AC-M18** `[E2E]` Given the Dealer has not acknowledged, Then the case sits at `waiting_on = dealer` with `waiting_since` - the delay is visibly theirs, which is what makes the hard gate safe.
- **AC-M19** `[E2E]` Given CS overrides the gate (*collect anyway*), Then a **reason is required** and recorded.

### Core attachment validator (R5, replacing AC-F10 to AC-F18)

- **AC-M20** `[BE][MIG]` Given `attachment_types`, Then it gains `validation_guidance`, `min_score`, `validate_on_upload`. **No new tables** - it is already the per-type upload policy table (`allowed_extensions`, `max_file_size_mb`, `max_count_per_entity`).
- **AC-M21** `[BE]` Given the validator, Then it lives **once**, in the `resources` module beside attachments, and is reachable by `complaints`, `service_jobs`, the forms platform and anything else that already depends on `resources`.
- **AC-M22** `[BE]` Given an attachment link row, Then it carries `ai_score`, `ai_suggestion`, `override_reason`, `latitude`, `longitude`.
- **AC-M23** `[E2E][AI]` Given `validate_on_upload` is true, Then validation runs **synchronously on upload** and scores the file against that type's `validation_guidance`.
- **AC-M24** `[E2E]` Given a score below `min_score`, Then the suggestion is shown, **Retake** is prominent, and **Use anyway** requires a reason.
- **AC-M25** `[BE][AI]` Given the validator, Then its prompt lives in `ai_prompt_registry` and per-type behaviour is **data**. No hardcoded branch per type exists.
- **AC-M26** `[E2E]` Given `rma_readiness` photos, Then guidance checks the claimed model, the claimed quantity and defect visibility - R5 is three guidance strings, not three features.
- **AC-M27** `[E2E]` Given geolocation is denied or unavailable, Then coordinates are omitted and the upload still succeeds. Never blocking.

### External providers and cost (R11)

- **AC-M28** `[BE][MIG]` Given `external_providers`, Then it is a **generic** master with a `provider_type` discriminator (plumber, contract technician, courier, ...), **not** a plumber-specific table, and **not** `suppliers` - which carries purchasing semantics and would couple after-sales to `procurement`.
- **AC-M29** `[BE]` Given a cost line, Then it carries the case, the provider, the amount and **what it was for** (labour / parts / travel).
- **AC-M30** `[BE]` Given cost lines, Then **money out is independent of the chargeability state** - a warranty job can be free to the consumer and still cost Sorento a plumber fee.
- **AC-M31** `[E2E]` Given a cost line, Then recording it needs **no approval** - it is bookkeeping. Reporting surfaces outliers.
- **AC-M32** `[BE]` Given reporting, Then spend per provider and cost per case are both answerable - the study's open costing question.

### Assignment, calls, location (R6, R9, R10)

- **AC-M33** `[E2E]` Given no assignee resolves, Then the case routes to a configured fallback (after-sales team lead) and is flagged `assignment unresolved`. **Never silently unassigned.**
- **AC-M34** `[BE]` Given a call, Then it is a **`call` activity** in the existing `activities` module carrying outcome and next action. **No new table.**
- **AC-M35** `[E2E]` Given a call and the contact has **exactly one** open case, Then it auto-attaches. Given more than one, Then it waits in a per-contact inbox for one-click attachment - **never auto-attributed**, because a wrong attribution puts false evidence in the record.
- **AC-M36** `[BE]` Given Respond.io call records, Then they arrive via the **n8n Respond.io node's `On Call ended` trigger** (verified 2026-08-01 from the node's trigger list, alongside `On Message received/sent`, `On Conversation opened/closed`, `On Contact created/updated`, `On Contact Tag/Lifecycle/Assignee updated`). **n8n owns the subscription**, consistent with n8n owning the message pump.
- **AC-M36a** `[BE]` Given `On Call ended` fires, Then n8n calls a CRM **write MCP tool** (`call_log_submit`), the same shape as `complaint_intake_submit`: `*_submit` naming so `_is_write_tool` strips it from prompt dry-runs, catalog-registered with an MCP restart, `agent_mcp_tools` seeded by the startup hook, and **idempotent on the call id** so an n8n retry cannot double-log.
- **AC-M36b** `[BE]` Given the event is **contact-keyed and carries no case reference**, Then attribution follows AC-M35 unchanged: auto-attach only when the contact has exactly one open case, otherwise a per-contact inbox. The webhook does not change the attribution rule - it only fills the same model automatically.
- **AC-M36c** `[BE]` Given a call ended, Then the activity records the **outcome** (`answered` / `missed` / `no_answer`) and **duration**, not merely that an event fired. **A call that ended is not a call that connected** - and this is the point of the requirement: Fanny's complaint was *"customer didn't receive any call from maintenance"*, so the evidence needed is whether contact was actually made.
- **AC-M36d** `[E2E]` Given repeated unanswered calls to a Consumer, Then they are what justifies `waiting_on = customer` on the Schedule stage - "we called three times, no answer" is the defensible version of blaming the customer for a delay.
- **AC-M36e** `[T]` Given the payload shape of `On Call ended` is **still unverified** (fields for direction, duration, outcome, handler, recording), Then one test call is required before AC-M36c can be implemented. **The manual path stands alone**, so R9 ships regardless.
- **AC-M36f** `[T]` Given the installed n8n Respond.io node reports **version 1.12.0 (Legacy)** with an update available, Then confirm `On Call ended` exists and behaves identically on the current package before depending on it.
- **AC-M37** `[BE][MIG]` Given a Site, Then it carries `latitude`, `longitude`, `place_id` **and** the typed address.
- **AC-M38** `[E2E]` Given the consumer form, Then the map pin is **optional** and never blocks submission. No pin -> geocode the address at dispatch.
- **AC-M39** `[BE]` Given pin and address disagree, Then **both are kept and neither is reconciled** - the pin is what the technician navigates to, the address is what appears on documents.
- **AC-M40** `[T]` Given the Google Maps key on a public page, Then it is **HTTP-referrer restricted** - a public portal key is scrapable and billable.

## Group L - Consumer profile and the purchase ledger

**Grilled and resolved 2026-07-31** (forks 1, 2, 3, 4, 7 in `OPEN-consumer-ledger-grill.md`).
Owned by a new **`consumers` MODULE**, not by `warranty` and not by core.

> **Fork 6 (consent) is still open and is a HARD GATE on S3.** A portal may not collect consumer personal
> data without consent wording matching the intended use. Fork 5 (dealer channel conflict) blocks no code
> but wants a stated Sorento position before the Consumer 360 page exists.

### Module and ownership

- **AC-L1** `[BE]` Given `app_modules_catalog`, Then a `consumers` module exists with deps `["base","product","order"]`, and `warranty` declares a dependency on it. Core stays exactly one module (`base`).
- **AC-L2** `[BE]` Given `warranty` is uninstalled, Then `consumer_profiles`, `consumer_purchases` and `consumer_purchase_lines` are **untouched** - the ledger and the consumer list survive, while policies, terms, kinds and assessments go. This is the uninstall test that decided fork 7.
- **AC-L3** `[BE][T]` Given naming, Then nothing in this module is called `purchase_order` or lives under a `purchase` key - `procurement` owns that word for Sorento buying **from suppliers**, the opposite direction.

### Consumer profile: provisional until verified

- **AC-L4** `[BE][MIG]` Given `consumer_profiles`, Then it is 1:1 with `respond_contacts` (following the four existing `respond_contact_*` satellites) and holds name, contact details, addresses (jsonb - a consumer may own several properties) and consent fields.
- **AC-L5** `[BE]` Given staff type a consumer's phone into an intake message, Then a **provisional** profile is created. The consumer never authenticated, and that is the majority case.
- **AC-L6** `[E2E]` Given a provisional profile's phone completes an OTP login, Then it is promoted to **confirmed** automatically - deterministic, no human judgement.
- **AC-L7** `[BE]` Given provisional profiles, Then they are **never included in marketing sends** and are **excluded from headline consumer counts**, so "we have N consumers" is not inflated by staff typing.
- **AC-L8** `[BE]` Given a phone is written, Then it is normalised to **E.164** first, so `0166372304`, `+60166372304` and `60 166372304` resolve to one profile.
- **AC-L9** `[E2E]` Given an incoming name conflicts with the name already on that phone (`Miss Ong daughter` arriving on a phone holding `Ong Mei Ling`), Then it goes to a **review queue** and is **never auto-merged**.
- **AC-L10** `[E2E]` Given two profiles are the same person, Then an authorised user can **merge** them, and purchases plus complaints follow the surviving profile. **Split is out of scope.**

### Purchase: header and lines, consumer optional

- **AC-L11** `[BE][MIG]` Given one receipt covers several products, Then `consumer_purchases` is the **header** (one purchase event) and `consumer_purchase_lines` holds the products - mirroring `orders`/`order_lines`.
- **AC-L12** `[BE]` Given a purchase, Then `consumer_profile_id` is **nullable**: cover resolves from the purchase alone, because policy clause 6 attaches cover to the product and its purchase date, not to a person. A staff-reported purchase may carry no profile.
- **AC-L13** `[E2E]` Given a house changes hands, When the new occupant complains about a product bought by someone else that is still inside its term, Then cover resolves and the claim proceeds.
- **AC-L14** `[BE]` Given the header, Then it carries `customer_id` (the Dealer), `dealer_document_number` **as printed** plus a normalised copy, `purchase_date`, `total_value` + `currency`, and `proof_attachment_id` - the receipt, **retained**, never discarded after extraction.
- **AC-L15** `[BE]` Given a line, Then it carries `product_id` (nullable - the variant may be unresolved), `kind_id`, `claimed_text`, `quantity`, and `line_value` (**usually null**).
- **AC-L16** `[BE]` Given warranty, Then an assessment attaches to a **complaint product line**, which links to a `consumer_purchase_line_id` for the date. Cover is per product and per part, never per purchase.

### Dedupe: link, never reject

- **AC-L17** `[BE][MIG]` Given the dedupe key `(customer_id, dealer_document_number_norm, purchase_date)`, Then it is a **partial** unique index applied only where all three are non-null, so an incomplete key still writes.
- **AC-L18** `[E2E]` Given a second Complaint months later cites a receipt already in the ledger, Then the new Complaint **links to the existing purchase** and no duplicate header is created.
- **AC-L19** `[E2E]` Given a key collision, Then the submission **is never rejected**. The packing-list precedent rejected on a triple match, which was right for a staff import; refusing a consumer's complaint because we think we have seen their receipt is not.
- **AC-L20** `[BE]` Given the dealer is unresolved or no document number was extracted, Then the purchase is written with `dedupe_pending = true` and appears in a CS review list. Never blocks (AC-C14).
- **AC-L21** `[BE]` Given the same file is uploaded twice, Then `attachments.file_hash` detects it regardless of the key.

### Value: as printed, gated

- **AC-L22** `[BE]` Given value capture, Then only `total_value` on the header is captured, **as printed**, with **no** SST handling, discount allocation or per-unit derivation. `line_value` stays null in the normal case.
- **AC-L23** `[FE]` Given value is displayed, Then it is labelled *"as printed on the dealer's receipt, unverified"*.
- **AC-L24** `[BE]` Given a new permission slug `consumers.purchase_value.view`, Then it is **off by default** and value is hidden without it - retail prices must not appear on every CS screen.
- **AC-L25** `[E2E]` Given any report totalling value, Then it states coverage (`value known on N of M purchases`) rather than silently under-reporting.

### Consumer 360 and reporting

- **AC-L26** `[E2E]` Given a Consumer detail page, Then it renders profile, every purchase (dealer, dealer document number, products, quantity, value if permitted, date), every Complaint, and every stored document - each section always rendered with an explicit empty state.
- **AC-L27** `[E2E]` Given a Consumer lodges a second Complaint months later, Then it attaches to the **same** profile and their earlier purchases are already visible.
- **AC-L28** `[BE]` Given reporting, Then Sorento can answer per Consumer (which Dealers, what they own) and per Dealer (which Consumers, what volume) - the sell-through visibility the dealer channel currently hides.
- **AC-L29** `[BE][T]` Given consumer personal data, Then `consumer_profiles` is company-scoped, carries audit listeners, and its retention is documented. **PDPA-relevant, collected for a warranty purpose - see fork 6.**

## Group E - Complaint lifecycle

- **AC-E1** `[BE]` Given ADR-0008, Then no Complaint has a parent Complaint, and a `parent_complaint_id` column does not exist.
- **AC-E2** `[BE][T]` Given one customer issue requiring a collect-back **and** a replacement **and** two visits, Then exactly **one** `complaints` row exists, one form-SLA thread, one portal card and one survey.
- **AC-E3** `[BE][MIG]` Given stage clocks, Then each is a `form_sla_configs` row chained by `next_config_id`, with its own `stage_code`, `start_event`, `respond_event`, `resolve_event`, `team_set_code` and policy: **Acknowledge**, **Assess**, **Schedule**, **Resolve**, **Fulfil**.
- **AC-E3a** `[E2E]` Given a Complaint is created from any channel, Then the **Acknowledge** stage spawns immediately and **notifies the assigned CS team member through the existing form-SLA assignment notification** - a new Complaint arrives as a personal, clocked assignment, not as a row someone must remember to look at. No daily digest is required for the system to work.
- **AC-E3b** `[E2E]` Given the Acknowledge stage is not responded to within its policy, Then it escalates to the configured tier and notifies that tier - structurally preventing "created perfectly and then ignored" rather than relying on adoption.
- **AC-E4** `[BE]` Given a stage tracker, Then `response_time` and `resolution_duration` are computed in **working hours** via `work_calendar_configs` + `public_holidays` (BRD targets are 2 and 14 **working** days), never wall-clock.
- **AC-E5** `[BE]` Given form-SLA stage identity, Then every query keys on `(source_entity_type, team_set_code)` and uses `conversation_tracking_scope()` so conversation-SLA rows are never matched.
- **AC-E6** `[BE]` Given `complaint_resolutions`, Then each row carries a **spawn trait**: `service_job` / `goods_movement` / `nothing`. Adding a resolution is configuration, not a deploy.
- **AC-E7** `[E2E]` Given CS picks a resolution whose trait is `service_job`, Then a Service Job is created. Given `goods_movement`, Then they are prompted to link the RMA and/or REP orders. Given `nothing`, Then no child is created.
- **AC-E8** `[BE][T]` Given a Complaint marked with a spawning resolution, Then a guard flags any Complaint whose resolution implies a child that does not exist.
- **AC-E9** `[BE][MIG]` Given `complaint_root_causes`, Then it is extended with the policy's exclusion categories: `Installation fault`, `Wear and tear`, `Not our product`, `No fault found`, alongside the existing `Manufacturing Defect`, `Packaging Faulty`, `Product Defect`, `Replacement under goodwill after salesperson appeal`.
- **AC-E10** `[BE]` Given diagnosis, Then the technician records it on the **Service Job**, and CS promotes one to the Complaint's existing `root_cause_id`. Two visits may reach two conclusions.
- **AC-E11** `[BE]` Given chargeability, Then it is a **state** on the Complaint / Job - `not_applicable` -> `pending_assessment` -> `quoted` -> `accepted` / `declined` -> `confirmed` - and **not** derived from which track the Complaint is on. No rule states that a dealer case cannot be chargeable.
- **AC-E12** `[E2E]` Given cover has expired or the matched term excludes installation, Then chargeability enters `pending_assessment` and a conditional price is shown to the Consumer **before dispatch** ("free if product fault, RM X if installation fault").
- **AC-E13** `[E2E]` Given a quoted charge, Then the Consumer accepts or declines in the portal, and the acceptance is recorded with a timestamp. A verbal warning is never the record.
- **AC-E14** `[BE]` Given the technician's diagnosis, Then it resolves `pending_assessment` to `confirmed` on the branch that applied.
- **AC-E15** `[BE]` Given no pricing rules engine is in scope, Then prices are entered by a human. No rule-evaluated pricing exists.
- **AC-E16** `[BE]` Given a rejected Complaint, Then rejection is a **terminal resolution outcome** and counts in resolution statistics (so rejecting is not the fast path to a good number).

## Group F - Service Jobs, dispatch and the technician

- **AC-F1** `[BE]` Given `service_jobs`, Then it carries `source_entity_type` / `source_entity_id` (polymorphic requester), site, window (`scheduled_from` / `scheduled_to`), status, and the clocks `proposed_at`, `confirmed_at`, `arrived_at`, `completed_at`.
- **AC-F2** `[BE]` Given the status graph, Then it is `Unscheduled -> Proposed -> Confirmed -> In progress -> Completed -> Verified`, plus `Proposed -> Unscheduled` for a declined proposal and a terminal `Cancelled` reachable from the four pre-completion rungs, registered **FK-based** in the status engine (AC-A3a, moved out of S0 because the table does not exist until this slice creates it).
- **AC-F3** `[E2E]` Given a job in *Proposed*, Then it cannot reach *Confirmed* until the customer's agreement is recorded. `Service Date: TBA` is not a valid *Confirmed*.
- **AC-F4** `[BE]` Given a job past its date still in *Proposed*, Then it appears as a **stall** on the dashboard with the elapsed stall time.
- **AC-F5** `[FE][E2E]` Given the dispatch board, Then jobs group by day and technician and can be reassigned by drag. No availability grid, skills matrix, geo-clustering or capacity optimiser exists.
- **AC-F6** `[BE]` Given `technicians`, Then it is its own entity, bound to a `respond_contact`, and **no technician has a `users` row created for them**.
- **AC-F7** `[BE]` Given `service_job_assignments`, Then a job may carry more than one technician, each with its own assignment state (ecohub `ServiceJobAssignment` shape).
- **AC-F8** `[E2E]` Given a technician opens the portal, Then they see **today's jobs only** - no listings, no search, no records but their own - and each job shows site, contact, fault and the Consumer's photos.
- **AC-F9** `[E2E]` Given the job screen, Then the actions are *On my way* -> *Arrived* -> upload photos -> diagnosis -> *Complete*.
> **SUPERSEDED 2026-08-01 (R4/R5 grill).** `service_job_photo_types` and `service_job_photos` are
> **deleted**. They were a special case of a general thing. Photo validation is now a **core attachment
> validator** in the `resources` module: `attachment_types` gains `validation_guidance`, `min_score` and
> `validate_on_upload`, and photos are ordinary attachments whose link row carries `ai_score`,
> `ai_suggestion`, `override_reason`, `latitude`, `longitude`. ACs F10 to F18 below are restated in
> **Group M** against that design. This is a simplification, not an addition.

- **AC-F10** ~~`service_job_photo_types` master data~~ - see **AC-M20**.
- **AC-F11** `[BE]` Given photos, Then each stores type, `latitude`, `longitude`, AI score, AI suggestion, and any override reason.
- **AC-F12** `[E2E]` Given the required set (at minimum one `start` and one `completion`), Then a job cannot reach *Completed* without it.
- **AC-F13** `[E2E][AI]` Given a photo upload, Then validation runs **synchronously, on upload, while the technician is still on site**, scoring it against that type's `guidance`.
- **AC-F14** `[E2E][AI]` Given a score below `min_score`, Then the suggestion is shown in plain language ("*step back and include the pipe joint*"), **Retake** is the prominent action, and **Use anyway** requires a reason.
- **AC-F15** `[BE][AI]` Given the validator, Then its prompt lives in `ai_prompt_registry` and the per-type `guidance` is data. No hardcoded branch per photo type exists.
- **AC-F16** `[E2E]` Given location permission is denied or GPS unavailable, Then coordinates are omitted and the job **still completes**. Geotag is captured in the background and is never a blocker.
- **AC-F17** `[E2E]` Given a dropped connection mid-completion, Then progress is saved server-side and uploads retry. No offline sync queue is built; a lost signal costs a retry, not a revisit.
- **AC-F18** `[E2E]` Given a Consumer-submitted photo at intake, Then the same validator checks it against its type guidance, because bad evidence at intake is what wastes a site visit.
- **AC-F19** `[E2E]` Given the technician portal, Then it is usable and non-clipped at **375px**, and any modal scrolls to its submit button.
- **AC-F20** `[BE]` Given a Complaint needing two visits, Then two Service Jobs exist against one Complaint, and **first-visit fix rate** is derivable.
- **AC-F21** `[BE]` Given technicians are measured individually, Then attend time (`confirmed_at` -> `arrived_at`), first-visit fix rate and repeat-visit rate compute per technician from job clocks, **not** from form-SLA trackers.
- **AC-F22** `[BE]` Given form-SLA assignment resolves via `agent_teams` -> `team_members` -> `users`, Then no Service Job clock is implemented as a form-SLA stage, and no technician is ever an SLA assignee or subject to a handling lock.
- **AC-F23** `[E2E]` Given the Complaint's **Schedule** stage (a form-SLA tracker owned by CS), Then it resolves the moment its Service Job reaches *Confirmed*. CS is accountable for a confirmed date; the technician for arriving.

## Group G - Goods track (exchange and replacement)

- **AC-G1** `[BE][MIG]` Given `complaint_fulfilment_orders`, Then it gains a **link role**: `rma` (collect back) / `replacement` (REP) / `credit_note`. Today's 12 rows are backfilled by inspecting the linked order's `order_type`.
- **AC-G2** `[E2E]` Given RMA and REP already arrive from AutoCount as `orders` (1,732 `RMA-*` rows with 1,731 carrying a dealer; 2,864 `REP*` rows), Then linking is a **link**, not a creation. No RMA or REP document is generated by this module.
- **AC-G3** `[E2E]` Given the real May 2026 case, Then `RMA-SRT2605-0107` and `REP202605-0187` both link to one Complaint for HANLIM TRADING, and `RMA-SRT2605-0118` links to the LIVING PORTAL Complaint.
- **AC-G4** `[E2E]` Given CS searches to link, Then they can find an RMA or REP by number and see the dealer on it, so the office never retypes a number a person read out in a chat.
- **AC-G5** `[BE]` Given existing auto-fulfilment behaviour, Then the `processed_by_cs` <-> `fulfilled` recompute and `LINKABLE_STATUSES` gating continue to hold with link roles present.
- **AC-G6** `[E2E]` Given a collect-back precedes a replacement (`"this item already discon & no stock, I will arrange to collect back defect unit first ya"`), Then both links coexist on one Complaint with distinct roles and a single SLA thread.

## Group H - Notifications and the Respond outbox

- **AC-H1** `[BE][MIG]` Given `notifications.user_id` is currently `NOT NULL`, Then it becomes nullable, `respond_contact_id` is added, and the unique index on `(user_id, source_entity_type, dedup_key, event_type)` becomes partial so both recipient kinds dedupe correctly.
- **AC-H2** `[BE]` Given any notification, Then exactly one spine records it regardless of whether the recipient is a user or a contact. WhatsApp joins `in_app` / `email` / `web_push` as a channel.
- **AC-H3** `[BE]` Given a contact recipient, Then no per-event preference toggles apply: they receive WhatsApp plus the portal. Preference toggles remain a staff-only feature.
- **AC-H4** `[E2E]` Given the notification matrix, Then it is honoured as specified: Lodged (Submitter ack + number, Dealer, Salesperson, CS) - Warranty assessed (Submitter, Dealer, Salesperson) - Approved/rejected (Submitter, Dealer, Salesperson) - Charge quoted (Submitter, Consumer, Salesperson) - Visit proposed (Submitter, Consumer, Technician) - Visit confirmed (Submitter, Consumer, Dealer, Salesperson, Technician) - En route (Submitter, Consumer) - Completed with proof (Submitter, Consumer, Dealer, Salesperson) - Replacement dispatched (Submitter, Dealer, Salesperson) - Feedback survey (Submitter, Consumer).
- **AC-H5** `[E2E]` Given the Consumer is not the Submitter, Then they receive **no lodgement acknowledgement**, only messages about something they must know or act on.
- **AC-H6** `[E2E]` Given SLA breach or escalation, Then **only the tier escalated to** is notified, resolved by `resolve_team_with_tier_fallback` and gated by the stage's `notify_on_escalation` plus each member's own toggles. Salesperson and CS are **not** notified as a fixed list.
- **AC-H7** `[BE]` Given every Respond.io send, Then an `integration_logs` row is written on **success and failure** (a 401 with intentionally-wrong local credentials must still appear), stamping the actually-attempted payload.
- **AC-H8** `[BE]` Given a send tied to a notification, Then `correlation_id` = the notification id and `business_table` / `business_id` = the Complaint, so the outbox can render event context.
- **AC-H9** `[E2E]` Given the Respond outbox screen, Then it renders event-first (`Complaint CMP2026-0123 - Visit confirmed - to Mr Vinod (017-3336634) - WhatsApp template - FAILED 401`) with the raw payload behind a disclosure.
- **AC-H10** `[E2E]` Given AI replies and n8n-initiated sends that carry **no** notification, Then they **still appear** in the outbox. The outbox is a **left join** over `integration_logs`, never an inner join.
- **AC-H11** `[BE]` Given `integration_logs.business_id` is a UUID column, Then a real UUID is always used, never a composite string key.
- **AC-H12** `[BE]` Given post-commit side effects (notification writes after the Complaint commits), Then they catch and warn, never raise, so a succeeded operation never returns 500.
- **AC-H13** `[BE]` Given WhatsApp sends, Then the workspace key is resolved via `RespondClient.for_identifier(...)`, not `settings.respond_api_key`.
- **AC-H14** `[BE]` Given a send to a contact outside the messaging window, Then a template is used and the outbox records it as a **template** attempt, not a text attempt.

## Group I - Feedback survey

- **AC-I1** `[BE][MIG]` Given `workflow_submissions`, Then it gains nullable `respondent_contact_id` -> `respond_contacts` and a `source_entity_type` / `source_entity_id` pair, so any form can be attached to any entity and answered by a non-user.
- **AC-I2** `[E2E]` Given the satisfaction survey, Then it is an ordinary workflow form definition, designable in the existing designer and versioned like any other. No dedicated `complaint_feedback` table exists.
- **AC-I3** `[E2E]` Given a Complaint resolved, Then **one working day later** (via `work_calendar_configs` + `public_holidays`) a WhatsApp message is sent carrying a `PortalToken` link to the survey.
- **AC-I4** `[E2E]` Given a response, Then it is logged against the Complaint and visible on its detail page.
- **AC-I5** `[BE]` Given the forms-versus-job line, Then forms hold prose (survey, optional per-kind technician checklist) and the Service Job holds facts the system reasons about (photos, diagnosis, charge state, timestamps). Diagnosis and proof photos are **never** stored only in `row_data` JSONB.
- **AC-I6** `[E2E]` Given one Complaint, Then exactly one survey is sent no matter how many Service Jobs or linked orders it had.

## Group J - Reporting and performance

- **AC-J1** `[E2E]` Given the operational view, Then open Complaints show by stage and by PIC with SLA risk colour-coding.
- **AC-J2** `[E2E]` Given the performance view, Then response and resolution time report by week, month, PIC, product category and dealer, in working hours.
- **AC-J3** `[E2E]` Given the customer-experience view, Then survey score trend, Complaints by category and recurring defect types (from diagnosis) are shown.
- **AC-J4** `[BE]` Given stage attribution, Then each stage has exactly **one** accountable party from its tracker's assignee, and no blended per-person resolution time is reported across stages.
- **AC-J5** `[BE]` Given **stall time**, Then it is reported per Complaint and per stage as time spent with nobody acting. This is the metric that surfaces `No arrange??`.
- **AC-J6** `[E2E]` Given a technician, Then attend time, first-visit fix rate and repeat-visit rate are reported individually.
- **AC-J7** `[E2E]` Given the dashboard, Then it exports to Excel and PDF, and KPI targets are configurable (default: response 2 working days, resolution 14 working days).
- **AC-J8** `[FE]` Given every listing, Then it uses the shared `DataGrid` with `tableLayout: { width: 'fixed', columnsResizable: true }`, explicit `size` per column and `truncate` + `title` on long text. No hand-rolled `table-fixed`.
- **AC-J9** `[FE]` Given every dropdown, Then it uses `SearchableSelect` / `SearchableMultiSelect`. No `ui/select`, no raw `<select>`.
- **AC-J10** `[FE]` Given every detail page, Then **every section renders** with an explicit empty state and next-step CTA, never hidden on missing data.
- **AC-J11** `[FE]` Given all datetimes, Then they render via `formatDateTimeInMalaysia(rawString)`, and the MCP emits **naive** Malaysia wall-clock (not offset-aware).

## Group K - Data, migration and guards

- **AC-K1** `[BE][MIG]` Given every new column on an entity with existing rows, Then a **backfill** migration runs, using idempotent JOIN-based "set where mismatch", not "update where NULL".
- **AC-K2** `[BE][MIG]` Given `alembic`, Then every new `down_revision` chains onto a **committed** main head, revision ids are <= 32 chars, and `alembic heads` shows a single head.
- **AC-K3** `[BE][T]` Given tests, Then they run on **Postgres only**. No sqlite engine, no `@compiles(..., "sqlite")`, no mutation of shared `Base.metadata` column types. Committed tests use a private `zzt_` scratch schema.
- **AC-K4** `[BE][T]` Given test cleanup, Then every `DELETE` is scoped to marker rows. The local DB is a copy of production data; an unscoped delete destroys real records.
- **AC-K5** `[BE]` Given new columns reaching the FE, Then they are added to **both** manual dict builders where one exists. Schema inheritance alone silently drops them.
- **AC-K6** `[BE][MIG]` Given the retired groups, Then a one-off import of the two `_chat.txt` exports plus their 1,238 media files is **out of scope** and recorded in `documentation/backlogs/backlog.md`.
- **AC-K7** `[E2E]` Given every destructive or detaching action (delete, **and unlink** of an RMA/REP or a Service Job), Then an `AlertDialog` confirmation appears with "This action cannot be undone" and a count for bulk actions. Never `confirm()`, never one-click.
- **AC-K8** `[BE]` Given `DELETE` endpoints, Then they hard-delete. Any retention action is named **Archive**.
- **AC-K9** `[FE][E2E]` Given every new surface, Then it is verified by real sidebar clicks from `/` (never a deep URL), at **375px and 1280px**, against a **production build** before handoff.

---

## Out of scope (recorded, not forgotten)

- Optimising scheduler: availability grids, skills matrix, geo-clustering, van capacity (Q8 option A).
- Full billing: invoicing and payment collection. `AutoCount` already does this (Q11 option C).
- Pricing rules engine (AC-E15).
- Consumer sign-off signature on the technician's phone (Q19).
- Offline / PWA sync queue for the technician portal (AC-F17).
- Soft module dependencies. `complaints` hard-depends on `warranty` and `service_jobs`; the seam gets cut when a second customer wants Complaints alone.
- Historical chat import (AC-K6).

## Open, pending Sorento (not blocking build)

1. **Policy clause 17** - cover is residential only, commercial and industrial excluded, yet 23 of 50 existing Complaints are Project cases. Modelled, not enforced (AC-D15).
2. ~~Who takes the money~~ - **RESOLVED 2026-07-26: Sorento invoices afterwards; the technician collects nothing.** No cash-capture surface on the technician screen.
3. ~~Who owns the burst debounce timer~~ - **RESOLVED 2026-07-26: the n8n wait node owns it.** The CRM stays stateless for intake and gains no scheduled job.
4. **Salesman code suffixes** - whether `SEAN` / `SEAN I` / `SEAN III` / `SEAN IV` are one person or several, per code (AC-B11). Confirmed **not** to be a company split.
