# UAC: Borrow lists locations with 0 free stock (BORROW-ZERO-FREE, 22 Oct 2026)

Plan: `PLAN-borrow-zero-free-22oct.md`.

- AC-1: On a line inside its reserve window, the Borrow list (board line panel, per-order sheet
  "Add a borrow" dialog) lists every location outside the line's Reserve pool that holds a stock
  row for the item, including those with 0 free; such a row shows 0 free and its signed
  availability.
- AC-2: The line's own location is still listed (BORROW-OWN-LOC), last, never recommended unless
  alone.
- AC-3: A location with free stock still ranks ahead of a 0-free one; exactly one row is
  recommended.
- AC-4: The Decide control's "Borrow from another location" dropdown lists 0-free locations.
- AC-5: Picking a 0-free location in Decide saves the line as a Borrow from that location for the
  whole open quantity, with the "only 0 free at X" warning, and Confirm records it short rather
  than refusing. It is not skipped.
- AC-6: The trail note "borrowing is possible from ..." still names only places with something
  free.
- AC-7: Reserve "Add location" is unchanged.
- AC-8: A line beyond its reserve window is unchanged until the owner rules on the gate.
