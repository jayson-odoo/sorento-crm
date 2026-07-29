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
