# UAC - Listing view memory (sticky sort + sticky filter)

**Status:** Implemented on `fm/listing-view-memory` (pilot: Stock Inquiries). Browser evidence run pending - no free stack slot at hand-off; AC-E4 is covered by a listing-level vitest instead of a new Playwright spec (repo standing order).
**Classification:** CORE (`public` schema, no new table)
**Plan:** `documentation/plans/listings/PLAN-listing-view-memory.md`
**Pilot listing:** Procurement Management -> Stock Inquiries

---

## Journey

**Actor.** An internal staff member on a list page. Three real shapes of the same person:
a purchasing officer, a project sales manager, and an admin. They arrive by clicking the
sidebar into the listing (Procurement Management -> Stock Inquiries).

**What the system already knows about them.** Who they are, which listing they opened, and
the sort order and filter they left that listing in the last time they used it. None of it
is asked for.

**The steps, in order.**

1. They click Stock Inquiries in the sidebar. The grid renders **already sorted and filtered
   the way they left it**. A purchasing officer lands on Pending Purchasing at the top; a
   project sales manager lands on Pending Project Sales. **Decisions required: zero.**
2. Above the grid a chip reads `Pending purchasing` with a clear affordance next to it. They
   see in one glance why the list is short. **Decisions available: one. Required: zero.**
3. They re-sort by Assigned To, or tick another status. It sticks silently - no Save button,
   no name prompt, no dialog. **Decisions required: zero.**
4. If they want the unfiltered list they click the clear affordance. The listing returns to
   its shipped default sort and no filter.

**What they hold at the end.** A listing that opens on their own work queue every time,
without them ever configuring anything.

**Who else is told.** Nobody. This is a purely personal preference with no admin surface and
no team visibility.

**Derived, never asked.** The view is derived entirely from the user's last interaction with
the listing. There is no "create a view" wizard, no naming step, and no settings screen. The
one thing we surface is the *consequence* (the active filter chip), because an invisible
filter is indistinguishable from missing data.

---

## Out of scope (explicitly)

| Not building | Why |
|---|---|
| Named / multiple segments with a picker | Journey needs exactly one view per person. Revisit only if a single user must toggle between saved views. |
| Role-owned or admin-set defaults | Decided: personal only. |
| Persisting page number | A remembered page 7 on a shrunken list renders an empty grid. |
| Persisting search text | Indistinguishable from a broken list on arrival. |
| Rollout beyond Stock Inquiries | Pilot first. Other listings opt in later, one line each. |

---

## Acceptance criteria

Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` end-to-end, `[T]` test-only.
Every AC traces to a journey step.

### Group A - Persistence contract `[BE]`

**AC-A1** `[BE]` **The stored config accepts sort and filter.**
Given a signed-in user,
When they `PUT /api/v1/list-query/column-config/{listing_key}` with a body containing
`sorting: [{"id": "status", "desc": false}]` and `filters: {"statuses": ["pending_purchasing"]}`,
Then the response `config` contains both keys with those exact values,
And a subsequent `GET` of the same `listing_key` returns them unchanged.
*(Traces to: step 1. Today both keys are silently dropped - `UserListColumnConfigPayload` does
not declare them, so `model_dump` discards them.)*

**AC-A2** `[BE]` **A partial write merges, it does not replace.**
Given a stored config holding `columnOrder`, `columnVisibility`, `columnSizing`, `sorting` and `filters`,
When a `PUT` arrives carrying only the three column keys,
Then `sorting` and `filters` survive unchanged in the stored row,
And when a `PUT` arrives carrying only `sorting`, the three column keys survive unchanged.
*(Traces to: step 3. Two independent writers share one row - see PLAN "Two writers, one row".)*

**AC-A3** `[BE]` **An explicit null clears a key.**
Given a stored config with `filters` set,
When a `PUT` arrives with `filters: null` explicitly present in the body,
Then `filters` is removed from the stored config,
And the other keys are untouched.
*(Traces to: step 4. Distinguishes "clear my filter" from "I am not writing that key".)*

**AC-A4** `[BE]` **Reset still clears everything.**
Given a stored config with all five keys,
When the user `DELETE`s the config,
Then a subsequent `GET` returns `config: null`.

**AC-A5** `[BE]` **The permission gate is unchanged.**
Given a user without view permission on `listing_key`,
When they `PUT` a body containing `sorting` or `filters`,
Then the response is `403` and nothing is stored.

**AC-A6** `[BE]` **Malformed sort is rejected, not stored.**
Given a signed-in user,
When they `PUT` with `sorting` that is not a list of `{id: string, desc: bool}` objects,
Then the response is a `422` validation error and no row is written.

### Group B - Applying the remembered view `[FE]`

**AC-B1** `[FE]` **A returning user lands on their own view.**
Given a user whose stored config for the Stock Inquiries listing holds
`sorting: [{id: "status", desc: false}]` and `filters: {statuses: ["pending_purchasing"]}`,
When they navigate to the listing from the sidebar,
Then the grid is sorted by Status ascending,
And the status filter shows Pending Purchasing selected,
And the rows shown are only Pending Purchasing rows.
*(Traces to: step 1.)*

**AC-B2** `[FE]` **A first-time user gets the shipped defaults.**
Given a user with no stored config for the listing,
When they open it,
Then sorting is the listing's shipped default (`created_at` descending),
And no status filter is applied,
And no request is made that would write a config before the user changes anything.

**AC-B3** `[FE]` **The list is fetched once, with the remembered view already applied.**
Given a user with a stored config,
When they open the listing,
Then the data query does not fire until preferences have resolved,
And exactly one list request is issued,
And it carries the remembered sort and filter.
*(Traces to: step 1. Without the gate the grid fetches with defaults, then refetches - a
visible flash plus a wasted round trip. `useListingColumnPreferences` already returns
`isLoading` for exactly this.)*

**AC-B4** `[FE]` **A stale filter shape is discarded, not applied.**
Given a stored config whose `filters` blob does not match the listing's current
`filtersVersion`,
When the user opens the listing,
Then the stored filter is ignored and the shipped default is used,
And the listing renders without error,
And the stale blob is overwritten the next time the user changes a filter.
*(Traces to: step 1. The blob is opaque to the shared layer, so the page owns its shape and
must survive its own past versions.)*

**AC-B5** `[FE]` **Changing sort persists it.**
Given a user on the listing,
When they sort by a different column,
Then the new sort is written to their config after the debounce window,
And re-entering the listing shows that sort.
*(Traces to: step 3.)*

**AC-B6** `[FE]` **Changing the filter persists it.**
Given a user on the listing,
When they tick or untick a status,
Then the new filter is written to their config after the debounce window,
And re-entering the listing shows that filter.
*(Traces to: step 3.)*

**AC-B7** `[FE]` **A saved view survives leaving and returning within the same session.**
Given a user changes the sort or filter, then navigates to another page and back to the
listing without a full reload,
Then the listing shows the value they just set, not the value it held when the page first
loaded.
*(Traces to: step 3. The config query uses `staleTime: Infinity` and the write mutation
neither invalidates nor seeds the cache, so today the stale pre-save value is re-applied on
re-mount - see PLAN 3.3.)*

**AC-B8** `[FE]` **Column preferences still work.**
Given a user who reorders, hides and resizes columns and also sets a sort and filter,
When they leave and return,
Then all five survive together.
*(Regression guard for AC-A2 seen from the UI.)*

### Group C - Making the filter visible `[FE]`

**AC-C1** `[FE]` **An active filter is stated on screen.**
Given a filter is applied on arrival,
When the listing renders,
Then a chip naming the active filter in human-readable terms is visible above the grid
without opening the filter menu,
And it is rendered by the shared `DataGridListToolbar`, not hand-rolled in the page.
*(Traces to: step 2. A silent sticky filter reads as data loss.)*

**AC-C2** `[FE]` **The chip clears the filter.**
Given the chip is shown,
When the user activates its clear affordance,
Then the filter is removed, the grid refetches unfiltered,
And the cleared state is persisted (AC-A3), so returning shows no filter.
*(Traces to: step 4.)*

**AC-C3** `[FE]` **No chip when nothing is filtered.**
Given no filter is active,
Then no chip is rendered and the toolbar layout is unchanged from today.

**AC-C4** `[FE]` **The chip is usable at 375px.**
Given a 375px viewport with a filter active,
Then the chip and its clear affordance are visible and tappable,
And the toolbar does not clip or overflow horizontally.

### Group D - Not persisted `[FE]`

**AC-D1** `[FE]` Given a user on page 3 of the listing, when they leave and return, then they
land on page 1.

**AC-D2** `[FE]` Given a user with text in the search box, when they leave and return, then
the search box is empty and the full (filtered, sorted) set is shown.

### Group E - Tests `[T]`

**AC-E1** `[T]` pytest covers AC-A1 through AC-A6, including the merge semantics from both
write directions and the 403 and 422 paths.

**AC-E2** `[T]` vitest covers the view-preferences hook: applies on mount, gates loading,
discards a version-mismatched blob, debounce-writes on change.

**AC-E3** `[T]` vitest covers the toolbar chip: renders when active, absent when not, clear
fires the handler.

**AC-E4** `[E2E]` One Playwright spec: sidebar click into Stock Inquiries -> set a status
filter and a sort -> reload -> assert both are still applied and the chip is shown -> clear
via the chip -> reload -> assert clean. Asserts the `/api/v1/list-query/column-config/*`
calls actually fire.

### Group F - Definition of Done `[E2E]`

**AC-F1** No mock left behind. The hook talks to the real endpoint.

**AC-F2** Verified by real sidebar clicks against live data at **375px and 1280px**.

**AC-F3** No backfill needed and none written: absent keys read as "no preference" and fall
back to shipped defaults (AC-B2). Stated here so the DoD backfill gate is consciously
answered, not skipped.

**AC-F4** No new permission introduced; the existing `_can_view_listing_key` gate covers the
new keys (AC-A5), so no grant sweep is required.
