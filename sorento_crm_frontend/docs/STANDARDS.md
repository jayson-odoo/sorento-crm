# Frontend Standards

This document references the product-wide ADR and highlights frontend-specific rules.

**Primary reference:** [ADR-PRODUCT-STANDARDS.md](../../docs/ADR-PRODUCT-STANDARDS.md)

## CRUD UX
- List + modal create/edit + dedicated view page + confirmation delete
- Use shared scaffolds: `ListPageScaffold`, `FormDialogScaffold`, `ConfirmDeleteDialog`

## Services
- Use shared `apiFetch` from `lib/api`, `extractApiError`, `buildDataGridParams` from `lib/api-client`
- User/team selects: use `services/userSelectService` (do not duplicate in feature services)

## Hooks
- Prefer shared CRUD mutation hooks where applicable
- Toast: `toast.success` / `toast.error` for CRUD; reserve `toast.custom` for special cases

## Empty States
- Detail sections always render; use explicit empty states with actionable copy
