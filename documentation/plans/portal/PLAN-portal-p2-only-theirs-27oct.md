# PLAN: PORTAL-P2-ONLY-THEIRS, "only theirs" on the server (27 Oct 2026)

Status: Plan. Behaviour card posted for owner answers; no product code yet.
Track: full (RBAC change), security review required. Lane PORTAL-P2-ONLY-THEIRS.

Source brief: `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md` (PR #1894), section
"Lane briefs" -> P2. That brief is the contract; this file records the lane's own decisions and
progress against it.

## Goal

A salesperson signed in to the CRM sees only their own and collaborator projects, and the records
under them, enforced on the server. P2 grants nothing: it adds `*.view_own` slugs (granted to no
role) and narrows what a holder of only `view_own` sees. Holders of `view`, admin and superadmin
are unchanged.

## Acceptance criteria

See `portal-p2-only-theirs-acceptance-criteria.md`.
