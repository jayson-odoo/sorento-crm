# PLAN: DATE-FORMAT-UNIFY (every CRM date as dd/mm/yyyy)

Status: Plan (inventory in progress). Track: standard (wide mechanical diff, no migration, no auth change).

## Owner ask (4 Nov 2026, verbatim)
"all the dates need to use dd/mm/yyyy format like a standardized format across the system"

## Rule
- Date: `dd/mm/yyyy`, zero-padded, Malaysia time.
- Range: `dd/mm/yyyy - dd/mm/yyyy` (separator decided in the inventory ask).
- Date-time: `dd/mm/yyyy, h:mm am/pm`.
- Wire formats (ISO) unchanged.

## Steps
1. Inventory of every formatter (FE + BE text surfaces), counts per pattern, existing helpers.
2. One shared `formatDate` / `formatDateRange` / `formatDateTime`, red-first tests, guard test.
3. Replace call sites by module, one commit per batch.
4. Browser pass at 1280/375 on key screens.
