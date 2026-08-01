# PLAN - After-Sales, Warranty & Service Scheduling

**Status:** **In build, S0.** Plan written 2026-07-26 from a completed grill (19 decisions). S0 rewritten
2026-08-01 after discovering the status engine already existed (ADR-0012): engine adopted, sibling alembic
heads merged, complaint registration in progress. Forms-platform F0 is in build in parallel (343 tests
authored test-first, implementation under way).
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
| **S3** | consumer portal intake: a Consumer can lodge a Complaint | S1, S2, **S3-pre spike**, bilingual consent notice (available) |
| **S4** | notification spine + Respond outbox: everyone is told | S1 |
| **S5** | WhatsApp AI intake: Sean's eight seconds | S3 (contract), S4 |
| **S6** | Service Jobs, dispatch board, technician portal | S0, S4 |
| **S7** | goods track: RMA/REP link roles | S4 |
| **S8** | feedback survey on workflow forms | S4, S6 |
| **S11** | **exchange/return request flow**: dealer submits, CS gates per line, dispositions, readiness gate | F0-F2, F1a, S4 |
| **S12** | **RMA lifecycle**: own status, age, owner; cross-request container; closes against REP or CN. Retires the "RMA summary" Excel | S11, S7 |
| **S10** | **dealer reciprocal view**: a Dealer sees complaints and service history for their own customers | S6, S7 |
| **S9** | reporting and dashboards, incl. dealer sell-through | S2, S6, S7, S8, S10 |

**The two WhatsApp groups can only be retired after S5 + S6 + S7.** Until all three land, some traffic has nowhere to go. State this to Sorento explicitly; a half-retired group is worse than an intact one.

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

Satisfies **AC-B1 to AC-B12**.

### Schema

```sql
-- respond_contacts: three independent nullable bindings, NO party_kind column
ALTER TABLE respond_contacts
  ADD COLUMN customer_id   uuid REFERENCES customers(id) ON DELETE SET NULL,
  ADD COLUMN user_id       varchar REFERENCES users(id)  ON DELETE SET NULL,
  ADD COLUMN technician_id uuid REFERENCES technicians(id) ON DELETE SET NULL;
-- no door_answered_at: there is no door question to remember (see "The door" below)

-- complaints: parties get real homes
ALTER TABLE complaints
  ADD COLUMN customer_id uuid REFERENCES customers(id),  -- the Dealer
  ADD COLUMN site_address text,
  ADD COLUMN site_contact_name text,
  ADD COLUMN site_contact_phone text,
  ADD COLUMN site_maps_url text;
ALTER TABLE complaints ADD COLUMN reported_by_role varchar(20);   -- ADDED, not renamed
```

**Additive, not a rename.** `reported_by_role` is a new column backfilled from `customer_type` via a documented mapping (`Project`, `SMC`, `E Commerce` were account categories, not reporters; the 7 blanks become `cs`). `customer_type` is **left in place, read-only, for one release** and dropped later, exactly like `customer_name` and `salesperson`. Renaming a column on a live table with 50 rows buys nothing and makes the migration irreversible mid-release; adding one is reversible by ignoring it. A guard test asserts nothing **reads** the legacy columns, so the eventual drop is a pure deletion.

### Kind derivation (AC-B2)

Never stored. `customer_id` set means dealer staff; `user_id` set means Sorento staff; `technician_id` set means technician; none set means Consumer. **More than one may be set** - the Sanimart case (a dealer's owner reporting a fault in his own home) sets `customer_id` and still resolves the Site to his house, because the Site lives on the Complaint (**AC-B3**).

### Salesperson: seed once, read forever (AC-B7 to AC-B11)

`customers.account_owner_user_id` is 0 of 3,284. A one-off script, not a runtime path:

1. Build a `salesman_code -> users.id` map. **Sorento creates the `users` rows** for salesmen (needed for Project Management anyway); the seed script creates stand-in users locally for testing only. 83 distinct codes; suffixes (`SEAN` / `SEAN I` / `SEAN III` / `SEAN IV`) collapse many-to-one where they are one person. **Confirmed not a company split** - every suffix appears under both Sorento and Mocha in `orders`. Junk codes (`0`, `ACT`, `CS01`, `WH02`, `MARKETING`, `SAMPLE`, `FUNITURE`, `TERA`) map to nothing.
2. Per customer, take the salesman on their **most recent** order. 2,191 resolve to a single code; 322 are multi and get most-recent-wins as a seed.
3. Write `account_owner_user_id`. Idempotent JOIN-based "set where mismatch", so a re-run corrects a prior bad run (**AC-K1**).

Page by **keyset**, not `yield_per` - a named cursor dies on commit. Dry-run must assign nothing (beware autoflush) and be verified at `--batch 1`.

**Runtime reads only `customers.account_owner_user_id`.** A guard test asserts no module code references `orders.salesman` (**AC-B9**). Unresolved (~770 dealers with no orders) routes to the after-sales team lead and flags the Complaint `salesperson unresolved` - never silently dropped (**AC-B10**).

### The door: there isn't one (AC-B4, AC-B5, AC-B5a, AC-B5b)

**No question is asked.** Kind resolves by elimination: `customer_id` means dealer staff, `user_id` means Sorento staff, `technician_id` means technician, **nothing set means Consumer**.

```
GET /api/v1/public/portal/journey  -> { journey: 'consumer'|'dealer'|'staff'|'technician' }
```

This works because the bindings get populated: Sorento configures dealer contacts manually and creates `users` rows for salesmen (they need them for Project Management regardless). Reuses `PortalToken` + OTP; no new auth.

**The failure mode, and how it self-heals.** An unbound dealer contact would be mis-routed to the Consumer journey and asked for a receipt they do not hold. So the Consumer journey's first step accepts **either a receipt photo or a typed order number**. A quoted Sorento order number resolves against `orders`, and we write `respond_contacts.customer_id` from that order's customer and switch them to the dealer track. The binding repairs itself, silently, without a question ever being asked - which is strictly better than a door question, because it also fixes contacts nobody remembered to configure.

### Seeding for test (AC-B12)

`scripts/seed_dealer_contacts.py` populates representative `respond_contacts.customer_id` bindings for local and staging. **Production bindings are configured manually by Sorento.** No bulk import ships.

---

## S2 - Warranty engine

Satisfies **AC-D1 to AC-D15**. This is a **deterministic engine, so it is test-first**: the golden set is written as failing tests before any implementation, per `PRINCIPLES.md` step 4.

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

CREATE TABLE warranty_policies (            -- versioned, dated
  id uuid PRIMARY KEY, version varchar(32),           -- 'v15'
  effective_from date, effective_to date,
  source_attachment_id uuid REFERENCES attachments(id),  -- the PDF, for Req #12
  policy_text text                          -- extracted, what the AI is restricted to
);

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

### Policy Q&A (AC-D14, BRD Req #12)

The AI is restricted to `warranty_policies.policy_text` for the version in force, answers by quoting, and **routes to Customer Service** when the situation is ambiguous or outside the document. Prompt lives in `ai_prompt_registry` (versioned, labelled, publishable without redeploy).

### Deliberate departures, both recorded in ADR-0010

- **Registration is optional.** Policy clause 3(b) says a product must be registered before a claim may be processed; the BRD says cover auto-activates from the purchase date. **BRD wins.** Lodging a Complaint auto-creates the Registration when absent (**AC-D8**).
- **Clause 17** (residential only, commercial and industrial excluded) is **modelled but not enforced**. 23 of 50 existing Complaints are Project cases. Awaiting Sorento's ruling (**AC-D15**).

`products.warranty_months` (0 of 11,415 populated) is abandoned; a guard test asserts nothing reads it (**AC-D13**).

---

## S3 - Consumer portal intake

Satisfies **AC-C10 to AC-C19**.

### S3-pre: extraction accuracy spike (approved 2026-07-26, blocks S3)

Before S3 is committed, a throwaway harness scores extraction over **50 real dealer receipts** from the corpus (`After-Sales/**/*.pdf` plus receipt photos). Measure three numbers separately: shop-name -> `customers` match rate, purchase-date extraction rate, model-code extraction rate. Publish them.

The whole consumer journey assumes these are high. If shop-name match lands under ~75%, Customer Service ends up fixing bad guesses instead of reading a clean template, and the feature inverts - it becomes more work than the WhatsApp group it replaced. That is worth half a day to learn now rather than after S3 ships. Throwaway code, not merged.

### The slice proper

**Extraction pre-fills an editable form, not a read-only confirmation.** Every extracted value - name, phone, site address, shop name, purchase date, value, quantity, Kind - renders as a normal input the consumer can correct. Both versions are stored (AI original + human correction), which means **production becomes its own measurement harness**: correction rate per field is extraction accuracy, continuously, without instrumenting anything else. Correcting the shop name re-runs the dealer match. This materially reduces the blast radius of concern 1 - a bad extraction costs the consumer one edit rather than costing CS a cleanup - but it does not eliminate it, because a wrong purchase date the consumer does not notice still mis-computes warranty. The S3-pre spike still runs.

A **Consumer 360 page** ships with this slice: profile, every purchase (dealer, dealer document number, product, quantity, value, date), every Complaint, every stored document. This is the screen that makes the commercial purpose real rather than aspirational. **Phase 1 is frontend-first against mocks** - build the whole flow with stubbed hooks, tune every state, verify in a browser via sidebar clicks, and only then wire the backend.

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

### UI rules

No SKU, product code or UUID ever shown to a Consumer; no dealer picker (**AC-C11**). Tiled chooser reads `warranty_product_kinds.consumer_label` / `consumer_icon`. Usable at 375px and 1280px; modals scroll to their submit button.

---

## S4 - Notification spine and the Respond outbox

Satisfies **AC-H1 to AC-H14**.

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

---

## S5 - WhatsApp AI intake

Satisfies **AC-C1 to AC-C9**. Depends on S3's extraction contract and S4's spine.

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

---

## S6 - Service Jobs, dispatch and the technician

Satisfies **AC-F1 to AC-F23**.

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
  site_address text, site_contact_name text, site_contact_phone text, site_maps_url text,
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

```sql
-- waiting attribution: the single design behind R2/R7/R8/R12 (AC-M1 to AC-M7)
-- Applied to the case (a form submission per adr/0011) and to service_jobs.
ALTER TABLE service_jobs
  ADD COLUMN waiting_on_party varchar(24),          -- cs|maintenance|plumber|customer|supplier|warehouse
  ADD COLUMN waiting_on_reason_id uuid REFERENCES lookup_values(id),
  ADD COLUMN waiting_since timestamp;
-- The SLA clock is NEVER paused. A real deadline move is Extend (PLAN-sla-extend-deadline.md).

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

Site geolocation (AC-M37 to AC-M40) adds `latitude`, `longitude`, `place_id` alongside the existing
`site_address`. Calls are a **`call` activity** in the existing `activities` module - no new table
(AC-M34).

### Dispatch board (AC-F3 to AC-F5)

Grouped by day and technician, drag to reassign. **No availability grid, skills matrix, geo-clustering or capacity optimiser** - explicitly out of scope. A job cannot leave *Proposed* without a date **and** a recorded customer agreement; `Service Date: TBA` is not a valid *Confirmed*. Jobs past their date still in *Proposed* surface as **stalls** with elapsed stall time.

### Technician portal (AC-F8, AC-F9, AC-F19)

One screen. Today's jobs only - no listings, no search, no records but their own. Job view shows site, contact, fault and the Consumer's photos. Actions: *On my way* -> *Arrived* -> photos -> diagnosis -> *Complete*. Verified at 375px.

### Photo validation (AC-F10 to AC-F18)

```
POST /api/v1/service-jobs/{id}/photos   (multipart)
->  { photo_id, ai_score: 0.42, ai_suggestion: "The whole product isn't visible - step back
      and include the pipe joint.", below_threshold: true }
```

**Synchronous, on upload, while the technician is still on site.** A few seconds with a spinner. Async validation that flags a bad photo after the van has left is worth nothing - the entire value is the retake, and the retake is only possible on site.

Below `min_score`: show the suggestion, make **Retake** prominent, allow **Use anyway** only with a reason. Score, suggestion and override reason all persist. The override reason is itself a metric - a photo type overridden by everyone means the `guidance` is wrong, not the technicians.

The validator's prompt lives in `ai_prompt_registry` and the per-type `guidance` is data. **No hardcoded branch per photo type.** The same validator checks Consumer intake photos (**AC-F18**), because bad evidence at intake is what wastes a visit.

**Geotag is captured in the background and never blocks.** Permission denied or no GPS omits coordinates and the job still completes. A technician who cannot close a job at 6pm in a basement will phone the office and have someone close it for them, which is worse data than not asking.

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

## S9 - Reporting

Satisfies **AC-J1 to AC-J11**. Three views per BRD Req #13: operational (open by stage and PIC, SLA risk colour-coded), performance (response and resolution by week / month / PIC / category / dealer, in **working hours**), customer experience (survey trend, complaints by category, recurring defect types from diagnosis).

Stage clocks are chained `form_sla_configs` rows (**AC-E3**) - `Acknowledge` -> `Assess` -> `Schedule` -> `Resolve` -> `Fulfil`, linked by `next_config_id`, each with its own `team_set_code`, policy and accountable assignee. Nothing new is built for timing: `conversation_sla_tracking` already stores `response_time`, `resolution_duration`, `assigned_to_id`, `responded_by`, `handled_by_id`, `resolved_by`, `escalated_at`.

**One accountable party per stage. No blended per-person resolution time across stages** - a Complaint passes CS, then a technician, then the warehouse, and a single number charges whoever held it for delays they did not cause.

**Stall time** is the metric that does not exist today: time in a state with nobody acting. It is what `No arrange??` is, and it would have caught every failure in the retired groups.

Rejection is a **terminal outcome that counts** in resolution statistics, so rejecting is not the fast path to a good number (**AC-E16**).

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

## Open, pending Sorento (not blocking build)

1. **Clause 17** - cover is residential only, yet 23 of 50 existing Complaints are Project/commercial.
2. ~~Who takes the money~~ - **RESOLVED: Sorento invoices afterwards, the technician collects nothing.** No cash surface on the technician screen.
3. ~~Who owns the burst debounce timer~~ - **RESOLVED: the n8n wait node.** CRM stays stateless for intake.
4. **Salesman suffixes** - whether `SEAN` / `SEAN I` / `SEAN III` / `SEAN IV` are one person, per code. Confirmed **not** a company split.

## Explicitly out of scope

Optimising scheduler (availability, skills, geo-clustering, capacity) - full billing (invoice and payment; AutoCount does this) - pricing rules engine - consumer signature on the technician's phone - offline/PWA sync queue - soft module dependencies - historical import of the two chat exports and their 1,238 media files (`documentation/backlogs/backlog.md`).

## Next step

**Grill this plan** before writing code (`PRINCIPLES.md` step 1: "Grill the plan itself before coding"). Weakest areas, in order: the S3 extraction contract under real receipt variety, the S0/Dealer-Kit coordination, and whether S2's golden set actually covers the policy's 31 kinds or just the seven cases written above.
