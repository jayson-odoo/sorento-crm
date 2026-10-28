# PLAN: PORTAL-P4-REQUESTS, MY REQUESTS opens the staff pages with server-side "only theirs" (28 Oct 2026)

Status: Plan. Behaviour card being filed to the owner (crew --ask); no code before the answers. Track: full (RBAC +
permission slugs migration + create stamping), security review required. Size L, LEAD pattern. Lane PORTAL-P4-REQUESTS.
Stacked on PR #1944 (PORTAL-P3-ROLE-MENU); this PR merges right after it.

Source: `PLAN-portal-p3-role-menu-28oct.md` (open MY REQUESTS decision), PR #1944 crew-note 6461917897, owner
28 Oct ~14:1x option (b): hold #1944 until MY REQUESTS opens the staff pages.

## Goal

A salesperson's MY REQUESTS > Stock Inquiry / Complaint / Purchase Request / Sponsorship Form opens the STAFF page
for that form (list, detail, edit, new), showing only their own rows, enforced on the server. Staff-only fields and
actions stay behind existing staff permissions. What they could do in the portal they can still do here (draft,
submit, revise, comments, attachments, duplicate, requestor picker). The embedded portal list leaves the CRM.

## Rule (draft, pending owner answers)

LIMITED in a module = holds its `view_own`, not its `view` (P2 rule, `app/services/own_scope.py`). "Theirs" to be
settled in the behaviour card.

## Design

Pending owner answers.

## Acceptance criteria

`portal-p4-requests-acceptance-criteria.md` (written after the owner answers).
