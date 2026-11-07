# UAC: price tag request, discontinued combo options stay selectable

Plan: `PLAN-pricetag-discontinued-pick-07nov.md`. Supersedes AC-C6 (disabled option and Approve block) in
`pricetag-combo-render-acceptance-criteria.md`.

- AC-1. In a choice-group picker on a price tag request line (single select, "Not sure, any of N"),
  a discontinued option is enabled and can be picked; its second line still reads "Discontinued".
- AC-2. In a k >= 2 group (multi select, "Pick k"), a discontinued option is enabled and can be
  picked; its badge still reads "Discontinued".
- AC-3. A line holding a discontinued pick in a choice group shows no "<code> is discontinued."
  problem on Approve.
- AC-4. A line holding a discontinued FIXED part does not stop Approve either; the part row shows
  the "Discontinued" badge as a warning (owner ruling 7 Nov, 1a). A discontinued Upgrade option is
  pickable and does not stop Approve (ruling 2a).
- AC-5. Saving a request whose line part picks a discontinued product succeeds (backend), and the
  pick reads back on the line.
- AC-6. Hand test: SRTKS7061-BL, template KS_1TAP_SP, pick SRTWT5831-BL in "Not sure, any of 5";
  the pick shows on the line and the request saves.
- AC-7. A line whose pre-filled promotion covers only an option NOT picked saves (no 422): the
  promotion is stored as none, no price on the tag changes, and the form says "Promotion removed
  from line i: it does not cover the option picked." A promotion that covers nothing in the line's
  package, or that this viewer cannot see, is still refused with PROMOTION_NOT_AVAILABLE.
