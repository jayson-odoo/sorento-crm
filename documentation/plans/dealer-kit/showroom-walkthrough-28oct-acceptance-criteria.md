# UAC: Showroom walkthrough (SHOWROOM-WALKTHROUGH)

Plan: `PLAN-showroom-walkthrough-28oct.md`.

## Building a stop

- AC-B1 A video of a slow turn on the spot becomes one stop with a stitched panorama.
- AC-B2 Several overlapping photos become one stop with a stitched panorama.
- AC-B3 One 2:1 photo is taken as a full 360 x 180 sphere without stitching.
- AC-B4 One ordinary photo becomes a stop covering one phone frame.
- AC-B5 Photos that do not overlap, or files that are not readable media, end the stop as Failed
  with a reason a person can act on ("do not overlap enough...", or the file named).
- AC-B6 Adding a stop answers at once with the stop Processing; the stop turns Done or Failed
  without anyone reloading.
- AC-B7 If the build cannot be queued, the stop shows Failed naming the queue, never Processing
  forever, and no uploaded copy is left in storage.
- AC-B8 A file that is not a JPG, PNG, WebP or a video is refused before anything is stored, by
  name. More than 300 MB in one stop is refused.
- AC-B9 Uploaded copies are removed from storage once the build ends, done or failed.
- AC-B10 Stops are numbered in upload order; a stop with no name is called "Stop N".

## Walking through

- AC-W1 The detail page shows the current stop's panorama; dragging left turns the view right, and
  the picture is not mirrored.
- AC-W2 The view cannot turn or zoom past the edge of a partial panorama into black; a 360 stop
  turns all the way round.
- AC-W3 Previous / Next move between finished stops in order and are disabled at the ends.
- AC-W4 Arrow keys look around and +/- zoom when the viewer has focus.
- AC-W5 A walkthrough with no stops shows an empty state (heading + hint), with Add stop only in
  the header.

## Managing

- AC-M1 The list shows every walkthrough with stop count and status (Building N / Ready), newest
  first, searchable by name; New walkthrough opens a modal and lands on the new walkthrough.
- AC-M2 A walkthrough can be renamed from its page.
- AC-M3 Deleting a walkthrough or a stop asks nothing and runs as a deferred action with a
  countdown and Cancel; the stored panoramas go with it.
- AC-M4 A stop deleted while it is being built is left alone by the build.

## Access and scope

- AC-A1 `dealer_kit.page.view` may list and walk; `dealer_kit.page.edit` is needed to create,
  rename, add or delete. Without view, every route is 403.
- AC-A2 Another company's walkthrough, stop or panorama is 404, never 403.
- AC-A3 Usable at 375px and 1280px with no horizontal page scroll.
