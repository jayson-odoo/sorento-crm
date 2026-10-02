# PLAN: several attachment types in one ask + human labels in the attachment picker

Status: Plan (behaviour card being filed; no code yet). Track: to be named once the diff is sized.
Lane: ATTACHMENT-MULTI (owner, 2 Oct 2026).

## Owner ask

1. A contact cannot get several attachment types at once (e.g. photo AND technical drawing in
   one ask). Support multiple types in one ask / pick.
2. The attachment picker shows the raw key `product_attachment`. No snake_case in any
   customer-facing reply; use human labels ("Photo", "Technical drawing"). Sweep other
   replies / pickers for leaked snake_case keys and list them.

Coordination: ACCESS-MODEL adds a per-contact switch for attachment stamping.

(Measured facts, rules and decisions follow once the code is read.)
