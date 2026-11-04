# UAC: NO-AC-MOVED-WARNING

Plan: `PLAN-no-ac-moved-warning-3nov.md`.

- N1. On the guided Confirm's Review split, a line whose saved decision differs from what a
  pending AutoCount change suggests shows no "AutoCount moved this line" row, no Keep button and
  no Take suggestion button.
- N2. Next stays on for that page, and Confirm posts the saved decision unchanged.
- N3. Nothing else in the Confirm flow (board pill, Confirm step, toast) mentions the change's
  suggestion against a saved decision.
- N4. Everything else #2091 and #2116 do still holds: their tests stay green.
