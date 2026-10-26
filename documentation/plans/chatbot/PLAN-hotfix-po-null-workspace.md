# PLAN: HOTFIX-PO-NULL-WORKSPACE

Status: Review (red e1fdf9c733, fix c28a5cc5da, kill-proof done). Track: small fix (size S, hotfix for #1880). No migration, no RBAC change, no new
ingest surface, no prompt change. UAC: `hotfix-po-null-workspace-acceptance-criteria.md`.

## Problem

#1880 (CHAT-PO-LOCATION-SCOPE, merged 3ce30c5c85) scoped `GET /procurement/purchase-orders/placed`
under a `contact_id` by calling `stock_visibility.resolve_policy(db, contact_id, space_id)`
(`app/api/v1/procurement/purchase_orders.py:177-179`). `resolve_policy` resolves through
`field_access.resolve_contact_id` (`app/services/stock_visibility.py:229-243`), whose Respond.io
branch joins `respond_workspaces` on the given `space_id` (`app/services/field_access.py:250-255`).
A contact whose `workspace_id` is NULL has nothing to join to, so it resolves to nobody and the
route fails closed with no rows.

The chatbot admits that same contact through
`field_access.resolve_contact_with_null_workspace_fallback` (`app/services/field_access.py:278`),
and the purchase-order rung sends the Respond.io id plus `space_id`
(`app/services/chatbot/lanes/business/answer.py:1313-1321`). So a NULL-workspace contact is
answered by the chatbot but told nothing is on order. Before #1880 the rows came back (the old
code only withheld `location`, `git show 3ce30c5c85^:.../purchase_orders.py:176-186`).

Reported by lane CHAT-INCOMING-LOCATION-SCOPE on #1882 (comment 6418229930), which fixes the
same bug for the incoming routes. This lane ships only the placed-route part, as a hotfix.

## Architecture

- Layer: the route's contact resolution, nothing below it. `resolve_policy` and
  `resolve_contact_id` are untouched (their docstring at `field_access.py:281-298` records why the
  fallback is NOT widened into `resolve_contact_id` itself).
- Shared mechanism: `eta_policy.resolve_request_contact` (`app/services/eta_policy.py:212`), the
  one-shot resolver over the NULL-workspace fallback that #1882 uses. The route resolves once, then
  calls `resolve_policy` on the internal id (which `resolve_contact_id` accepts directly,
  `field_access.py:247-249`). No second policy function.
- Fail-closed stays: an unresolvable or ambiguous id (two NULL-workspace contacts with one
  Respond.io id, `field_access.py:313-321`) still returns no rows.

## Change

`app/api/v1/procurement/purchase_orders.py`: replace
`policy = resolve_policy(db, contact_id, space_id)` with
`resolved = resolve_request_contact(db, contact_id, space_id)` then
`policy = resolve_policy(db, resolved) if resolved else None`. Identical to #1882's hunk, so
#1882 rebases onto this cleanly or drops its copy.

## Tests (red first)

`tests/test_po_placed_location_visibility.py`:
1. NULL-workspace contact, asked by Respond.io id + space_id, no location policy: every row
   comes back (the same row set staff and pre-#1880 got), locations named.
2. NULL-workspace contact with an include list: only the in-scope row, summary counts it alone.
3. Unresolvable Respond.io id + space_id: no rows. Ambiguous NULL-workspace id: no rows.

Kill test: revert the route hunk, 1 and 2 fail again.

## Data (read-only, shared dev DB `sorento_prod_1020`)

Measured 26 Oct 2026, read-only transaction (`default_transaction_read_only=on`):

| measure | count |
| --- | --- |
| `respond_contacts` total (newest `created_at` 2026-10-14) | 405 |
| `workspace_id IS NULL` | 0 |
| contacts whose workspace has a `space_id` | 405 |

So on this copy no contact is affected today. NULL can still arise: `create_contact` falls back to
the default workspace only when one exists (`app/services/contact_service.py:415-419`, update
path `:946-950`), and `respond_contacts.workspace_id` is `ondelete="SET NULL"`
(`app/models/access.py:276`), so deleting a workspace drops its contacts into this case. The
7 Sep measurement of 16 (`field_access.py:284`) was on an older copy; why those 16 later gained a
workspace is UNVERIFIED (the create fallback dates from 5f38c67f2f, 2 May, so it is not the
reason). Live prod is not measured (lane rule: never touch prod), UNVERIFIED.
