# PLAN: census-scroller-fix (25 Oct 2026)

Status: PR #1862 open, reviewer READY, small fix track (test-only, under 30 changed lines, no migration, no
auth/RBAC change, no product code). Lane CENSUS-SCROLLER-FIX.

## Problem

On main `4af8fb2756` the census vitest
`sorento_crm_frontend/components/ui/data-grid-scroller.inventory.test.ts` ("every
scrollerMaxHeight: false site is enumerated with a reason") is red. It expects 2
`scrollerMaxHeight={false}` sites in
`app/(protected)/scm/sales-orders/[id]/components/SoLineHistoryBody.tsx` and finds 1.

Cause: #1855 (DO-SO-LINK-SURFACE, `b2f15efb32`) gave `DeliveriesTable` an `onPage` prop and
changed its site to `scrollerMaxHeight={onPage ? undefined : false}` (`SoLineHistoryBody.tsx:171`)
on purpose: inside the lightbox the grid still opts out of its own scroller, but on the SO page's
Delivery tab it keeps the bounded default. The census regex only matches the literal
`scrollerMaxHeight={false}` / `scrollerMaxHeight: false`, so the conditional site went uncounted.

## Fix (census only, no behaviour change)

- Teach the census regex the conditional form `scrollerMaxHeight={<cond> ? <x> : false}`: such a
  site still opts out of the bounded scroller in the branch that renders inside a dialog, so it
  belongs on the list. Only one such site exists in the FE today (grep of
  `scrollerMaxHeight(=\{|:)...\?` over app/components/lib).
- Update the `SoLineHistoryBody.tsx` entry's reason to say the delivered-DOs site is conditional.
- Pin the recognition with a small regex self-check in the same file, so a later tightening of
  the pattern fails loudly instead of re-opening this drift.

## UAC

- U1: the census file is green on main's tree with SoLineHistoryBody still counted as 2.
- U2: the regex matches `scrollerMaxHeight={onPage ? undefined : false}` and does not match a
  site that never yields `false` (e.g. `scrollerMaxHeight={onPage ? undefined : '24rem'}`);
  `PoPlanCard.tsx` stays off the list.
- U3: no file outside `components/ui/data-grid-scroller.inventory.test.ts` and this plan changes.
- U4: all `*inventory*` / `*census*` vitest files plus `loading-inventory.test.tsx` are green.
