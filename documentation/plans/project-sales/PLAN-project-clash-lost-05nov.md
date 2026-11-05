# PLAN: project clash check shows every match; Lost stage and outcome agree

Status: owner hand test (small fix track, lane PROJECT-CLASH-LOST; pytest + vitest run in the lane sandbox)

## Journey

Owner, 5 Nov: registering "test" said "No clash" although PPF2611001 "test" exists (outcome Won).
After marking PPF2611001 Lost, its header pill read Lost while the Projects list Outcome read Won.

## Root causes

(a) Backend `find_clashes` (sorento_crm_backend/app/services/project_clash_service.py) already
returns every approved project of the company above the surface bar, in every outcome; only
`outcome == open` BLOCKS (`BLOCKING_OUTCOMES`, app/models/projects.py). The register form
(sorento_crm_frontend/.../ProjectForm.tsx `checkResult`) renders only a BLOCKING candidate and
says "No clash" otherwise, so a Won/Lost match was fetched and then hidden. Matching rules were
not the cause ("test" vs "test" scores 1.0).

(b) The pill is the funnel STATUS (status rung "lost"); Outcome is a separate column derived
from quotations only (`derive_project_outcome`, any won quotation => won). `change_status`
never touched outcome, so moving to Lost left Outcome Won.

## Fix

1. Step 1 Check lists every candidate (code link, title, stage, outcome, owner). Blocking
   rule unchanged: only an open project of the same/unknown developer blocks.
2. A terminal Lost / Dormant stage is authoritative for outcome: `derive_project_outcome`
   returns lost/dormant when the project's status key is lost/dormant; leaving that stage
   re-derives from quotations. `change_status`, the PO auto-advance and the admin bulk status
   migration re-sync outcome after every move. With the seeded funnel Lost and Dormant are
   terminal, so a project cannot leave them; a won quotation on a Lost-stage project leaves
   the outcome Lost, and "make quotation" names the stage that stops it.
3. Data fix: read-only count query + dry-run/apply script for existing rows.

## Tests

- pytest: clash preview returns a Won and a Lost match with blocks false; change_status to
  lost sets outcome lost though a quotation is won; back to a live rung re-derives won.
- vitest: Check renders non-blocking matches with outcome instead of "No clash".
