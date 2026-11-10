# UAC: Town v2 (hover, lightbox, tilt camera, incoming port)

Plan: `PLAN-town-v2-10nov.md`. Each line is checked by a test (T) or the browser pass (B).

1. (T,B) Pointer over a shop shows a tooltip with its name (or "Dealer" when redacted) and today's
   amount / invoice count, without any click; leaving it hides the tooltip.
2. (T,B) Clicking a shop, the "!" label, the depot, the office, the scoreboard, the port, or any stat
   card opens a centred `role="dialog"` lightbox; no `Sheet` is rendered anywhere on the Town page.
3. (T,B) Esc, the close button and a click on the dimmed backdrop each close the lightbox.
4. (T) On a coarse pointer, the first tap shows the tooltip only; a second tap on the same object opens
   the lightbox.
5. (T,B) Vertical drag changes the camera elevation, clamped to 20-80 degrees; horizontal drag still turns.
6. (T,B) Wheel / pinch zoom is clamped to 0.7x-2.2x; "Reset view" restores default yaw, tilt and zoom.
7. (T) The snapshot carries `incoming` with exact `on_water`, `arriving_soon`, `late`, `total`,
   `next_eta` and at most 30 shipment rows (ETA ascending, no-ETA last); drafts and fully received
   shipments never count; another company's shipments never count.
8. (T) `redact()` and `strip_names()` drop `supplier` from every incoming row; counts stay.
9. (T,B) The port lightbox lists the rows (Late badge on late rows), "+N more" past 30, an empty state
   "Nothing on the way" at zero, and one "Open packing lists" button.
10. (T) A snapshot without `incoming` renders no port and no sixth card, and does not crash.
11. (B) Usable at 375 px and 1280 px; idle scene draws no frames (render on demand kept).
