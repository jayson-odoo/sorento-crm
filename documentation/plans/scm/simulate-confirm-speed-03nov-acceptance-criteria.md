# UAC: Simulate confirm speed

Plan: `PLAN-simulate-confirm-speed-03nov.md`.

- AC-1: A multi-line order that fails with a refused job (`SimulationWouldCommit`) and names no
  line is not probed line by line: the confirm runs once for it, `simulated_errors` is null, the
  error text is unchanged. A one-line order is still named. A 409 naming one line (no
  `failing_lines`) is still probed and named.
- AC-2: An order whose first 5 probed lines all fail with the same text stops probing after those
  5 runs and reports `simulated_errors` null.
- AC-3: A real line-level failure (one line fails alone) is still probed and named, as today.
- AC-4: Active-decision snapshots read twice in one session with no change return the same rows
  and the second read does not reload `line_snapshots`.
- AC-5: An in-place rewrite of an active decision's `line_snapshots`, a new active decision and
  a retired one are each seen by the next read in the same session (identical to a cold read).
- AC-6: The server log carries a per-order and a total simulate time.
