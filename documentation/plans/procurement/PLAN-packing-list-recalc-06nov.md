# PLAN: packing list status recompute on input change (PACKING-LIST-RECALC)

Status: scouting (small fix track candidate, no migration expected)

## Problem
Prod: SPO container number arrived via the AutoCount pull, but the packing list's line
links and received status only updated when someone opened the packing list page,
because `GET /procurement/packing-lists/{id}` calls `refresh_shipment_line_statuses`
(`app/api/v1/procurement/packing_lists.py:274`), a recompute-on-read.

## Plan
To be filled after the scout (see crew-note on the PR).
