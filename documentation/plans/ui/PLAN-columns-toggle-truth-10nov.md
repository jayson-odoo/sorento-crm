# PLAN: Columns menu is the truth for every DataGrid list (COLUMNS-TOGGLE-TRUTH)

Status: in progress (small fix track, bug; no migration, no auth/RBAC)

## Problem

Owner, 10 Nov: on Products > All Products the Columns menu ("Toggle Columns") shows columns
ticked (Type, Variant Of, Variants, ...) that the grid does not render. Menu ticks and visible
columns disagree.

## Plan

1. Reproduce and locate the cause (file:line).
2. Fix at the shared level so the menu is derived from the same visibility state the grid renders.
3. Reconcile stale saved preferences (unknown/renamed keys).
4. Red-first vitest: menu state == rendered columns, including a saved preference with a stale key.
