# PLAN: Complaints "Assigned to" filter lists all staff

Status: in progress (small fix track: under 300 lines, no migration, no auth/RBAC change)
Lane: ASSIGNED-FILTER-ALL-STAFF. Owner ruling 12 Nov 2026: "the filter should just list all staff".

## Cause
- The filter's options come from `getUserLookup({ respond_synced: true, include_inactive: true })`
  (`ComplaintsList.tsx`), so staff without a successful Respond.io sync are never offered.
- The option value is `respond_user_id`; the backend filter (`ComplaintsService._build_list_query`)
  matches it verbatim against `Complaint.assigned_to`, which holds either a CRM user id or a
  Respond.io agent id (`_resolve_user_display_name` reads both).

## Fix
1. FE: options from the all-staff lookup (`include_inactive` kept, no `respond_synced`); option
   value = CRM user id. Same `SearchableMultiSelect`.
2. BE: each chosen person matches `Complaint.assigned_to` by their CRM id OR their Respond.io id
   (one lookup over `users`). A value that is a Respond.io id still works, so a filter saved by
   LIST-FILTER-MEMORY-4 before this change still applies. `__unassigned__` still ORs in.

## Reused
- `getUserLookup` (`services/userSelectService.ts`), `UserService.list_user_lookup`,
  `SearchableMultiSelect`, `multi_values`, the existing `_build_list_query` filter block.

## Tests
- pytest: a non-synced staff member's complaint is returned when filtering by their id; a
  synced one by CRM id and by Respond id; a person with none returns an empty list; Unassigned
  plus a person returns both.
- vitest: the filter options include a staff member without a Respond.io id.

## Not in scope (listed in the PR)
SLA lists (`ConversationSLATrackingList.tsx`, `EventLogTable.tsx`, `EventLogList.tsx`) also use
`respond_synced: true`, but their trackers key on Respond.io ids; not the same one-line cause.
