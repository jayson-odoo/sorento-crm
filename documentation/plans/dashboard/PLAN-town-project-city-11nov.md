# PLAN: Town project district (TOWN-PROJECT-CITY)

Status: Plan - card v2.2 + Malaysia-map mock posted for owner sign-off. Track: full (size L: new snapshot sections, redaction, a map world).

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

- **Where a dealer is (for the map).** `customers.region` (AutoCount `Debtor.AreaCode`, `models/order.py:159-161`)
  is EMPTY for 100% of 3,164 dealers on the dev copy (crew, 11 Nov; the masters feed never wrote it), and
  `billing_address` / customer addresses are empty too. What is filled: `orders.deliver_address`
  (`models/order.py:488`, AutoCount delivery orders, indexed by `ix_orders_customer_id`) for 2,153 dealers (68%),
  2,129 of them with a 5-digit postcode. Decision (crew/owner Q6): a dealer's state = the state of the most
  frequent postcode over its last 20 delivery orders, through an official Malaysian postcode-range -> state
  reference table (geography lookup, not record name matching). `customers.region` resolved through `my_state` wins
  when the feed ever fills it.
- **Where a project is.** `sales_profile.state` (`models/projects.py:432-433`), free text filled from the editable
  lookup set `my_state` (seeded with the 13 states + Kuala Lumpur, Labuan, Putrajaya,
  `alembic/versions/prreg_0001_project_registrations.py:62-79`). `LookupResolverService.resolve("my_state", raw)`
  (`services/lookup_resolver.py:29`) matches a typed value to a set value. The set has 16 options and no aliases
  (crew, dev copy), so a project's state is an exact (case-insensitive) match or nothing.

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
   a short high street inside their state (rule 9). A
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
9. **State resolution and "State not set".** Dealers and trading houses (both customers): `customers.region` through
   `my_state` if set, else the postcode rule: take the last 20 non-deleted, non-cancelled delivery orders of the
   customer, take the LAST 5-digit group in each `deliver_address` (a Malaysian address ends "..., 40150 Shah Alam,
   Selangor"; a lot or unit number earlier in the line can also be 5 digits), keep the most frequent (tie: the most recent),
   map it to a state through the postcode-range table `app/services/town/my_postcodes.py` (a static reference table
   with its source cited, KL / Putrajaya / Labuan included, the few shared prefixes such as 68xxx decided by range).
   Projects: `sales_profile.state` matched to a `my_state` value. Anything left without a state goes to a small
   **"State not set"** islet just off Shah Alam: visible and fixable, never guessed. No name is ever matched; the
   postcode and the address never leave the snapshot job (only the resolved state is stored).
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
    one indexed query over `orders` for the drawn customers only (30 shops + today's stalls + 12 trading houses,
    last 20 delivery orders each), memoised per customer per day in Redis beside the ranking. Nothing per viewer.

### Examples (names masked, fake but stable; shapes from the schema, the sandbox has no dev data)

| Thing | Data | On the map |
| --- | --- | --- |
| Dealer "D-Alpha" | region empty; last 20 DOs: 40150 x14, 47301 x6 -> 40150 -> Selangor; bought today | lit shop on the Selangor street near HQ |
| Dealer "D-Bravo" | region empty; DOs with no postcode | shop on the "State not set" islet |
| Dealer "D-Charlie" | DOs: 81300 x9 -> Johor | shop on the Johor street |
| Project "Residensi Alpha" P-0101 | Quoted, state "Johor", Mar 2025 -> Mar 2028 | amber flag, frame + crane (~55%), Johor project quarter |
| Project "Hotel Bravo" P-0102 | Tendering + critical, state "Sabah", no launch date | orange flag + red pennant, tidy prepared plot, Sabah |
| Project "Taman Charlie" P-0103 | Registered, state blank, launch Jan 2027 | blue flag, "Launching" footprint, "State not set" islet |
| Trading house "TH-Alpha" | DO postcode 50450 -> Kuala Lumpur, project invoice today | lit tower in Kuala Lumpur |
| Due order, project type, customer in Sarawak | - | coaster ship Port Klang -> Sarawak project quarter |

Board (full): "Sold today RM 48,200.00 / Dealers RM 39,900.00 · Projects RM 6,100.00 · Other RM 2,200.00".

### Edge cases

- Many dealers on "State not set" (about a third of all dealers have no delivery address): the map still works; the
  islet grows a second street rather than overflowing, and it is the honest signal of who has no address.
- A dealer that delivers to two states (a branch): the most frequent postcode wins, one shop, one state.
- A postcode outside every range (typo "4015"): ignored; the next most frequent valid one counts.
- A self-collect dealer (no delivery orders): "State not set".
- A lot or unit number that looks like a postcode ("No. 12345, Jalan ..., 81300 Skudai, Johor"): the last 5-digit
  group wins, so 81300; tested.
- A dealer whose deliveries mostly go to ITS customers' sites (drop-ship) rather than its shop: the map places it
  where most of its goods go, which can differ from where the shop stands. Accepted and stated (the state answers
  "where does this dealer's business go"); `customers.region` overrides it the day the feed fills it.
- Selangor holds about half the top 30 (16 on dev): it gets two short streets around HQ, and at default zoom one
  "Selangor: 16 dealers, 5 lit" pill instead of per-shop labels.
- A state with many shops (Selangor, KL): its street wraps into two rows; the schematic map gives it room.
- A project state typed outside the lookup (older free text): no match -> "State not set".
- A trading house that is also a top-30 dealer: shop and tower both, same state, each lit by its own sales type.
- KL / Putrajaya projects: their own enclave, not Selangor.
- No open projects: no project quarters; HQ sign "No open projects".
- Snapshot built before this ships (no state fields): drawn on the old single-island layout until the first new
  tick a few minutes later, so the town never flashes every shop onto the "State not set" islet.

### Decided

- Q6 (crew + owner, 11 Nov): dealer state from the delivery-order postcode as rule 9; `customers.region` via
  `my_state` preferred when filled. Top-30 coverage on dev (crew, sorento_prod_1104): **30 of 30 get a state**:
  Selangor 16, Johor 6, Kuala Lumpur 3, Kedah 1, Pahang 1, Sarawak 1, Negeri Sembilan 1, Pulau Pinang 1. Caveat:
  that copy has no `billing_documents`, so crew ranked by 90-day retail sales-order line totals
  (`sales_order_lines.line_total`, as `agent_class_service.py:348`), not by invoiced sales; the real top 30 may
  differ by a few shops. The hand-test re-checks the count on the real snapshot.
- Q7 (a): Sabah, Sarawak and Labuan orders go by coaster ship from Port Klang.

## Mock

- `mock/town-project-city-mock.html`: the Malaysia-map Town (card v2.2), one self-contained page (three.js from the
  jsDelivr CDN, as the v5 mock). Mock controls under the stage: time of day, viewer Full / No amounts / Wallboard,
  dark theme, shipment volume. Every dealer, project, trading house, value and date in it is invented; the shop spread
  follows the dev shape (Selangor 16, Johor 6, KL 3, one each in Kedah, Pahang, Sarawak, Negeri Sembilan, Pulau
  Pinang) plus 3 stalls, 12 sites, 5 trading houses and a "State not set" islet.
- Screenshots in `mock/town-project-city/`: `1280.png`, `375.png` (full page), `lightbox-site.png`,
  `wallboard-1280.png`, `zoom-selangor.png` (HQ, Selangor street, tidy no-dates plot), `zoom-johor.png` (frame +
  crane, groundworks, trading tower, lorry).
- Element -> component map: the table at the bottom of the mock page.
- v1 (single island) kept as `mock/town-project-city-mock-v0-single-island.html`.

## Phase plan (after sign-off)

1. Mock sign-off: `mock/town-project-city-mock.html` (v2, the map). v1 single island kept as
   `mock/town-project-city-mock-v0-single-island.html`.
2. Red tests first: `today.split`; `projects.sites` (open only, approved only, cap 30 + more, dormant count, lost gone,
   look from timeline, flag from status, `state` matched); `trading_houses` (cap 12, lit on project-type invoice,
   state); shops carry `state` (region first, then postcode mode of last 20 DOs, range table incl. edges); unresolved -> `null` (drawn on "State not set"); deliveries split by `demand_class`
   with a destination state; redaction (no value/name/code/id, hashed order, opaque keys) and wallboard strip; vitest
   for the board line, state placement helper, lightbox targets `site` / `trading_house` / `state`, legend.
3. Backend snapshot sections, then the map world in `townWorld.ts` (state polygons in `town/lib/townMap.ts`), then
   lightbox, cards, legend.
4. Reviewer + security reviewer (redaction) + browser pass; hand-test script.
