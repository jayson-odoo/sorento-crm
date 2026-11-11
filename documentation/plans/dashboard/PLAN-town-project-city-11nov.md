# PLAN: Town project district (TOWN-PROJECT-CITY)

Status: Plan - behaviour card posted for owner sign-off (LEAD pattern; no code before sign-off). Track: full (size L: new snapshot sections, redaction rules, a new 3D district).

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

## Behaviour card

### Rules

1. **Split board.** The plaza board keeps "Sold today RM X" and adds one line under it:
   "Dealers RM a · Projects RM b · Other RM c". a = posted invoices today whose sales type is `dealer`, b = `project`,
   c = everything else (other, set apart, mixed, type not set, no sales order), so a + b + c = X exactly, credit notes
   included with their sign. Viewers without `sales.reports.view` see no RM anywhere (server-side): their line reads
   "Dealers 14 · Projects 3 · Other 2 invoices". The sales lightbox gets the same three rows.
2. **The district.** A second, smaller island across the existing bridge (the bridge at 287 degrees stops at its
   shore). The dealer street is untouched. Its own legend entry: "Project site" and "Trading house".
3. **Sites.** One site per project with `outcome = open` and an approved or staff registration, in the viewer's company.
   Cap: 30 sites. Full viewers get the top 30 by `estimated_sales_value` (blank value last, ties by project code);
   the rest are counted on a "+N more projects" sign at the district gate. Redacted viewers get the same 30 sites in
   a stable hashed order (as shops are today), so the layout does not leak the value ranking.
4. **What a site looks like = the project's own timeline, never our sales stage.** Progress =
   (today - launch_date) / (delivery - launch_date), delivery = `expected_delivery_from`, else `expected_delivery_to`.
   Both dates set, delivery after launch:
   - before launch: fenced plot with a site board
   - 0-25%: groundworks (excavator, foundation slab)
   - 25-60%: frame going up with a tower crane
   - 60-95%: clad building, crane still up
   - 95% and over (incl. past delivery): finished building, no crane
   Either date missing (or delivery not after launch): plain fenced plot. Building height comes from the project type
   only as a tint, never from value or stage. The derived "launch + lag" delivery year is a forecast default and is
   NOT used for the look.
5. **Our sales stage = a small flag at the site gate only.** Colour per rung: Identified grey, Registered blue,
   Spec In teal, Quoted amber, Tendering orange, PO Received green. `is_critical` (Final Negotiation) adds a red
   pennant above the flag. The flag never changes the building.
6. **Click a site -> lightbox**, then "Open project" goes to `/project-sales/{id}` (the project page enforces its own
   permission). Full viewer sees: project name (or title) and code, stage, Final negotiation yes/no, state, timeline
   ("Launch Mar 2026 · Delivery Dec 2028 · 31% of the way"), estimated value. Redacted viewer sees stage, state and
   timeline only, with no name, code, value or link (the key is opaque, like shops).
7. **Trading houses = office blocks.** Tall, flat-roofed, glass-banded slate-blue towers on the district's waterfront,
   unmistakably not the pitched-roof cream dealer shops. One block per customer that is linked as `trading_house`
   (party with a `customer_id`) on at least one open site. Cap 12, ordered by how many open projects they sit on, then
   code; the rest are "+N more trading houses". **Lit** (warm windows, amber roof light, same light-pool as a shop) when
   that customer has a posted invoice today with sales type `project`. Click -> lightbox: name (full only), open
   projects it is on, invoices today. No amounts per trading house on the redacted variant.
8. **Lost** projects drop off at the next tick (within ~5 minutes, same day): the snapshot only ever reads open
   projects. **Dormant**: also off the map (nobody is working them), counted on the district gate sign:
   "+3 dormant" (number only), so nobody reads "the district shrank" as lost business.
9. **Lorries.** The due/overdue sales-order count and the up-to-6 lorries split by the order's `demand_class`:
   `project` orders drive over the bridge to the district gate (never to a specific site: no explicit link exists);
   all others keep today's rule (to the dealer's shop, or out of town). Out-of-town lorries now leave by the
   port road instead of the bridge, so the bridge carries project traffic only. The depot label reads
   "12 to deliver · 3 projects".
10. **Wallboard.** No project names, codes, values, trading house names or customer ids; keys opaque. Sites keep stage
    flag and look; office blocks keep lit/unlit. Same as shops today.
11. **Cost.** Two extra small queries per tick (open projects + profile + status; trading-house links + today's
    project-type buyers), one extra filtered sum in the existing today query, one extra group in deliveries. Nothing
    per viewer; everything comes from the cached snapshot.

### Examples (shapes from the schema; names masked, fake but stable)

The sandbox holds no dev data, so these are shapes the schema allows and the crew fact implies, not counted rows.

| Project | Stage / flag | Launch -> delivery | Look | Notes |
| --- | --- | --- | --- | --- |
| "Residensi Alpha" P-0101, Selangor, est RM 1.2m | Quoted (amber) | Mar 2025 -> Dec 2027 | frame + crane (~59%) | trading house TH-A linked, TH-A bought today -> TH-A lit |
| "Hotel Bravo" P-0102, Johor, est RM 640k | Tendering (orange) + red pennant | none -> Jun 2026 | plain plot | no launch date (hotel fit-out type) |
| "Taman Charlie" P-0103, Perak, no value | Registered (blue) | Jan 2027 -> Jan 2030 | fenced plot with site board (before launch) | sorts after valued projects for full viewers |
| "Menara Delta" P-0104, KL, est RM 3.0m | PO Received (green), outcome open | Jun 2022 -> Jun 2025 | finished building | delivery passed; still open because another scope quotes |
| "Pangsa Echo" P-0105 | was Quoted, set Lost at 14:10 | - | gone by the 14:15 tick | - |

Board (full): "Sold today RM 48,200.00 / Dealers RM 39,900.00 · Projects RM 6,100.00 · Other RM 2,200.00".
Board (redacted / wallboard without amounts): "31 invoices / Dealers 26 · Projects 3 · Other 2".

### Edge cases

- No open projects: the district island stays (so the town does not jump), with an empty-lot sign "No open projects".
- A trading house that is also a top-30 dealer: it is both a shop (dealer business) and an office block (project
  business); each lights by its own sales type.
- Trading-house party not yet a customer (`customer_id` null): no office block (it has never bought).
- Invoice to a trading house typed `type_not_set`: counted under Other, block stays dark. This is the true data, not a bug.
- Delivery before launch, or launch == delivery: plain plot (no division by zero).
- A redacted viewer must not be able to rebuild the value ranking from site order, sizes or keys (hashed order, opaque keys, no size-by-value).
- Snapshots built before this ships have no `projects` section: the district shows the empty-lot sign, the board has no split line.

### Questions (each with a recommendation)

1. **Where the district sits.** (a) a second island across the existing bridge, default view zoomed out ~20% so both
   islands fit; (b) squeeze sites onto the main island between the office and the port. Recommendation: **(a)**,
   because the main island has no free arc (shops -60..104 deg, office 128, warehouses 160-208, port 232, depot 270)
   and owner's "Project City across the bridge" picture needs its own ground.
2. **Board third term.** (a) "Dealers a · Projects b · Other c" so it adds up; (b) only Dealers + Projects, which will
   not add up to X on most days. Recommendation: **(a)**: a board that does not add up reads as a bug.
3. **Delivery date for the site look.** (a) explicit `expected_delivery_from`/`to` only, else plain plot; (b) also use
   launch + the system delivery lag. Recommendation: **(a)**, your words were "when both are set"; the lag is a forecast guess.
4. **Dormant.** (a) hidden like lost, number on the gate sign; (b) keep as a greyed, weed-grown plot. Recommendation:
   **(a)**: fewer things on screen, and nobody acts on a dormant site from the Town.
5. **Trading house lit rule.** (a) lit on a posted invoice today with sales type Project; (b) lit on any invoice today.
   Recommendation: **(a)**: it matches the Projects RM on the board, so the board and the lit blocks tell one story.

## Phase plan (after sign-off)

1. Mock sign-off (this lane: `mock/town-project-city-mock.html`).
2. Red tests first: snapshot `today.split`, `projects` section (open only, approved only, cap 30 + more, dormant count,
   lost gone, look from timeline, flag from status), `trading_houses` (cap 12, lit on project-type invoice today),
   deliveries split; redaction (no value/name/code/id, hashed order, opaque keys), wallboard strip; vitest for board
   line, lightbox targets `site` / `trading_house`, legend entries.
3. Build backend, then frontend district in `townWorld.ts`, then lightbox and legend.
4. Reviewer + security reviewer (redaction) + browser pass; hand-test script.
