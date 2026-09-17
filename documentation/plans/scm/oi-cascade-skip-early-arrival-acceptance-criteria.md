# UAC - Order inquiries: cascade skips a document arriving outside the lead-time window

Plan: `PLAN-oi-cascade-skip-early-arrival.md`. Dates below are the seed's; "lead" is the
product's stated `standard_lead_time_days` unless the criterion says default.

## S1 - the predicate

* AC-EA-1 `arrives_outside_window(expected, delivery, lead)` is True when `expected == delivery - lead days`, False when `expected == delivery - lead + 1 day`, False when `expected > delivery`, False when either date is None.
* AC-EA-2 The worklist's `_attach_link_suggestions` calls `arrives_outside_window`; the existing suggestion tests (`reallocate` on a link a full lead time early, `unlink` with no candidate, `None` inside the window or received) pass unchanged.

## S2 - the cascade

* AC-EA-3 Row delivery 2027-01-15, lead 30, the only open PO line for the product promised 2026-10-01: `auto_place_for_products` writes no link, `placed_rows == 0`, the row stays `raised`, and the worklist row carries no `suggestion` (there is no link to carry one).
* AC-EA-4 Same row, PO line promised 2026-12-20 (inside the window): linked as before, `placed_rows == 1`.
* AC-EA-5 Product with no stated and no measured lead time: default 90. PO promised 2026-10-17 (= delivery - 90) is refused; promised 2026-10-18 is linked.
* AC-EA-6 An early PO line THIS row's own SO claims (`scm.order_link_claim`) is linked regardless of the window.
* AC-EA-7 An early PO line whose document number the row cites is linked regardless of the window.
* AC-EA-8 Two candidates, one early and one inside the window: only the inside one is taken. When the inside one alone cannot cover the row's need in full, nothing is linked (the early line does not count toward cover) and the row stays `raised`.
* AC-EA-9 An SPO allocation candidate promised a full lead time early is refused the same way as a PO line.
* AC-EA-10 Re-deal: a row already holding a cascade draft on an early line, walked again with `redeal_drafts=True` and no better candidate, keeps that draft (no unlink, no note appended).
* AC-EA-11 Row due beyond the link horizon is still counted `after_horizon` first, never reaching the window check (existing horizon tests unchanged).
* AC-EA-12 `po_candidates_for_row` (Link dialog) still lists the early line; `place_on_po_allocations` by hand still links it, and that link then shows the `reallocate` / `unlink` suggestion on the worklist.

## Browser (end of lane, agent-browser on the lane stack :3082/:8082)

* AC-EA-13 Order inquiries worklist, a seeded Jan 2027 row whose only candidate is an early PO: Auto link all leaves it Not linked and the toast reads `1 skipped`; the PO cell shows the muted dash, no pill.
