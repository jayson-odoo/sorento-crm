# PLAN: Target record, Edit as the primary button (TARGET-EDIT-CTA)

Status: built, PR #2184 open, awaiting owner hand test. Track: small fix (frontend only, no
migration, no RBAC change).

UAC: `target-edit-cta-05nov-acceptance-criteria.md`.

Owner, 5 Nov: "edit should be the CTA here". The target record (`/sales/targets/{id}`) showed
no primary button; Edit was a gear item (set by the 27 Sep hand test, F4). Edit moves into the
`DetailActions` `primary` slot (`components/common/DetailActions.tsx`), the same button the
opportunity record uses (`sales/opportunities/[id]/components/SalesOpportunityDetail.tsx`):
`variant="primary" size="sm"` with `SquarePen`. Gate unchanged (`sales.targets.edit`). Back to
targets and the pager stay. Export commission statement, Duplicate and Delete stay in the gear.
No new component, no backend change.

Round 2, owner 5 Nov ~10:50: "if I am at dealer target, then I go back should go back to
dealer target tab". `TargetPageHeader` (client) points Back to targets and the Targets crumb
at `/sales/targets?tab=<subject_kind>`, the list's own `?tab=` key (`SalesTargetsView`
`writeUrl`/`tabOf`), with the list state the row click handed over appended
(`useBackToListHref`); the shape follows the quotation page's Back to its project tab
(`project-sales/[projectId]/quotations/[quotationId]/page.tsx`). Deriving the tab from the
record's kind makes a direct link return to the right tab. `useHrefWithListState` now merges
onto a path that carries its own query (it produced `?tab=dealer?page=..` before). The agent
tab's Team filter rides on the row href so it comes back too. Delete returns to the same tab.
The pager already walks only targets of the record's kind (`TargetRecord.tsx`, `siblings`).

Files: `sales/targets/[id]/page.tsx`, `sales/targets/components/TargetPageHeader.tsx`,
`components/common/BackToList.tsx`, `sales/targets/components/SalesTargetsView.tsx`,
`sales/targets/components/TargetRecord.tsx`, `sales/targets/actions.tsx` (comment only),
`sales/targets/components/TargetRecord.test.tsx`.

Not in scope (crew-note on the PR): Sales Teams and Sales Orders records also keep Edit in the
gear, but each already has a different primary button.
