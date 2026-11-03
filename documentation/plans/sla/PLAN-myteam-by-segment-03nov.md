# PLAN: My Team + Coverage show only tasks the viewer's segment/brand tags serve

Status: in progress (small fix track: backend filter only, no migration, no RBAC change)

Lane: MYTEAM-BY-SEGMENT. Owner approval 3 Nov 22:50 ("ok for my team and coverage").

## Problem

One team (DO Customer Service) holds retail and project CS. The dashboard My Team tab and the
Coverage picker show every teammate's open tasks, so project CS see retail tasks and vice versa.

## Rule

- A team membership already carries market segments and brands (empty = serves all). The
  round-robin uses them to pick an assignee for a contact.
- My Team and the Coverage view keep a task only when its CONTACT's segments overlap the
  viewer's own membership segments, and its contact brand is one the viewer serves.
- Viewer with no segment tags (and no brand tags) on any membership sees everything.
- A task whose contact has no segment (or no brand) stays visible to everyone on that axis.
- One shared predicate, used by both the round-robin and the dashboard filter.

## Acceptance (red-first tests)

1. Project CS viewer sees a project-contact task, not a retail-contact task.
2. Retail CS viewer sees the retail task, not the project task.
3. Untagged lead sees both.
4. Task whose contact has no segment is visible to project CS and retail CS.
5. Brand: a viewer tagged brand A does not see a task whose contact brand is B.

## Check query

`sorento_crm_backend/scripts/sql/check_do_cs_member_segments.sql` (read-only).
