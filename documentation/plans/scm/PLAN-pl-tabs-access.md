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

## Findings

(filled in as the repro lands)
