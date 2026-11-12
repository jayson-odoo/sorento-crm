# Sorento Town browser evidence

The first browser pass (8 Nov, head b8f9f70db3) used a fake snapshot that copied real dev-data
figures, so its screenshots were removed. Masked screenshots (fictional names and figures only)
replace them after the fix round. Measurements from that pass, which carry no business data:

- Draw calls: 22 per frame at 1280 and 375 (budget < 100).
- Pixel ratio: canvas buffer / CSS width = 1.5 on a DPR 3 emulation.
- Idle: 0 frames and 0 draws in 5 s idle, and 0 in 3 s after a drag, at 6x CPU throttle.
- Hidden tab: 0 snapshot requests and 0 frames in 75 s; next poll 32 s after the tab became visible.
- Polling: 200 at 0 s, 304 at 60.0 s and 120.1 s.
- Drag frame at 6x CPU on SwiftShader (software GL): render callback p50 7.0 ms / p95 36.6 ms at 1280,
  p50 7.8 ms / p95 22.8 ms at 375. No real GPU in the sandbox.
- Bundles (dev server): the dashboard's 69 chunks contain no "WebGLRenderer"; /town loads three.js.
- No WebGL and reduced motion: cards only, no errors. 375 px: no horizontal scroll.
- Viewer without sales.reports.view: no RM, no names, keys s1..sN in the response body.

## Re-pass after fix round 3 (masked, fictional data only)

Head fa15db0420 (fix round 3 included). Data: a stored fictional snapshot (30 shops named Alpha Tiles,
Beta Home Centre and so on, 8 lit, 60 stalls named "Stall NN Trading", round invented figures). Users:
admin, a staff user with the purchasing role (no `sales.reports.view`), a portal_user. Sidebar click from `/`.

Screenshots (2x, palette compressed under 200 KB):

- `a-admin-1280-panel-lit-shop.png`: admin 1280x800, Sheet panel open on a lit shop.
- `b-admin-375-town-and-cards.png`: 375 town stage plus the top cards.

Results:

- Stalls and tags: instanced building draw counts are 35 = 30 shops + 5 stalls (60 stalls in the snapshot);
  5 name tags drawn; "+64 more dealers bought today" = 77 dealers minus 13 lit buildings drawn. PASS.
  Tags are not clipped at the canvas edge, but one of the five overlaps another (see defects). PARTIAL.
- Scoreboard says "23% vs Sun 1 Nov" in the scene and in the card (date derived from today). PASS.
- Sheet: every tap (scoreboard, shop, "!", depot, approvals) opens it; focus is inside it; Escape closes it;
  with it open a tap on the depot swaps its content (scene still tappable, one dialog). PASS.
- Loading skeleton ("Loading town") shown while the snapshot response was held 3 s, gone after. PASS.
- 375x812: no horizontal scroll (scrollWidth 375), stage is square (341x341), cards stack below, panel inside
  the viewport and closes on Escape. The town does NOT fill the stage (see defects). PARTIAL.
- Staff user: no RM, no money-shaped figure, no names, no UUID, in the page or the scene text; shops read
  "Dealer"; counts present. The response keeps only `account_label, key, kind, today_docs` per shop with keys
  `s1..sN`, and the order is not the rank order (lit first, then a key hash). PASS.
- Portal_user: `GET /api/v1/town/snapshot` answers 403 `town_staff_only`; staff and admin answer 200. PASS.
- 6x CPU throttle, DPR 3, 60 stalls: 18 draw calls per frame at both widths (limit 100); pixel ratio 1.5;
  0 rendered frames in 5 s idle and 0 in 3 s after a drag. Drag render callback p50 8.5 ms, p95 23.7 ms at
  1280 (p50 4.8 ms, p95 13.8 ms at 375), software GL, first frame 630 ms and 450 ms.

Defects:

1. One name tag is partly hidden behind its neighbour at 1280 and at 375 (Iota Ceramics under Mu Flooring).
2. The island is small inside its stage: at 1280 about 45 percent of the stage height, at 375 about two thirds
   of the width with an empty band on top; the legend then overlaps the island's lower edge on a phone.
3. Opening the "products low" Sheet at 375 logs two React warnings: Missing `Description` or
   `aria-describedby={undefined}` for DialogContent.
4. The Sheet close icon button is 16x16 px at 375.

## Final pass (head e6cc673215, stacked tags; same fictional snapshot: 8 lit shops, 60 stalls)

The two screenshots above were replaced (same names, fictional data only). Three name tags are drawn (Alpha Tiles,
Omicron Ceramics, Upsilon Home Centre), stacked in screen space.

- Tags, checked on canvas screenshots of the default view and one drag each way at 1280 and 375 (six frames):
  - No tag covers another tag in any frame: PASS (the earlier Omicron/Upsilon overlap is gone).
  - No tag is clipped at the canvas edge, and "+64 more dealers bought today" is complete in every frame: PASS.
    After a drag to the left the "+64" pill is the closest to an edge: 6.5 css px from the right edge at 1280 and
    2.5 css px at 375 (tight, not clipped).
  - While the 6 s "Tap any building" hint is still shown at 375 it sits over the top of the Alpha Tiles tag after a
    quick drag (the hint is a transient overlay, the tag itself is whole).
- Legend below the canvas at 1280 and 375: PASS. No console warnings or errors opening all five panels: PASS.
- Sheet close hit area on a coarse pointer (375): 44x44 px, PASS (16x16 with a fine pointer at 1280).
- Draw calls 16 per frame (limit 100); 0 rendered frames and 0 draws in 4 s idle at both sizes: PASS.
- Fill (canvas pixels, default view, unchanged from the previous pass): 1280 canvas 582x505 css: 72 percent of the
  width, 54 percent of the height; 375 canvas 341x228: 72 percent of the width, 70 percent of the height.
- The 128 to 192 colour palette used to keep the png under 200 KB slightly shifts some hues (the red legend dot
  looks magenta in the 375 image).
