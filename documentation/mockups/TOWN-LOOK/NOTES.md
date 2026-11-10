# TOWN-LOOK: town v6 look and motion mock (10 Nov 2026)

Open `index.html` in a browser (three.js 0.185.1 from jsDelivr, the version the product already uses,
`sorento_crm_frontend/package.json`). Video: `town-v6.mp4` (18 s, 30 fps; `town-v6.gif` is a smaller copy).
Screens: `screens/` (1280 and 375 px, hover, lightboxes, dusk, night, reduced motion).
Plan + UAC: `documentation/plans/dashboard/PLAN-town-look-10nov.md`, `town-look-acceptance-criteria.md`.
Data: the same masked dev snapshot as v5 (#2310); the lorries' customer list and the sale beats are SAMPLE.

## 1. Why v5 looks cheap (against the references)

1. **Flat light, no shadows, no occlusion.** Hemisphere 2.0 + a weak sun on `MeshLambertMaterial`, nothing
   casts a shadow, so buildings float and every face is the same grey. Zippy Town and Townscaper both live on a
   warm key light with soft shadows and darkened wall bases.
2. **A disc on a white void.** No sky, no horizon, no sea around the town; the port's sea is a cyan oval stuck
   behind the disc. There is no place, only a diagram.
3. **Primitive, identical shapes.** Every shop is one box + one prism in one grey; no door, window, eave or
   roof variety. Townscaper's charm is small detail (doors, trims, chimneys, awnings) on simple masses.
4. **No palette.** Grey buildings, beige disc, cyan water, and the only strong colours are five saturated label
   stickers, so the UI shouts and the town whispers.
5. **Hierarchy upside down.** About 12 canvas-sprite labels and a 16-unit billboard cover the town; the labels are
   bigger than the buildings they name. Sprite text also blurs on zoom.
6. **Motion without mass.** Lorries run on straight 5-degree chords and snap their heading each segment; one ease
   over the whole trip makes them crawl at both ends; the crane lifts a box with no trolley or cable; pops and
   buildings grow from scale 0.01 (things appear from nothing).
7. **A diagram camera.** Orthographic, fixed lens, no entrance: nothing says "you are arriving somewhere".

## 2. What v6 changes

| Area | v6 |
|---|---|
| Light | One warm sun with soft PCF shadows (2048 map sized to the island), cool sky fill, Khronos Neutral tone mapping so the data colours stay true. Baked darkening at the foot of every wall + a soft contact shadow under each building. |
| Place | The town is an island: grass top, cliff, sand beach, foam line, a shallow turquoise sea fading to deep, fog into a sky gradient. A causeway bridge leaves the island. |
| Shapes | Shops 1 to 3 storeys by 90-day rank, with plinth, trim bands, door, awning, windows; three roof types (gable to the street, ridge along the street, hipped) with chimneys. Stalls are market stalls. Barrel-roof warehouses with ribbed fronts, a depot with a roller door, a gantry crane, ships with hull stripe, bridge and deck containers. Seeded trees (two kinds). Street lamps. |
| Palette | Calm base: cream walls, slate roofs, sage grass, sand, teal sea. Saturated colour is reserved for data: amber roof + lit windows + a warm light pool = bought today; blue = deliveries; teal = port; violet = approvals; red = late / low. |
| Labels | DOM pills projected from 3D anchors (the app's Badge look, crisp at any zoom, dark theme for free), culled or nudged on collision, never over the board's face, never clipped by the stage edge. |
| Camera | Perspective 30-degree lens. One 2.4 s fly-in on load on `--ease-standard` while buildings rise plaza-outward and labels arrive last; any input hands the camera over where it is. Drag turns with momentum, tilt 20 to 80, zoom 0.7 to 2.2, animated reset. |
| Motion (Mini Metro rule: only where it carries a figure) | **Lorries** (owner Q6 = a): one per customer with orders due, up to 6, out of the depot door on curved lanes keeping left, accelerate / cruise / brake, lean into bends, nose dips when braking, U-turn at the customer, back to the depot; a customer outside the town drives off over the bridge. **Ships**: anchored = incoming (gentle bob); one sails in out of the haze with a V wake, the crane trolley runs out, lowers, lifts the container, runs back and sets it on the quay, the ship sails off. Red stack on the quay = late. Idle life (trees, flags, swell) stays under 0.2 units. |
| The one delight | A new sale: the shop dips and springs, a gold coin arcs (a true parabola) from its roof to the board, a ripple rings out on the ground, the board pulses with a warm halo and counts up, "+RM 9,010" rises once. A shop that had not bought yet lights up for the rest of the day. |
| Calm and cost | Render on demand: frames only while something moves; paused, reduced motion or a hidden tab = zero frames (measured: no animation frame scheduled). 60 fps cap; pixel ratio steps down if a machine cannot hold 50 fps. |
| Reduced motion | No fly-in, nothing drives or bobs (lorries parked at their customers, ship alongside); the sale becomes a colour change + number change + a fading chip. Play is still offered (the viewer's choice). |

Motion vocabulary follows the repo, not a new system: the only curve is `--ease-standard`
(`sorento_crm_frontend/css/config.reui.css:87`, DESIGN-LANGUAGE.md:136 "do not introduce a second one"),
solved exactly in JS; things with mass use a trapezoid speed profile; springs are analytic damped sines.

## 3. Evidence (this Mac mini, Apple M4, Chrome for Testing, ANGLE Metal)

- 60 fps at pixel ratio 1 and 2 (1600x1000 viewport), 71 to 73 draw calls including the shadow pass, 68k triangles.
- Paused / reduced motion: `requestAnimationFrame` not scheduled while idle; a sale crossfade schedules frames, then stops.
- Recorded deterministically: the mock's clock and every CSS/WAAPI animation step 1/30 s per frame (`?capture`).
- 1280 and 375 screenshots in `screens/` (09 and 10 are 375 px touch).

## 4. Recommendation

Approve v6 as the look TOWN-V2 builds. It keeps every approved card rule (hover tooltip, tap = lightbox,
lightbox popups, tilt / zoom / reset, INCOMING vs LATE, supplier names only in the personal view, "Open packing
lists") and adds no new screen. Build cost for TOWN-V2 is mostly `TownScene.tsx` (scene, loop, labels) plus one
snapshot key, `deliveries.customers[]` (key, name, orders), for Q6. The sale beat should play once per poll
that finds new invoices (summed amount, one beat), so a busy hour never stacks beats.

Not done on purpose: post-processing (SSAO, bloom, depth of field) and real-time reflections. They cost frames on
the wallboard; the baked occlusion and contact shadows get most of the look for almost nothing.
