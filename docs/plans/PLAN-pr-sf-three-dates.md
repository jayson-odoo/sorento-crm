# PLAN — PR/SF three-date model (Submitted / Request / Approved)

Status: DONE — BE migration + portal stamp + schema/serializers; FE detail/footer/edit/create/public/excel; pytest (2) green; browser-verified on local PSSF26-0317 (Submitted 23/06, Request —, Approved —).

## Business requirement (from Project Sales Sponsorship Form)

The paper form has three distinct dates:

| Form position | Meaning | Source |
|---|---|---|
| Top "Date:" (`*filled by CS*`) | **Submitted date** — when the form entered the system | auto-generated |
| Bottom-left "Date:" under **Requested by** | **Request date** — when the requester made the request | user-entered |
| Bottom-right "Date:" under **Approved by** | **Approved date** | auto on approval |

## Column mapping

| Position | Column | Editable | Behaviour |
|---|---|---|---|
| Submitted date (top) | `submitted_at` (NEW `DateTime`) | read-only | re-stamped `utcnow()` on **every** submit, incl. resubmit-after-rejection |
| Request date (footer-left) | `request_date` (existing `Date`) | user | collected in portal / create form |
| Approved date (footer-right) | `approved_at` (existing) | — | stamped on approval decision |

`requested_at` (existing column) is **deprecated** — no longer shown/edited anywhere. Left in DB, unused.

## Resubmit behaviour (locked with user)

`submitted_at` updates to the **latest** submit. Mirrors `approved_at`, which already resets each approval cycle.

```
Submit (5-Jun)   → submitted_at = 5-Jun
Rejected         → submitted_at = 5-Jun (unchanged)
Resubmit (9-Jun) → submitted_at = 9-Jun   ← updates
Approved (10-Jun)→ approved_at  = 10-Jun
```

`created_at` still preserves the original system-entry date.

## Stamp point

PR/SF reach `status="submitted"` **only** in `portal_service.submit_draft` (PR/SF branch). Resubmit-after-rejection sets `status="submitted"` again there. So stamp `row.submitted_at = _utcnow()` in that one branch — covers submit + resubmit uniformly. `set_pending_approval` is the approval-send step, NOT a submit; it must NOT re-stamp.

System-created rows that never go through portal submit keep `submitted_at = NULL` (top date blank). Acceptable edge case.

## Backfill

`UPDATE purchase_requests SET submitted_at = created_at WHERE submitted_at IS NULL AND status <> 'draft';`

## Surfaces to change

### Backend
1. Model `PurchaseRequestHeader`: add `submitted_at`.
2. Alembic migration: add column + backfill.
3. `portal_service.submit_draft` PR/SF branch: stamp `submitted_at`.
4. Response schema `PurchaseRequestHeaderResponse`: add `submitted_at`.
5. Serializers (detail dict, list dict, portal detail, public summary): include `submitted_at`.

### Frontend
6. `purchaseRequest.types.ts`: add `submitted_at`.
7. `PurchaseRequestDetail`: top label → "Submitted date" = `submitted_at` (read-only); footer-left → "Request date" = `request_date`.
8. `PurchaseRequestSignoffFooter`: footer-left date = `request_date`, label "Request date" (un-hide).
9. `PurchaseRequestDocumentEditCard`: top → read-only "Submitted date"; footer renderRequestedColumn → add editable "Request date" (`request_date`).
10. `PurchaseRequestForm` (create): keep top date field as "Request date" (`request_date`); submitted is auto.
11. `view/request/page.tsx` (public): top → "Submitted date" = `submitted_at`; footer-left = `request_date`. Needs `submitted_at` in public summary.
12. Excel export: top "Date:" = `submitted_at`; footer "Requested by" date = `request_date` (PR + SF).

### Tests (Phase 2)
- pytest: portal submit stamps `submitted_at`; resubmit re-stamps; reject leaves unchanged; approve does not touch `submitted_at`.
- vitest: detail/footer render the three dates from the right fields.
