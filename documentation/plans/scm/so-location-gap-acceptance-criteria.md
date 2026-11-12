# UAC: A location move made before detection is part of the next change (SO-LOCATION-GAP)

Plan: `PLAN-so-location-gap-09nov.md`.

Sequence for every criterion: a line confirmed at location A (Buy, ORDER raised at A); AutoCount
later moved the line to B without a change row (before #2221); now a date change is detected.

- G1. The "What changed" lightbox shows Location was A now B, beside the Date row.
- G2. The Confirm Review split shows LOCATION A and NEW LOCATION B for that line.
- G3. The purchasing email line reads at B with REMARK "<date word>, NEW LOCATION (was A)"; its
  table and Excel attachment print LOCATION A and NEW LOCATION B.
- G4. The line's OI row ends the Confirm the same way it does for a move #2221 detected.
- G5. A line moved the same way that gets no change of its own is not flagged (no row, no column,
  no email line).
- G6. A line with no confirmed decision whose ORDER rows sit at A reads the same as G1-G2 when it
  gets a change.
