# PLAN: Showroom walkthrough (SHOWROOM-WALKTHROUGH)

**Status:** Built and browser-verified on a local stack (28 Oct 2026); awaiting owner review
before PR. Track: full (one migration, new worker queue). Not grilled with the owner: the ask
was one line ("a module to build showroom 3D walkthrough by processing video and images"), so the
decisions below are the defaults taken and are the first thing to confirm.
**UAC:** `showroom-walkthrough-28oct-acceptance-criteria.md`.

## Journey

A marketing or sales person stands in a showroom (Sorento's own, a dealer's, or a developer's
show unit). At each spot worth showing they film a slow turn on the spot with a phone, or take
overlapping photos while turning, or take one photo with a 360 camera. They upload each spot as a
**stop**. The CRM turns each stop into one panorama on the worker. Anyone with Dealer Kit access
then opens the walkthrough, looks around each stop by dragging, and walks stop to stop with
Previous / Next.

## Decisions (defaults, to confirm)

- **D1 Panoramas, not a reconstructed 3D model.** Photogrammetry, NeRF or gaussian splats need a
  GPU box and COLMAP-class tooling this stack does not run. Per-stop panoramas joined in walking
  order are what OpenCV (already a backend dependency) can build on the existing worker, and what
  a customer looks at in a virtual showroom tour. Trigger to revisit: an owner need for
  free-movement 3D (walk anywhere, measure), plus a GPU host.
- **D2 Lives in Dealer Kit.** It is showroom and catalogue material, Dealer Kit already ships
  three.js (Room Designer) and has the `dealer_kit` schema. Menu: Dealer Kit > Room Designer >
  Showroom Walkthroughs.
- **D3 No new permission.** Reads `dealer_kit.page.view`, writes `dealer_kit.page.edit`, the call
  the flyer routes made: a new slug needs a grant sweep before any role holds it.
- **D4 Same request/worker split as the flyer read.** The request stages the uploads and answers
  202 with the stop `processing`; RQ job `build_stop` on a new `walkthrough` batch queue builds
  the panorama and writes `done` or `failed` with the reason. The row is the record.
- **D5 One stop = one panorama + the angle it covers** (`h_fov_deg`, `v_fov_deg`). A 2:1 photo is
  taken as a full 360 x 180 sphere. Several photos, or frames sampled from a video (24, evenly
  spaced), are stitched with `cv2.Stitcher` in panorama mode. The angle is computed from an
  assumed phone lens (68 degrees across the long side), marked as a `shortcut:` in
  `panorama.py`.
- **D6 Panorama served through the backend** (`GET .../panorama`, image/jpeg), so WebGL never
  needs CORS on the bucket.
- **D7 Viewer is plain three.js** (not react-three-fiber, same reason as `RoomScene.tsx`): the
  panorama is drawn on the matching piece of a sphere and the camera cannot turn past its edge.
  Drag or arrow keys to look, wheel or +/- to zoom.
- **D8 Stops are ordered by upload.** Walking order = upload order.

## Not built (named, not forgotten)

- Hotspots placed inside a panorama that link to the next stop; floor plan / minimap.
- Reordering stops, editing a stop's title after upload, replacing a stop's media.
- A public (no login) link for customers, and linking a walkthrough to a Project or customer.
- Cropping the wavy top and bottom edge of a stitched panorama beyond the empty band.
- Reading the real lens from EXIF instead of the 68 degree assumption.

## Shape

| Layer | Files |
| --- | --- |
| Migration | `alembic/versions/wt_0001_showroom_walkthrough.py` |
| Models | `Walkthrough` (company owned), `WalkthroughStop` (through its parent) in `app/models/dealer_kit.py` |
| Builder | `app/services/dealer_kit/panorama.py` (pure: bytes in, JPEG + angles out) |
| Service | `app/services/dealer_kit/walkthrough_service.py` |
| Job | `app/tasks/walkthrough_tasks.py`, queue `walkthrough` (batch) in `worker.py` |
| Routes | `app/api/v1/dealer_kit/walkthroughs.py` |
| Deferred deletes | `dk_walkthrough.delete`, `dk_walkthrough_stop.delete` in `record_actions.py` |
| FE | `app/(protected)/dealer-kit/walkthroughs/**`, `services/walkthroughService.ts`, `lib/dealer-kit/panoramaGeometry.ts` |

Limits: 300 MB per stop, 40 files, JPG/PNG/WebP photos and MP4/MOV/M4V/WebM/AVI/MKV video.

## Verification

- `tests/test_dealer_kit_walkthroughs.py` (19): the builder on synthetic photos and a synthetic
  turn video, the 360 passthrough, refusals in words, the route lifecycle with the job run
  inline, queue outage, deletes taking their stored panoramas, permissions, company scope (404).
- Guard suites updated: owned-table count (173), worker queue roles.
- `lib/dealer-kit/panoramaGeometry.test.ts` (9): sphere segment, zoom limit, look clamp/wrap.
- Migration downgrade/upgrade round trip on a bootstrapped database; single head.
- Browser (agent-browser, sidebar navigation from `/`, real RQ worker): created a walkthrough,
  added a video stop and a 360 photo stop, both built; the panorama reads unmirrored; dragging
  left turns the view right; Previous / Next; deferred stop delete with countdown; 1280px and
  375px with no horizontal scroll.

## Found on the way (not this lane)

`requirements.txt` pins `rq>=2.0`; a fresh install resolves rq 3.0.0, under which
`ForkSafeWorker.perform_job(job, queue)` no longer matches rq's signature and EVERY worker job
dies before running. Raised as its own task.
