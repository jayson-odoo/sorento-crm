# IKEA "Design your space" planner - hands-on interaction study

Status: Complete (observed live via Playwright, 2026-07-29)
Target: https://www.ikea.com/addon-app/space/platform/latest/my/en/#/room/bathroom (Malaysia locale, bathroom domain)
Screenshots: `/private/tmp/claude-501/-Users-tehjayson-Documents-foundryx-sorento-crm/9e7e8d96-8dab-40b1-898d-199179b36007/scratchpad/ikea/`
(Everything below was directly observed unless explicitly marked INFERRED.)

---

## What we observed

### 1. First-run journey

- Landing page (`01-landing.png`): headline "Design any space in your home", a room-type chip row (Bathroom preselected because the URL said so; Bedroom / Workspace / Hallway / Dining / Living room / Outdoor / Children's room), and exactly two entry cards: **"Design from scratch"** and **"Open a design"** (continue previous). That's it - one decision (which room), one decision (new vs resume).
- Clicking "Design from scratch" drops you STRAIGHT into a fully-formed default room: 300x250 cm, 250 cm ceiling, tiled walls, tiled floor, an interior door already placed (`04-editor-initial-3d.png`). **Zero questions asked** - no dimension wizard, no unit dialog, no template gallery. The user edits a working room rather than building one from nothing.
- The only interstitial is a dismissible "Before you plan: 3 tips" safety dialog (`02-first-run-tips-dialog.png`) - 3 cards with photos + Next/Back. Skippable via X. Shown once (not shown again on a later fresh start in the same browser).
- The product panel is ALREADY OPEN on the right at first paint, showing the domain hero category (Wash stands) with priced product cards. So the first screen simultaneously shows: room, price ticker (RM 0), Save, Summary (disabled until >0 items), and shoppable products.
- Decisions before seeing a room: **2 clicks** (room chip is preselected, "Design from scratch"). Decisions before seeing products: same 2.

### 2. Room shaping ("Customise room" mode)

Room editing is a **separate mode** entered via a single bottom-center "Customise room" button. Entering it: auto-switches to top-down view, swaps the product catalog for a 5-tab room sidebar (**Modify room / Doors / Windows / Objects / Customise room style**), and shows a one-time 4-step onboarding carousel with looping videos (`05-customise-onboarding-move-walls.png`): "Move walls" (drag a wall to change size), "Change measurements" (click the label, type a length), "Add a corner" (select wall > Split wall), "Wall and railing options" (wall <-> railing <-> remove).

- **Every wall carries a pill-shaped dimension label** (e.g. "300 cm") floating outside the plan (`06-customise-topview.png`). The label is a button: click it and it becomes an **inline stepper input** (textbox + increment/decrement buttons) right where the label was - type 350, Enter, wall re-lays out instantly (`07-wall-length-typed-350.png`). No side-panel form for lengths; the number lives on the wall.
- **Drag a wall face** to resize: mid-drag the wall highlights **blue** and the dimension label updates **live every frame** (`08-wall-drag-mid.png` shows 294 during drag). Resolution is 1 cm - it stopped at 294, not a rounded 290/295, so there is **no coarse snap on wall drag** (only integer cm). The wall stays selected (blue) after release (`09-wall-drag-after.png`).
- **Click a wall** to select it: a floating horizontal icon toolbar appears near the bottom of the canvas with 6 actions: **Split wall / Change colors and materials / Add sloped ceiling / Add inner wall / Add railing / Delete wall** (`10-wall-selected-options.png`). Corners are not dragged directly in the default flow - you get more corners by splitting walls (accessibility list confirms: room = list of walls, each 300/250 cm).
- **Ceiling height** is the one property in the side panel ("Modify room" tab): a single textbox, 250 cm default. Wall thickness is NOT exposed anywhere.
- **Doors/Windows are click-to-place types, not products**: Doors tab lists Interior (Modern/Traditional/Glass/Sliding/Double x3) / Exterior (5) / Openings (plain wall hole). One click places the door on the currently-selected wall and opens an **Edit Door** panel: variant thumbnails, **Width (111) and Height (221) cm textboxes**, Opening direction (Outside/Into room), Handle side (Left/Right) (`12-door-added.png`). The canvas jumps to an elevation view of that wall with **live distance labels from the door to each wall end and to the ceiling** (145 cm / 95 cm / 29 cm), each announced to screen readers as "N cm right/left/up to nearest obstacle". Windows are identical in pattern (Single: Modern/Traditional/Sliding/Sash/Split; Double; Fixed glass panels).
- Undo/Redo buttons live bottom-right in both modes and are enabled per-action. Wall edits undo cleanly. BUT: **undoing a just-added door crashed the whole app** to a raw React error page ("Missing product params component for entity: 66", no ErrorBoundary) (`13-crash-after-undo.png`) - and after reload the session state was corrupted (blank scene, `18-topview-check.png`). Navigating away triggers a **beforeunload "leave site?" guard**.
- Dragging a wall into another wall was not directly exercised (NOT OBSERVED); minimum-size clamping is INFERRED.

### 3. Product placement

- **Finding products**: a vertical icon rail of ~8 domain categories (Wash stands, Mirrors, Bathroom storage, Shower & bath, Toilets and bidets, Laundry, Lighting, Accessories) opens a wide panel with sub-category chips (e.g. "Wash stands with sink / without sink / Sinks"), a count ("45 items"), and an **All filters** button. Filters = Series checkboxes, Width buckets (40-59 / 60-79 / 80-99 / 100+ cm), Depth buckets, Color swatches, "View 45 articles" (`43-all-filters.png`). **There is NO free-text search anywhere in the planner.** "Browse products by room" swaps the whole catalog to another room domain (bedroom, workspace...) so you can furnish cross-domain (`42-browse-by-room.png`).
- **Product card** (`04-editor-initial-3d.png`): photo, product family name (TÄNNFORSEN / ORRSJÖN), one-line spec incl. dimensions ("Wash-stnd w drawers/wash-basin/tap, white, 82x49x69 cm"), price, (i) info button, and a **variant strip** ("More options available" + 2-4 thumbnails + "+N") directly on the card.
- **Into the room = click the card** (panel header for doors/windows says "Click or drag to add an object in the scene", so drag-in also exists). On click, the item **auto-places itself against a free wall stretch at correct mounting height** - no placement step, no ghost-follow-cursor phase. Price ticker updates instantly (RM 0 -> RM 2,389) and the Summary button activates (`20-product-placed.png`).
- **Selection**: click the item in-scene -> white outline glow, a **vertical action toolbar** appears beside the canvas (Selected/hand, Information, Modify, Group [needs 2+], Duplicate, Delete) and the right panel becomes **"Selected product"**: big image, full name, price, expandable "Safety recommendations (2)", "Modify product" CTA, plus a cross-sell block ("Organise with VISSLAÅN") (`21-product-selected.png`).
- **Moving**: dragging a wall-mounted item slides it **along its wall**; dragged toward another wall it **hops to that wall and auto-rotates** to back against it (`22-product-drag-mid.png` right wall -> `24-product-drag-after.png`, then top-view drag hopped right wall -> bottom wall, `27`-`29`). Items never float free mid-room; there is **no user-facing rotate control at all** - orientation is derived from the wall. The back-to-wall toilet behaved identically. (Freestanding-item rotation NOT OBSERVED - nothing tested was freestanding.)
- **Clearance labels are the core feedback**: with the ruler toggle ON (and always while dragging), the selected item shows **live "distance to nearest obstacle" chips** left/right (and up in elevation): 104 cm / 114 cm etc., updating continuously during the drag (`25-measurements-on.png`, `26-topview-with-product.png`). A cm/in unit toggle sits next to the ruler.
- **Collision**: impossible to produce an overlap - wall-glued items simply refuse to cross each other or leave the wall; the drag just stops tracking into illegal space (`32`/`33`). No red-tint invalid state was ever shown (NOT OBSERVED - likely exists for genuinely free items, INFERRED).
- **Modify** opens a **focused stage**: the single item alone on a neutral background with a variant grid on the right, Cancel / "Update design" (`34-modify-panel.png`). Swap keeps placement.
- Non-sellable placeholders ("**Design extras**" - toilets, since IKEA MY sells none) are explicitly labeled "Everyday items to help you picture your space - and not for sale" and priced RM 0 (`40-view-options.png` right panel).

### 4. Categories / tiles / finishes

- Finishes live in Customise-room mode. Select a wall -> "Change colors and materials" -> right panel "**Wall coverings**": Paint colors (66 swatches, "Show 60 more"), Tiles (38: "Blue 20x20 Grid", "Beige 20x20 Grid"...), Outdoor walls (wood panel, stucco, brick...). Picking a swatch applies **live to that ONE wall** and the camera has already jumped to an elevation view facing it, wall outlined blue (`11-wall-covering-applied.png`). Selected swatch gets a pressed/black-border state.
- Scope is **per-surface**: one wall at a time; the floor is its own selectable surface (clicking the floor gives its own "Edit options" incl. Change colors and materials). No "apply to all walls" was seen (NOT OBSERVED).
- These are generic finishes, not SKUs - they never appear in the price or summary.

### 5. 2D vs 3D

- One toggle button bottom-left ("Change to Top view" / "Change to 3D view") plus a **View options** caret: "Refocus the room" (reset camera), "Top view", "3D view" (`40-view-options.png`). No first-person/walkthrough mode.
- **3D**: orbit by left-drag on empty canvas (`39-orbit.png`), wheel zoom; walls nearest the camera are automatically hidden/peeled so you always see into the room. **Top view**: fixed orthographic plan, products render as their real photographic top-down footprints (not boxes) (`26-topview-with-product.png`).
- Customise-room mode forces top view (you can toggle back to 3D inside it; wall covering selection forces an elevation view of the selected wall).
- Everything persists across the switch: selection, clearance labels, measurements toggle, price. The same selection toolbar works in both.
- 2D is where dimension labels + wall editing shine; 3D is for judging look/height. Same scene graph, two cameras.

### 6. Summary / checkout

- Blue **Summary ->** button (top center, next to the live RM total, enabled only when the design has >= 1 sellable item) opens a full-page **Design Summary** (`36-summary-loaded.png`): tabs **Product list / Images / Safety / Printout measurements**; utilities "Check in-store stock", "Sort by", print icon, "Edit design" back-link.
- Product list rows: **include/exclude checkbox** (Deselect all above), thumbnail, name, unit price, **qty (1x)**, line total. A composite product expands via "**Includes several articles**" into its 4 orderable SKUs **with IKEA article numbers** (605.354.43 etc.) (`37-summary-articles.png`). Design extras (toilet) are excluded entirely.
- Right rail: a rendered **3D snapshot of the actual room**, grand total (RM 2,389), primary CTA **"Add to bag"**, secondary "Save", plus share and wish-list icons. Checkout = push the checked items into the normal ikea.com cart.
- Main menu (`41-menu.png`): Save / Save as / Share / My designs / **Open design code** (retrieve any design by code - the store-handoff mechanism) / Start from scratch / Settings / Help / Select store / Log in.

### 7. What makes it feel good / bad

**Good (the five that matter):**
1. **Live clearance chips** - the selected/dragged item constantly tells you its distance to the nearest obstacle on each side, in both 2D and 3D, screen-reader announced. This single mechanism replaces rulers, collision warnings and "will it fit?" anxiety.
2. **Dimension label = input** - wall lengths are pills on the wall; click one and it becomes a stepper input in place. Type or drag, same spot, zero panels.
3. **Wall-magnet placement with auto-rotation** - items can never be wrongly oriented or float in space; a drag toward another wall hops and re-orients in one motion. Placement is one click with no aiming.
4. **Mode camera choreography** - entering Customise room -> top view; picking a wall covering -> elevation facing that wall; Modify product -> item alone on a stage; exit -> back to 3D. The camera always frames the current decision.
5. **Always-on running price + one-tap Summary** - RM total ticks on every add/remove; Summary explodes bundles into article numbers and feeds the real cart, with per-row opt-out checkboxes.

**Bad / slow:**
1. **Fragile undo + no error boundary** - undo after adding a door hard-crashed to a stack trace, and the auto-saved session came back corrupted (blank scene). Heavyweight state, weak recovery.
2. **Heavy loads** - initial boot ~10 s, Summary product list shows a spinner for several seconds, every category click re-fetches. Feels server-bound.
3. **No text search and no multi-surface apply** - finding a specific product means knowing its category and paging "Show more" 12 at a time; tiling 4 walls means 4 separate wall selections.

---

## The interaction model in one page

The user holds four objects in their head, each with exactly one way to touch it:

1. **The room** is a loop of walls. A wall is a thing you click (toolbar: split / finish / delete) or drag (resize, blue highlight, live label) - and its length label IS the numeric input. Ceiling height is one number. You never place walls; you deform a room that already exists.
2. **Openings** (doors/windows) are typed stamps that live IN a wall. One click adds one to the selected wall; editing is a form (width/height/direction/handle) plus dragging along the wall, with live distances to wall ends. They are not products and have no price.
3. **Products** are catalog cards. Click a card -> it places itself sensibly (wall-snapped, right height). In the scene a product is: drag = slide along wall / hop walls (orientation is never the user's job), select = glow + action toolbar (Info / Modify / Duplicate / Delete) + detail panel. Numbers around it (clearance chips) do the fitting-feedback job; the app quietly forbids illegal positions instead of warning about them.
4. **Money** is ambient. Every add ticks the header total; Summary is a shopping list derived from the scene (checkbox per line, bundles exploded to SKUs, "Add to bag").

Two modes only - **Furnish** (default, 3D, catalog on the right) and **Customise room** (top view, walls/doors/windows/finishes) - one button toggles them, and each mode swaps BOTH the side panel and the camera. 2D vs 3D is a camera choice inside a mode, not a different editor: same scene, same selection, same labels.

The systemwide grammar: **click = select + show the one relevant toolbar; drag = the only spatial verb; type = only via a label you clicked; everything else auto-derives** (orientation, height, camera, price).

---

## Gap list vs our current tool

Our current state: top-down SVG plan (drag corners + wall faces, 50 mm snap, live wall-length labels), products as flat real-size boxes, separate crude Three.js box view, product picker with server-side search, running total. No wall height/thickness, no doors/windows, no finishes, no collision, no wall snapping, no rotate, no undo, no category browse, no camera niceties.

| # | IKEA behaviour | Our gap |
|---|---|---|
| G1 | Click wall-length label -> becomes inline numeric input (type exact mm) | Labels are display-only |
| G2 | Products magnet to walls, slide along, hop wall-to-wall with auto-rotation | Products are free boxes; no wall relationship, no rotate at all |
| G3 | Live clearance-to-nearest-obstacle chips on the selected/dragged product | We only label walls, never product gaps |
| G4 | Selection toolbar on the item (Duplicate / Delete / Modify / Info) | No in-canvas actions; no duplicate |
| G5 | Doors/windows as typed stamps in walls (click-to-add, width/height form, live edge distances) | Nothing - plans have no openings, so 3D walls are always solid |
| G6 | Per-wall / floor finishes (swatch panel, live apply) | Single hardcoded look in both SVG and 3D |
| G7 | Undo/redo everywhere (incl. wall drags) | None |
| G8 | 2D/3D as two cameras on ONE scene; switch preserves selection; "Refocus" reset; auto-hide near walls in 3D | Two disconnected views; 3D is fire-and-forget boxes |
| G9 | Default room on entry (no blank canvas), one-time skippable coach marks | We start from a blank/template-less state |
| G10 | Summary page: per-line checkboxes, qty, bundle explode, room snapshot, Add to bag | Running total only, no reviewable list page |
| G11 | Category rail + facet filters (widths/series/color) | Search-only picker (we actually beat IKEA on text search - keep it) |
| G12 | Collision = movement simply constrained (no overlaps possible) | Boxes overlap freely with no feedback |
| G13 | beforeunload guard + session autosave + design code share | Unknown/none |
| G14 | Ceiling height + door/window heights = the only Z numbers (no wall thickness UI) | We have no Z model at all - adopting just these two numbers gets us credible 3D |

---

## Ranked recommendations (mimic order = user-visible payoff per build effort)

1. **Clickable dimension label -> inline input** (G1). Our SVG already renders live wall labels; making them a `foreignObject` input with Enter-commit is an afternoon. Single highest trust-builder ("I typed 3050 and the room IS 3050").
2. **Wall-snap + slide + auto-rotate for products** (G2). In 2D: nearest-wall projection when a dragged box's edge comes within ~150 mm of a wall, rotate to wall normal, clamp to wall segment; hop = re-project to whichever wall is nearest the cursor. 2-3 days in SVG land, and it silently kills most of the rotate/collision problem for the showroom case (everything backs onto a wall).
3. **Live clearance chips while dragging/selected** (G3). Cast along the wall axis to nearest neighbour/wall-end, render two pills. A day once G2 exists (the wall axis gives you the measurement line for free). This is THE "feels professional" feature.
4. **Undo/redo** (G7). We mutate one plan JSON; a bounded snapshot stack (immer patches or plain deep-copies at <= 50 entries) + Cmd/Ctrl-Z + two footer buttons is a day. Do it before shipping anything else touch-heavy - and note IKEA's crash: keep undo entries self-contained so restoring one can never dangle a reference.
5. **Selection toolbar (Delete / Duplicate / +90-degree Rotate for free items)** (G4). Small floating toolbar anchored to the selected box in SVG; duplicate = clone + offset 200 mm. A day. Rotate stays a button, not a handle - IKEA ships NO free rotation and doesn't miss it.
6. **Doors & windows as wall stamps** (G5). Type list (door / window / opening), click wall -> stamp at wall midpoint, drag along wall, width/height fields in a small panel, live distances to wall ends (re-uses G3 rendering). In 3D: CSG-free cheat - draw wall as segments around the opening. ~3-4 days total across SVG + Three.js, and it's what makes the 3D view stop looking like a shoebox.
7. **One scene, two cameras** (G8): drive the Three.js view from the same plan state, keep selection across switch, add "Refocus" (fit-to-room) and hide the two camera-facing walls (dot product test per frame). The wall-hiding + refocus part is 1-2 days and transforms the 3D view's usefulness; full live-sync depends on how separate our current views are (budget a week if state is currently duplicated).
8. **Default room + zero-question entry** (G9). Ship every new design as a pre-sized rectangle (e.g. 3000x2500) with finishes on, editor open, picker open. Half a day, removes the scariest blank screen.
9. **Summary/quote page** (G10): checkbox rows, qty merge of identical SKUs, grand total, plan snapshot (SVG -> PNG is nearly free for us), single CTA. 2-3 days; this is the dealer-kit money screen and our running total already has the data.
10. **Per-wall + floor finish swatches** (G6). Six curated swatches per surface, fill in SVG, material swap in Three.js. 1-2 days for flat colors/patterns; skip photo-real tiling.
11. **Ceiling height + opening heights as the only Z inputs** (G14). Two numeric fields; give the 3D box real height. Half a day, prerequisite for G5's 3D payoff.
12. **Category chips alongside search** (G11). We keep server-side text search (better than IKEA) and add a chip row from product categories. A day. Facet buckets can wait.

Skip for now: free-drag rotation handles, first-person camera, photo-real materials, safety-recommendation content, in-store stock — none are load-bearing to the feel.

---

## Second pass: six interactions (2026-07-30)

Observed live via Playwright against the same MY bathroom planner, fresh "Design from scratch" session (no Resume dialog appeared this run - the previous session had been corrupted by the undo crash, see first pass). Screenshots: `/private/tmp/claude-501/-Users-tehjayson-Documents-foundryx-sorento-crm/9e7e8d96-8dab-40b1-898d-199179b36007/scratchpad/ikea2/`. Gestures were injected as real mouse events (left/middle/right down-move-up, wheel with deltaX/deltaY, modifier keys); every claim below was observed unless marked INFERRED.

### 1. Camera / navigation

3D (Furnish mode), tested one gesture at a time from a "Refocus the room" reset:

- **Left-drag on empty canvas = orbit** (yaw + pitch; drag up pitches the camera down so you look up into the ceiling). `d-left-h120.png`, `d-left-v96.png`.
- **Middle-drag = orbit, identical to left** (same +120 px drag from the same reset produced a pixel-identical view to left-drag: `d-middle-h120.png` == `d-left-h120.png`). Not dolly, not pan.
- **Right-drag = pan** (truck). With the camera orientation unchanged, the room translates with the mouse (`c-3d-rightdrag.png` vs `c-3d-leftdrag.png`: same wall angles, scene shifted left+down following a -100,+50 drag). No context menu appears on right-drag.
- **Wheel = zoom** (dolly in/out). **Zoom converges on the CURSOR, not the canvas centre**: same wheel amount with the cursor over the door vs over the right wall ends framed on the door vs on the right wall (`z-wheel-at-door.png` vs `z-wheel-at-right.png`, run in top view where it is unambiguous; the 3D corner test agrees).
- **Shift+wheel = same zoom** (no alternate axis). **Ctrl+wheel = zoom too** (so trackpad pinch, which browsers deliver as ctrl+wheel, zooms; `z-ctrlwheel.png`). **Horizontal wheel (two-finger sideways scroll) does NOTHING** in 3D (`d-hwheel-only.png` == `d-base.png`).
- **Reset/refocus exists in two places**: the "View options" caret bottom-left opens a 3-item menu "Refocus the room / Top view / 3D view" (`01-view-options-menu.png`); Refocus restores the default 3/4 framing exactly.
- **Top view**: NOT fixed - it pans and zooms but never rotates. Left-drag, middle-drag AND right-drag all pan (grab-the-world, plan follows the mouse; `t-leftdrag-center.png`, `t-middledrag.png`, `t-rightdrag.png`); wheel zooms to cursor; the plan stays axis-aligned under every gesture. Dragging the floor of the room pans the camera (does not move the room).

**Copy this:** wheel-zoom-to-cursor in both views plus a one-click "Refocus" reset; in React+SVG the 2D half is a screen-space transform (one afternoon), and in Three.js it is OrbitControls with `zoomToCursor: true` plus a fit-to-bounds helper (a day).

### 2. Selecting and moving a product

- **Select = single click** on the item, no hover-first requirement. Feedback: white outline glow on the mesh, and a **vertical action toolbar fixed to the right edge of the canvas** (NOT anchored to the item - it stays at the same screen spot wherever the item is; it replaces the category icon rail while a selection exists). Buttons top-to-bottom: Selected (hand, acts as header), Information, Modify, Group (disabled until 2+ selected), Duplicate, Delete (`11-product-selected-3d.png`). The right panel simultaneously swaps to "Selected product" (photo, name, price, Safety recommendations, Modify product CTA).
- **Dismiss** = click empty canvas (or the hidden "Deselect product" a11y button). Esc does NOT deselect. Toolbar reverts to the category rail, panel reverts to the catalog.
- **Drag** is wall-constrained sliding: the wash-stand slides along its wall keeping orientation; drag toward another wall makes it **hop and auto-rotate** to back against that wall. There is no free-floating state and no rotate handle anywhere.
- **Live numbers while dragging**: black pill chips on thin measurement lines, updating every frame - distance to nearest obstacle left and right ALONG the wall (e.g. "117 cm" to the door frame, "101 cm" to the right wall) plus a vertical "16 cm" chip below the item (gap to floor). Chips render at the measurement lines in-scene, not in a HUD corner (`13-drag-mid-alongwall.png`).
- **Into another product**: movement clamps; overlap is impossible. A translucent **ghost wireframe renders at the cursor's attempted position** while the solid body stays at the last legal spot (`28-toilet-into-vanity.png`); release leaves it at the clamp point (it does not snap flush; ours ended 8 cm short: `29-toilet-drop.png`).
- **Into a wall/door**: same refusal + ghost pattern - dragging the vanity into the door zone clamps it against the door frame with the ghost overlapping the door (`16-drag-into-door.png`, `17-drag-past-door.png`).
- **Out of the room entirely**: simply refuses - the item stays clamped at the boundary, nothing is deleted, price unchanged (`21-drag-outside-mid.png`).
- **Nothing ever turns red.** No invalid-state tint exists anywhere in these flows; illegality is communicated purely by the body not following the cursor (plus the ghost showing what you asked for).
- Quirk worth knowing: an item mounted on a camera-culled (peeled) wall is **hidden and unclickable** while deselected (`23-deselected.png`); it re-renders when its wall faces the camera again, and while selected it renders even on a hidden wall.

**Copy this:** the clamp-plus-ghost drag (solid body never enters illegal space, a wireframe ghost shows the attempted position) - in SVG this is just rendering the unclamped rect at 40% opacity when clamped != attempted, roughly a day on top of our existing drag code.

### 3. Doors and windows

- Doors are **not selectable in Furnish mode** - clicking one there just deselects the current product. All door editing lives in Customise-room mode.
- In Customise mode, click the door: door highlights blue, a small **horizontal toolbar anchored NEXT TO the door** appears (drag-handle dots / Duplicate / Delete - note doors get an item-anchored toolbar while products get a screen-edge one), and the right panel becomes **Edit Door**: variant gallery (Modern etc., +4 more), Size = Width (90) and Height (210) cm textboxes, then "Position - viewed from inside the room, facing the door": Opening direction (Outside room / Into room) and Handle side (Left / Right) (`32-door-selected.png`, `33-door-panel-scrolled.png`).
- **There is no numeric offset field in the panel** - but the wall's dimension strip splits into live segments (60 / 90 / 100 summing to the wall length) and **each segment label is clickable, turning into an inline input** (tooltip "Change width"); typing 120 + Enter moved the door to exactly 120 cm from the corner (`38-segment-label-clicked.png`, `40-segment-committed.png`). Segment resolution is 0.1 cm (a drag left it at 109.6).
- **Drag across a corner onto a different wall: it HOPS.** Dragging the left-wall door down past the corner made it jump onto the bottom wall, landing flush at the corner (segments 0 / 90 / 210), then it slides along the new wall normally (`35-door-drag-at-corner.png`, `36-door-drag-bottom-wall.png`). No refusal, no straddling state, opening arc preserved.
- **3D drag works too and is wall-constrained**: in Customise 3D the selected door slides along its wall following the horizontal component of the drag; pulling the mouse up/away from the wall does nothing vertical - it never moves in free space (`47-door-3d-drag-mid.png`, `48-door-3d-drag-up.png`). Live corner-distance chips render in-scene in 3D as well, including the "40 cm to ceiling" vertical chip. At the corner in 3D it clamped at 2 cm rather than hopping to the (camera-culled) adjacent wall; 3D hop onto a visible wall NOT TESTED.
- In Customise mode products render translucent (ghosted) so openings are easy to hit.

**Copy this:** the wall-length label splitting into clickable per-segment inputs when an opening is selected (offset editing with zero extra form fields) - our SVG labels already exist, so segment math + reusing the G1 inline-input pattern is 1-2 days.

### 4. Full screen and chrome

- **No browser-fullscreen affordance exists** (menu contains only Start page / Save / Save as / Share / My designs / Open design code / Start from scratch / Settings / Help / Select store / Log in: `55-menu-open.png`).
- The real "focus mode" is the **X button at the top-right of the right panel**: it collapses the whole product panel, the canvas expands to full window width, the category icon rail docks to the far right edge, and the price + Summary pill moves to the top-right (`51-panel-closed.png` collapsed vs `53-panel-reopened.png` expanded). Reopen = click any category icon in the rail (the rail is the persistent breadcrumb back into the catalog). Esc does NOT close or reopen the panel; there is no drag handle.
- The left side has no rail to collapse (Menu and Save are floating pills). In Customise mode the same X collapses the room-tools panel.
- Camera note: collapsing does not reframe the room automatically beyond the wider viewport; "Refocus the room" is the recovery.
- The bottom-left caret is the View-options popover (Refocus / Top view / 3D view), i.e. the "how do I get back" affordance lives permanently bottom-left (`52-caret-clicked.png`).

**Copy this:** panel-collapse-as-focus-mode (X on the panel, icon rail stays as the way back, canvas takes the full width) - a flex-width toggle + keeping the rail mounted, half a day in our layout.

### 5. Dimension editing discoverability

Three distinct visual states on the wall-length labels (Customise mode):

- **Rest**: white rounded pill floating outside the wall, bold black number + lighter grey unit ("300 cm"), sitting on a thin dimension line with end ticks. The pill shape + the grey unit are the only rest-state affordances; the labels are canvas-drawn at rest, so the mouse cursor stays a default arrow (measured `cursor: auto` on the canvas; no pointer cursor, no icon).
- **Hover**: the pill gains a **thick black border** (`41-walllabel-hover.png`). This border is the clickability signal.
- **Editing (click)**: the pill is replaced by a DOM overlay - a white card containing a **blue-outlined text input** (number selected, grey "cm" suffix inside the field), a black tooltip above ("Change width"), and a small **anchor dot on each side** of the card (`42-walllabel-editing.png`) - INFERRED these dots pick which wall end stays fixed on resize; not exercised. **No stepper arrows, no OK button, no Enter/Esc hint text.** Commit = Enter (verified: door segment 120 applied instantly); cancel = Escape (verified: editor closed, value unchanged). Resolution is 0.1 cm.
- Same pattern everywhere: wall lengths, door/window corner-distance segments, ceiling height is the one number living in a side panel instead.

**Copy this:** the three-state label (pill -> black-border hover -> inline input with the value pre-selected, Enter/Esc semantics, no chrome) - ours are SVG `<text>`, so pill rect + hover class + `foreignObject` input is about a day including tests.

### 6. The catalogue-to-room path

Timed with rapid screenshots (150 ms / 500 ms / 1200 ms after the card click, `60-add-t150.png` - `62-add-t1200.png`):

- **One click on the card = the item EXISTS in the room already at t~150 ms**, auto-placed against a free wall stretch at correct mounting height, **already selected** (glow + action toolbar + clearance chips visible immediately). There is **no ghost-follow-cursor phase, no cursor change, no placement animation, no toast, and no camera move** - the only motion is the **price ticker counting up** (caught mid-roll at RM 2,401 on the way from 2,389 to 4,778) and the right panel cross-fading from catalog to "Selected product" (briefly blank at t150).
- The panel header for doors/windows says "Click or drag to add an object in the scene", so drag-from-panel also exists (drag-in NOT TESTED this pass).
- **Strictly one click = one item.** There is no multi-select or queueing in the catalog; clicking another card adds another item immediately (each add lands selected, replacing the previous selection). Variant thumbnails on the card only swap the card image, not the room.
- Design extras (toilets) behave identically but add RM 0 and show a "not for sale" note in the panel.
- "Add to room" from a normal ikea.com product page outside the planner: no such entry point was reachable from this session; IKEA MY product pages link to planners but do not inject items into an open design (INFERRED, not directly testable here).

**Copy this:** click-means-placed with the item arriving pre-selected and the running total animating - auto-place = "first free wall stretch wide enough, else room centre"; in our stack this is a placement heuristic + react-query cache update + a count-up on the total, about a day.

### Corrections / additions to the first pass

- First pass said orbit was left-drag only: middle-drag orbits identically, right-drag pans, and zoom is to-cursor (first pass did not test these).
- First pass described the wall-length editor as a "stepper input": the current UI shows a plain inline input with side anchor dots and a "Change width" tooltip - no +/- steppers.
- First pass said door editing shows "live distance labels" only: those labels are themselves editable inputs (offset-by-typing), which is stronger than we recorded.
- New gotcha: items and doors attached to a camera-culled wall are invisible AND unclickable while deselected; selection keeps them rendered. Any "one scene, two cameras" copy of the wall-peeling trick must decide what to do with wall-mounted items on hidden walls (IKEA hides them, which confused us in testing).
