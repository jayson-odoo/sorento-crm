# PLAN: portal / system unification scout (27 Oct 2026)

Status: scout delivered, awaiting owner rulings on Q1 to Q5 (design lane, no product code).
Track: scout. Lane PORTAL-UNIFY-SCOUT.

Design doc (the deliverable, self-contained HTML):
`documentation/plans/portal/portal-unify-scout-27oct.html`.

## Owner question (27 Oct 2026, verbatim)

> "our sign in has two places: portal and system. It works fine for forms like stock inquiry,
> purchase request, all these easy forms, but when it comes to project registration, quotation,
> and further flow down the road of project sales, the UI and function is gonna be complex and I
> don't want to replicate the function in portal and in system view, I want to maintain one."

## Findings (detail and file:line evidence in the HTML)

- Unified identity S0, S1 and S3 shipped; S2 (the portal on the `user_sessions` session) is not
  built (`PLAN-unified-identity-26sep.md`, slice S2).
- The backend services are mostly shared between the portal and the system. The duplication is in
  the FE screens (about 1,300 to 2,000 lines estimated) and in the two route surfaces in front of
  them (83 `get_portal_token` dependencies). Sales opportunity is a full FE mirror
  (1,136 portal lines vs 1,934 staff lines).
- Staff project reads are wide open by design (`app/services/project_service.py:407-408`). Putting
  salespeople on the staff API therefore needs a new server-side own-records read rule.
- On the portal, project sales covers registration only (#1849). Everything after Approve is
  staff-only.

## Recommendation

Option B: one login (finish S2) and one app with two shells. The portal URL and look stay as the
salesperson's entry. Project detail, quotation and the later steps are built once on the staff API,
mounted in a slim portal shell, with `projects.projects.view_own` enforced in the backend. The
simple forms stay as they are.

## Phases (one lane each)

1. P1 identity S2 (already planned and ruled), M, full track + security review.
2. P2 `projects.projects.view_own` read rule on every project-sales read, S to M, full track +
   security review.
3. P3 portal shell + "My projects" using the staff project detail components, M.
4. P4 quotation in the portal from the same editor, scoped per Q3, M to L.
5. P5 retire the sales opportunity mirror when it next needs a change (named trigger).

## Owner questions

Q1 salesperson reads only own + collaborator projects (rec: yes). Q2 project sales beyond
registration only for set-up users (rec: yes). Q3 portal quotation scope (rec: draft + lines +
send for approval; admin issues). Q4 salesperson never sees the CRM sidebar (rec: portal shell
only). Q5 P1 and P2 as two parallel lanes now (rec: yes).
