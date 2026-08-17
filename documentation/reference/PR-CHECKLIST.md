# PR Checklist: Product Standards

Before merging, verify compliance with [ADR-PRODUCT-STANDARDS.md](./ADR-PRODUCT-STANDARDS.md).

## CRUD structure
- [ ] List page has search/filter and "Add/Create" button
- [ ] Create/edit uses modal by default (dedicated page only when ADR-exempt)
- [ ] Dedicated detail page for view
- [ ] Delete requires confirmation dialog (never inline or automatic)

## Delete / Archive
- [ ] Delete is hard delete (permanent)
- [ ] If retention needed, separate Archive endpoint exists
- [ ] Confirmation dialog shows clear consequence ("This action cannot be undone")

## Detail pages
- [ ] All sections render even when empty (never hide entire section)
- [ ] Empty states are explicit and actionable ("No X yet. Do Y to add.")

## Shared usage
- [ ] Uses `extractApiError`, `buildDataGridParams` from `lib/api-client` (no duplication)
- [ ] Uses shared scaffolds: `ListPageToolbar`, `ConfirmDeleteDialog`, `FormDialogScaffold` where applicable
- [ ] User/team selects: `services/userSelectService` (no feature-local duplication)

## Test cost
- [ ] New backend tests do not add whole-suite-running slow tests without cause; check the `--durations=30` block in the backend CI logs for the PR ("Backend test suite (Postgres)" and "Backend test suite - SCM (Postgres)") and justify any new entry over ~2s
- [ ] A test that only asserts against production-copy data goes in `tests/ci_excluded.txt` with a reason, not into the gated set
