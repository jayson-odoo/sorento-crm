# PLAN: Packing-list tabs for users without SCM permission (PL-TABS-ACCESS)

Status: In progress (small fix track: frontend only, no migration, no backend RBAC change)

## Journey

Owner, prod, 1 Oct 2026: viewing a packing list as Kah Xin, the Proforma invoices, Documents and
SPO planner tabs "hang"; Shipment lines works. Granting every SCM permission fixed it, so it is
permission-driven.

## Scope

1. Find the real hang cause (file:line).
2. Hide the tabs a user cannot use; `RequireAccess` / `AccessDenied` on those routes for a deep link.
3. The layout provider's source-invoices read is silent on 403 (no toast, no retry) so the tabs the
   user CAN open do not show an error that belongs to a tab they cannot.
4. Fix the hang cause.

Not in scope: changing which permission the backend endpoints require.

## Findings (repro, 1 Oct 2026, sandbox stack, Playwright + agent-browser)

User with only `procurement.packing_lists.view/edit`, direct login and admin view-as, dev build:

| Tab | Request | Result before the fix |
|---|---|---|
| (all, layout provider) | `GET /scm/inbound-shipments/{id}/source-proforma-invoices` | 403 `scm.dashboard.view`, retried once, permission toast; re-fired on every tab mount |
| Details | `GET /scm/container-sizes` | 403 + retry + toast |
| Proforma invoices | source-proforma-invoices | renders the EMPTY state "Read from a packing list, not drafted from a proforma invoice." (`SourceProformaInvoicesCard.tsx` branched on `isLoading` only) |
| Shipment lines | `/scm/.../packing-list`, `/scm/.../line-photos` | 403 + retry + toast; grid itself works |
| Documents | none of its own; reads the provider | "No proforma invoice behind this container." (false) |
| SPO planner | `/scm/.../spo-suggestion` | raw "Permission required: scm.dashboard.view / Try again" card |

Backend gates: `require_permission("scm.dashboard.view")` (`app/api/v1/scm/proforma_invoices.py:45`,
`app/api/v1/scm/fulfilment.py:61`). `/me/permissions` returns every slug for superadmin/admin.

## Fix

- `[id]/components/packing-list-context.tsx`: `SCM_READ_PERMISSION`, `canReadScm`; source-invoices
  read only with it.
- `hooks/usePackingLists.ts`: that read is `retry: false` + `meta.silent`; the card reports the
  failure in place (`SourceProformaInvoicesCard.tsx`).
- `[id]/layout.tsx`: Proforma invoices + SPO planner tabs only with the permission.
- `[id]/proforma-invoices/page.tsx`, `[id]/spo/page.tsx`: `RequireAccess` for a deep link.
- Lines / Details / Documents: their SCM reads are skipped without the permission.
