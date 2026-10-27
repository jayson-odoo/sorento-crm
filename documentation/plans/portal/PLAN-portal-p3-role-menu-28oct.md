# PLAN: PORTAL-P3-ROLE-MENU, salesperson role + trimmed CRM sidebar (28 Oct 2026)

Status: Plan. Behaviour card filed to crew (`crew report --ask`), waiting on owner answers before code.
Track: full (RBAC grant + landing change), security review required. Size M, LEAD pattern. Lane PORTAL-P3-ROLE-MENU.

Source: scout `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md` (PR #1894, v3 + alignment),
P1 #1908 (`portal_link` session), P2 #1911 (`*.view_own`, `own_scope.py`). Both merged.

## Goal

A salesperson (CRM user linked to a WhatsApp contact that is an active sales agent) who signs in from
the portal link, or at `/signin`, lands in the CRM shell. The sidebar is the existing
permission-driven menu, trimmed to what the `salesperson` role holds, under MY WORK / MY REQUESTS
headings. Contacts without a CRM user keep today's portal byte for byte. Existing staff: no change.

## Reuse (owner 27 Oct: "don't reinvent the wheel")

To be filled from the behaviour card (every sidebar item -> permission -> existing component).

## Open (behaviour card questions)

Pending crew relay.

## Acceptance criteria

`portal-p3-role-menu-acceptance-criteria.md` (written after the owner answers the card).
