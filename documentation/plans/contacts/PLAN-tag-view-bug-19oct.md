# PLAN: contact tag view shows phantom "Removed" values (TAG-VIEW-BUG)

Status: in progress, reviewer READY on a567a105a5, browser pass next. Track: small fix (FE only, under 100 lines, no migration, no auth change)

## Owner report (19 Oct)

"I faced problem when viewing Dealer" (Users & Access > Access > Contact Tags). Dealer is the tag
with the big settings object (53 leaves: media, 10 agents, chatbot, agent_fields, 8 portal forms,
20 field reveals, market segments, 6 attachment types, outbound, requires registered project).

## Reproduction

The owner's Dealer settings JSON rendered by `ContactTagSettings` (view mode) with a catalog that
names every id (all 10 agents, 6 attachment types, brands and companies exist on dev,
`sorento_cagent_stack`, read-only query) reads, under Attachment types:

    Removed Removed Removed Removed Removed  <6 real attachment type names>

and React logs "Encountered two children with the same key, `Removed`" five times.

## Root cause

1. `Pills` keys each badge by its LABEL
   (`sorento_crm_frontend/app/(protected)/user-management/contact-tags/components/ContactTagSettings.tsx:225`).
2. `labelOf` answers "Removed" for any id the catalog does not hold, including while the catalog is
   still loading (`ContactTagSettings.tsx:149-150`); the catalog query starts only when the settings
   card mounts, so the first view of a tag always renders before it arrives.
3. So a list of N ids first renders N badges all keyed `Removed`. When the names arrive, React's
   keyed reconcile maps only ONE of the duplicate-key fibers and never deletes the other N-1, so
   they stay on screen next to the N real names until the page unmounts.

Why Dealer: it is the tag with the longest id list (6 attachment types) and the first one opened,
so the catalog was not cached yet. Any tag opened first with 2+ ids in a list group shows the same
thing (Sorento Dealer: 4 brands -> 3 phantoms; Sorento Dealer - Business Owner: 3 access types ->
2 phantoms); a tag opened after the catalog is cached looks right.

## Fix

- `Pills` keys badges by position (read-only, stateless badges; two removed ids both read Removed).
- View mode: a set group whose names come from the catalog shows a loading placeholder until the
  catalog arrives, never "Removed"; if the catalog request fails, the group shows the error
  message instead (the page keeps rendering every other group).
- Edit mode is unchanged (its pickers key by value already, `SearchableMultiSelect.tsx:359`).

## Tests (red first)

`ContactTagSettings.catalogNames.test.tsx`:
1. a 6-id list shows each name exactly once after the names load, no "Removed";
2. while the names load, no "Removed" label shows;
3. a failed catalog load shows its message in the group, not "Removed";
4. two ids the catalog no longer holds read "Removed" twice, no duplicate-key warning.

## Non-goals

- A malformed settings value (wrong JSON type) crashing the card: every write goes through
  `validate_settings` (`sorento_crm_backend/app/services/contact_tag_settings.py:224`), so no such
  row can exist today. Trigger to revisit: any write path that bypasses the API.
