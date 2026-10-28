# PLAN: Register a project v2 (PROJECT-REGISTER-V2)

Status: Plan. Card being written (behaviour card before any code). Track: full, size L (new flow
"register interest" + management reassign, likely a migration, AI extract incl. images).
Branch `crew/project-register-v2`, base origin/main `30a40cf04f`.
UAC: `project-register-v2-acceptance-criteria.md` (after the card is answered).
Mock: `documentation/mockups/project-register-v2/index.html` (after the card is answered).

## Owner's request (28 Oct ~14:1x, intent)

"After we unify the portal, the project registration is here":

1. Project title becomes a TEXTAREA and the FIRST field.
2. AI extract button next to the title fills the other fields from the title text, reusing the existing
   AI extract (portal project registration, PR #1849). It also accepts an IMAGE (photo). Extract only
   proposes; the user confirms before Register. Unmatched names follow item 4.
3. Duplicate project: "Check" must NOT block. If the project exists, offer "Register interest" instead of
   "Register project". Record who is interested and when. Management may later REASSIGN the project to an
   interested person. Interested people show on the project; reassign is permission-gated and audited.
4. Architect and Main contractor: like Lead, create on the spot when not found.
5. "Why is the brand field here": explain, recommend keep / move / remove.
6. "Needs to be customer instead of lead?": explain Lead vs Customer, recommend.

## Known context (verified)

- ADR-0004 (`documentation/adr/0004-project-registration-exclusivity.md`) makes staff registration
  exclusive: a fuzzy title clash BLOCKS, with recourse "request to join" / "dispute". Item 3 reverses the
  block for staff registration; the ADR needs an amendment.
- Existing recourse tables: `projects.takeover_requests` (kind join | dispute, requester, reason, status,
  decided_by/at; `app/models/projects.py:503-541`) and `projects.collaborators`
  (`app/models/projects.py:482-500`). Dev copy: 0 rows in both.
- "Brand" dropdown = `projects.brands` M2M onto core `brands` ("brands being pushed into a project",
  `app/models/projects.py:413-438`). Dev copy: 3 rows, all on one project.
- Portal registration (PR #1849, merged `1b6f73f56e`) already has AI Extract and "a possible duplicate never
  blocks" for the portal path (`PLAN-project-registration-portal-25oct.md`, D7/D8).

## Open (card)

Answers to items 5 and 6, extract field mapping, interest + reassign rules, duplicate basis, examples,
questions. Filled after exploration.
