# UAC: Town v2 (hover, lightbox, tilt camera, incoming port)

Plan: `PLAN-town-v2-10nov.md`. Each line is checked by a test (T) or the browser pass (B).

1. (T,B) Pointer over a shop shows a tooltip with its name (or "Dealer" when redacted) and today's
   amount / invoice count, without any click; leaving it hides the tooltip.
2. (T,B) Clicking a shop, the "!" label, the depot, the office, the scoreboard, the port, or any stat
   card opens a centred `role="dialog"` lightbox; no `Sheet` is rendered anywhere on the Town page.
3. (T,B) Esc, the close button and a click on the dimmed backdrop each close the lightbox.
4. (T) On touch, a tap on an object opens its lightbox straight away; no tooltip is shown on touch.
5. (T,B) Vertical drag changes the camera elevation, clamped to 20-80 degrees; horizontal drag still turns.
6. (T,B) Wheel / pinch zoom is clamped to 0.7x-2.2x; "Reset view" restores default yaw, tilt and zoom.
7. (T) The snapshot carries `incoming` with exact `incoming` (ETA today or later, or none) and `late`
   (ETA before today) counts, `next_eta`, and at most 30 incoming rows (ETA ascending, no ETA last) plus
   at most 30 late rows (most recently late first); `eta_delay_date` overrides the ETA; drafts and fully
   received shipments never count; another company's shipments never count.
8. (T) `redact()` and `strip_names()` drop `supplier` from every incoming row; counts stay.
9. (T,B) The port lightbox shows an Incoming section and a Late section, each "+N more" past 30, an empty
   state "Nothing on the way" at zero, and one "Open packing lists" button; supplier hidden when redacted.
10. (T) A snapshot without `incoming` renders no port and no sixth card, and does not crash.
11. (B) Usable at 375 px and 1280 px; with motion paused or reduced, an idle scene draws no frames (render on demand kept).
12. (T,B) Motion: lorries move only while motion is on; reduced motion or Pause draws a still town and the
   loop stops; a hidden tab advances nothing.
13. (T) A poll whose snapshot gives a shop more `today_docs` than the previous one yields one receipt pop
   for that shop (`newSales(prev, next)`), none on the first load.
14. (T) `GET /api/v1/town/snapshot` answers 403 to a staff user without `dashboards.town.view`, wallboard
   mode included; 200 to admin, superadmin and any role granted the permission.
15. (T) The Town menu item is gated on `dashboards.town.view`; `/town` renders Access denied without it.
16. (T) Migration `town_0001_view_perm` seeds the permission and grants it to `admin` and `superadmin` only.
