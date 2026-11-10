# PLAN: Town look v6 (lighting, materials, motion with intent)

Status: Build (mock). Design-only scout lane, no product code. Track: M scout (mock + notes only, no
migration, no auth/RBAC change, no ingest surface). UAC: `town-look-acceptance-criteria.md`.
Feeds lane TOWN-V2 (PR #2310), which builds whatever look the owner approves.

## Journey (owner, 10 Nov ~16:07 MYT, on TOWN-V2 mock v5)

"you done the research already? this is the best we can do?" and earlier "it doesn't wow me, the
things won't move some more". The town must WOW on the Mac mini wallboard and on the owner's laptop.

Owner answer Q6 (10 Nov ~16:10): lorries drive to the real CUSTOMERS of orders due today or overdue
(a customer can be a shop in the town), option (a), up to 6 drawn.

## Inputs

- v5 mock: `documentation/plans/dashboard/mock/town-v2-mock-v5.html` on branch
  `claude/town-v2-hover-lightbox-camera-14vlam` (#2310), three.js 0.185.1.
- Research note: `documentation/plans/dashboard/town-v2-research.md` on the same branch (8 references).
- Card rules already approved (kept as is): hover tooltip desktop / tap on touch, lightbox popups, no side
  panels, tilt 20-80 deg + zoom + reset, port INCOMING vs LATE (red) only, supplier names only in the
  personal view, "Open packing lists" in the port lightbox, minimal UI.

## Deliverables

1. Critique of v5 against the references (short list) in `documentation/mockups/TOWN-LOOK/NOTES.md`.
2. Mock v6, one static HTML, three.js from a pinned CDN version:
   `documentation/mockups/TOWN-LOOK/index.html`. Forks v5's page shell (header, 2D cards, lightbox,
   tooltip, controls, data block) and replaces the scene.
3. 15-20 s video + screenshots (1280 and 375) beside the mock.
4. `crew report TOWN-LOOK --ask` with critique summary, what v6 changes, paths, recommendation.

## v6 design decisions

- Lighting: soft PCF shadows from one warm key sun (shadow map sized to the island only), cool
  hemisphere fill, ACES tone mapping, sRGB output, subtle fog to the sky colour so the island sits in
  air instead of on a white void. Baked-look AO: vertex-colour darkening at the foot of every building
  and a soft contact-shadow blob under props (cheap, no SSAO pass).
- Palette: one warm/cool pair. Warm: terracotta roofs, cream walls, sand ground. Cool: teal sea, slate
  shadows, blue-grey sky gradient. Data colours (amber lit shop, red low stock, blue lorries, violet
  approvals, teal ships) stay the app's chart tokens and are the only saturated colours on screen.
- Shapes: low-poly but characterful. Shops get gabled roofs, chimneys, awnings, a door and window
  insets; warehouses get barrel roofs and loading doors; the port gets a crane with a moving trolley.
  Island edge is a bevelled cliff with a sand beach where it meets the sea.
- Camera intro: one 2.4 s eased fly-in (ease-out-quart) from a high wide angle to the default view,
  skippable by any input, skipped under reduced motion.
- Motion with intent (Mini Metro rule: motion only where it carries data):
  - lorries = orders due today or overdue; up to 6, each drives to its customer's shop on a curved
    road (Catmull-Rom path), eased start/stop, body banks into turns, waits, drives back to the depot.
  - ships = incoming shipments on the water; each trails a V wake; one docks, the crane lifts a
    container off onto the quay (containers = arriving this week, red = late).
  - lit shops = bought today: warm window glow + slow breathing halo.
  - idle life (trees, flags, water) stays under 0.15 units amplitude.
- One moment of delight: a new sale. The shop flashes, a coin arcs from the shop to the board with an
  overshoot, the board counter rolls up, a soft ring ripples on the ground. Once per sale, rate-limited.
- Performance: render on demand. The loop stops when nothing is moving (motion paused, reduced motion,
  tab hidden) and re-renders only on input or resize. 60 fps target on the Mac mini; shadow map 2048.
- `prefers-reduced-motion`: no fly-in, no driving, no bobbing; state shown statically (lorries parked
  at their customers, ships at anchor); the delight becomes an opacity flash only.

## Out of scope

Product code, backend, snapshot changes, tests. TOWN-V2 owns the build.
