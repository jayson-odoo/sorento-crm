# ADR: Product-Wide UX and Architecture Standards

**Status:** Accepted  
**Last updated:** 2026-07-14

## Overview
This ADR defines mandatory standards for CRUD UX, delete/archive semantics, detail page behavior, and engineering layering across the Sorento CRM product. All new and refactored features MUST adhere to these standards.

---

## 1. CRUD Interaction Rules

### Default Pattern
- **List page:** Shows entities in a DataGrid/table with search, filters, pagination, and an "Add" or "Create" button.
- **Create:** Modal dialog by default. Opens from list page.
- **Edit:** Modal dialog by default. Triggered from list row actions or detail page.
- **View:** Dedicated detail page at `/{module}/{id}`. Read-only overview with links to edit.
- **Delete:** Always via confirmation dialog (never inline or automatic).

### Modal vs Dedicated Page
| Use case | Pattern | Rationale |
|----------|---------|-----------|
| Simple entities (e.g. roles, teams, units) | Modal create/edit | Fast, keeps context. |
| Complex forms (many tabs, nested entities) | Dedicated create/edit page | Avoid cramped modals. |
| Default | Modal | Per product decision. Use dedicated pages only when ADR-exempt. |

### Button Placement
- List page: "Add" or "Create {entity}" in toolbar (top right).
- Detail page: "Edit" and "Delete" in header actions.
- Modal footer: "Cancel" (outline) left, "Save" or "Create" (primary) right.

---

## 1b. Form Controls - Dropdowns MUST be searchable

**Doctrine:** every dropdown-select in the product MUST be **searchable** and MUST use the standard
component. A "dropdown-select" = click a field → a popover opens showing an option set → filter by
typing in the popover's search box → pick one (or many).

- **Standard components (the only allowed dropdown-selects):**
  `@/components/common/SearchableSelect` (single, `value: string`) and
  `@/components/common/SearchableMultiSelect` (multi, `value: string[]`). Both are one-component /
  two-mode: pass `options` for a client-filtered static list, or `fetchOptions(query)` for a
  debounced server search (async also passes `selectedOption`/`selectedOptions` so the trigger label
  survives when the current value isn't in the fetched page).
- **Search is always shown - no option-count threshold.** A 2-option Active/Inactive dropdown is
  searchable too. Consistency over per-field micro-optimisation.
- **Banned (code-review hard-fail + ESLint `error`):** Radix `@/components/ui/select`, raw native
  `<select>`, and hand-rolled `CommandInput` pickers. `@/components/ui/select` is being deleted once
  migration completes (`PLAN-searchable-dropdown-standard`).
- **Trigger appearance:** the standard trigger shares `selectTriggerVariants`
  (`@/components/common/select-trigger-variants`) with the old Radix trigger, so a migrated dropdown
  is pixel-identical to the Select it replaced (`size` = `sm | md | lg`, default `md`).
- **Clearing:** optional fields opt into a clear affordance via `clearable`; required fields omit it.
  There is no re-click-to-deselect on single-select.
- **Out of scope (NOT a dropdown-select, not banned):** the free-text type-ahead pattern
  (`AsyncCombobox` / `AsyncMultiCombobox`) where the user types into the field itself and suggestions
  appear (portal `SubmissionForm`), and genuine Cmd+K command palettes.

---

## 1c. Form Controls - a date RANGE is ONE control

**Doctrine:** any "X from / X to" pair MUST render a single range control,
`@/components/ui/date-range-picker` (`DateRangePicker`). Two date inputs side by side are
**banned** for a value that is one range.

- **Why.** Two fields make the user hold the relationship in their head: nothing stops "to"
  landing before "from", the two labels have to be read separately to learn they describe one
  fact, and at phone width they wrap apart so the pair stops looking like a pair. A range
  picker enforces the order by construction - an end cannot be picked before a start.
- **Label the range, not the ends.** "Expected delivery", never "Expected delivery from" plus
  "Expected delivery to".
- **Both ends stay optional** where the domain allows a half-known range (a developer often
  gives the start of a delivery window months before the end). The control renders `01/05/2027 - ?`
  rather than hiding the half it has.
- **Wire format is unchanged:** two `YYYY-MM-DD` fields on the API. `onChange` emits both ends
  together because they are one fact; `parseIsoDate` / `toIsoDate` are exported for callers.
- Filtering a list BY a date range is the same rule.

---

## 1d. Lists - the row is the way in, and status is a pill

**Doctrine, applies to every list in the product:**

- **No "Open" / "View" action column.** Clicking the ROW opens the record (`onRowClick` on the
  shared `DataGrid`). A column whose only job is to repeat what the row already does spends a
  column on nothing.
- **A status-like value renders as a status pill** (`@/lib/status-pill`), never as an `outline`
  badge. An outlined box containing a verb-shaped word ("Open") reads as a BUTTON - and once one
  cell looks clickable, the reader stops trusting which parts of the row are actions. Map new
  vocabularies onto the shared palette's existing keys rather than inventing colours; an unknown
  key silently falls back to grey, which is how the miss hides.
- **Timestamps are ABSOLUTE, never relative.** "yesterday" and "3 days ago" cannot be compared
  between two rows, cannot be quoted to anybody, and change meaning depending on when the page
  was loaded - a list left open overnight goes on claiming "today" about yesterday. Use
  `describeLastActivity`.
- **A total belongs IN the table, under the column it sums.** Declare `footer` on the column
  definition and the shared `DataGrid` renders a `<tfoot>` row aligned to it (both the draggable
  and non-draggable branches). A total parked beside the toolbar - "1 PO, RM 1,810,640.62" -
  competes with the buttons and never says WHICH column it totals; under its own column it needs
  no caption at all. Sum from `table.getCoreRowModel().rows` so a search narrows the total with
  the list.
- **Row counts come from the standard pagination bar, always shown.** "1 - 1 of 1", a page picker
  and a rows-per-page selector, exactly as the user list has them. Never write a sentence like
  "1 PO on this project", and never hide the bar because the list fits on one page: a short list
  that drops its footer reads as a different component from the long one.

---

## 1d-bis. A HISTORY is a timeline, not a grid

**Doctrine:** activity feeds and audit trails render `@/components/common/EventTimeline`.
Everything else that lists rows renders a `DataGrid`. This is the only exception to 1d, and
the line between them is what to check first when adding a surface.

- **Records** (quotations, POs, stakeholders, schedules, documents) are a GRID. The reader
  scans one column, sorts it, compares two rows, clicks one to open it.
- **Events** (activity, audit, status history) are a TIMELINE. The client's reference points
  were Lazada / Shopee / Lalamove parcel tracking and Google Sheets version history: "a
  timeline that explains what happens at what time". Nobody sorts parcel tracking by courier.
  What a history is read for is the SEQUENCE and the gaps in it, and a rail with a dot per
  event makes "then, three days later" visible at a glance. A table of timestamps hides it.
- **Shape:** newest first; grouped under a date heading so the day is stated once instead of
  per row; the time on the right of each step; the rail continuous between dots so it reads as
  one thread; the newest event marked as the live step. An avatar may replace the dot for a
  human post, which is what Sheets history does.
- **Times are absolute here too** (1d). A feed left open overnight must not keep claiming
  "3h ago", and two entries cannot be compared when both say "yesterday".
- An undated event is still shown, dated honestly, never dropped: dropping it makes the record
  read as though the thing never happened.

---

## 1e. Empty values and helper text

- **An unknown value is `-`.** Not "Not recorded", not "Not set", not "None". A card of mostly
  empty fields reads as prose when each blank is a sentence; `-` keeps it a table of facts.
- **An empty COLLECTION is also `-`.** "No collaborators", "No open requests", "None yet" are
  the same absence dressed as a sentence, and they cost a line each in a panel whose job is to
  be skimmed. Zero rows renders `-`.
- **What stays in words is an answer that names a different PATH or STATE, not an absence.**
  "Registered directly, with no lead before it" says this project never had a lead, which is a
  fact about how it began; "No source yet" is an allocation's real state. Test: could the value
  ever become known later? If yes it is an absence, so `-`. If the answer is itself the record
  of what happened, keep the words.
- **Do not explain the feature inside the form.** Helper text under a field is for a CONSTRAINT
  the user cannot infer ("Codes must be unique per company"), never for teaching what the field
  is for or what the system will do with it. Explanations belong in the user guide. This is the
  existing cursor rule ("no feature explanations inside the UI itself") applied to field hints.
- **Do not title a fact inside a card.** One more `Fact` in the same grid beats a bordered
  sub-section with its own heading and a sentence. (Promoting a fact to a top-level SECTION is a
  different decision, governed by 1f: it is warranted when people come to the page asking for
  that one thing.)

---

## 1f. Detail pages - group facts into named sections

**Doctrine:** a detail page is a set of titled sections, each holding facts that are read
together. One card listing every column the entity has is banned.

- **Why.** In an undifferentiated grid of fifteen facts, finding any one of them means reading
  all of them, and there is no signal about which belong together. The client's words against
  exactly that layout: "too many information here, too many words". Sections give the eye a
  place to land, and each heading answers "what is this group for" once instead of per field.
- **Group by the question, not by the table.** "The development", "Value and timing",
  "Consultants" are groups a salesperson thinks in. `project_profiles` versus `projects` is not
  a grouping the reader can see or cares about, so it must not shape the page.
- **A question people ask directly earns its own section.** "Which lead did this come from" was
  one `Fact` labelled "Source" at the bottom of a long grid, and it was missed - it is now a
  section of its own. The test is whether someone would open the record specifically to answer
  it.
- **Do not repeat a fact across sections.** Owner lives in Access; it is not also a registration
  fact. Two copies drift the moment one of them gains a link or a badge.
- Sections still follow section 3: **every one renders even when empty**, with `-` per 1e.

---

## 2. Delete and Archive Semantics

### Delete Policy
- **Delete is always hard delete** (permanent removal from the database).
- **Confirmation required:** User MUST confirm in a dialog before delete executes.
- **No soft delete under the name "delete":** Do not use `is_deleted`, `deleted_at`, or similar for the primary delete action.

### Archive Policy
- If historical retention is required, implement an explicit **Archive** action (separate from Delete).
- Archive = mark as archived / inactive; data remains queryable for reporting.
- Archive UI: Optional "Archive" button with its own confirmation; archived items appear in a filter or separate view.

### Confirmation Dialog Requirements
- Title: "Delete {entity name}?" or "Confirm delete"
- Description: Explain consequence (e.g. "This action cannot be undone.")
- Buttons: "Cancel" (outline), "Delete" (destructive)
- No pre-checked "I understand" unless risk is exceptionally high

---

## 3. View and Empty-State Rules

### Detail Page Structure
- **Always render all sections** relevant to the entity, regardless of whether data exists.
- Do NOT hide entire sections when empty (e.g. "Team Assignments" must always appear on Access Agent detail).
- **Detail pages carry prev/next record navigation** using `components/common/RecordNavigation`.
  Reviewing a list of records one at a time is the normal case, and forcing a return to the list
  between each is what makes a screen feel half-built. See `user-management/users/[id]` and
  `order-management/customers` for the established usage.

### View and Edit must share one layout
The read view and the edit view of the same record MUST present the same structure: the same tabs
in the same order, and the same fields in the same order within each tab. Editing swaps a
read-only value for an input **in place**; nothing moves, appears, or disappears.

The read view is what teaches a user where things are. If Edit rearranges them, every edit begins
with the user re-finding the field they came to change, and a value they could see a moment ago
but now cannot reads as data loss.

- Group a record's distinct concerns (identity vs configuration, say) into **tabs once**, and use
  that same tab set on both views rather than a long scroll on one and tabs on the other.
- **Read-only metadata** (Created, Last Updated, ids) belongs in the page header or a meta strip,
  **never inside a tab body** - it has no edit counterpart, so putting it in a tab guarantees the
  two views differ.
- Keep field help to a short hint at most. Multi-sentence explanation belongs in the user guide,
  per the existing "no feature explanations inside the UI" rule.

### Empty States
- Each section with optional data MUST have an explicit empty state.
- Empty state should:
  - Explain why it's empty (e.g. "No team assignments yet")
  - Provide a clear next step (e.g. "Edit agent to add assignments" or "Add assignment" button)
- Use consistent copy and styling across modules.

---

## 4. Frontend Service and Hook Layering

### Layer Structure
```
UI Components
    ↓
Hooks (useXxxMutations, useXxxQuery)
    ↓
Feature Services (xxxService.ts)
    ↓
Shared API Client (lib/api-client, apiFetch)
    ↓
Backend API
```

### Rules
- **No duplication:** Common patterns (DataGrid params, error extraction, user/team selects) live in shared modules.
- **Single responsibility:** Each service handles one domain; shared primitives (e.g. `getUsersSelect`, `getTeams`) live in a central service.
- **Consistent error handling:** Use shared `extractApiError`; surface user-facing messages via toast.

### Mutation Hooks
- Use shared `useCreateMutation`, `useUpdateMutation`, `useDeleteMutation` patterns where applicable.
- On success: invalidate relevant queries, show success toast.
- On error: show error toast with extracted message.

---

## 5. Data Model Standards

### Every domain table has a uuid `id` primary key
- New tables MUST declare `id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))`.
- A natural business key (e.g. a `code` like `retail` / `MSEG-A`) is fine and encouraged - but it lives **alongside** the surrogate `id` as a `unique=True, nullable=False` column, not **as** the primary key. Foreign keys may reference either the uuid `id` or the unique business key.
- **Why this is mandatory, not stylistic.** The polymorphic key columns - `audit_logs.entity_id`, `conversation_sla_tracking.source_entity_id`, `notifications.source_entity_id`, and similar - store a stringified id and can only be typed `uuid` (which makes Postgres reject a `uuid = text` mismatch at write time) if *every* id they might hold is genuinely a uuid. A single natural-key-PK table forces those columns back to `text`, which silently accepts the mismatch. One code-keyed table costs the whole system its type safety on the audit/SLA/notification trails.
- **Enforcement.** `sorento_crm_backend/tests/test_schema_uuid_id_principle.py` walks the SQLAlchemy models and fails CI if any table lacks a uuid `id`. A new table must either comply or be consciously added to that file's `EXEMPTIONS` allowlist (junction / external / documented-legacy) in a reviewed diff. The allowlist may only shrink.
- **Legitimate exceptions** (already in the allowlist): pure M2M junction tables (a composite natural PK is correct); schemas owned by another system (NextAuth, n8n, the Respond ingest); and grandfathered legacy auth/RBAC tables whose text ids hold uuid-shaped values (conversion is a tracked FK-heavy migration, not licence to add more).
- Worked example: `alembic/versions/298_market_segments_uuid_id.py` moves `market_segments` from a `code` PK to a uuid `id` while keeping `code` as the unique FK target.

---

## 6. Exceptions and Exemptions
- Exceptions must be documented in this ADR or a linked ADR.
- Resource-heavy or file-centric flows (e.g. attachment bulk upload) may use dedicated pages instead of modals.
- Read-only modules (e.g. logs) do not require create/edit modals.

---

## References
- Plan: `product-ux-standards` (Cursor plan)
- Backend error contract: `documentation/BACKEND-API-CONTRACT.md` (to be created)
- Frontend scaffolds: `components/common/` (ListPageToolbar, FormDialogScaffold, ConfirmDeleteDialog)
