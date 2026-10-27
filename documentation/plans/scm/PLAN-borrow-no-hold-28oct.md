# PLAN: BORROW-NO-HOLD - a Borrow decision is a plan, not a stock hold

Status: Plan. Behaviour card filed as one crew-ask, waiting for owner answers before any code. Track: full
(size M, LEAD pattern: tester + coder + reviewer subagents). Base: main 71a43b3ba1 (carries #1919).

## Journey

Owner, 28 Oct ~00:20 MYT: "borrow shouldn't affect the planning also". This reverses the 27 Oct BOARD-NO-HOLD
Q3 answer ("Borrow as today, keeps holding"). #1919 (merged 3783f8c08b) made a confirmed Reserve a plan only:
it no longer holds stock in Stock Debt, the board strip, location stock, the ladder or the confirm floor, and in
the Stock Debt walk its line draws the planned bin at its own date (walk rule 7, a ROUTE). Borrow still holds
stock ahead of everyone and the lending order shows "lent to".

Goal: a confirmed Borrow becomes a planning choice only, like Reserve after #1919. Deciding and confirming on
the board must keep working exactly as today (owner's condition for #1919, kept here).

## Findings

Filled from the code map (file:line) in the behaviour card: `CARD-borrow-no-hold-28oct.md`.

## Shape of the change (after the owner answers)

Reuse #1919's one shared rule: `_hold_query` stops matching Borrow sources too, so every free / held reader
follows; Stock Debt `_holds` hands a Borrow to the walk as a route (`Hold(route=True)`), not a pin. No per-screen
copy.

## Red-first test list

After the owner answers.

## Coordination

STOCK-DEBT-DECOUPLE #1667 (delivered qty consumes Reserve/Borrow before Buy) is rebasing onto #1919. This lane
bases on main and merges main again after #1667 lands.
