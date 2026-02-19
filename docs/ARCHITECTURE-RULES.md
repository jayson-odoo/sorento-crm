# Architecture Rules (Lint / Review Guardrails)

Reference: [ADR-PRODUCT-STANDARDS.md](./ADR-PRODUCT-STANDARDS.md)

## Banned patterns

1. **Error extraction duplication**  
   Do not copy `response.json().catch(() => ({}))` + `error.detail || error.message` in feature services. Use `extractApiError(response, fallback)` from `lib/api-client`.

2. **DataGrid params duplication**  
   Do not manually build `URLSearchParams` with `page`, `limit`, `sort`, `dir`, `query`. Use `buildDataGridParams(params, extra)` from `lib/api-client`.

3. **User select duplication**  
   Do not implement `getUsersSelect` or similar in feature services. Use `services/userSelectService`.

4. **Delete without confirmation**  
   Do not call delete APIs from buttons without a confirmation dialog. Use `ConfirmDeleteDialog`.

5. **Hidden empty sections**  
   Do not conditionally hide entire sections on detail pages when data is empty. Render section with empty state.

6. **Soft delete labeled as "delete"**  
   Backend DELETE must perform hard delete. Use Archive (soft delete) only for retention.

7. **Listing tables: no overlap, resizable columns**  
   All DataGrid-based listing tables MUST use `tableLayout: { width: 'fixed', columnsResizable: true }` and `columnResizeMode: 'onChange'` in `useReactTable`. Columns MUST have `size` (and optionally `minSize`) to prevent overlap. Long text (e.g. filenames) MUST use `truncate` plus `title` for overflow.
