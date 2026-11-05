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

Files: `sales/targets/components/TargetRecord.tsx`, `sales/targets/actions.tsx` (comment only),
`sales/targets/components/TargetRecord.test.tsx`.

Not in scope (crew-note on the PR): Sales Teams and Sales Orders records also keep Edit in the
gear, but each already has a different primary button.
