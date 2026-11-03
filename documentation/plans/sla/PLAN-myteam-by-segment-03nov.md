# PLAN: My Team + Coverage show only tasks the viewer's segment/brand tags serve

Status: in review (small fix track: backend filter only, no migration, no RBAC change)

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
- One shared predicate (`member_serves_segments`, `market_segment_service.py`), used by both
  the round-robin pool (`UserService._rr_pool`) and the My Team filter; brands reuse
  `member_serves_brand`. The task's brand is the tracker's stamped `brand_code` (the value the
  round-robin and escalation already route on).
- The viewer's tags are the union over all their memberships.

## Decisions (crew ruling 3 Nov)

1. Coverage = tasks only. The Coverage picker, the subscribe/assign scope check and Reassign
   are untouched; segment tags never stop someone covering a colleague.
2. While I hold an active coverage of a colleague, that colleague's tasks show to me in full on
   My Team, so the coverage deep link never opens an empty list.
3. Acting permission (`can_user_act_on_tracking`) is unchanged: this narrows the list, not RBAC.

## Acceptance (red-first tests)

1. Project CS viewer sees a project-contact task, not a retail-contact task.
2. Retail CS viewer sees the retail task, not the project task.
3. Untagged lead sees both.
4. Task whose contact has no segment is visible to project CS and retail CS.
5. Brand: a viewer tagged brand A does not see a task whose contact brand is B.
6. Project CS covering a retail CS sees the retail CS's retail tasks; without (or with an
   expired) coverage they stay hidden.

## Check query

`sorento_crm_backend/scripts/check_do_cs_member_segments.sql` (read-only). Hand test:
`laneboard/scripts/2150.md`.
