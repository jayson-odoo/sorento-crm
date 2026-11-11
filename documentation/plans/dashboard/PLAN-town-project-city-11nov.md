# PLAN: Town project district (TOWN-PROJECT-CITY)

Status: Plan - owner answered card v1 (11 Nov 19:58); card v2 (Malaysia map) + mock in progress. Track: full (size L: new snapshot sections, redaction, a map world).

Trigger: owner, 11 Nov 2026 ~19:15 MYT. Show the project business beside the dealer street in Sorento Town.
PR: foundryx-sdn-bhd/sorento-crm#2342 (`crew-lane: TOWN-PROJECT-CITY`). Mock: `mock/town-project-city-mock.html`.

## Facts this card stands on (read on main, a80d65fa)

- Snapshot: `build_snapshot` `sorento_crm_backend/app/services/town/snapshot.py:408`; one build per company per tick into
  Redis (full + redacted twins, `store` :552); the route `app/api/v1/town.py:72` reads no business table; wallboard =
  `strip_names` :529 applied on serve.
- Sales type per invoice: `inv.document_sales_type()` (`services/sales/invoiced_sales.py`), values `dealer` / `project` /
  `other` / `set_apart` / `mixed` / `type_not_set` / `no_sales_order` (:47-66). `_today_and_compare` (snapshot.py:76)
  already joins it, so the project total is one more filtered sum in the same query.
- Projects: `projects.projects` (`models/projects.py:285`): `outcome` open | won | lost | dormant (:78-81), `status_id`
  -> statuses keyed `identified, registered, specified (label "Spec In"), quoted, tendering, po_received, lost, dormant`
  (`services/project_seed_service.py:51-63`). "Final Negotiation" is the flag `is_critical`, not a rung (:349).
  There is no Sample rung; samples are their own record (`sample-requests`). A project can sit on PO Received with
  outcome still open (another scope still quoting, models/projects.py:73-76). Portal registrations not yet approved
  (`approval_state` draft / pending / resubmitted / rejected) are kept out of every internal path (:86-95).
- Sales profile (`models/projects.py:408`): `state`, `estimated_sales_value`, `launch_date`, `expected_delivery_from`,
  `expected_delivery_to`.
- Trading house = the party role `trading_house` (`services/project_party_roles.py:34`) on `projects.party_links`
  (:175), party -> customer through `parties.customer_id` (set only once the party has actually bought).
- Project detail page: `/project-sales/{projectId}`.
- Crew data fact (dev copy to 06 Nov): 1 of 1,650 project-type sales orders in 90 days links to a CRM project. So
  NOTHING here is per-project sales, and `project_label` text is never used.

- **Where a dealer is (for the map).** The only location AutoCount sends for a debtor is `Debtor.AreaCode`, stored as
  `customers.region` (`models/order.py:159-161`, canonical field `schemas/canonical_masters.py:179-185`): free text, no
  reference table, written whenever sent. `customers.billing_address` (JSONB, `models/order.py`) is never written by
  the import (`services/customer_import_service.py:99`, NEVER_WRITTEN) and `customers.country` holds no state.
  There is no other state column on customers. How many dealers have a usable `region`, and what spellings it holds,
  is NOT measurable in this sandbox (no dev data): asked of crew (card question Q6).
- **Where a project is.** `sales_profile.state` (`models/projects.py:432-433`), free text filled from the editable
  lookup set `my_state` (seeded with the 13 states + Kuala Lumpur, Labuan, Putrajaya,
  `alembic/versions/prreg_0001_project_registrations.py:62-79`). `LookupResolverService.resolve("my_state", raw)`
  (`services/lookup_resolver.py:29`) already turns a typed spelling into a set value; the Town reuses it.

## Owner answers (11 Nov ~19:58 MYT)

Q1 (a), plus a new layout: the whole Town is a stylised Malaysia map, Sorento HQ at Shah Alam, dealers in their own
state, project sites in the project's state. Q2 (a). Q3 (a), and the no-dates plot must look nicer (a tidy prepared
plot with a site board, not a bare fence). Q4 hide dormant (the "+N dormant" count stays in the mock; owner may
strike it). Q5 (a).

## Behaviour card (v2: the Malaysia map)

### Rules

1. **The map.** The Town is a stylised (not to scale) map of Malaysia in the existing shallow sea: Peninsular
   Malaysia (Perlis, Kedah, Pulau Pinang, Perak, Kelantan, Terengganu, Pahang, Selangor, Negeri Sembilan, Melaka,
   Johor, with Kuala Lumpur and Putrajaya as enclaves in Selangor) and East Malaysia across the sea (Sarawak, Sabah,
   Labuan). Each state is its own land patch with a name label. Busy states get more room than their real size (a
   schematic, like a metro map). The state shapes are a static polygon table in the frontend; they are not data.
   One camera fits the whole map at 1280 and 375 wide; drag, tilt, zoom and reset stay as today.
2. **HQ at Shah Alam.** The scoreboard plaza, approvals office, warehouses, depot and the port (Port Klang, on the
   Selangor coast) all sit at Shah Alam. Incoming overseas ships arrive there as today.
3. **Split board** (unchanged from v1, Q2 a). Under "Sold today RM X": "Dealers RM a · Projects RM b · Other RM c",
   from each invoice's sales type, so a + b + c = X exactly, credit notes with their sign. Without `sales.reports.view`
   no RM anywhere (server-side): "Dealers 26 · Projects 3 · Other 2 invoices". Same three rows in the sales lightbox.
4. **Dealers by state.** The same 30 shops and the stalls as today (ranking, caps and lit rule unchanged) are placed on
   a short high street inside their state, from `customers.region` resolved to a `my_state` value (rule 9). A
   state's street holds as many shops as it has; empty states are plain land.
5. **Project sites by state.** One site per open project (outcome open, approved or staff registration), cap 30: full
   viewers get the top 30 by estimated value (blank last, ties by code), redacted viewers the same 30 in hashed
   order. Each sits in a small project quarter inside the project's state (`sales_profile.state`, resolved through
   `my_state`), beside that state's dealer street. "+N more projects" on one sign at HQ.
6. **Site look = the project's own timeline** (Q3 a). Progress = (today - launch_date) / (delivery - launch_date),
   delivery = `expected_delivery_from`, else `expected_delivery_to`; both must be set and delivery after launch.
   Before launch: a marked-out footprint with a "Launching" board. 0-25% groundworks; 25-60% frame + tower crane;
   60-95% clad + crane; 95% and over finished. **No usable dates: a tidy prepared plot** (levelled pad with neat
   edging, survey pegs, a clean site board, a short hoarding with a Sorento-blue band, a site cabin).
7. **Sales stage = flag only.** Identified grey, Registered blue, Spec In teal, Quoted amber, Tendering orange, PO
   Received green; Final Negotiation (`is_critical`) adds a red pennant. Stage never changes the building. No Sample
   flag (there is no Sample rung).
8. **Trading houses = slate-blue glass towers**, flat-roofed, unlike the cream pitched-roof shops; own legend entry.
   One per customer linked as `trading_house` on an open site (party with a `customer_id`), cap 12 by number of open
   projects then code; placed in that customer's state like a dealer. Lit on a posted Project-type invoice today (Q5 a).
9. **State resolution and "State not set".** A dealer or trading house uses `customers.region`, a site uses
   `sales_profile.state`; each is resolved to a `my_state` value with `LookupResolverService` (exact value or a
   known alias in the set). Anything blank or unresolved goes to a small **"State not set"** islet just off Shah
   Alam, so it is visible and fixable, never guessed. No address text or name is parsed for a state.
10. **Lost and dormant disappear** at the next tick (~5 minutes); dormant is counted on the HQ sign "+3 dormant" (Q4).
11. **Click.** A site opens its lightbox (name, code, stage, final negotiation, state, timeline, estimated value,
    "Open project" to `/project-sales/{id}`; redacted: stage, state, timeline only). A trading house: name (full only),
    open projects it is on, invoices today. A state: "Selangor: 8 dealers (3 bought today) · 3 project sites · 2
    trading houses" (counts only, every variant).
12. **Lorries and ships leave from Shah Alam.** Lorries drive the depot -> a west-coast highway spine (branch to the
    east coast) -> the dealer's shop (dealer orders) or the state's project quarter gate (project orders, never a
    specific site: no order-to-project link exists). Orders for Sabah, Sarawak and Labuan go by a small coaster ship
    from Port Klang. A due order whose customer has no shop drives to the edge of its state when resolved, else to
    the "State not set" islet. Depot label "12 to deliver · 3 projects".
13. **Wallboard.** No dealer, project or trading-house names, codes, values or ids (keys opaque); state names, counts,
    flags, looks and lit state stay.
14. **Cost.** Per tick: open projects + profile + status (one query), trading-house links + today's project-type
    buyers (one query), one extra filtered sum in the today query, `demand_class` in the deliveries group, and
    `region` read alongside the dealer rows already fetched. State resolution runs once per distinct spelling per
    tick (a few dozen values). Nothing per viewer.

### Examples (names masked, fake but stable; shapes from the schema, the sandbox has no dev data)

| Thing | Data | On the map |
| --- | --- | --- |
| Dealer "D-Alpha" | region "SELANGOR" -> Selangor, bought today | lit shop on the Selangor street near HQ |
| Dealer "D-Bravo" | region "JB" -> unresolved (no alias) | shop on the "State not set" islet |
| Project "Residensi Alpha" P-0101 | Quoted, state "Johor", Mar 2025 -> Mar 2028 | amber flag, frame + crane (~55%), Johor project quarter |
| Project "Hotel Bravo" P-0102 | Tendering + critical, state "Sabah", no launch date | orange flag + red pennant, tidy prepared plot, Sabah |
| Project "Taman Charlie" P-0103 | Registered, state blank, launch Jan 2027 | blue flag, "Launching" footprint, "State not set" islet |
| Trading house "TH-Alpha" | customer region "Kuala Lumpur", project invoice today | lit tower in Kuala Lumpur |
| Due order, project type, customer in Sarawak | - | coaster ship Port Klang -> Sarawak project quarter |

Board (full): "Sold today RM 48,200.00 / Dealers RM 39,900.00 · Projects RM 6,100.00 · Other RM 2,200.00".

### Edge cases

- Everything lands on "State not set" (region never sent): the map still works; the islet becomes the busiest place,
  which is the honest signal to fill AreaCode. The islet grows a second street rather than overflowing.
- A state with many shops (Selangor, KL): its street wraps into two rows; the schematic map gives it room.
- `region` holding a non-state value (a sales area like "NORTH" or "EAST COAST"): unresolved -> "State not set" unless
  the owner adds it as an alias (Q6).
- A trading house that is also a top-30 dealer: shop and tower both, same state, each lit by its own sales type.
- KL / Putrajaya projects: their own enclave, not Selangor.
- No open projects: no project quarters; HQ sign "No open projects".
- Snapshot built before this ships (no state fields): drawn on the old single-island layout until the first new
  tick a few minutes later, so the town never flashes every shop onto the "State not set" islet.

### Questions

6. **Dealer location source.** `customers.region` (AutoCount AreaCode) is the only candidate. Crew, please run on the
   dev copy (read-only):
   `SELECT region, count(*) FROM customers c WHERE EXISTS (SELECT 1 FROM sales_orders s WHERE s.customer_id = c.id AND s.demand_class = 'retail') GROUP BY 1 ORDER BY 2 DESC;`
   Options (a) resolve region through `my_state` (+ aliases the owner adds to that lookup set), unresolved -> "State
   not set"; (b) add a `state` column on customers that sales admin fills by hand. Recommendation: **(a)** if most
   dealers resolve; it needs no new field and the islet shows exactly who to fix. Switch to (b) only if AreaCode turns
   out to be sales areas rather than states.
7. **East Malaysia deliveries.** (a) a coaster ship from Port Klang; (b) lorries drive off the map edge.
   Recommendation: **(a)**: it is how the goods actually travel.

## Phase plan (after sign-off)

1. Mock sign-off: `mock/town-project-city-mock.html` (v2, the map). v1 single island kept as
   `mock/town-project-city-mock-v0-single-island.html`.
2. Red tests first: `today.split`; `projects.sites` (open only, approved only, cap 30 + more, dormant count, lost gone,
   look from timeline, flag from status, `state` resolved); `trading_houses` (cap 12, lit on project-type invoice,
   state); shops carry `state`; unresolved -> `null` (drawn on "State not set"); deliveries split by `demand_class`
   with a destination state; redaction (no value/name/code/id, hashed order, opaque keys) and wallboard strip; vitest
   for the board line, state placement helper, lightbox targets `site` / `trading_house` / `state`, legend.
3. Backend snapshot sections, then the map world in `townWorld.ts` (state polygons in `town/lib/townMap.ts`), then
   lightbox, cards, legend.
4. Reviewer + security reviewer (redaction) + browser pass; hand-test script.
