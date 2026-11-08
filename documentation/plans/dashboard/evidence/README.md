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
