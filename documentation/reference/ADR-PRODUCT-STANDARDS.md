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

## 1b. Form Controls — Dropdowns MUST be searchable

**Doctrine:** every dropdown-select in the product MUST be **searchable** and MUST use the standard
component. A "dropdown-select" = click a field → a popover opens showing an option set → filter by
typing in the popover's search box → pick one (or many).

- **Standard components (the only allowed dropdown-selects):**
  `@/components/common/SearchableSelect` (single, `value: string`) and
  `@/components/common/SearchableMultiSelect` (multi, `value: string[]`). Both are one-component /
  two-mode: pass `options` for a client-filtered static list, or `fetchOptions(query)` for a
  debounced server search (async also passes `selectedOption`/`selectedOptions` so the trigger label
  survives when the current value isn't in the fetched page).
- **Search is always shown — no option-count threshold.** A 2-option Active/Inactive dropdown is
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

## 5. Exceptions and Exemptions
- Exceptions must be documented in this ADR or a linked ADR.
- Resource-heavy or file-centric flows (e.g. attachment bulk upload) may use dedicated pages instead of modals.
- Read-only modules (e.g. logs) do not require create/edit modals.

---

## References
- Plan: `product-ux-standards` (Cursor plan)
- Backend error contract: `documentation/BACKEND-API-CONTRACT.md` (to be created)
- Frontend scaffolds: `components/common/` (ListPageToolbar, FormDialogScaffold, ConfirmDeleteDialog)
