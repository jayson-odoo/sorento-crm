# PLAN - After-Sales, Warranty & Service Scheduling

**Status:** **In build. S0, S1, S2, S2a, S2b, S4 and S4a implemented; forms-platform F0 to F2c implemented
alongside them.** Migrations 310 to 321. **S3-pre is RUN (2026-08-03) and passed** - see
`S3-pre-extraction-accuracy.md`. **Fork 6's PDPA notice is BUILT** (migration 322,
versioned + bilingual + admin-editable), so S3's second hard gate is closed too. Next slice:
**S3** (consumer portal intake). Outstanding for Sorento rather than for the build: sign-off
on the Malay wording, and whether the 31 `warranty_product_kinds` get real
`consumer_icon`s or the AC-C11 tiles fall back to text. Everything below the "In build, S0" history is the
original plan text, amended in place.

Plan written 2026-07-26 from a completed grill (19 decisions). S0 rewritten
2026-08-01 after discovering the status engine already existed (ADR-0012): engine adopted, sibling alembic
heads merged, complaint registration in progress. Forms-platform F0 is in build in parallel (343 tests
authored test-first, implementation under way).
**Group M slotted 2026-08-02, before S1.** All of `AC-M1` to `AC-M40` now belongs to a slice - see
"Group M slotting" under the slice sequence. Two slices added (**S2a** core attachment validator, **S4a**
waiting attribution); ten conflicts between Group M and existing slice text are recorded under
"Group M conflicts with existing slice text" and need decisions before the slices they sit in are built.
**UAC (the contract this fulfils):** `after-sales-warranty-acceptance-criteria.md` - every section below cites the ACs it satisfies.
**Decisions:** `adr/0008` one Complaint per issue - `adr/0009` Service Job is requester-agnostic - `adr/0010` Warranty Terms scope to Kind - `adr/0001` status engine is core - `adr/0007` a Dealer is a Customer.
**Vocabulary:** root `CONTEXT.md` (`Complaint`, `Submitter`, `Service Job`, `Site`, `Technician`, `Warranty Term`, `Warranty Product Kind`, `Dealer`, `Consumer`).
**BRD:** Cluster D, Requirements #5 to #13.
**Branch:** `worktree-after-sales-warranty`.

> **ENGINE PIVOT, 2026-08-01.** The two after-sales flows are built as **workflow form definitions** on the
> forms platform, not as bespoke tables - `adr/0011` supersedes `adr/0008` narrowly. This plan therefore
> **depends on `plans/forms-platform/PLAN-forms-platform.md` F0 to F2** (document model · status on the
> submission · the SLA / portal / notification / attachment integration layer) and explicitly **not on F4**,
> so migrating the four existing forms is never on this feature's critical path.
>
> Sections below that assume bespoke `complaints` columns need rereading against that pivot. The
> **child-table shape survives unchanged** (product lines, Service Jobs, linked RMA/REP orders), as does
> everything in `adr/0009` and `adr/0010`. What changes is the case table.
>
> The discovery study (`flowcharts/Sorento_Operational_Discovery_Study_CS.pdf`) also split after-sales into
> **two flows**, not one: an **exchange/return request** (commercial - CS gate, optional RMA, closes against
> a REP or CN) and a **service complaint** (attendance, spare parts, plumber). New requirements from that
> reading are captured ungrilled in `REQUIREMENTS-inbox-2026-08-01.md`.

## Why this exists commercially (read before the schema)

> **Grilled 2026-07-29 to 07-31. All seven forks answered**, recorded in
> `OPEN-consumer-ledger-grill.md`. Sorento's positions: **consent is warranty-and-service only**
> (erasure anonymises the person, retains the purchase); **the dealer relationship is reciprocal** (dealers
> see complaints and service history for their own customers); **dealer-margin visibility is intended.**
>
> **Two consequences still need a decision, both flagged in the grill doc:** margin granularity (fork 4
> captured header-only value, so per-product margin is not computable) before S9, and confirmation that
> service-only consent is understood as effectively permanent before S3.
>
> **Cleared 2026-08-01:** the **bilingual PDPA notice** is available (Sorento confirmed), so S3's consent gate
> is satisfiable - the Malay wording still has to be written by someone who writes it properly. And
> **Respond.io does expose calls** via the n8n node's `On Call ended` trigger, so R9's auto-enrich path is
> real rather than speculative.

**To capture consumer data by bypassing the dealer.** Sorento sells through dealers and so has no idea who owns its products. A complaint is the one moment a consumer volunteers their identity, address, purchase and receipt. The warranty verdict and the service visit are the value Sorento gives; **the purchase ledger is what Sorento keeps.**

Every lodgement must therefore leave behind, permanently: a **Consumer profile** that persists across complaints, **which Dealer they bought from**, **that dealer's own document number**, **the value if the receipt shows it**, **product and quantity**, **purchase date**, and **the receipt document itself**. The BRD says it more quietly - *"the added value of warranty registration to Sorento is to have the sales data from the dealership indirectly."*

This is why `warranty_registrations` is a **purchase record**, not a warranty flag, and why receipts are retained rather than discarded after extraction (Group L in the UAC).

## Classification (recorded per `PRINCIPLES.md`, before UAC)

| piece | class | deps | schema |
|---|---|---|---|
| status engine | **CORE** | - | `public` |
| `consumers` | **MODULE** (new) | `base`, `product`, `order` | `public` |
| `service_jobs` | **MODULE** (new) | `base`, `resources` | `public` |
| `warranty` | **MODULE** (new) | `base`, `product`, **`consumers`** | `public` |
| `complaints` | MODULE (existing, deps grow) | `+ order, product, sla, notifications, workflow_forms, consumers, warranty, service_jobs` | `public` |

**`consumers` owns the strategic asset, and `warranty` only reads it** (fork 7, resolved 2026-07-29). Applying the uninstall test: turning off `warranty` must not take the consumer list or the sell-through ledger with it, because those are durable business records and warranty's policies are not. So:

| `consumers` module (durable) | `warranty` module (its own artifacts) |
|---|---|
| `consumer_profiles` - identity, addresses, consent | `warranty_policies` - versioned policy text |
| `consumer_purchases` - dealer, dealer doc no., product, qty, value, date, receipt | `warranty_terms` - part / duration / defect scope |
| | `warranty_product_kinds` + `warranty_kind_rules` |
| | `warranty_assessments` - computed verdicts |

Not **CORE**: core is currently exactly one module (`base`), and consumer data would be the first domain data in it. A company selling **through a channel** installs `consumers`; a company selling **direct** already knows its customers and never would. That is a real tenant-level switch, which is the definition of a module.

Not named **`purchase`**: `procurement` already owns purchase requests, SPOs and GRNs, and `orders.order_type` has `PO`. Those are Sorento buying **from suppliers** - the opposite direction. A `purchase` module beside `procurement` would be indistinguishable within months.

No dedicated Postgres schema. `scm.*` earned its namespace as a self-contained analytical engine; after-sales threads through `orders`, `products`, `customers` and `attachments`, so cross-schema FKs would buy ceremony and nothing else. Satisfies **AC-A4, AC-A7**.

---

## Slice sequence

Each slice is a tracer bullet: schema -> service -> route -> UI -> tests, shippable and verifiable on its own. S0 and S1 are enablers with no end-user value, and are flagged as such rather than dressed up.

| slice | delivers | gated by |
|---|---|---|
| **S0** | complaint registered on the ADOPTED status engine (CORE) - not a port, see ADR-0012 | the engine reaching `main` (`0ec9875d2`, currently on the project-sales branches). **Dealer Kit S2.5 shares this dependency** |
| **S1** | parties: the portal knows who you are without asking | S0 |
| **S2** | warranty engine + policy Q&A: CS sees a verdict, AI answers policy questions | S1 |
| **S2a** | **core attachment validator** (`resources`): typed upload guidance, synchronous AI score, retake affordance | nothing after-sales-specific (`resources` + `ai_prompt_registry` both exist). **Must land before S3** |
| **S3** | consumer portal intake: a Consumer can lodge a Complaint | S1, S2, **S2a**, **S3-pre spike**, bilingual consent notice (available) |
| **S4** | notification spine + Respond outbox + calls + assignment fallback: everyone is told, nobody is silently unassigned | S1 |
| **S4a** | **waiting attribution**: the system can say "waiting on someone who is not us" | S4. **Must land before S6, S11, S12 and S9** |
| **S5** | WhatsApp AI intake: Sean's eight seconds. Plus the `On Call ended` automatic call path | S3 (contract), S4 |
| **S6** | Service Jobs, dispatch board, technician portal, external providers and case cost | S0, S4, **S4a** |
| **S7** | goods track: RMA/REP link roles | S4 |
| **S8** | feedback survey on workflow forms | S4, S6 |
| **S11** | **exchange/return request flow**: dealer submits, CS gates per line, dispositions, readiness gate | F0-F2, F1a, S4, **S2a**, **S4a** |
| **S12** | **RMA lifecycle**: own status, age, owner; cross-request container; closes against REP or CN. Retires the "RMA summary" Excel | S11, S7 |
| **S10** | **dealer reciprocal view**: a Dealer sees complaints and service history for their own customers | S6, S7 |
| **S9** | reporting and dashboards, incl. dealer sell-through | S2, **S4a**, S6, S7, S8, S10 |

**The two WhatsApp groups can only be retired after S5 + S6 + S7.** Until all three land, some traffic has nowhere to go. State this to Sorento explicitly; a half-retired group is worse than an intact one.

### Group M slotting (added 2026-08-02)

Group M (`AC-M1` to `AC-M40`) arrived from the 2026-08-01 requirements grill **after** this sequence was
written, and no slice claimed any of it. Every AC is placed below. Nothing is silently dropped, and nothing
appears twice. Two slices are new (**S2a**, **S4a**); the reasoning for each is in its own section.

| AC | slice | note |
|---|---|---|
| AC-M1 to AC-M7 | **S4a** (new) | waiting attribution. The single design behind R2, R7, R8, R12. See "Why its own slice" below |
| AC-M8, AC-M9, AC-M10 | **S11** | **ALREADY BUILT** by forms-platform F1a. S11 inherits, does not implement |
| AC-M11 | S12 | RMA as a cross-request collection container |
| AC-M12 | S12 | RMA link is a LINE attribute. **Conflicts with S7's header-grain link table - see S7** |
| AC-M13 | **S11** | disposition option **already built**; the mandatory reason is **not enforced** - S11 owns that thin guard |
| AC-M14, AC-M15, AC-M16 | S12 | RMA own lifecycle / closes against REP or CN / local versus outstation sequencing |
| AC-M17, AC-M18, AC-M19 | S11 | collection readiness gate. AC-M18 depends on S4a |
| AC-M20 to AC-M25, AC-M27 | **S2a** (new) | the validator mechanism, in `resources`, used by S3, S6 and S11 |
| AC-M26 | S11 | the `rma_readiness` type and its three guidance strings: **data seeded by S11**, not a feature |
| AC-M28, AC-M29, AC-M30, AC-M31 | S6 | `external_providers` master + `case_cost_lines`, bookkeeping only |
| AC-M32 | S9 | spend per provider and cost per case in reporting |
| AC-M33 | S4 | assignment fallback. **Changes CORE form-SLA behaviour - see S4** |
| AC-M34, AC-M35 | S4 | the manual call path and the attribution rule. Stands alone (AC-M36e) |
| AC-M36, AC-M36a, AC-M36b, AC-M36c, AC-M36e, AC-M36f | S5 | the `On Call ended` automatic path: n8n owns the subscription, CRM exposes `call_log_submit` |
| AC-M36d | **S4a** | repeated unanswered calls are the evidence that justifies `waiting_on = customer` |
| AC-M37 | S1 | Site carries `latitude` / `longitude` / `place_id` **and** the typed address (settled 2026-08-02) |
| AC-M38, AC-M39 | S3 | pin optional, never blocking; pin and address both kept, neither reconciled |
| AC-M40 | S3 | **deployment gate, not build work.** Rides S3's release checklist because S3 is what puts a Maps key on a public page |

**Where Group M contradicts a slice**, the contradiction is stated in that slice's section rather than
resolved by quietly editing the slice. There are six, and they are listed together under
"Group M conflicts with existing slice text" at the end of this document.

---

## S0 - Register on the status engine (CORE)

Satisfies **AC-A1, AC-A2, AC-A3**.

**REWRITTEN 2026-08-01. There is no port to do.** The engine already exists: commit `0ec9875d2` on the
project-sales branches ships it as CORE, and the shared dev database already has it. This slice **adopts** it
rather than porting a second time. See `../../adr/0012-adopt-the-existing-status-engine-rather-than-porting-it-twice.md`
for the decision and for the three reasons the duplicate stayed invisible (a filesystem-only `alembic heads`,
two branches both numbering their migration 308, and `blank_session()` building from `Base.metadata` rather
than from migrations, so a duplicate port went fully green against a schema the real database could never have).

Done so far: `0ec9875d2` cherry-picked, its 52 tests green in this tree, and the resulting sibling heads
(`308_status_engine` and `308_requestor_uploader_attr`, both off `307_admin_listing_company`) rejoined by the
empty `309_merge_status_engine`. `workflow_stages` is dropped by the adopted migration, so AC-A1 is met by
adoption; AC-A2's `UUID(as_uuid=False)` rule is already satisfied by the adopted models.

What remains is only the after-sales-specific part: **register `complaint`**, seed its default graph, and
guard transitions.

The one adaptation that matters: the engine is **FK-based** (`assert_transition_allowed` works on status ids,
`StatusEntity.status_attr` defaults to `status_id`), while `complaints.status` is a bare `VARCHAR(50)` holding
the key itself, with no FK and no CHECK, over 51 live rows. We add a thin **key-valued adapter** over the
existing id-based guard (`StatusGraph.by_key` already exists) rather than adding a `status_id` FK and
migrating the rows. Adding the FK would touch every branch site and destroy the property that makes this
slice safe.

The graph is **12 keys, not 11** - `resolved` is a live comparison target in `_VOID_BLOCKED_STATUSES` and in
both frontend pill maps. Edges, flags and colours are specified with a file:line citation each in
`status-graph-evidence.md`, which also records four errors in the first attempt: an invented `draft -> new`
edge (there are genuinely **two** entry points), an invented `submitted -> updated` edge that resurrected
deliberately-removed behaviour, a wrong colour for `voided`, and the unguarded `PUT /complaints/{id}` that
leaves the graph advisory rather than enforced.

**`service_job` moves out of S0.** Its table does not exist yet, so it registers FK-based natively in the
slice that creates it, not through the adapter complaints need.

Register two entity types with default graphs:

```
complaint    new -> submitted -> updated -> responded -> approved | rejected
                 -> processed_by_cs -> fulfilled | closed        (existing strings preserved)
service_job  unscheduled -> proposed -> confirmed -> in_progress -> completed -> verified
```

The `complaint` graph **must** reproduce today's exact status strings. 50 live rows carry them and `complaint_fulfilment_service` branches on `processed_by_cs` / `fulfilled` by name. This slice is a no-op for behaviour: same strings, now declared instead of scattered.

Reporting groups by `key`, never by status id (forked graphs re-key ids) and never by `category` (the source marks it a legacy cosmetic mirror).

> **Coordination:** Dealer Kit S2.5 is already blocked on this. Land S0 on `main` as its own PR before either feature continues, so both consume one port rather than two.

---

## S1 - Parties and identity

Satisfies **AC-B1 to AC-B12** (as corrected by **AC-B13 to AC-B21**), **AC-M37**. `technician_id` is
**not** in S1: AC-B13 defers it to S6. AC-B6a is unsatisfiable as written and was replaced by
AC-B6b / AC-B6c / AC-B6d.

**Status: implemented 2026-08-02.** Migration `316_after_sales_parties`; gate
`tests/test_after_sales_parties.py` (55) + `tests/test_after_sales_legacy_column_guard.py` (12) green.
The shared dev database is stamped on another worktree's chain, so the DDL is applied there by hand;
until it is, every live-DB (`pg_session`) suite touching `respond_contacts` / `complaints` fails with
`column "customer_id" ... does not exist`.

### Schema

**Updated 2026-08-02 to what actually shipped** in `alembic/versions/316_after_sales_parties.py`.
Three corrections against the original block, each forced by the red suite: the third binding is
deferred (AC-B13), the Site pin columns are unprefixed, and the code map needed a table.

```sql
-- respond_contacts: TWO independent nullable bindings, NO party_kind column.
-- technician_id is DEFERRED to S6 (AC-B13): `technicians` does not exist, so the
-- constraint cannot be created here, and a stub table would hand S6 a half-defined
-- core entity to migrate. derive_contact_kind already reads it defensively.
ALTER TABLE respond_contacts
  ADD COLUMN customer_id uuid    REFERENCES customers(id) ON DELETE SET NULL,
  ADD COLUMN user_id     varchar REFERENCES users(id)     ON DELETE SET NULL;
-- no door_answered_at: there is no door question to remember (see "The door" below)

-- complaints: parties get real homes
ALTER TABLE complaints
  ADD COLUMN customer_id uuid REFERENCES customers(id),  -- the Dealer
  ADD COLUMN site_address text,
  ADD COLUMN site_contact_name text,
  ADD COLUMN site_contact_phone text,
  -- AC-M37 / AC-B21: the Site is a typed address AND a pin. site_maps_url is NOT
  -- created. Unprefixed names, matching the S1 gate: there is exactly one Site per
  -- Complaint, so `complaints.site_latitude` would repeat the table it sits on.
  ADD COLUMN latitude numeric(10,7),
  ADD COLUMN longitude numeric(10,7),
  ADD COLUMN place_id varchar(128);
ALTER TABLE complaints ADD COLUMN reported_by_role varchar(20);   -- ADDED, not renamed

-- AC-B18: the sales-agent code map needs a persisted, upsertable home. `users` has
-- no code column and one person carries four codes, so a column could not hold them.
-- Deliberately NOT company-partitioned: every suffix appears under both Sorento and
-- Mocha, so the suffix is not a company split.
CREATE TABLE salesman_code_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  salesman_code varchar(100) NOT NULL UNIQUE,
  user_id varchar NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  notes text,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
```

### What AC-M37 changes about this slice

**Schema only, and only by getting the Site right the first time.** S1 originally gave the Site a single
`site_maps_url text`. AC-M37 says a Site carries `latitude`, `longitude`, `place_id` **and** the typed
address. Defining the Site twice - a pasted URL now, coordinates later - is a second migration on the same
concept plus a decision about whether the URL survives, so `site_maps_url` is **dropped from this slice
before it is ever written**. No behaviour is added here: capturing a pin is the consumer form's job
(AC-M38, S3) and navigating to one is the technician's (S6). S1 only provides somewhere for it to land.

A pasted `maps.app.goo.gl` link (which the chat log shows people already doing by hand) is not a
substitute: it is opaque, it cannot be geocoded, and it cannot be reverse-looked-up to a place. If a
paste-a-link affordance is wanted later it resolves to these three columns rather than adding a fourth.

**Additive, not a rename.** `reported_by_role` is a new column backfilled from `customer_type` via a documented mapping (`Project`, `SMC`, `E Commerce` were account categories, not reporters). ~~the 7 blanks become `cs`~~ **corrected 2026-08-02 (AC-B16): blanks backfill to NULL.** Counted against the live table (47 rows): `Project` 24, `SMC` 7, `Salesperson` 5, `Dealer` 4, NULL 3, `End User` 3, `E Commerce` 1 - so the "7" was the `SMC` count, and mapping an unknown value to `cs` would assert Customer Service reported those complaints, which nothing supports. 32 of 47 rows stay NULL. `Salesperson` is in the map despite being absent from the configured lookup options (AC-B17). `customer_type` is **left in place, read-only, for one release** and dropped later, exactly like `customer_name` and `salesperson`. Renaming a column on a live table with 50 rows buys nothing and makes the migration irreversible mid-release; adding one is reversible by ignoring it. A guard test asserts nothing **reads** the legacy columns, so the eventual drop is a pure deletion.

### Kind derivation (AC-B2)

Never stored. `customer_id` set means dealer staff; `user_id` set means Sorento staff; `technician_id` set means technician; none set means Consumer. **More than one may be set** - the Sanimart case (a dealer's owner reporting a fault in his own home) sets `customer_id` and still resolves the Site to his house, because the Site lives on the Complaint (**AC-B3**).

**As shipped:** `app/services/party_service.py`. Precedence is declared data, not branches - `KIND_PRECEDENCE = ("technician", "staff", "dealer", "consumer")` (AC-B14), with `BINDING_FOR_KIND` naming the column per kind so S6 adds one entry and changes nothing else. `derive_contact_kind(contact)` is a pure function of the row, no query (AC-B15), and reads the deferred third binding via `getattr(contact, "technician_id", None)`. All four kinds ship in S1 even though `technician` is unreachable: the journey route is a public contract consumed by the portal FE and by n8n, neither of which deploys atomically with the backend, so widening a three-member literal later would be a breaking change with a silent failure mode.

### Salesperson: seed once, read forever (AC-B7 to AC-B11)

`customers.account_owner_user_id` is 0 of 3,284. A one-off script, not a runtime path:

1. Build a `salesman_code -> users.id` map, **persisted in `salesman_code_users`** and read by the seed, never hardcoded (AC-B18): `load_salesman_code_map(db)` / `upsert_salesman_code(db, code, user_id)`. **Sorento creates the `users` rows** for salesmen (needed for Project Management anyway); the seed script creates stand-in users locally for testing only. 83 distinct codes; suffixes (`SEAN` / `SEAN I` / `SEAN III` / `SEAN IV`) collapse many-to-one where they are one person. **Confirmed not a company split** - every suffix appears under both Sorento and Mocha in `orders`. Junk codes (`0`, `ACT`, `CS01`, `WH02`, `MARKETING`, `SAMPLE`, `FUNITURE`, `TERA`) map to nothing.
2. Per customer, take the salesman on their **most recent** order. 2,191 resolve to a single code; 322 are multi and get most-recent-wins as a seed.
3. Write `account_owner_user_id`. Idempotent JOIN-based "set where mismatch", so a re-run corrects a prior bad run (**AC-K1**).

Page by **keyset**, not `yield_per` - a named cursor dies on commit. Dry-run must assign nothing (beware autoflush) and be verified at `--batch 1`. Most-recent-wins is ordered `order_date DESC NULLS LAST, order_number DESC, id DESC` (**AC-B19**): `order_date` is nullable and Postgres sorts NULLs first on `DESC`, and a same-day tie broken arbitrarily makes the seed non-idempotent. The seed **sets its own company scope to all-companies** (**AC-B20**) - a bare `SessionLocal` is `UNSET`, which is fail-closed to zero rows, so the naive script exits 0 having done nothing.

**Runtime reads only `customers.account_owner_user_id`.** A **module-scoped** guard asserts the new party service references none of the legacy columns (**AC-B6c**); the repo-wide form of **AC-B9** is permanently red and was replaced by the frozen reader inventory (**AC-B6b**) plus the behavioural test (**AC-B6d**). Unresolved (~770 dealers with no orders) routes to the after-sales team lead and flags the Complaint `salesperson unresolved` - never silently dropped (**AC-B10**).

### The door: there isn't one (AC-B4, AC-B5, AC-B5a, AC-B5b)

**No question is asked.** Kind resolves by elimination: `customer_id` means dealer staff, `user_id` means Sorento staff, `technician_id` means technician, **nothing set means Consumer**.

```
GET  /api/v1/public/portal/journey
     -> { journey: 'consumer'|'dealer'|'staff'|'technician', dealer_name: string|null }

POST /api/v1/public/portal/journey/order-lookup   { order_number }
     -> { matched: bool, journey: ..., dealer_name: string|null }
```

Both require `X-Portal-Token` (401 without). The response carries **no identifiers** - the portal is a
frontend, so the Dealer is named, never identified. An unresolvable order number is a **200 with
`matched: false`**, never a 4xx (AC-B4's dead end / AC-C14): a Consumer holding a dealer's own receipt
will type something that does not exist in `orders`, and a wall there hits exactly the people the
self-heal was not aimed at. A blank / whitespace-only `order_number` is a 422 - that is a scan of the
orders table, not a lookup.

This works because the bindings get populated: Sorento configures dealer contacts manually and creates `users` rows for salesmen (they need them for Project Management regardless). Reuses `PortalToken` + OTP; no new auth.

**The failure mode, and how it self-heals.** An unbound dealer contact would be mis-routed to the Consumer journey and asked for a receipt they do not hold. So the Consumer journey's first step accepts **either a receipt photo or a typed order number**. A quoted Sorento order number resolves against `orders`, and we write `respond_contacts.customer_id` from that order's customer and switch them to the dealer track. The binding repairs itself, silently, without a question ever being asked - which is strictly better than a door question, because it also fixes contacts nobody remembered to configure.

**An existing binding is never re-pointed.** The self-heal repairs an ABSENT binding only. A contact Sorento configured is a deliberate act, and moving them to another Dealer because somebody pasted an order number would silently re-route their complaints, their notifications and their salesperson. The write lives in `party_service.self_heal_dealer_binding`, not on the route, so the S5 WhatsApp intake inherits the same rule (ADR-0013 rule 7).

### Seeding for test (AC-B12)

`scripts/seed_dealer_contacts.py` populates representative `respond_contacts.customer_id` bindings for local and staging. **Production bindings are configured manually by Sorento.** No bulk import ships.

---

## S2 - Warranty engine

Satisfies **AC-D1 to AC-D7, AC-D13, AC-D15**. This is a **deterministic engine, so it is test-first**: the golden set is written as failing tests before any implementation, per `PRINCIPLES.md` step 4.

### Split into S2 and S2b - decided 2026-08-02, before the slice started

**The original S2 bundled two modules and this section still shows both.** The schema below carries the
warranty tables AND `consumer_profiles` / `consumer_purchases` / `consumer_purchase_lines` /
`warranty_assessments` - and the plan's own comment already marks the second group `module: consumers
(NOT warranty, NOT core - fork 7)`. They are separated because they genuinely are separable, not to make
the slice smaller:

`resolve(kind, purchase_date, defect_type, registered?)` takes **plain values, not a purchase row**. The
entitlement engine never reads a consumer, a profile or a receipt: it answers from the policy in force on
a date. So the deterministic core can be built and proven against the golden set with no consumer table
in existence, which is exactly the property that makes it testable first.

- **S2 (this slice)** - `warranty_product_kinds`, `warranty_kind_rules`, `warranty_policies`,
  `warranty_terms`, the `resolve` algorithm, the golden set, and the AC-D13 guard. Pure, deterministic,
  no AI, no identity, no consent.
- **S2b** - the consumer module: `consumer_profiles` (consent, provisional promotion, anonymisation),
  `consumer_purchases` + lines (the dedupe key), `warranty_assessments` (one per complaint product line),
  and AC-D8's auto-created Registration. This is where PDPA-shaped decisions live, and it deserves its
  own grill rather than riding along behind a lookup table.
- **AC-D14 (policy Q&A)** is an AI surface restricted to `policy_text`, so it is a different risk class
  again and lands with S2b at the earliest. It cannot be built before `warranty_policies` exists, which
  is this slice.

Keeping them together would have meant writing the consent model, the anonymisation path and the receipt
dedupe key in the same breath as a date-arithmetic function whose whole virtue is that it is boring and
provable.

### Schema

```sql
CREATE TABLE warranty_product_kinds (      -- ~31 rows from Policy v15
  id uuid PRIMARY KEY, code varchar(64) UNIQUE, name varchar(255),
  consumer_label varchar(120),             -- what the tiled chooser shows
  consumer_icon varchar(64), sort_order int, is_active boolean
);

CREATE TABLE warranty_kind_rules (          -- how a product resolves to a Kind
  id uuid PRIMARY KEY, kind_id uuid REFERENCES warranty_product_kinds(id),
  match_type varchar(20),                   -- 'category' | 'model_prefix' | 'model_list' | 'series'
  match_value text, priority int            -- most specific wins
);

CREATE TABLE warranty_policies (            -- versioned, dated, COMPANY-SCOPED (AC-D16)
  id uuid PRIMARY KEY, version varchar(32),           -- 'v15'
  effective_from date NOT NULL, effective_to date,    -- both ends inclusive
  source_attachment_id uuid REFERENCES attachments(id),  -- the PDF, for Req #12
  policy_text text,                         -- extracted, what the AI is restricted to
  company_id uuid NOT NULL REFERENCES companies(id),  -- AC-D16, see the note below
  UNIQUE (company_id, version)
);
-- company_id is AC-D16 and was NOT in the original plan. `companies` holds both Sorento and Mocha
-- and the two publish DIFFERENT durations for the same product kinds (flushing fittings 5y vs 3y,
-- seat cover 2y vs 1y, SS304 kitchen sink 25y vs 10y, no booster pump at all). A policy row that
-- cannot say which company published it answers a Sorento customer with Mocha's terms. Resolution
-- is "the policy in force FOR THIS COMPANY on that date", enforced by CompanyScopedMixin, so
-- `resolve` never filters by company by hand. Deliberately NO Sorento server-default (unlike
-- migration 306's idiom): a raw insert that forgets the company must fail loudly, not silently
-- become Sorento. `warranty_terms` is NOT separately scoped - it is only reachable via policy_id,
-- and a second copy of the same fact can disagree with the first.

CREATE TABLE warranty_terms (
  id uuid PRIMARY KEY, policy_id uuid REFERENCES warranty_policies(id),
  kind_id uuid REFERENCES warranty_product_kinds(id),
  part_name varchar(120),                   -- 'Ceramic Body' | 'Flushing Fittings' | ...
  duration_months int,                      -- NULL when is_lifetime
  is_lifetime boolean DEFAULT false,
  covered_defect_type_ids uuid[],           -- empty = all defects
  installation_included boolean NOT NULL,
  registration_bonus_months int,            -- Booster Pump: 12
  qualifications text, exclusions text
);

-- ── module: consumers (NOT warranty, NOT core - fork 7) ──────────────────────
CREATE TABLE consumer_profiles (               -- the strategic prize
  id uuid PRIMARY KEY,
  respond_contact_id uuid UNIQUE REFERENCES respond_contacts(id),  -- 1:1, identity stays there
  full_name varchar(255), email varchar(150),
  addresses jsonb,                             -- a consumer may own several properties
  is_provisional boolean NOT NULL DEFAULT true, -- staff-typed; promoted on first OTP (fork 1)
  confirmed_at timestamp,
  consent_purpose varchar(40) NOT NULL,        -- 'warranty_service' only (fork 6)
  consent_notice_version varchar(16),          -- which bilingual notice they were shown
  consent_recorded_at timestamp,
  anonymised_at timestamp                      -- erasure: person stripped, purchase retained
);
-- NO marketing_consent column. Consent is warranty-and-service only, so a marketing flag would be
-- a field nobody may lawfully act on. Adding marketing later needs fresh consent per person.

CREATE TABLE consumer_purchases (              -- HEADER: one receipt = one purchase event
  id uuid PRIMARY KEY, purchase_number varchar(64) UNIQUE,       -- CP{year}-
  consumer_profile_id uuid REFERENCES consumer_profiles(id),      -- NULLABLE (fork 2)
  customer_id uuid REFERENCES customers(id),     -- the Dealer who sold it
  dealer_document_number varchar(120),           -- the dealer's OWN invoice/DO number as printed
  dealer_document_number_norm varchar(120),      -- normalised, part of the dedupe key
  purchase_date date NOT NULL,
  total_value numeric(14,2), currency varchar(3),-- what the receipt says at the bottom; nullable
  proof_attachment_id uuid REFERENCES attachments(id),  -- the receipt, RETAINED
  registered_at timestamp,                       -- Warranty Registration = the ACT
  registration_source varchar(20),               -- 'self'|'auto_on_complaint'|'smc'|'ecommerce'
  dedupe_pending boolean NOT NULL DEFAULT false, -- partial key: written, flagged, NOT blocked
  policy_id uuid REFERENCES warranty_policies(id)-- policy in force on purchase_date, snapshotted
);
-- dedupe key: (customer_id, dealer_document_number_norm, purchase_date)
-- enforced as a PARTIAL unique index (only where all three are non-null), because an incomplete
-- key must still write. On collision the service LINKS the new complaint to the existing purchase;
-- it never rejects. attachments.file_hash catches an exact re-upload for free.
CREATE UNIQUE INDEX consumer_purchases_dedupe ON consumer_purchases
  (customer_id, dealer_document_number_norm, purchase_date)
  WHERE customer_id IS NOT NULL AND dealer_document_number_norm IS NOT NULL;

CREATE TABLE consumer_purchase_lines (         -- one product on that receipt
  id uuid PRIMARY KEY,
  purchase_id uuid NOT NULL REFERENCES consumer_purchases(id) ON DELETE CASCADE,
  product_id uuid REFERENCES products(id),       -- nullable, variant may be unresolved
  kind_id uuid REFERENCES warranty_product_kinds(id) NOT NULL,
  claimed_text text,                             -- what the receipt actually said
  quantity numeric(12,3),
  line_value numeric(14,2)                       -- usually NULL: most receipts do not show it
);
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE warranty_assessments (         -- one per complaint product line
  id uuid PRIMARY KEY,
  complaint_product_line_id uuid REFERENCES complaint_product_lines(id) ON DELETE CASCADE,
  term_id uuid REFERENCES warranty_terms(id),
  computed_verdict varchar(20),             -- 'covered' | 'expired' | 'defect_not_covered' | 'no_term' | 'unknown'
  computed_expiry date, computed_at timestamp,
  installation_included boolean,
  confirmed_verdict varchar(20), confirmed_by varchar, confirmed_at timestamp,
  override_reason text                      -- mandatory when confirmed != computed
);
```

`computed_*` is **never overwritten** by a human decision - both survive side by side (**AC-D11**).

### Entitlement algorithm (AC-D4, AC-D5, AC-D6, AC-D7)

```
resolve(kind, purchase_date, defect_type, registered?):
  policy  <- warranty_policies where purchase_date between effective_from and effective_to
             # judged against terms in force ON THE PURCHASE DATE, never today's
  terms   <- warranty_terms where policy_id = policy and kind_id = kind
  for each term:
     if term.covered_defect_type_ids non-empty and defect_type not in it -> defect_not_covered
     months <- term.duration_months + (registered ? term.registration_bonus_months : 0)
     expiry <- term.is_lifetime ? NULL : purchase_date + months
     verdict <- lifetime or today <= expiry ? covered : expired
  return the terms, each with its own verdict   # a Water Closet returns THREE
```

Never returns one answer for a product. A water closet reports ceramic body (lifetime, crack+leak only, installation included), flushing fittings (5y, installation excluded) and seat cover (2y, installation excluded) independently.

**Replacement inherits remaining cover** (**AC-D7**): a replacement line copies the source assessment's `computed_expiry` rather than recomputing from a new purchase date. Policy clause 6 note - "the replaced Warranty Part does not carry a new warranty".

### Golden set (written first, as failing tests)

| case | expect |
|---|---|
| Water Closet, bought 2025-10-16, `Leakage` | ceramic body **covered** (lifetime); fittings covered to 2030-10-16; seat cover covered to 2027-10-16 |
| Water Closet, bought 2015-01-01, `Leakage` | ceramic body **covered** (lifetime); fittings + seat cover **expired** |
| Water Closet, ceramic body, defect `Holder broken` | **defect_not_covered** - lifetime is crack and leak only |
| Kitchen Sink SS304, bought 2024-01-01, `Rust` | covered to 2049-01-01 (25 years) |
| Booster Pump, unregistered / registered | 2y / **3y** (clause 26 bonus) |
| Seat cover replaced 2026-07 under a term expiring 2027-10 | new part expires **2027-10**, not 2028-07 |
| Sensor Tap, `Sensor Eye`, bought 2024-06-01 | expired 2025-06-01, **installation excluded** -> callout chargeable |

Postgres only. No sqlite - a mostly-zero UUID gets coerced to an integer under NUMERIC affinity. Use `tests/_pg_fixture.py` `blank_session()`, seed real FK targets, and scope every cleanup `DELETE` to marker rows (the local DB is a copy of production data).

> **Build status, 2026-08-02: S2 is COMPLETE. 79 gate tests and 12 guards green.**
>
> BLOCKER 1 is cleared. Warranty Policy v15 was supplied by the user and is committed at
> `sorento_crm_backend/scripts/data/warranty_policy_sorento_v15.pdf` plus its extracted text.
> `scripts/seed_warranty_policy_v15.py` transcribes clause 6 item by item: **31 product kinds, the
> v15 policy row with its full text, 41 terms and 2 kind rules.** Every duration, lifetime flag,
> installation answer, qualification and exclusion is read off the document, never off the golden
> set. Each Kind carries the document's verbatim `Product(s)` cell in the seed so a row can be
> checked against the PDF in one step, and the document's own item numbering is the `sort_order`.
>
> BLOCKER 2 is cleared by a DATA decision, as proposed: **v15 is RETROACTIVE** (user ruling,
> 2026-08-02), seeded `effective_from = 2000-01-01` with `effective_to` NULL, so the 2015 golden row
> has a policy in force. A later version must CLOSE this window rather than edit the row.
>
> Six things the document does not answer are printed by the seed on every run and are S3's or
> Sorento's, not S2's: kind rules for 29 of the 31 kinds (clause 6 states the mapping for only item
> 9's *Honeycomb Series* and item 10's model list, both of which ARE seeded); item 11's `Product(s)`
> cell, which ends at "Concealed Shower Mixer & Cold" and reads as truncated; item 23, which states
> no installation answer at all (set to excluded to match every comparable fitting row, and the one
> installation value in the seed not read off a cell); `consumer_label` / `consumer_icon` chooser
> copy; the defect vocabulary beyond the four clause 6 and the golden set name; and whether a v16
> exists.
>
> One seeded label differs from the document by one word: the Water Closet's third part is
> `Seat Cover Soft Close` (AC-D4's name, which the gate, the CS panel and the portal all key on)
> where the document's cell reads "Seat Cover Soft Close System". Same part, same 2 years, same
> installation answer.

### Policy Q&A (AC-D14, BRD Req #12)

The AI is restricted to `warranty_policies.policy_text` for the version in force, answers by quoting, and **routes to Customer Service** when the situation is ambiguous or outside the document. Prompt lives in `ai_prompt_registry` (versioned, labelled, publishable without redeploy).

### Deliberate departures, both recorded in ADR-0010

- **Registration is optional.** Policy clause 3(b) says a product must be registered before a claim may be processed; the BRD says cover auto-activates from the purchase date. **BRD wins.** Lodging a Complaint auto-creates the Registration when absent (**AC-D8**).
- **Clause 17** (residential only, commercial and industrial excluded) is **modelled but not enforced**. 23 of 50 existing Complaints are Project cases. Awaiting Sorento's ruling (**AC-D15**).

`products.warranty_months` (0 of 11,415 populated) is abandoned; a guard test asserts nothing reads it (**AC-D13**).

---

## S2a - Core attachment validator (NEW, added 2026-08-02 for Group M)

Satisfies **AC-M20 to AC-M25, AC-M27**. Supersedes **AC-F10 to AC-F18** as the *mechanism* those ACs
described; S6 keeps only their technician-facing use.

### Why this is its own slice, and why it sits before S3

R5's grill outcome moved photo validation out of `service_jobs` and into a **core attachment validator in
the `resources` module** (AC-M21). That makes it not after-sales work at all: it ships to every module that
already depends on `resources`. Three separate slices consume it - S3 (consumer intake evidence), S6
(technician proof) and S11 (`rma_readiness` collection proof) - and the first of those is S3.

Leaving it inside S6, where the plan currently parks the `attachment_types` ALTER, has one concrete cost:
S3's flow already says "proof photos (validated live)", so S3 would either ship without validation and be
re-shaped later, or build a second validator. AC-M23's synchronous-on-upload behaviour is a **UI shape**
(spinner, score, a prominent Retake, a reason-gated "Use anyway"), not a decoration bolted on afterwards -
exactly the thing the Phase 1 prototype is supposed to settle once.

It also **shrinks S6**, which was the largest slice in the sequence.

### What changes

**Schema.** `attachment_types` gains `validation_guidance`, `min_score`, `validate_on_upload` (AC-M20). **No
new tables** - it is already the per-type upload policy table beside `allowed_extensions`,
`max_file_size_mb`, `max_count_per_entity`, `supports_field_linkage`. The link row
`entity_attachment_links` gains `ai_score`, `ai_suggestion`, `override_reason`, `latitude`, `longitude`
(AC-M22). One link table serves forms submissions, complaints and service jobs
(`workflow_submission_attachments.py:59` already routes submission and line attachments through it), so
the validator reaches all three without a per-domain path.

**Behaviour.** Validation runs **synchronously on upload** when the type says so (AC-M23), scores the file
against that type's `validation_guidance`, and returns a score plus a suggestion. Below `min_score` the FE
shows the suggestion, makes **Retake** prominent, and allows **Use anyway** only with a reason (AC-M24).
Score, suggestion and override reason all persist - the override reason is itself the metric that says the
guidance is wrong rather than the uploader.

**No hardcoded branch per type** (AC-M25). The prompt lives in `ai_prompt_registry`; per-type behaviour is
the `validation_guidance` string. A new photo type is admin data entry, not a deployment.

**Geolocation never blocks** (AC-M27). Denied or unavailable means the coordinates are omitted and the
upload still succeeds.

**Admin surface.** `validation_guidance` / `min_score` / `validate_on_upload` join the existing attachment
type dialog, the same way `max_count_per_entity` did.

### Risk this slice carries

Synchronous AI on a bad phone connection. Same mitigation as before: a hard timeout that degrades to
"unvalidated" rather than blocking the upload. A validator that can block a technician closing a job at
6pm in a basement is worse than no validator.

---

## S3 - Consumer portal intake

Satisfies **AC-C10 to AC-C19**, **AC-M38, AC-M39, AC-M40**.

### S3-pre: extraction accuracy spike (approved 2026-07-26, blocks S3)

**RUN 2026-08-03. Verdict: proceed. Full write-up: `S3-pre-extraction-accuracy.md`.**

Before S3 is committed, a throwaway harness scores extraction over **50 real dealer receipts** from the corpus (`After-Sales/**/*.pdf` plus receipt photos). Measure three numbers separately: shop-name -> `customers` match rate, purchase-date extraction rate, model-code extraction rate. Publish them.

The whole consumer journey assumes these are high. If shop-name match lands under ~75%, Customer Service ends up fixing bad guesses instead of reading a clean template, and the feature inverts - it becomes more work than the WhatsApp group it replaced. That is worth half a day to learn now rather than after S3 ships. Throwaway code, not merged.

**Measured, over 38 consumer-track receipts** (12 of the 50 were Sorento-issued, which is
AC-C13's dealer track and scored separately): shop name read **87%**, dealer resolved exactly
**68%**, purchase date **97%**, model code **97%**, illegible **0%**.

**68% passes, and the 75% bar was aimed at the wrong risk.** Misses are cheap - AC-C14 submits
anyway, AC-C10a makes every field editable, AC-C10c re-matches on correction. The expensive
failure is a **confident wrong** match, and three receipts produced one (`SENG HUAT` ->
`CHENG HUAT HARDWARE`, `LEHAO FURNITURE` -> `LEGIT INTERIOR DESIGN`, `IRC HOME DECOR` ->
`DE HARMONI HOME DECO`). The score distribution is bimodal - 26 receipts at exactly 1.00 and
**nothing between 0.70 and 0.99** - so there is no threshold to tune: a match is the dealer or
it is noise.

Three contract changes fall out, and they bind the slice below:

1. **The extract response returns a dealer match STATE** (`resolved | candidate | unmatched`),
   decided server-side, **not** a confidence float the FE thresholds itself. Only `resolved`
   pre-fills.
2. **Normalisation is contractual**: strip corporate suffixes AND bracketed branch qualifiers
   from both sides before comparing. Unstripped, "SORENTO SDN BHD" matched "SL & A SDN BHD" at
   0.42 on the strength of "SDN BHD" alone; stripping branches lifted exact resolution from 23
   to 26 of 38.
3. **The dealer track is 24% of real traffic**, not an edge case. It gets first-class treatment
   in the Phase 1 prototype.

Two things the spike found that are NOT extraction problems: `warranty_product_kinds` has 31
`consumer_label`s and **zero** `consumer_icon`s, so AC-C11's tiled picture chooser has no
pictures (Sorento's call); and a short-edit-distance fallback for OCR typos
(`SAINMART`/`SANIMART`) is the obvious next lever, deliberately left for S3 with a test rather
than bolted into a spike.

### The slice proper

**Phase 1 (frontend prototype on mocks) is BUILT, 2026-08-03.** Route `/portal/lodge`, with
`?scenario=resolved|candidate|unmatched|dealer_track` walking the four extraction outcomes -
three of which are normal traffic, not error paths. Contract shapes live in
`portal/components/lodge/lodgeMocks.ts` and are what Phase 2 must satisfy. Walked at 375px,
zero console errors.

Two findings from walking it, both recorded because they change the slice rather than the code:

1. **The tiled chooser has no pictures and the fallback proves the cost.** Four tiles render
   "K" and two render "W" (K Kitchen Mixer Tap, K Kitchen & Bathroom Cold Tap, K Kitchen &
   Bathroom Mixer Tap, K Kitchen Sink). An initial differentiates nothing, and the wrong tap
   is the wrong Warranty Product Kind, which is the wrong warranty verdict. **Sorento's call:
   31 real icons, or accept text-only tiles.**
2. **"Did we get this right?" over an empty sentence reads as a broken screen**, and roughly a
   quarter of receipts print no usable shop name. The confirm step now says what actually
   happened and carries on.

**Extraction pre-fills an editable form, not a read-only confirmation.** Every extracted value - name, phone, site address, shop name, purchase date, value, quantity, Kind - renders as a normal input the consumer can correct. Both versions are stored (AI original + human correction), which means **production becomes its own measurement harness**: correction rate per field is extraction accuracy, continuously, without instrumenting anything else. Correcting the shop name re-runs the dealer match. This materially reduces the blast radius of concern 1 - a bad extraction costs the consumer one edit rather than costing CS a cleanup - but it does not eliminate it, because a wrong purchase date the consumer does not notice still mis-computes warranty. The S3-pre spike still runs.

A **Consumer 360 page** ships with this slice: profile, every purchase (dealer, dealer document number, product, quantity, value, date), every Complaint, every stored document. This is the screen that makes the commercial purpose real rather than aspirational. **Phase 1 is frontend-first against mocks** - build the whole flow with stubbed hooks, tune every state, verify in a browser via sidebar clicks, and only then wire the backend.

**Phase 2 (backend) is PART-BUILT, 2026-08-03.** Two pieces landed, both test-first:

- `dealer_resolution_service` (commit a1f68f6a1, 16 tests). Returns a **state**, never a score:
  the spike's distribution is bimodal (26 receipts at exactly 1.00, nothing between 0.70 and
  0.99), so there is no gradient to threshold, and a float invites every caller to invent a
  cutoff that eventually pre-fills one of the three real-but-WRONG dealers. Replayed against
  the spike corpus: 26/38 resolved (68%), 4 candidates, 8 unmatched, **zero wrong**.
  Sorento's decision, taken 2026-08-03: text-only tiles are accepted, so item 1 above is
  closed and the initial-letter circle is gone from the prototype.
- `consumer_lodge_service` (commit 1866fa41e, 12 tests) plus **migration 323**. One
  transaction: profile, consent, purchase, complaint, lines, verdict. The ALTER below was
  already half-present (`consumer_purchase_line_id` and `defect_type_id` landed with S1/S2),
  so 323 adds only the remaining four and is idempotent per column. `defect_type_id` points
  at `lookup_options`, not `lookup_values` as written below.

- `product_resolution_service` (commit 6a2885fc2, 20 tests). The ladder of AC-C16 to C18:
  exact, dash-strip, the `SRT` prefix the carton omits, a trailing unit the consumer added,
  the base-code family, then trigram neighbours. An earlier rung always wins, and rungs 2
  to 4 fire only when they land on exactly one product. `ambiguous` is normal traffic and
  keeps `product_id` NULL so the Kind decides cover.
- Three routes under the existing portal-token auth (same commit, 12 tests):
  `GET /portal/lodge/kinds`, `POST /portal/lodge/resolve` (side-effect free, re-runnable),
  `POST /portal/lodge`. The contact comes from the resolved token and the body's copy is
  ignored, so a valid token cannot lodge against somebody else's contact.
- FE off mocks (commit 5dc8f11ef, 10 vitest). `LodgeFlow` now takes a `LodgeBackend`:
  `/portal/lodge` keeps the four-scenario prototype, and `/portal/c/{slug}/lodge` runs the
  real endpoints with the phone and name taken from the token. Editing the shop name
  re-runs the dealer match on blur.

**The extract endpoint was NOT built, deliberately.** `POST /portal/ai-extract` already
reads receipts and returns a generic per-form shape; mapping it onto this journey is its
own piece of work, and blocking the whole path on it would have left nothing usable. The
live backend therefore resolves what the consumer TYPES rather than pretending to read a
photo, which still gives a real dealer match against the real customer table. Wiring
ai-extract into `LodgeBackend.extract` is a contained follow-up: one method, one shape map.

- Consumer 360 (commit b59249ce2, 14 pytest + 6 vitest). Three endpoints under a new
  `consumer-management` router, a searchable list and a detail page, reachable from a new
  sidebar group. Adds `consumers.profiles.view`, kept SEPARATE from the value grant.

- Receipt extraction wired, on its own form key. `portal.consumer_lodge` (11 pytest + 11
  vitest) rather than reusing `portal.complaint`, which reads the WRONG document: that form
  asks for a Sorento DO number and for the buyer being billed, while a consumer's
  attachment is the dealer's own invoice where the letterhead company is the SELLER and the
  document number matched nothing in `orders` six times out of six (AC-C12). The map from
  extract response to form state never decides anything - it reads a shop NAME and a model
  CODE, and the server decides whether either is a dealer or a product. A failed or empty
  extraction lands on the same editable form rather than raising, because 24% of receipts
  print nothing usable and that is the ordinary case, not an error path.
- `e2e/consumer-lodge.spec.ts` (5 passing, 1 skipped without `PORTAL_E2E_TOKEN` /
  `PORTAL_E2E_SLUG`). Walks resolved / unmatched / candidate, the full journey to a
  reference number, and asserts zero horizontal overflow at 375px. The live half proves the
  FE -> BE -> DB round trip and checks the network calls.

**Phase 2 is complete.** Phase 3 (code review) is the remaining gate before a PR.

**Two environment findings from verifying Consumer 360 in a browser, both of which apply
to production and neither of which is code:**

1. **The `consumers` and `warranty` modules were never installed on the tenant.** Every
   engine S1 and S2 built has been sitting behind a module guard that was off, and the
   sidebar group correctly refused to render because of it. Installed on the local dev
   tenant via `install_modules(db, DEFAULT_TENANT_ID, ["consumers", "warranty"], None)`;
   **production needs the same install** before any of this is reachable there.
2. **`consumers.profiles.view` did not exist** - the registry carried only the value
   permission. Added to `permission_registry.py` and synced locally; production needs
   `sync_permissions` and then a grant to whichever roles should open the ledger. Nobody
   holds it by default, and superadmin bypasses it, which is why the endpoint tests seed a
   plain CS role rather than asserting against a superadmin (an assertion that would pass
   whether or not the permission worked).

Also worth knowing: a consumer row written by a script with no company scope gets
`company_id = NULL` and is then invisible to the API, which filters by company. The
auto-stamp fires on ORM flush inside a scoped request, not in a bare script.

**Unrelated flaky test found while verifying, NOT caused by this slice and not fixed here.**
`test_complaint_analytics::test_group_by_product_ranked_desc` passes or fails run to run on
the same commit (measured: pass, fail, pass, fail). `complaint_analytics` sorts groups by
count and truncates at `limit` (50) while its underlying `q.all()` carries **no ORDER BY**,
and the shared dev database has now crossed the cliff: 54 distinct product codes on
`complaint_product_lines`, 32 of them tied at count 1. The test seeds `WIDGET-B` with a
single complaint, so whether it survives the cut depends on physical row order. The
production-facing half of this matters more than the test: "which product has the most
complaints" silently drops groups past 50 with no indication it truncated. Verified innocent
by running the same selection at HEAD.

### The flow (Journey actor 1)

```
receipt upload -> AI extract -> "Did I get this right?" -> tiled Kind chooser
              -> fault description per item -> proof photos (validated live) -> submit
```

### Extraction contract (documented here, built in Phase 2)

```
POST /api/v1/public/portal/complaints/extract   { attachment_ids: [...] }
->  {
      shop_name_raw: "TOTAL HOME DIY",
      dealer: { customer_id, customer_name, confidence: 0.0-1.0 } | null,
      purchase_date: "2025-10-16" | null,
      lines: [ { claimed_text: "SRTWC8152 INLET PROBLEM", model_code_raw: "SRTWC8152",
                 kind: { id, consumer_label: "Water closet", confidence },
                 product_id: null,            # variant ambiguous, deliberately
                 candidates: ["SRTWC8152-RL-RG","SRTWC8152-SH","SRTWC8152-300-RL"],
                 quantity: 1 } ],
      unresolved: ["dealer_low_confidence"]
    }
```

**Two OCR strategies, not one** (**AC-C12, AC-C13**):

- **Consumer track** - the attachment is the *dealer's own* invoice. `KCS-2112-0054`, `CS002629`, `NV20-2-008850`, `IV01029`, `DO10-2-123494`, `CS40964` were all tested against `orders`: **every one NO MATCH**. Order-number matching is not attempted. Extract shop name -> trigram fuzzy match to `customers` -> confidence.
- **Dealer track** - a quoted Sorento order number (`202604-0348`) **does** match, and dealer, products and date resolve from the order directly.

### Product resolution (AC-C16 to AC-C18)

`complaint_product_lines` keeps `product_code` as free text (already nullable-FK-free) and gains:

```sql
ALTER TABLE complaint_product_lines
  ADD COLUMN consumer_purchase_line_id uuid REFERENCES consumer_purchase_lines(id),  -- supplies the date
  ADD COLUMN claimed_text text,                                  -- exactly what was said
  ADD COLUMN product_id uuid REFERENCES products(id),            -- nullable, resolved
  ADD COLUMN kind_id uuid REFERENCES warranty_product_kinds(id), -- resolved with confidence
  ADD COLUMN defect_type_id uuid REFERENCES lookup_values(id),
  ADD COLUMN fault_description text;
```

Resolution ladder: exact code -> dash-strip -> `SRT` prefix-strip (`WC189-G2` -> `SRTWC189-G2`) -> trailing-unit strip (`SRTWC8517-200mm` -> `SRTWC8517-200`) -> trigram neighbours. Base-code hits returning several variants resolve the **Kind** with confidence and leave `product_id` null. Overlaps the already-grilled `PLAN-suggest-on-miss-variant-graph.md`; reuse it rather than writing a second resolver.

**Nothing blocks submission.** Low confidence submits and flags for CS (**AC-C14**).

### What AC-M38 / AC-M39 / AC-M40 change about this slice

**Behaviour, plus one release gate.** The consumer form gains a **map pin step** writing the three Site
columns S1 created.

- **The pin is optional and never blocks submission** (AC-M38). No pin means the typed address is geocoded
  **at dispatch**, not at submit: a consumer who denies location permission or cannot find their own roof
  on a map must still be able to lodge a complaint. This is the same rule as photo geotagging (AC-M27) and
  the same rule as low-confidence extraction (AC-C14) - nothing in this journey blocks on a nicety.
- **Pin and address are both kept and neither is reconciled** (AC-M39). They answer different questions:
  the pin is what the technician navigates to, the address is what appears on documents. A reconciliation
  step would force a consumer to resolve a disagreement they do not perceive, and would throw away the
  half that the other consumer needs.
- **AC-M40 is a deployment gate, not build work.** A Google Maps key rendered on a public portal page is
  scrapable and billable, so the key must be **HTTP-referrer restricted** before this page is public. It
  rides S3's release checklist because S3 is the slice that first exposes a key publicly. S6's technician
  screen must reuse the restricted key or carry its own, never an unrestricted one.

This adds a step to the Journey between "site address" and "submit", so the Phase 1 prototype must include
it: pin present, pin skipped, and permission denied are three states to draw, not one.

### UI rules

No SKU, product code or UUID ever shown to a Consumer; no dealer picker (**AC-C11**). Tiled chooser reads `warranty_product_kinds.consumer_label` / `consumer_icon`. Usable at 375px and 1280px; modals scroll to their submit button.

---

## S4 - Notification spine, the Respond outbox, calls and assignment fallback

Satisfies **AC-H1 to AC-H14**, **AC-M33, AC-M34, AC-M35**.

**Status: implemented 2026-08-03.** Migration `320_notification_spine_calls`; gate
`tests/test_after_sales_notification_spine.py` + `test_after_sales_notify_guards.py` (75 green). The DDL
below is superseded on two points the tests forced: `respond_contact_id` is TEXT (a uuid FK onto
`respond_contacts.id` cannot be created), and the old unique constraint is **dropped**, not amended, because
NULL-distinctness silently stops it deduplicating contact rows.

```sql
ALTER TABLE notifications ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE notifications ADD COLUMN respond_contact_id uuid REFERENCES respond_contacts(id);
ALTER TABLE notifications ADD CONSTRAINT notifications_recipient_present
  CHECK (user_id IS NOT NULL OR respond_contact_id IS NOT NULL);
-- the existing unique (user_id, source_entity_type, dedup_key, event_type) becomes TWO partial
-- indexes, one per recipient kind, so both dedupe correctly
```

WhatsApp joins `in_app` / `email` / `web_push` as a `notification_deliveries.channel`. Contacts get **no preference toggles** - WhatsApp plus portal, always; toggles stay staff-only (**AC-H3**).

### The outbox stays, and improves (AC-H8, AC-H9, AC-H10)

`integration_logs` remains the wire truth. Every send stamps `correlation_id = notification.id` and `business_table` / `business_id` = the Complaint, so the screen renders event-first:

```
Complaint CMP2026-0123 - Visit confirmed - to Mr Vinod (017-3336634)
WhatsApp template - FAILED 401 - payload
```

**The outbox query is a LEFT JOIN over `integration_logs`.** AI replies and n8n-initiated sends carry no notification and must still appear. An inner join silently loses exactly the visibility this protects.

Non-negotiables carried from existing lessons: log on success **and** failure (local testing runs intentionally-wrong credentials, so a 401 must appear); stamp the *actually attempted* payload so a closed-window failure reads as a template attempt; `business_id` is a real UUID, never a composite string; resolve the workspace key via `RespondClient.for_identifier(...)`, not `settings.respond_api_key`; and every post-commit notification write **catches and warns, never raises**.

Escalation notifies **only the tier escalated to**, via `resolve_team_with_tier_fallback`, gated by the stage's `notify_on_escalation` and each member's own toggles. No fixed recipient list (**AC-H6**).

### AC-M33 - nobody assignable is a routing outcome, not an exception

**Behaviour change, and it reaches beyond after-sales.** Today `FormSLAOrchestrator._start_for_config`
(`sorento_crm_backend/app/services/form_sla_service.py:836`) **raises** a validation error when
`resolve_team_with_tier_fallback` finds no team at or above the start tier. That is loud, but it is loud in
the wrong place: the caller creating the case gets an error, and whether a case exists at all now depends
on team configuration.

AC-M33 requires the opposite shape: route to a **configured fallback** (the after-sales team lead), flag
the case `assignment unresolved`, and never leave a clock running on nobody. This is the same pattern
AC-B10 already uses for an unresolved salesperson, which is why it belongs in S4 beside the rest of the
assignment-and-notify machinery rather than in a new slice.

**Loud flag: this is a CORE form-SLA change with blast radius past this module.** `_start_for_config` is
shared by purchase requests, sponsorship forms, stock inquiries and complaints. Turning a raise into a
fallback changes what those flows do when misconfigured. Two things must be decided before build, and are
**not** decided here:

1. **Where the fallback is configured** - a column on `form_sla_configs`, a `system_settings` key, or an
   agent-level default. A per-config column is the most precise and the most rows to fill in.
2. **Whether the change applies to all form types or only to after-sales configs.** Applying it
   selectively means two behaviours in one function, which is how this kind of guard rots.

The `assignment unresolved` flag renders on the pending-task row built in S4a, beside the waiting label.

### AC-M34 / AC-M35 - calls are the third channel, and this slice owns the manual path

**Behaviour, no new table.** A call becomes a **`call` activity** in the existing `activities` module
(`app/models/activities.py`), the per-entity feed that already carries notes and system events, recording
outcome and next action. This grows S4's remit from "outbound machine messages" to "the case's
communication record", which is a deliberate scope decision: the outbox screen is already the place a CS
member goes to ask "what have we actually told this person", and a phone call is the channel that leaves
no trace today.

**Attribution is deliberately conservative** (AC-M35): a call auto-attaches only when the contact has
**exactly one** open case. More than one and it waits in a per-contact inbox for one-click attachment. A
wrong attribution puts false evidence into the record CS relies on, and the existing system already makes
the same compromise for messages (the Respond thread is contact-keyed and merely surfaced on the case via
`respond_inbox_url`).

**Two things to resolve before build, flagged not guessed:**

- **`activity_events.kind` is `system` | `user_update` today, and `entity_type` / `entity_id` are both NOT
  NULL.** An unattached call has no entity, so AC-M35's per-contact inbox has nowhere to sit under a strict
  reading of AC-M34's "no new table". The cheapest reading that honours both is to park unattached calls
  as `entity_type = 'respond_contact'` and re-key them on attachment. That is a decision about what an
  activity's entity *means*, so it needs an explicit yes rather than being assumed.
- **Structured outcome and duration** (`answered` / `missed` / `no_answer`, AC-M36c) have to live
  somewhere. `system_payload` JSONB is the existing shape; whether reporting needs them as columns is a
  question for S9, not for this slice.

The automatic path (Respond.io `On Call ended` via n8n) is **S5**, because it is the same MCP write-tool
machinery as `complaint_intake_submit`. AC-M36e is explicit that the manual path stands alone, so R9 ships
whether or not the webhook does.

---

## S4a - Waiting attribution (NEW, added 2026-08-02 for Group M)

Satisfies **AC-M1 to AC-M7**, **AC-M36d**.

**Status: implemented 2026-08-03.** Migration `321_sla_waiting_attribution`; gate
`tests/test_sla_waiting_attribution.py` (39 green) plus 5 vitest specs on the banner. Two corrections the
build forced, both recorded in the commits: AC-M1's `waiting_on_reason_id` **cannot be an id** (a bound
column must hold the option VALUE or `lookup_validator` rejects every write), and the AC-M4 guard is scoped
to entity types **registered on the status engine** - the first version blocked conversation-SLA extends and
broke 16 existing tests, which is exactly the live-integration damage AC-M33 warned about one slice earlier.

### Why this is its own slice

The 2026-08-01 grill's own closing observation is that R2, R7, R8 and R12 are one gap, not four: **the
system cannot express "waiting on someone who is not us"**, so every delay reads as internal inaction and
every metric blames whoever holds the record. Four slices consume the answer and none of them owns it:

| consumer | what it needs from this slice |
|---|---|
| S6 | R12 - a customer rejecting a visit sets `waiting_on = customer` on the Schedule stage |
| S11 | AC-M18 - the collection gate is **only safe** because an unacknowledged request reads as the Dealer's delay |
| S12 | an RMA that sits open needs a party attached to the sitting |
| S9 | AC-M7 - "of 40 breaches, 26 were waiting on an external party" |

Folding it into **S6** was the obvious alternative, since S6 already carries the `service_jobs` ALTER. It
is rejected for two reasons. First, S6 was already the largest slice in the sequence, and this is a
cross-cutting SLA and dashboard dimension, not a service-jobs feature. Second, **S11's readiness gate is
unsafe without it** - a hard gate that blocks collection until a Dealer acknowledges is only defensible
when the dashboard says the delay is the Dealer's. Ordering S11 behind S6 would work, but it would tie a
commercial-flow safety property to a technician-portal slice for no reason.

Folding it into **S4** was the other alternative. S4 is notifications; this is SLA semantics and reporting
attribution. The only overlap is that both eventually render on a dashboard.

So: **its own slice, immediately after S4, before S6 / S11 / S12 / S9.** It needs no forms-platform slice:
`workflow_submissions` and `conversation_sla_tracking` both exist today.

### What it changes

**Schema.** Three fields - `waiting_on_party`, `waiting_on_reason_id` (FK to configurable master data),
`waiting_since` (AC-M1) - on the **SLA tracker**, not on the case table, and mirrored onto the event log
for point-in-time capture. See "Ruling 1" below for why, and for what that leaves S6 to do. **One
shared reason vocabulary** serves both the pending reason and the overdue reason: "pending plumber" is the
same fact whether or not the clock has expired, and two lists would drift. The vocabulary is a
`lookup_sets` / `lookup_options` / `lookup_bindings` triple, the same shape the seven existing bindings use
and the same shape F1a used for line dispositions - dropdowns, not free text, and the admin can add one
without a migration.

**The clock is not touched** (AC-M2). Time spent waiting on an external party still counts toward
resolution. Pausing makes "how long did this take from the customer's point of view" unanswerable - their
toilet is broken whether or not our clock runs - and it is the classic gamed metric, where a queue parked
on "pending customer" reports a perfect SLA. The accepted consequence is that SLA numbers will look worse;
attribution is what makes that honest rather than merely bad.

**A genuine deadline move is Extend, and only Extend** (AC-M6). See the note below: **Extend is already
built**, so this slice's work here is to surface it on after-sales cases and to assert nothing else writes
`due_at_resolution`.

**`waiting_on` becomes mandatory once overdue** (AC-M4) - a write guard, not a nag.

**The pending-task row reads the truth** (AC-M3, AC-M5): "waiting on maintenance since 3 Aug", never "stuck
at CS". Rows are coloured by breach risk **and** carry the waiting party as a text label, because colour is
never the only signal (accessibility, and the code-review rule already forbids it). The surface is the
existing `MyPendingSLAWidget` plus the in-form SLA banner, which already colour an overdue due date
`text-destructive` - so this is an addition to a live component, not a new dashboard.

**AC-M36d** lands here rather than with calls: repeated unanswered calls are what *justify*
`waiting_on = customer`. "We called three times, no answer" is the defensible version of blaming the
customer for a delay, and it is the rule for setting the field, not a property of the call log.

### Three things this slice must decide - RULED 2026-08-03, before the gate

The third was already answered by the UAC ("Rulings, binding on the slices that inherit them"): the
**party is configurable master data**, seeded with AC-M1's list plus `dealer`. Nothing left to decide, and
the seed is `sla_waiting_party` = `cs`, `maintenance`, `plumber`, `customer`, `supplier`, `warehouse`,
`dealer`. The other two are ruled here.

#### Ruling 1 - waiting lives on the TRACKER, and only on the tracker

AC-M1 says "a case". Taken literally that is a column on six tables: `complaints`, `workflow_submissions`,
`stock_inquiries`, `purchase_requests`, `sponsorship_forms`, `tickets` - every member of `FORM_SLA_TYPES` -
and `service_jobs` after S6. Six copies of one dimension, each with its own write path, is how a dimension
stops meaning the same thing in two places.

**Group M itself speaks per-stage twice.** R12 sets `waiting_on = customer` "on the Schedule stage", and
AC-M36d repeats "on the Schedule stage". A case running Acknowledge, Assess, Schedule and Resolve
concurrently is not waiting on one party; the Schedule stage waits on the customer while Assess waits on
maintenance, and a case-level column has to pick one and lie about the rest.

**AC-M7 needs the breach unit, and the tracker IS the breach unit.** "Of 40 breaches, 26 were waiting on an
external party" counts trackers, not cases. So:

- `conversation_sla_tracking` carries `waiting_on_party`, `waiting_on_reason_id`, `waiting_since`. It
  answers **what now**, per stage.
- `conversation_sla_event_log` carries the same `waiting_on_party` / `waiting_on_reason_id`, stamped on
  **every** event row from the tracker's live value at that instant. It answers **what then**. Reporting
  reads the captured value, never the live column, per the UAC ruling - otherwise every historical breach
  silently re-attributes itself the next time somebody edits the case.
- The **case-level** answer AC-M1 asks for is **derived** from the case's open trackers, not stored. One
  open tracker gives one answer; several give several, which is the truth.
- **S6 adds the three columns to `service_jobs` only if a Service Job does not get its own tracker.** If it
  does, it inherits this and adds nothing. The plan text above ("the same three on `service_jobs`") is
  superseded by that condition.

#### Ruling 2 - AC-M4 guards three actions, all of them human

"Before further action" is: **resolve, manual escalate, extend** on a tracker that is already past its
deadline. Named as a set in the service (`form_sla_service` / `sla_service`), never on the routes, per
ADR-0013 rule 7.

What is deliberately **not** guarded, and why:

- **Anything a machine does.** The auto-escalation cron and any auto-resolve carry `trigger = 'auto'` and
  have no answer to give. Guarding them would either stall every overdue tracker forever or force the
  system to invent an attribution, which is worse than no attribution.
- **Status transitions on the case.** Already double-guarded by `assert_transition_allowed` and
  `handling_lock_service.assert_can_act_on_form`. A third guard there buys no attribution that the SLA
  actions do not already capture, and it would block a CS agent from recording progress.
- **Any save at all.** Editing a phone number on an overdue case is not the moment to demand attribution.
- **Claiming a handling lock.** Picking up somebody else's escalated work is the behaviour we want; taxing
  it with a dropdown discourages exactly the right action.

**Evidence, per ADR-0013 rule 7 ("aggregate what has actually happened before guarding a live path"),
measured on the production copy 2026-08-03:**

| what | count |
|---|---|
| form-SLA trackers resolved, all types | 178 |
| resolved **while already overdue** - what the guard newly rejects | **35 (20%)** |
| open and overdue right now - staff meet the guard on their next action | 307 |
| escalation event logs written **after** the deadline | **0** |
| of 671 escalation events, `trigger = 'manual'` | 74 |

So the guard costs one dropdown on about one resolve in five, and historically rejects **zero**
escalations: every escalation in the database fired at or before the deadline, which is what escalation is
for. The 307 open overdue trackers are the reason the field is mandatory rather than encouraged - they are
the population AC-M7 exists to explain, and today every one of them reads as internal inaction.

### Extend is already built (correcting `PLAN-sla-extend-deadline.md`)

That plan's status line still reads "Designed (grilled 2026-06-24). Not started." It is **wrong**. The
mechanism exists end to end:

- `sla_service.py` - `compute_extension`, `evaluate_extension_warnings`, `extend_tracking`
- `POST /conversation-sla-tracking/{id}/extend` and `.../extend/preview`, assignee-gated
- `conversation_sla_tracking.extension_count` / `extension_days_total` on the model
- FE `ExtendDueDialog.tsx`, `ExtendDueButton.tsx`, `SlaExtendAction.tsx`, wired into `MyPendingSLAWidget`
- `sorento_crm_backend/tests/test_sla_extend_deadline.py`

So AC-M6 costs this slice **no engine work**. What it costs is a rule and its guard: the after-sales case
surfaces Extend, and **nothing else may move `due_at_resolution`** - in particular a waiting flag must not,
which is the whole point of AC-M2. Someone should also fix that plan's status line.

---

## S5 - WhatsApp AI intake, and the automatic call path

Satisfies **AC-C1 to AC-C9**, **AC-M36, AC-M36a, AC-M36b, AC-M36c, AC-M36e, AC-M36f**. Depends on S3's extraction contract and S4's spine.

### Architecture: n8n is the pump, the CRM is the tool (AC-C0a to AC-C0d)

Respond.io messages arrive at **n8n**, not at the CRM - n8n is already the message pump for every WhatsApp flow here. The CRM neither polls nor subscribes.

```
Respond.io -> n8n  (receives each message, debounces the burst with a WAIT NODE - decided 2026-07-26)
                |
                +-- calls ONE write MCP tool when the burst closes:
                       complaint_intake_submit(messages[], media_refs[], contact, burst_key)
                    -> { complaint_number, missing_fields[] }
```

Extraction stays **CRM-side, not in an n8n LLM node**, for two reasons: the prompt must be versioned and traceable through `ai_prompt_registry`, and the dealer / product / Kind resolvers already live in the CRM. An LLM node in n8n forks the prompt registry and duplicates the resolvers.

Tool requirements: named `*_submit` so `_is_write_tool` strips it from the prompt dry-run and no test can persist a real Complaint; registered in `sorento_crm_mcp.catalog.CATALOG` **and the MCP process restarted** (catalog entry alone does not register it with FastMCP); `agent_mcp_tools` linkage seeded by the startup hook with intent keywords on the `ToolSpec`, because the implementer owns seeding, not the admin; and **idempotent on `burst_key`**, so an n8n retry after a timeout returns the same number instead of creating a second Complaint.

Burst grouping reuses `conversation_frames` (already models a contiguous span opened on first turn, closed on topic-switch or idle, and already written by n8n exchanges). One frame -> one Complaint, however many messages and media (**AC-C1**).

Two real cases are the acceptance bar:

```
[13/05 10:14:18-10:16:05] 8 media
[13/05 10:16:33] Unihome. SRTWC8366 x 1 / SRTWC8152 x 1 / Seatcover no soft close. Pls replace to shop
   -> ONE complaint, TWO product lines, 8 attachments        (AC-C2)

[11/05 11:08:15] photo   [11/05 11:08:26] photo
[11/05 11:08:55] DILOOMA-USJ. CSS3310BL holder broken. Pls replace to shop
   -> media BEFORE text, same frame                          (AC-C3, AC-C4)
```

Missing-field follow-up asks for **only** what is missing, in the same conversation - automating what the office does by hand a day later (*"this one wat issue? for which dealer? for wat model?"*). Never re-asks anything already extracted (**AC-C5**).

Prompts live in `ai_prompt_registry`; every turn stamps `metadata_json.prompt_versions`. Tests use **paraphrases** of real messages, never one canonical sentence, and no per-phrasing keyword branch is permitted (**AC-C8**).

A **forwarded** group message is accepted during cutover, tagged removable (**AC-C9**).

### The automatic call path rides the same machinery (AC-M36, AC-M36a to AC-M36f)

**Behaviour only. No schema beyond what S4 already built for the manual path.** Respond.io exposes calls
through the n8n node's **`On Call ended`** trigger, verified 2026-08-01 from the node's trigger list, so
**n8n owns the subscription** exactly as it owns the message pump (AC-M36). The CRM neither polls nor
subscribes.

This is placed in S5 rather than S4 because it is the identical shape to `complaint_intake_submit` and
would otherwise be built twice: `call_log_submit` is a **write MCP tool** named `*_submit` so
`_is_write_tool` strips it from prompt dry-runs, registered in `sorento_crm_mcp.catalog.CATALOG` **with the
MCP process restarted** (a catalog entry alone does not register it with FastMCP), `agent_mcp_tools`
seeded by the startup hook with intent keywords on the `ToolSpec`, and **idempotent on the call id** so an
n8n retry cannot double-log (AC-M36a).

**The webhook does not make attribution solvable** (AC-M36b). The event is contact-keyed and carries no
case reference, so AC-M35's rule is unchanged: auto-attach only when the contact has exactly one open
case, otherwise the per-contact inbox. Automation fills the same model faster; it does not license a
guess.

**Record the outcome, not the event** (AC-M36c). `answered` / `missed` / `no_answer` plus duration. **A
call that ended is not a call that connected**, and that distinction is the entire requirement: Fanny's
complaint was *"customer didn't receive any call from maintenance"*, so the evidence needed is whether
contact was actually made.

**Two verification gates before this can be built, and neither blocks R9:**

- **AC-M36e** - the `On Call ended` **payload shape** (direction, duration, outcome, handler, recording) is
  still unverified. One test call is required before AC-M36c can be implemented. The manual path from S4
  stands alone, so R9 ships regardless.
- **AC-M36f** - the installed n8n Respond.io node reports **1.12.0 (Legacy)** with an update available.
  Confirm `On Call ended` exists and behaves identically on the current package before depending on it.

If either gate fails, this subsection drops out of S5 with no other change to the slice, and calls remain
manual. That is the reason it is a subsection and not a dependency.

---

## S6 - Service Jobs, dispatch and the technician

Satisfies **AC-F1 to AC-F23** (except **AC-F10 to AC-F18**, whose mechanism moved to **S2a**), plus
**AC-M28, AC-M29, AC-M30, AC-M31**. Consumes **S2a** (validator) and **S4a** (waiting attribution).

```sql
CREATE TABLE technicians (
  id uuid PRIMARY KEY, name varchar(255), phone varchar(32),
  respond_contact_id uuid UNIQUE REFERENCES respond_contacts(id),
  is_active boolean, employment_type varchar(20)   -- 'employee' | 'contractor'
);                                                  -- NO users row is ever created

CREATE TABLE service_jobs (
  id uuid PRIMARY KEY, job_number varchar(64) UNIQUE,     -- SV{year}/{month}-
  source_entity_type varchar(40) NOT NULL,                -- 'complaint' (NO FK - adr/0009)
  source_entity_id uuid NOT NULL,
  status_id uuid REFERENCES statuses(id),
  -- AC-M37: site_maps_url is NOT created here either. The job copies the Site S1 defines:
  site_address text, site_contact_name text, site_contact_phone text,
  site_latitude numeric(10,7), site_longitude numeric(10,7), site_place_id varchar(128),
  scheduled_from timestamp, scheduled_to timestamp,
  proposed_at timestamp, confirmed_at timestamp, customer_agreed_by text,
  arrived_at timestamp, completed_at timestamp, verified_at timestamp,
  diagnosis_root_cause_id uuid REFERENCES complaint_root_causes(id),
  charge_state varchar(24), charge_amount numeric(12,2), charge_accepted_at timestamp
);
CREATE INDEX ON service_jobs (source_entity_type, source_entity_id);

CREATE TABLE service_job_assignments (
  id uuid PRIMARY KEY, service_job_id uuid REFERENCES service_jobs(id) ON DELETE CASCADE,
  technician_id uuid REFERENCES technicians(id), state varchar(20), assigned_at timestamp
);

-- SUPERSEDED 2026-08-01 (R4/R5 grill): service_job_photo_types and service_job_photos are DELETED.
-- Photo validation is a CORE ATTACHMENT VALIDATOR in the `resources` module. attachment_types is
-- already the per-type upload policy table (allowed_extensions, max_file_size_mb,
-- max_count_per_entity, supports_field_linkage), so it is extended rather than duplicated:
--
--   ALTER TABLE attachment_types
--     ADD COLUMN validation_guidance text,   -- what "correct" MEANS; the AI's input
--     ADD COLUMN min_score numeric(3,2),
--     ADD COLUMN validate_on_upload boolean NOT NULL DEFAULT false;
--
-- Photos become ordinary attachments; the link row carries ai_score, ai_suggestion,
-- override_reason, latitude, longitude. One validator serves consumer intake evidence,
-- technician proof, and dealer collection readiness. See Group M (AC-M20 to AC-M27).
```

A CI guard asserts `service_jobs` declares no FK to `complaints` and the module imports nothing from `app.models.complaints` (**AC-A6**).

### New tables from the 2026-08-01 requirements grill

**Waiting attribution moved out of this slice to S4a** (added 2026-08-02). The
`waiting_on_party` / `waiting_on_reason_id` / `waiting_since` fields and the shared reason vocabulary are
now S4a's, so the case and the job get one design rather than two. S6 keeps only its **consumption** of
them, described under "R12" below.

**Amended 2026-08-03 by S4a's Ruling 1:** those three fields live on the **SLA tracker**, not on the case
table, so `service_jobs` declares them only if a Service Job turns out NOT to run its own
`conversation_sla_tracking` row. Decide that when S6 designs the job's clocks - the note under "Clocks stay
off the SLA engine" below says they do not, which means S6 **does** add the three columns to
`service_jobs`, reading the same two lookup sets S4a seeds. Do not seed a second vocabulary.

```sql
CREATE TABLE external_providers (                 -- generic, NOT plumber-specific, NOT suppliers
  id uuid PRIMARY KEY, name varchar(255) NOT NULL,
  provider_type varchar(32) NOT NULL,             -- plumber | contract_technician | courier | ...
  phone varchar(32), notes text, is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE case_cost_lines (                    -- money OUT; independent of chargeability (money IN)
  id uuid PRIMARY KEY,
  source_entity_type varchar(40) NOT NULL, source_entity_id uuid NOT NULL,  -- polymorphic, adr/0009 shape
  external_provider_id uuid REFERENCES external_providers(id),
  cost_kind varchar(24) NOT NULL,                 -- labour | parts | travel
  amount numeric(14,2) NOT NULL, currency varchar(3),
  incurred_on date, recorded_by varchar, recorded_at timestamp
);
CREATE INDEX ON case_cost_lines (source_entity_type, source_entity_id);
```

Site geolocation is **S1's** (AC-M37); the job copies the same three columns. Calls are **S4's** (AC-M34,
AC-M35) with the automatic path in **S5** (AC-M36 and its sub-clauses).

### AC-M28 to AC-M31 - external providers and what a case costs

**Schema plus one new admin CRUD, no behaviour attached.** `external_providers` is a **generic** master
with a `provider_type` discriminator (plumber, contract technician, courier, and so on), not a
plumber-specific table (AC-M28) - the discovery study already shows the role blurring (*"forward the
details to the plumber; can be an outstation technician"*). It is deliberately **not** `suppliers`, which
carries purchasing semantics (payment terms, lead times, SPO linkage) and would couple after-sales to
`procurement` for nothing.

A cost line carries the case, the provider, the amount, and **what it was for** (labour / parts / travel,
AC-M29). One number per complaint would not answer Ms Tan's costing question, which is the requirement's
whole origin.

**Money out is independent of money in** (AC-M30). A warranty job can be free to the consumer and still
cost Sorento a plumber fee, so `case_cost_lines` is never part of `charge_state`. The two live side by
side on the job and neither derives from the other.

**Recording needs no approval** (AC-M31). It is bookkeeping; reporting surfaces outliers. An approval queue
for a RM80 plumber callout would add friction exactly where CS already gates the case. Reporting on it
(spend per provider, cost per case) is **AC-M32 in S9**.

### R12 - what S6 consumes from S4a

A customer rejecting the technician's visit returns the job to *Proposed* with the rejected attempt kept in
history (never overwritten), and sets `waiting_on = customer` on the Schedule stage. **Rejected attempts
are excluded from the technician's attend-time metric**, or the metric punishes the wrong person - which
also means the exclusion has to be explicit in the S9 query, not assumed.

### Dispatch board (AC-F3 to AC-F5)

Grouped by day and technician, drag to reassign. **No availability grid, skills matrix, geo-clustering or capacity optimiser** - explicitly out of scope. A job cannot leave *Proposed* without a date **and** a recorded customer agreement; `Service Date: TBA` is not a valid *Confirmed*. Jobs past their date still in *Proposed* surface as **stalls** with elapsed stall time.

### Technician portal (AC-F8, AC-F9, AC-F19)

One screen. Today's jobs only - no listings, no search, no records but their own. Job view shows site, contact, fault and the Consumer's photos. Actions: *On my way* -> *Arrived* -> photos -> diagnosis -> *Complete*. Verified at 375px.

### Photo validation - the mechanism is S2a's, this slice only uses it

**AC-F10 to AC-F18 are superseded by AC-M20 to AC-M27 and built in S2a.** S6 no longer builds a validator.
What remains here is configuration and one screen: the technician photo types, their
`validation_guidance` strings, their `min_score`, and the on-site upload UI.

> **CONFLICT, flagged not silently rewritten.** The endpoint contract printed in earlier revisions of this
> slice -
> `POST /api/v1/service-jobs/{id}/photos -> { photo_id, ... }` -
> contradicts **AC-M21** ("the validator lives once, in the `resources` module") and the deletion of
> `service_job_photos`. A per-domain `service-jobs/{id}/photos` route re-creates exactly the special case
> R5's grill removed. Technician photos must upload through the shared attachment path against
> `entity_attachment_links`, returning `attachment_id` with `ai_score` / `ai_suggestion` on the link row.
> The old contract above is retired; S2a owns the real one.

**Synchronous, on upload, while the technician is still on site** (AC-M23). A few seconds with a spinner.
Async validation that flags a bad photo after the van has left is worth nothing - the entire value is the
retake, and the retake is only possible on site.

Below `min_score`: show the suggestion, make **Retake** prominent, allow **Use anyway** only with a reason
(AC-M24). The override reason is itself a metric - a photo type overridden by everyone means the guidance
is wrong, not the technicians.

**Geotag is captured in the background and never blocks** (AC-M27). Permission denied or no GPS omits coordinates and the job still completes. A technician who cannot close a job at 6pm in a basement will phone the office and have someone close it for them, which is worse data than not asking.

No offline sync queue. Progress saves server-side as they go and uploads retry, so a dropped signal costs a retry, not a revisit (**AC-F17**).

### Clocks stay off the SLA engine (AC-F21, AC-F22, AC-F23)

Form SLA resolves assignees through `agent_teams` -> `team_members` -> `users`, and a Technician is deliberately not a user. So technician metrics (attend time `confirmed_at` -> `arrived_at`, first-visit fix rate, repeat-visit rate) compute from the job's own columns. The Complaint's **Schedule** stage is a form-SLA tracker owned by CS and resolves the moment its job reaches *Confirmed*: CS is accountable for a confirmed date, the technician for arriving.

---

## S7 - Goods track (exchange and replacement)

Satisfies **AC-G1 to AC-G6**. The smallest slice with the largest surprise: **almost nothing needs building.**

```sql
ALTER TABLE complaint_fulfilment_orders
  ADD COLUMN link_role varchar(20);    -- 'rma' | 'replacement' | 'credit_note'
```

RMA and REP already arrive from AutoCount as `orders`: **1,732 `RMA-*` rows (1,731 carrying a dealer) and 2,864 `REP*` rows.** Every number the office retypes into the group is already a row:

| chat, May 2026 | `orders` | dealer |
|---|---|---|
| `RMA-SRT2605-0107` | `RMA-SRT`, 2026-05-13 | HANLIM TRADING SDN BHD |
| `REP202605-0187` | `SORENTO`, 2026-05-13 | HANLIM TRADING SDN BHD [A/C I] |
| `RMA-SRT2605-0118` | `RMA-SRT`, 2026-05-14 | LIVING PORTAL (M) SDN BHD |

So this slice is **linking, not generating**. No RMA, REP or credit note document is produced by this module. Backfill the existing 12 rows by inspecting each linked order's `order_type`. A collect-back and a replacement coexist on one Complaint with distinct roles and a single SLA thread (*"this item already discon & no stock, I will arrange to collect back defect unit first ya"*). The existing `processed_by_cs` <-> `fulfilled` recompute and `LINKABLE_STATUSES` gating must keep working with roles present.

### Group M owns no AC here, and that is itself a finding

The UAC's slotting note (2026-08-02) says **"S7 inherits"** the already-built dispositions and **"its
remaining work is the RMA container and the collection gate"**. That reads S7 as *the goods track as a
whole*. **In this plan the goods track is three slices**, and the note's contents map onto the other two:

| the note says | this plan |
|---|---|
| line dispositions, per-line approve/reject, derived header (AC-M8 to AC-M10, AC-M13) | **S11**, the exchange/return request flow |
| collection gate (AC-M17 to AC-M19) | **S11**, "readiness gate" in its own one-line description |
| RMA container (AC-M11, AC-M14, AC-M15, AC-M16) | **S12**, "RMA lifecycle: own status, age, owner; cross-request container" |
| RMA/REP `link_role` (AC-G1 to AC-G6) | **S7**, this slice, unchanged |

Slotted to S11 / S12 accordingly. **Flagged rather than assumed** - if the intent really was to collapse
S7, S11 and S12 into one slice, that is a sequence change that needs saying out loud, because S11 is gated
on forms-platform F0 to F2 and S7 is not.

> **CONFLICT with AC-M12, and it is a grain conflict, not a wording one.** AC-M12 says *"the RMA link is a
> **line** attribute, not a request attribute"*. This slice's `complaint_fulfilment_orders` is
> **header-grain**: `(complaint_id, order_id)` with no line column
> (`sorento_crm_backend/app/models/complaints.py:151`). Adding `link_role` to it does not make the link
> per-line, so a complaint with three products where only one is collected back cannot express which one.
> The two are reconcilable in either direction - S7 stays header-grain for the legacy complaint flow and
> S12 introduces a line-grain link for the new request flow, or the link table gains a nullable line
> reference - but **that is a decision, and S12 must make it explicitly** rather than discovering it while
> wiring the container.

---

## S8 - Feedback survey

Satisfies **AC-I1 to AC-I6**.

```sql
ALTER TABLE workflow_submissions
  ADD COLUMN respondent_contact_id uuid REFERENCES respond_contacts(id),
  ADD COLUMN source_entity_type varchar(40),
  ADD COLUMN source_entity_id uuid;
CREATE INDEX ON workflow_submissions (source_entity_type, source_entity_id);
```

Two columns generalise beyond the survey: **any** form becomes attachable to **any** entity and answerable by **any** contact. The survey is then an ordinary form definition, designable and versioned - no `complaint_feedback` table exists.

Fired one **working** day after resolution via `work_calendar_configs` + `public_holidays`, delivered as a WhatsApp message carrying a `PortalToken` link (the existing `/view?token=` pattern). Exactly one survey per Complaint regardless of how many jobs or linked orders it had.

**The line:** forms hold what a human writes in prose (survey, optional per-Kind technician checklist); the Service Job holds what the system reasons about (photos, diagnosis, charge state, timestamps). Diagnosis and proof photos are never stored only in `row_data` JSONB, because diagnosis drives billing and the recurring-defect report.

---

## S11 - Exchange / return request flow

Satisfies **AC-M8, AC-M9, AC-M10, AC-M13** (**inherited, already built**), **AC-M17, AC-M18, AC-M19,
AC-M26**. Gated by forms-platform **F0 to F2** and **F1a**, plus **S2a** (validator) and **S4a** (waiting
attribution). Section added 2026-08-02 - this slice previously existed only as a row in the sequence table.

### What is already built, and must not be built again

Verified in this tree on 2026-08-02. **ADR-0011 paying off rather than a coincidence:** the goods track
asked for line-level disposition, and the case was already a form submission.

| AC | already provided by | evidence |
|---|---|---|
| AC-M8 (seven dispositions) | `app/services/workflow_submission_line_disposition.py` | `LINE_DISPOSITION_OPTIONS` seeds exactly `write_off`, `cn_cancellation`, `replacement_same_model`, `replacement_equivalent_value`, `replacement_wrong_model`, `repair`, `maintenance` - as admin-editable lookup master data, so nothing branches on the values |
| AC-M9 (approve some, reject others) | `app/services/workflow_submission_line_status_graph.py` | lines carry their own entity type and graph, scoped to the definition; a decision is per item |
| AC-M10 (derived header, both directions) | `app/services/workflow_submission_derived_status.py` | derives from `is_terminal` over the non-`is_archived` population, reopens when a line stops being decided, and refuses the manual path into or out of the derived pair |
| AC-M13 (nothing to collect) | same disposition module | the `nothing_to_collect` option exists and `disposition_reason` is a real column |

**The one gap inside that inheritance:** AC-M13 says the disposition **requires a reason**, and nothing
enforces it. `WorkflowFormsService.set_line_disposition`
(`sorento_crm_backend/app/services/workflow_forms_service.py:1322`) accepts `nothing_to_collect` with
`disposition_reason=None`. That is a thin guard, and **S11 owns it** - it is the exact failure the
discovery study names, where RMAs stay open forever because nobody recorded why nothing came back. Whether
"requires a reason" is a property of the option (data, so the admin can mark any option reason-required)
or a hardcoded check on that one value is a small design call this slice should make rather than inherit.

### Collection readiness gate (AC-M17 to AC-M19)

**Behaviour, and it is a hard gate.** When collection is arranged the Dealer is notified and must
**acknowledge with photos** before collection is scheduled (AC-M17). The photos are proof of readiness
**before** dispatch, not proof of handover after it - the failure being prevented is a truck arriving and
finding nothing collectable.

The gate is **only safe because of S4a** (AC-M18). An unacknowledged request sits at `waiting_on = dealer`
with `waiting_since`, so the delay is visibly theirs and CS is not blamed for it. Without waiting
attribution this is a hard block that makes CS's numbers worse for someone else's inaction, which is
precisely the complaint R2 came from. **S11 must not ship ahead of S4a.**

CS may override (*collect anyway*) **with a required, recorded reason** (AC-M19). An unoverridable gate
would be routed around by phone within a week.

> Note the party vocabulary problem flagged in S4a: AC-M1's list does not contain `dealer`, yet AC-M18
> requires it. Resolve that in S4a, not here.

### `rma_readiness` is data, not a third feature (AC-M26)

R5's three checks - the claimed model, the claimed quantity, defect visibility - are **three sentences in
one `validation_guidance` string** on a new `rma_readiness` attachment type, using the S2a mechanism. If
this slice finds itself writing code per check, S2a's AC-M25 ("no hardcoded branch per type") was not
actually delivered, and that is the signal to go back rather than to special-case here.

---

## S12 - RMA lifecycle

Satisfies **AC-M11, AC-M12, AC-M14, AC-M15, AC-M16**. Gated by **S11** and **S7**. Section added
2026-08-02 - this slice previously existed only as a row in the sequence table.

### What Group M asks for

**An RMA that is a first-class thing rather than an order number in a spreadsheet.** Today all 1,732 RMA
rows carry only `NEW` / `DELIVERED` and the truth lives in an Excel file called "RMA summary" (AC-M14). So
the RMA gains its **own lifecycle status, age and owner**, not the outbound order vocabulary, and it
**closes against its REP or CN** (AC-M15).

**It is a cross-request collection container** (AC-M11): lines from several requests may attach to one
RMA, and lines may be added to an **existing open** RMA. That is forced by the SOP (*"items can be added
onto an existing RMA"*), and it is what makes the RMA an entity rather than a per-request child.

**Sequencing is expressible per line** (AC-M16): local allows REP before RMA; outstation requires RMA first
so it is one trip, not two. Per line, because one request's lines do not all move together.

### Two decisions this slice must make explicitly

1. **What the container actually is.** S7 established that RMAs **arrive from AutoCount as `orders`** and
   that this module does **not** generate documents. But AC-M11 needs a container that can exist and
   accept lines **before** an AutoCount RMA number exists, and AC-M14 needs a lifecycle the `orders`
   vocabulary does not have. Either the container is a CRM-side row that later binds to the AutoCount
   order, or it is the order plus a CRM-side lifecycle sidecar. **Not resolved here** - it decides whether
   S7's "linking, not generating" survives intact.
2. **The line-grain link** (AC-M12). See the conflict recorded under S7: `complaint_fulfilment_orders` is
   header-grain, and AC-M12 requires the RMA link to be a **line** attribute so that a line settled by a
   CN alone closes with no RMA. This slice either adds a line-grain link for the new request flow and
   leaves S7's header-grain table alone for the legacy complaint flow, or unifies them. Both are
   defensible; drifting into one by accident is not.

---

## S10 - Dealer reciprocal view

No Group M ACs. Unchanged by the 2026-08-01 grill.

---

## S9 - Reporting

Satisfies **AC-J1 to AC-J11**, **AC-M32**. Renders the attribution S4a captures (**AC-M7**). Three views per BRD Req #13: operational (open by stage and PIC, SLA risk colour-coded), performance (response and resolution by week / month / PIC / category / dealer, in **working hours**), customer experience (survey trend, complaints by category, recurring defect types from diagnosis).

Stage clocks are chained `form_sla_configs` rows (**AC-E3**) - `Acknowledge` -> `Assess` -> `Schedule` -> `Resolve` -> `Fulfil`, linked by `next_config_id`, each with its own `team_set_code`, policy and accountable assignee. Nothing new is built for timing: `conversation_sla_tracking` already stores `response_time`, `resolution_duration`, `assigned_to_id`, `responded_by`, `handled_by_id`, `resolved_by`, `escalated_at`.

**One accountable party per stage. No blended per-person resolution time across stages** - a Complaint passes CS, then a technician, then the warehouse, and a single number charges whoever held it for delays they did not cause.

**Stall time** is the metric that does not exist today: time in a state with nobody acting. It is what `No arrange??` is, and it would have caught every failure in the retired groups.

Rejection is a **terminal outcome that counts** in resolution statistics, so rejecting is not the fast path to a good number (**AC-E16**).

### What Group M changes about this slice

**Two report surfaces, no new capture.**

- **Breach attribution (AC-M7).** "Of 40 breaches, 26 were waiting on an external party" is the sentence
  that makes AC-M2's decision (never pause the clock) survivable. It **cannot** be computed from a mutable
  case-level column, because by report time the case is waiting on something else or nothing at all. S4a
  must therefore capture waiting changes as point-in-time records; **S9 reads them, and this slice fails
  if S4a shipped only the column.** Say so during S4a's review, not here.
- **Cost reporting (AC-M32).** Spend per provider and cost per case, from `case_cost_lines`. Both are
  needed: per provider answers "who are we paying", per case answers Ms Tan's original question "what did
  this complaint cost us". Neither is derivable from the other.

**One exclusion to write explicitly, or the metric lies:** rejected visit attempts (R12) are excluded from
technician attend time, while still counting toward the case's own resolution clock. An implicit exclusion
here is the same failure as a paused clock elsewhere.

Every listing uses shared `DataGrid` (`tableLayout: {width:'fixed', columnsResizable:true}`, explicit `size`, `truncate` + `title`); every dropdown uses `SearchableSelect`; every detail page renders **all** sections with explicit empty states; datetimes render via `formatDateTimeInMalaysia(rawString)`.

---

## Cross-cutting

**Migrations.** Each `down_revision` chains onto a **committed** main head, never an uncommitted WIP migration (`alembic heads` reads the filesystem and will lie). Revision ids <= 32 chars. After any branch merge, verify a single head and fix a fork with `alembic merge`.

**Every new owned table** registers with `CompanyScopedMixin` and is added to the multi-company CI guard, with the leak test asserting `UNSET` scope returns 0 rows.

**Every new column that must reach the FE** goes into both manual dict builders where one exists. Schema inheritance alone silently drops it.

**Tests are Postgres only.** No sqlite engine, no `@compiles(..., "sqlite")`, no mutating shared `Base.metadata` column types. Committing tests use a private `zzt_` scratch schema. Every cleanup `DELETE` is scoped to marker rows - the local DB is a copy of production data and an unscoped delete has already destroyed real records once. Pytest needs the DB exclusively; a `--reload` uvicorn or a parallel suite produces hundreds of bogus failures.

**Every destructive or detaching action** - including **Unlink** of an RMA/REP or a Service Job - gets an `AlertDialog` confirmation with "This action cannot be undone" and a count for bulk. Never `confirm()`, never one-click. `DELETE` endpoints hard-delete; retention is a separately-named **Archive**.

**Handoff** is always a production build (`npm run build && npm start`), never a dev server. Verify by real sidebar clicks from `/`, at 375px and 1280px.

---

## Risks

| risk | mitigation |
|---|---|
| **S0 is a shared dependency.** Dealer Kit S2.5 is already blocked on it; two features porting it separately means a merge conflict in core plumbing | **This risk materialised, and was missed.** project-sales had already built the engine (`0ec9875d2`) before this plan was written, so the "two features porting it separately" case was live from day one. Resolved by adopting rather than porting (ADR-0012); Dealer Kit S2.5 must adopt the same commit. **The residual risk is merge ORDER:** the engine is still unmerged, so after-sales cannot merge until it reaches `main`. That belongs to whoever sequences project-sales. |
| **Consumer receipt OCR is the weakest link.** Shop names are fuzzy-matched against 3,284 customers with no verification possible | **S3-pre spike measures it before S3 is committed** (approved); never block submission; flag low confidence for CS |
| **Groups retired too early.** Retirement needs S5 + S6 + S7; a half-retired group is worse than an intact one | keep the forwarded-message fallback until all three ship; make retirement an explicit go/no-go with Sorento |
| **Office stops reading a group and never starts reading a dashboard**, so complaints are created perfectly and ignored | the **Acknowledge** form-SLA stage notifies the assigned CS member on creation and escalates on breach, so a Complaint arrives as a clocked personal assignment rather than a row to notice. Structural, not cultural - no daily digest needed for correctness |
| **Salesman code map is a human judgement** (83 codes, unknown collapse) | seed script is idempotent and re-runnable; unresolved routes to a team lead and is visible, never silent |
| **AI photo validation adds latency on a bad phone connection** | synchronous but with a hard timeout that degrades to "unvalidated" rather than blocking completion |
| **`notifications` is a core table used everywhere** | the NOT NULL drop plus two partial unique indexes is a migration, not a redesign; existing user-only paths keep their index shape |
| **Clause 17 unresolved** (residential-only versus 23 Project complaints) | modelled, not enforced; flagged to Sorento; the engine reports it as a qualification rather than a refusal |
| **SLA numbers get worse the day S4a ships**, because time waiting on a plumber still counts (AC-M2) and nothing is paused | accepted deliberately, not a defect. Attribution is the mitigation: "of 40 breaches, 26 were waiting on an external party" (AC-M7) is more useful than a clean number that hides them. Tell Sorento **before** the first report, not after |
| **S11's collection gate shipping ahead of S4a** would hard-block CS on a Dealer's inaction with no way to say whose delay it is | ordering is a stated gate on S11, not a preference. If S4a slips, the gate ships advisory (notify, do not block) rather than hard |
| **S4a's waiting field captured as a mutable column only**, making AC-M7 uncomputable at report time and discovered in S9 | point-in-time capture is an S4a acceptance condition, reviewed at S4a, not at S9 |

## Group M conflicts with existing slice text (added 2026-08-02)

Recorded loudly rather than resolved by editing a slice quietly. Each one needs a decision before the
slice it sits in is built.

| # | conflict | where | resolution needed from |
|---|---|---|---|
| 1 | **`site_maps_url` is declared twice.** The UAC's slotting note caught S1's copy; `service_jobs` in S6 declared the same column. AC-M37's three fields replace both | S1, S6 | already applied in this plan; no decision needed, but the S6 occurrence was missed by the note |
| 2 | **A per-domain photo endpoint contradicts a core validator.** S6 printed `POST /api/v1/service-jobs/{id}/photos -> { photo_id }`, which is exactly the special case AC-M21 removes | S6 | applied: retired in favour of the shared attachment path. Verify at S2a review that no domain re-adds one |
| 3 | **AC-M12's line-grain RMA link versus S7's header-grain link table.** `complaint_fulfilment_orders` is `(complaint_id, order_id)`; a per-line RMA cannot be expressed on it | S7, S12 | **S12 must decide**: separate line-grain link for the new flow, or unify |
| 4 | **AC-M11 needs an RMA container that can exist before an AutoCount RMA number does**, while S7 says this module never generates RMA documents | S7, S12 | **S12 must decide**: CRM-side container that binds later, or order-plus-sidecar |
| 5 | **The UAC slotting note assigns Group M's goods-track ACs to "S7"**, but this plan splits the goods track into S7 / S11 / S12 and the note's contents map onto S11 and S12 | slice sequence | slotted to S11 / S12 here. If a slice merge was intended, that is a sequence change and needs saying |
| 6 | **AC-M33 turns a raise into a fallback in CORE form-SLA code** shared by PR, SF, stock inquiry and complaint, not just after-sales | S4 | where the fallback is configured, and whether it applies to all form types |
| 7 | **AC-M1's party list has no `dealer`, but AC-M18 requires `waiting_on = dealer`.** An inconsistency inside Group M itself | S4a, S11 | UAC owner. Recommendation: make the party configurable master data, like the reason |
| 8 | **AC-M34's "no new table" versus AC-M35's inbox of unattached calls.** `activity_events.entity_type` / `entity_id` are NOT NULL, so a call with no case has nowhere to sit | S4 | whether an unattached call parks as `entity_type = 'respond_contact'` |
| 9 | **AC-M4's "mandatory before further action" is unspecified**, and would be the third write guard on the same actions beside the status engine and the handling lock | S4a | which actions the guard covers, and where it sits in the stack |
| 10 | **AC-M1 puts waiting on the case; AC-M7 needs it per breach.** A mutable column cannot answer "what were we waiting on when this breached", and one case runs several stage trackers | S4a, S9 | point-in-time capture (event log) is required; per-tracker column is the open call |

**Also corrected:** `documentation/plans/PLAN-sla-extend-deadline.md` still reads *"Not started"*. Extend is
**built** - service, both endpoints, model counters, FE dialog and button, and
`tests/test_sla_extend_deadline.py`. AC-M6 therefore costs no engine work. Someone should fix that status
line.

## Open, pending Sorento (not blocking build)

1. **Clause 17** - cover is residential only, yet 23 of 50 existing Complaints are Project/commercial.
2. ~~Who takes the money~~ - **RESOLVED: Sorento invoices afterwards, the technician collects nothing.** No cash surface on the technician screen.
3. ~~Who owns the burst debounce timer~~ - **RESOLVED: the n8n wait node.** CRM stays stateless for intake.
4. **Salesman suffixes** - whether `SEAN` / `SEAN I` / `SEAN III` / `SEAN IV` are one person, per code. Confirmed **not** a company split.

## Explicitly out of scope

Optimising scheduler (availability, skills, geo-clustering, capacity) - full billing (invoice and payment; AutoCount does this) - pricing rules engine - consumer signature on the technician's phone - offline/PWA sync queue - soft module dependencies - historical import of the two chat exports and their 1,238 media files (`documentation/backlogs/backlog.md`).

## Next step

**Grill this plan** before writing code (`PRINCIPLES.md` step 1: "Grill the plan itself before coding"). Weakest areas, in order: the S3 extraction contract under real receipt variety, the S0/Dealer-Kit coordination, and whether S2's golden set actually covers the policy's 31 kinds or just the seven cases written above.

**Since 2026-08-02, add to that list the ten items under "Group M conflicts with existing slice text".**
Three of them gate a slice that is already in the sequence and cannot be started without an answer:
AC-M4's enforcement point and AC-M1-versus-AC-M7's grain (both **S4a**), and the RMA container's identity
(**S12**).
