# PLAN: Town v2 (hover names, lightbox popups, tilt camera, incoming shipments port)

Status: Owner hand test PASS (10 Nov, test copy :3102, build 45aaa7e7: "I like it quite a lot").
Merge-ready: `town_0001_view_perm` re-parented LAST onto `ppr_0001_party_roles` (#2301 -> #2305 -> #2300
-> #2310) after #2300 merged; single head. Track L. Reviewer READY (round 2), security reviewer READY; crew-tests green on fd670e4; browser pass
in `evidence/town-v2/`.

## Journey (owner, 10 Nov ~15:35 MYT, Dashboards > Town)

"It is quite bad experience for me to click each dealer store and it opens the side bar, like
sometimes I am just wondering what's the store name there ... this one only can rotate in a circle,
I cannot drag up and down ... all these side panels quite distracting ... remember our design
principle is to have lightbox popup; and due to nature of Sorento we need to add elements of incoming
shipments also ... how about purchased from overseas?"

## Scout (what exists today, file:line)

| Thing | Where |
|---|---|
| Page shell, holds the selected target, renders scene + cards + panel | `sorento_crm_frontend/app/(protected)/town/components/TownPage.tsx:35-79` |
| Side panel (Radix Sheet, `side="right"`, non-modal) - the thing the owner dislikes | `town/components/TownPanel.tsx:155-176` (`body()` content builder `:46-152`) |
| Five stat cards, click -> panel | `town/components/TownCards.tsx:57-159` |
| Scene: orthographic camera, fixed elevation (`cam.position.set(cos*80, 70, sin*80)`) | `town/components/TownScene.tsx:153-159` |
| Input: drag X only -> yaw; tap -> raycast -> `select()` | `town/components/TownScene.tsx:450-477` |
| Pickables (board, shops instanced, warehouses, "!" label, depot, lorries, office, badge) | `town/components/TownScene.tsx:286, 315, 353-358, 376, 400-404, 420-432` |
| Label layout (fixed labels + stacked name tags, re-run on every camera move) | `town/components/TownScene.tsx:119-152`, `town/lib/townFormat.ts` (`separateLabels`, `stackTags`) |
| Payload types (schema 1) | `sorento_crm_frontend/types/town.types.ts` |
| Snapshot build (one FULL per company per tick, Redis, gzip) | `sorento_crm_backend/app/services/town/snapshot.py:305-328` (`build_snapshot`) |
| Due-delivery count (lorries) | `town/snapshot.py:119-133` (`_deliveries`) |
| Redaction / wallboard strip | `town/snapshot.py:363-390` (`redact`, `strip_names`) |
| Route (reads Redis only) | `sorento_crm_backend/app/api/v1/town.py` |
| Incoming shipments source: "still incoming" line rule, not-draft rule | `sorento_crm_backend/app/services/incoming_stock_service.py:71-96` (`_remaining_expr`, `_still_incoming_filter`, `_not_draft_shipment_filter`) |
| Incoming shipments list (what `crm_incoming_stock_shipments` reads) | `incoming_stock_service.py:614-711` (`IncomingStockService.incoming_shipments`), route `app/api/v1/incoming_stock.py:355` |
| Shipment model (company-scoped; `estimated_arrival_date`, `etd_date`, `eta_delay_date`, `actual_arrival_date`, `shipment_status`, `supplier_id`) | `sorento_crm_backend/app/models/procurement.py:128-200` |
| Existing screen for shipments (link target) | `/procurement-management/packing-lists` (`config/menu.config.ts:452`) |
| Lightbox component (centred modal, Esc + click outside close) | `sorento_crm_frontend/components/ui/dialog.tsx` (`Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogBody`) |
| Tooltip | in-canvas overlay `div` positioned from the hovered object's screen point (Radix `Tooltip` needs a DOM trigger, a 3D object has none) |

## Behaviour card (rules, owner answers folded in)

1. **Hover = name (mouse only).** Pointer over a shop, warehouse, depot, office, scoreboard, port, ship,
   container or lorry shows a small tooltip: name + one key number (shop: `Name [A/C I] · RM 12,340 today`;
   redacted viewer: `Dealer · 2 invoices today`; port: `Port · 29 incoming · 70 late · next ETA Wed 11 Nov`).
   No click. Cursor turns into a pointer over anything clickable.
2. **Touch (owner Q4 = b):** a tap opens the lightbox straight away. No tooltip on touch and no
   "tap again" hint ("don't want so many tips").
3. **Click = lightbox.** Clicking a building, a label or a stat card opens a centred modal (the app's
   `Dialog`) over a dimmed town, with the content the side panel shows today plus the new port lightbox.
   Esc, the close button or a click outside closes it. The side panel (`TownPanel` Sheet) is removed.
4. **Camera.** Drag left/right turns (as today). Drag up/down tilts between street level (elevation 20
   degrees) and bird's-eye (80 degrees); the default stays today's ~41 degrees. Scroll wheel / pinch zooms
   0.7x-2.2x. Icon buttons bottom-right: Pause/Play motion, Zoom out, Zoom in, Reset view (each with an
   `aria-label`).
5. **Port.** A dock outside the island behind the warehouses and the depot. Ships on the water =
   INCOMING shipments (at most 6 drawn); red containers on the quay = LATE shipments (at most 12 drawn).
   The sign reads `Incoming: 29`, plus a red `70 late` tag. Hover = counts + next ETA, click = port lightbox.
6. **Which shipments count** (owner Q2: "late means late, incoming means incoming", no windows): not draft
   and at least one line still incoming, using the rule `crm_incoming_stock_shipments` uses
   (`incoming_stock_service.py:71-96`, imported, not re-derived). Effective ETA = `eta_delay_date` when
   set, else `estimated_arrival_date`. Two states only:
   - **Incoming:** ETA today or later, or no ETA.
   - **Late:** ETA before today (MYT).
7. **Snapshot.** `build_snapshot` gains `incoming` (schema stays 1, the key is additive; the FE treats
   a missing key as "no port yet"):
   `{"incoming": n, "late": n, "next_eta": "YYYY-MM-DD"|null, "shipments": [{shipment_number, container,
   supplier, eta, products, quantity, late}]}`, with up to 30 incoming rows (ETA ascending, no ETA last)
   then up to 30 late rows (most recently late first). Same tick, same 5 s statement timeout, same Redis
   keys; the route still reads no business table.
8. **Redaction (owner Q3 = a).** Shipments carry no amounts. `supplier` is stripped from the redacted
   variant and from the wallboard (same as dealer names); counts, ETAs, shipment/container numbers stay.
9. **Port lightbox** has two sections, "Incoming, by ETA (29)" and "Late, ETA passed, not received (70)".
   Columns: Shipment · Container · Supplier · ETA · Products · Qty. Each section ends "+N more" past 30.
   One button: "Open packing lists" (owner Q5 = a). Phone: Container and Products columns hidden.
10. **Motion (owner on v4: "doesn't wow me, things won't move"; research: `town-v2-research.md`).**
    Calm, and every movement stands for a figure:
    - Lorries (at most 6 of `deliveries.to_deliver`) drive depot -> ring road -> customer -> back, with
      eased starts and stops. The rest stay parked at the depot.
    - Ships at anchor bob; one ship sails in every 24 s and the crane lifts two containers onto the quay.
    - Lit shops breathe (a soft glow on their own phase) and flash when a lorry or a sale arrives.
    - **New invoice:** when a poll brings a shop more `today_docs` than the last snapshot, a receipt pops
      above that shop ("+ RM 2,340", or "+1 invoice" when redacted or on the wallboard) and the scoreboard
      counts up to the new total. This is a pure frontend diff of two snapshots; no backend change.
    - Trees sway, two flags wave, the water moves (faceted low-poly).
    - The town assembles on load: buildings rise in a short stagger, then labels fade in.
    - Time of day: light and sky follow the snapshot's `as_of` hour (warm near 18:00, blue after 20:00).
    - Guard rails (as shipped from v6): render on demand with a 60 fps cap (pixel ratio steps down below
      50 fps), the clock stops while the tab is hidden, `prefers-reduced-motion` = the still v6 town (no
      fly-in, nothing drives), and a Pause/Play button (WCAG 2.2.2), remembered per viewer in localStorage.
    - The sale beat diffs shop keys between two polls. That needed one backend change: the redacted and
      wallboard variants' opaque keys were list positions (`s1..sN`) and moved when the redacted list
      re-sorted, so they are now `opaque_key()` = "s" + 12 hex of an HMAC (own key derived from
      JWT_SECRET) over company, day and customer id. Trade-off, accepted: a viewer without
      `sales.reports.view` can follow one unnamed dealer's invoice count through the day (never across
      days, never its name or id); the Town is admin-only, so that viewer is a granted non-admin.

11. **Admin-only (owner, 10 Nov ~16:55).** Only admins see the Town, through the app's permission system:
    `dashboards.town.view` (`app/rbac/permission_registry.py`), granted to `admin` and `superadmin` by
    migration `town_0001_view_perm` (and the existing admin grant seed), never a role-name check. The Town
    menu item is gated on it, `/town` renders Access denied without it (`town/layout.tsx`), and
    `GET /api/v1/town/snapshot` (the only Town API) answers 403 without it, wallboard mode included.
    The wallboard has no credential of its own: it is `/town` with the Wallboard toggle in a signed-in
    browser (`TownPage.tsx:35-47` -> `useTownSnapshot({mode:'wallboard'})` -> `townService.ts:10-12`
    `apiFetch` with the user's bearer session -> `town.py` `get_current_user`). The Mac mini keeps working
    while that browser is signed in as an admin (30-day sliding session).

## Exemption recorded

The port lightbox lists shipments in a plain read-only table, not a DataGrid: at most 30 rows per section
inside a popup, no paging, sorting, filtering, column preferences or row links (the "Open packing lists"
button is the way to the real list). DESIGN-LANGUAGE's DataGrid rule is for listing screens; a DataGrid
inside a lightbox would add toolbar and chrome the owner's minimal-UI rule argues against.

## Real examples (dev data)

Crew data request answered 10 Nov (dev DB = 4 Nov prod copy; no receipts after 4 Nov, so "late" is
inflated by shipments received 4-10 Nov). Effective ETA vs 10 Nov, open = not draft + a line still incoming:

| Company | ETA > 7 d or none | ETA <= 7 d | <= 14 d | Late (ETA passed) | No ETA | Total | Next ETA | Oldest ETA |
|---|---|---|---|---|---|---|---|---|
| SRT (Sorento) | 3 | 26 | 27 | 70 | 2 | 99 | 10 Nov | 14 Jun |
| Mocha | 0 | 4 | 4 | 39 | 0 | 43 | 13 Nov | 2 Aug |

Under the owner's two-state rule SRT shows **29 incoming, 70 late**, and Mocha **4 incoming, 39 late**.

## Edge cases

- **No shipments:** the port is drawn empty (no ship, no container, no docking ship), the sign reads
  `Incoming: none`, and the lightbox shows the empty state "Nothing on the way" plus "Open packing lists".
- **100+ shipments:** at most 6 ships and 12 containers are drawn (the sign and tooltip counts stay
  exact); the snapshot carries at most 60 rows plus exact totals (~8 KB before gzip).
- **No ETA:** counts as incoming, sorts last, shown as "No ETA".
- **Mobile (375 px):** a tap opens the lightbox; one-finger drag turns and tilts, two-finger pinch zooms,
  so the canvas keeps `touch-none`; the lightbox is the standard `Dialog`.
- **Reduced motion:** static town (as today). **No WebGL:** cards only, plus a sixth card "What is coming
  in?" that opens the same port lightbox.
- **Old snapshot without `incoming`** (first tick after deploy): no port, no sixth card, no crash.
- **No lit shop:** lorries stay parked (nowhere to drive); no receipt pops.

## Questions for the owner

Answered 10 Nov ~16:00-16:05: Q1 dropped; Q2 two plain states (incoming / late); Q3 (a) supplier names on
the personal view only; Q4 (b) a tap opens the lightbox, hover tooltips on desktop only; Q5 (a) "Open
packing lists".

Answered 10 Nov ~16:10: Q6 (a).

6. **Where lorries drive (answered: a).** Shipped as `deliveries.customers` = up to 6 `{key, name,
   orders}`, earliest due first: `key` = the customer's shop in the town, else null with the customer's
   `name` (personal full view only; dropped on the redacted and wallboard variants). The question was:
   the snapshot has only a count of due sales orders, not who they are for. (a)
   Add `deliveries.customers`: the keys of up to 6 shops with an order due today or overdue (one GROUP BY
   on the existing `_deliveries` query), so a lorry drives to a real customer; on the redacted or
   wallboard variant the keys stay opaque as they are today. (b) Lorries drive to lit shops (decoration,
   says nothing true). Rec (a): one small query, and a lorry heading to a shop then means something.

## Mock

- v4 `mock/town-v2-mock.html` (static: hover, lightbox, tilt, port). Screenshots in `mock/town-v2/`.
- v5 `mock/town-v2-mock-v5.html` (alive), with a 23 s recording `mock/town-v2/town-v2-mock-v5.mp4` (+ `.gif`).
  Its shipment counts mirror SRT's dev shape (29 incoming, 70 late); the numbers, suppliers and ETAs are invented.
- Placement: the port sits outside the island behind the warehouses and the depot (angle 226), at the top
  of the default view, which v5 centres between the island and the port.

## Element -> component map

| Mock element | Component (repo path) |
|---|---|
| Hover tooltip | overlay `div` in `town/components/TownScene.tsx` with the `components/ui/tooltip.tsx` look (`bg-popover text-popover-foreground rounded-md border px-2 py-1 text-xs shadow-md`) |
| Lightbox | `components/ui/dialog.tsx` `Dialog` + `DialogContent` + `DialogHeader` + `DialogTitle` + `DialogDescription` + `DialogBody`; content from today's `TownPanel.body()`, moved to `TownLightbox.tsx` |
| Pause / Zoom / Reset | `components/ui/button.tsx` `Button variant="ghost" mode="icon"` + lucide `Pause`/`Play`, `Minus`, `Plus`, `RotateCcw`, each with `aria-label` |
| Port, ships, containers, crane lift, water, flags | three.js meshes in `TownScene.tsx` (instanced where repeated, same `part()`/`merge()` helpers) |
| Lorry routes, glow, receipt pop, intro | `TownScene.tsx` animation loop; pure helpers (`route`, `along`, easing, `newSales(prev, next)`) in `town/lib/townMotion.ts` with vitest |
| Port sign, late tag | existing `label()` sprite, fixed labels in `separateLabels` |
| Late section chip | `components/ui/badge.tsx` `Badge variant="destructive"` |
| Sixth card | `town/components/TownCards.tsx` `Card` |

## Build slices (after sign-off)

1. BE: `_incoming(db, company_id, day)` in `town/snapshot.py`, reusing the `incoming_stock_service`
   filters; `redact`/`strip_names` drop `supplier`; `deliveries.customers` (Q6 = a): up to 6 customers of
   due orders, earliest due first, as their shop key or None when not in the town, remapped to the opaque
   key on the redacted/wallboard variants. Tests first in
   `tests/town/test_town_snapshot_v2_incoming.py`.
2. FE: `TownPanel` Sheet -> `TownLightbox` Dialog; cards + scene open it. Tests: role=dialog, Esc
   closes, no Sheet rendered.
3. FE: hover tooltip (mouse) / tap = open (touch) + tilt/zoom/reset camera (pure clamps in `townFormat.ts`).
4. FE: port + ships + containers + port lightbox + sixth card.
5. FE: motion layer (`townMotion.ts` + loop in `TownScene.tsx`), pause button, reduced-motion guard,
   receipt pops from the snapshot diff.
