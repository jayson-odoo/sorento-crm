# PLAN: Town v2 (hover names, lightbox popups, tilt camera, incoming shipments port)

Status: Plan, waiting on the owner. Behaviour card + mock v4 filed for the owner (`crew report --ask`); build waits for the
owner's OK. Track: M (LEAD pattern), expected diff ~600-900 lines, no migration, no auth/RBAC change,
no new ingest surface. UAC: `town-v2-acceptance-criteria.md`.

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
| Redaction / wallboard strip | `town/snapshot.py:363-390` (`redact`, `strip_names`) |
| Route (reads Redis only) | `sorento_crm_backend/app/api/v1/town.py` |
| Incoming shipments source: "still incoming" line rule, not-draft rule | `sorento_crm_backend/app/services/incoming_stock_service.py:71-96` (`_remaining_expr`, `_still_incoming_filter`, `_not_draft_shipment_filter`) |
| Incoming shipments list (what `crm_incoming_stock_shipments` reads) | `incoming_stock_service.py:614-711` (`IncomingStockService.incoming_shipments`), route `app/api/v1/incoming_stock.py:355` |
| Shipment model (company-scoped; `estimated_arrival_date`, `etd_date`, `eta_delay_date`, `actual_arrival_date`, `shipment_status`, `supplier_id`) | `sorento_crm_backend/app/models/procurement.py:128-200` |
| Existing screen for shipments (link target) | `/procurement-management/packing-lists` (`config/menu.config.ts:452`) |
| Lightbox component (centred modal, Esc + click outside close) | `sorento_crm_frontend/components/ui/dialog.tsx` (`Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogBody`) |
| Tooltip | in-canvas overlay `div` positioned from the hovered object's screen point (Radix `Tooltip` needs a DOM trigger, a 3D object has none) |

## Behaviour card (rules)

1. **Hover = name.** Pointer over a shop, warehouse, depot, office, scoreboard, port or ship shows a
   small tooltip next to it: name + one key number (shop: `Name [A/C I] · RM 12,340 today`; redacted
   viewer: `Dealer · 2 invoices today`; port: `Port · 7 on the water · 3 arriving this week`). No click.
   Cursor turns into a pointer over anything clickable.
2. **Touch:** first tap on a building shows its tooltip; a second tap on the same building (or a tap on
   the tooltip) opens its lightbox. A tap on empty ground hides the tooltip.
3. **Click = lightbox.** Clicking a building, a label or a stat card opens a centred modal (the app's
   `Dialog`) over a dimmed town, same content the side panel shows today plus the new port lightbox.
   Esc, the close button or a click outside closes it. The side panel (`TownPanel` Sheet) is removed.
4. **Camera.** Drag left/right turns (as today). Drag up/down tilts between street level (elevation 20
   degrees) and bird's-eye (80 degrees); default stays today's ~41 degrees. Scroll wheel / pinch zooms
   0.7x-2.2x. A small "Reset view" icon button (bottom-right of the canvas, labelled) returns to the
   default angle, tilt and zoom. Still render-on-demand, 30 fps cap while dragging, nothing drawn while
   hidden: no extra cost on the Mac mini wallboard when idle.
5. **Port (new).** A dock at the town's edge (outside the ring, toward the sea side): ships on the
   water for shipments still sailing, containers stacked on the quay for shipments arriving soon. One
   sign: `Incoming: 10` . Hover = counts + next ETA, click = lightbox listing the shipments.
6. **Which shipments count** (same rule the assistant's `crm_incoming_stock_shipments` uses, imported,
   not re-derived): not draft, at least one line still incoming (`line_status != received` and
   shipped - received > 0). Split by effective ETA (`eta_delay_date` when set, else
   `estimated_arrival_date`) against today (MYT):
   - **On the water:** ETA after today + 7 days, or no ETA -> ships.
   - **Arriving this week:** ETA today .. today + 7 -> containers on the quay.
   - **Late:** ETA before today and still incoming -> containers with a red tag ("3 late").
7. **Snapshot.** `build_snapshot` gains `incoming` (schema stays 1, the key is additive; the FE treats
   a missing key as "no port data yet"):
   `{"on_water": n, "arriving_soon": n, "late": n, "total": n, "next_eta": "YYYY-MM-DD"|null,
   "shipments": [{shipment_number, container, supplier, eta, products, quantity, bucket}] (earliest 30 by ETA)}`.
   Same tick, same 5 s statement timeout, same Redis keys; the route still reads no business table.
8. **Redaction.** Shipments carry no amounts. The supplier name is stripped from the redacted variant
   and from the wallboard (same as dealer names); counts, ETAs, shipment/container numbers stay.
9. **Port lightbox lists** up to 30 shipments, ETA ascending: `Shipment no. · Container · Supplier ·
   ETA · Products · Qty`, a late row shows a red "Late" badge, and one button "Open packing lists".
   More than 30: footer "+N more" and the same button.

## Real examples (dev data)

Requested with `crew-data-request:` on the PR (counts and ETA spread only; no supplier names on
GitHub). Filled in here when crew answers.

## Edge cases

- **No shipments:** the port is drawn empty (no ship, no container), sign reads `Incoming: none`,
  tooltip "Nothing on the way", lightbox shows the empty state "Nothing on the way" (heading, no button
  other than "Open packing lists").
- **100+ shipments:** at most 6 ships and 12 containers are drawn (the counts on the sign and tooltip
  stay exact); the snapshot carries only the earliest 30 rows plus the exact totals, so payload size
  stays bounded (~4 KB).
- **No ETA:** counts as on the water, sorts last, shown as "No ETA".
- **Mobile (375 px):** tap-tap rule (2); tooltip clamps inside the canvas; lightbox is the standard
  `Dialog` (full-width on small screens); one-finger drag turns and tilts, two-finger pinch zooms, so
  the canvas keeps `touch-none` (the page scrolls from the cards below and the page margins).
- **Reduced motion / no WebGL:** cards only (as today) plus a sixth card "What is coming in?" -> the
  same port lightbox.
- **Old snapshot without `incoming`** (first tick after deploy): port not drawn, sixth card hidden.

## Questions for the owner (each with a recommendation)

1. **"Arriving soon" window:** (a) 7 days (b) 14 days (c) this calendar month. Rec (a) 7 days: one
   week is what the warehouse plans collection around; longer windows turn most ships into containers.
2. **Late shipments** (ETA passed, not yet received): (a) own red count on the quay (b) fold into
   "arriving soon". Rec (a): a passed ETA is the one thing purchasing must chase.
3. **Supplier names in the port lightbox:** (a) shown on the personal view, hidden on wallboard and for
   viewers without `sales.reports.view` (b) always shown (c) never. Rec (a): same rule as dealer names,
   one rule to remember.
4. **Touch:** (a) tap = tooltip, second tap = lightbox (b) tap = lightbox straight away (tooltip only
   with a mouse). Rec (a): matches "no click needed to learn a name" on the iPad too.
5. **Lightbox button for the port:** (a) "Open packing lists" (`/procurement-management/packing-lists`)
   (b) none. Rec (a): every other lightbox has one way out to the real screen.

## Mock (v4, filed for the owner)

`mock/town-v2-mock.html`, a fork of the approved v3 mock. The scene is real three.js, so its camera,
hover and port code is the prototype for the build. Screenshots are in `mock/town-v2/`. The shipments
in it are a SAMPLE until the crew data request is answered.
Placement: the port sits outside the island behind the warehouses and the depot (angle 226), at the top
of the default view where there is empty sky. At the side (angle 136) it clipped off the canvas edge.
On a phone the port lightbox drops the Container and Products columns; they stay in the hover tooltip.

## Element -> component map

| Mock element | Component (repo path) |
|---|---|
| Hover tooltip | new `TownTooltip` overlay in `town/components/TownScene.tsx` (absolutely positioned `div`, token classes from `components/ui/tooltip.tsx` look: `bg-popover text-popover-foreground rounded-md border px-2 py-1 text-xs shadow-md`) |
| Lightbox | `components/ui/dialog.tsx` `Dialog` + `DialogContent` + `DialogHeader` + `DialogTitle` + `DialogDescription` + `DialogBody`; content from today's `TownPanel.body()` (renamed `TownLightbox`) |
| Reset view | `components/ui/button.tsx` `Button variant="outline" mode="icon" size="sm"` + lucide `RotateCcw`, `aria-label="Reset view"` |
| Port, ships, containers | three.js meshes in `TownScene.tsx` (instanced, same `part()`/`merge()` helpers) |
| Port sign | existing `label()` sprite, a fixed label in `separateLabels` |
| Late badge in the list | `components/ui/badge.tsx` `Badge variant="destructive"` |
| Sixth card | `town/components/TownCards.tsx` `Card` |

## Build slices (after OK)

1. BE: `_incoming(db, company_id, day)` in `town/snapshot.py` reusing `incoming_stock_service`
   filters; `redact`/`strip_names` drop `supplier`. Tests first in `tests/town/test_town_snapshot_v2_incoming.py`.
2. FE: `TownPanel` Sheet -> `TownLightbox` Dialog; cards + scene open it. Tests: lightbox role=dialog,
   Esc closes, no Sheet.
3. FE: hover/tap tooltip + tilt/zoom/reset camera (pure helpers `clampTilt`, `clampZoom`,
   `pickTooltip` in `townFormat.ts` with vitest).
4. FE: port + ships + containers + port lightbox + sixth card.
