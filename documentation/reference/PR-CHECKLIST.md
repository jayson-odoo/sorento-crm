# PR Checklist: Product Standards

Before merging, verify compliance with [ADR-PRODUCT-STANDARDS.md](./ADR-PRODUCT-STANDARDS.md).

## CRUD structure
- [ ] List page has search/filter and "Add/Create" button
- [ ] Create/edit uses modal by default (dedicated page only when ADR-exempt)
- [ ] Dedicated detail page for view
- [ ] Delete is a deferred (grace-window) action, not a confirmation dialog (D7 - see
      "Apple Alignment" below); a bare `confirm()` or a new `ConfirmDeleteDialog` /
      destructive `AlertDialog` importer is a defect, not a style choice

## Delete / Archive
- [ ] Delete is hard delete (permanent)
- [ ] If retention needed, separate Archive endpoint exists
- [ ] The record/list row shows the grace-window countdown with Cancel (10s hard delete,
      5s reversible) and no dialog opens; Escape does not cancel the pending action

## Detail pages
- [ ] All sections render even when empty (never hide entire section)
- [ ] Empty states are explicit and actionable ("No X yet. Do Y to add.")

## Shared usage
- [ ] Uses `extractApiError`, `buildDataGridParams` from `lib/api-client` (no duplication)
- [ ] Uses shared scaffolds: `ListPageToolbar`, `DetailActions`, `FormDialogScaffold` where
      applicable (`ConfirmDeleteDialog` is retired for anything on the deferred model)
- [ ] User/team selects: `services/userSelectService` (no feature-local duplication)

## Apple Alignment (design-system, every screen)
- [ ] Status renders as a pill via `<Badge status>` (`getStatusBadgeVariant`), not a
      hand-rolled coloured span
- [ ] DataGrid rows use `rowHref` (or `onRowClick` for a lightbox-edited record); log and
      sub-tables carry no pointer cursor and no row action
- [ ] No confirm dialogs on a destructive or detach action - the grace-window/deferred-action
      model (D7) is used instead; see "Delete / Archive" above. The only exceptions are the
      carve-outs `ADR-PRODUCT-STANDARDS.md` section 2 names (bulk selection, `PeopleGrid`, the
      portal ticket-draft confirm, `ReportViewsMenu`, the 22 `project-sales` files awaiting the
      `FormAction` auth-callback follow-up) - a confirm dialog anywhere else is a defect
- [ ] The page renders exactly one `PageHeader` (no hand-rolled `<h1>`, no `ToolbarTitle`)
- [ ] Tab strips use `variant="line"` (the default) unless they are a two/three-option
      segmented switch, which pins `variant="default"` explicitly
- [ ] Every icon-only button (`mode="icon"` / `size="icon"`) has an `aria-label` or an
      `sr-only` label - a bare icon with no accessible name is a defect

## Design
- [ ] `documentation/reference/DESIGN-LANGUAGE.md` hard-fails absent (`transition-all`,
      `scale(0)` entrance, `ease-in` entrance, raw `cubic-bezier` outside `config.reui.css`,
      motion on a keyboard-initiated action)
- [ ] Primitives are from the roster (`DESIGN-LANGUAGE.md` section 4), not hand-rolled
- [ ] No feature-explanation prose in the UI
- [ ] 375px and 1280px screenshots attached
- [ ] Any new motion honours `prefers-reduced-motion` (`useReducedMotion` from `lib/motion.ts`)

## Test cost
- [ ] New backend tests do not add whole-suite-running slow tests without cause; check the `--durations=30` block in the backend CI logs for the PR ("Backend test suite (Postgres)" and "Backend test suite - SCM (Postgres)") and justify any new entry over ~2s
- [ ] A test that only asserts against production-copy data goes in `tests/ci_excluded.txt` with a reason, not into the gated set
