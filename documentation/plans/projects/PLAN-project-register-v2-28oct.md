# PLAN: Register a project v2 (PROJECT-REGISTER-V2)

Status: Plan done; card answered 28 Oct (Q1-Q5, Q7 = b); mock v1.4 + card Q6 awaiting owner OK. No code before that.
Track: full, size L (new flow + permission-gated reassign; no migration expected). Security review required
(reassign / interest rules, new AI upload route, party and customer pickers).
Branch `crew/project-register-v2`, base origin/main `30a40cf04f`.
Card: `CARD-project-register-v2-28oct.md` v1.2. UAC: `project-register-v2-acceptance-criteria.md`.
Mock: `documentation/mockups/project-register-v2/index.html` v1.2.

## Owner's request (28 Oct ~14:1x, intent) and answers

1. Title is a textarea and the first field. 2. AI extract next to the title (text and photo), reusing the existing
extract; proposes only. 3. A duplicate does not block: offer "Register interest"; management may reassign to an
interested person; interested people shown on the project. 4. Architect / Main contractor created on the spot.
5. Brands: removed everywhere (Q5 b). 6. Customer replaces Lead as the required field, search-only, salespeople never
create customers (Q4 a). Plus: long titles never fill the screen (owner addition 14:3x).
Answers: Q1 (a), Q2 (a), Q3 (a) incl. the management slug fix, Q4 (a) search-only, Q5 (b). Q6 (Lead wizard buyer
step search-only) pending.

## Architecture (what is reused, nothing new where something exists)

- Interest = the existing takeover request, kind `dispute`, relabelled "Register interest" in the UI only
  (`BE/models/projects.py:508`, `BE/services/project_service.py:484` create, `:549` decide, routes
  `BE/api/v1/projects/projects.py:699/729/763`). Reassign to an interested person = approving that request
  (moves the owner, keeps the old owner as collaborator, `project_service.py:605-614`). No new table.
- Notifications: two new functions in `BE/services/project_notify_service.py` on the existing `_send` (:116);
  `MANAGEMENT_PERMISSION` (:33) becomes `projects.projects.manage`.
- Activity line: one new template in `BE/services/project_activity_service.py` (`record_project_event` :107).
- AI extract: new staff route in `BE/api/v1/projects/projects.py` calling `AIExtractService.extract`
  (`BE/services/ai_extract/extract_service.py:284`) with `portal.project_registration`
  (`form_schema_registry.py:403`); the validation copies `BE/api/v1/public/ai_extract.py:122-150`; the per-user
  limit reuses `portal_rate_limit` (`BE/services/portal_rate_limit.py:51`) keyed by user. Name -> id matching in one
  small service function (parties by type, project types, `my_state` lookup, customers).
- FE AI dialog: lift `app/(auth)/portal/components/AIExtractDialog.tsx` to a shared place with the extract call and
  the result renderer passed in; the portal keeps its behaviour.
- Pickers: `components/common/SearchableSelect.tsx` async mode (`fetchOptions`) + `createOption` for parties; Customer
  uses `GET /api/v1/order-management/customers/select` (`BE/api/v1/order_management/customers_select.py:27`).
- Party create dedupe (UAC B4) inside the existing create (`BE/services/project_reference_service.py`).
- Long titles: `components/common/TruncatedTextCell.tsx` gains `lines`; every unclamped site uses it.
- Brands: code removal only; `projects.brands` table and rows untouched (no migration).
- Customer required on register: enforced in the register route / `register_project`, not only the FE.

## Cross-lane: PORTAL-P4-REQUESTS (agreed with that lane 28 Oct, pending owner Q7)

MY REQUESTS > Project Registration links to `/project-sales/new`; submitted registrations show in the Projects
list / pipeline under view_own. P4 defines the submit slug (name per the Q7 ruling) in `permission_registry.py`
and grants it to the salesperson role in its `pp4_0001` migration; this lane only references the string (page gate
and register API accept `projects.projects.edit` OR it). A salesperson's submit uses the direct path (pending
project + existing approve / reject / notify), not P4's portal-token adapter (that stores typed names).

## Slices (one lane, one PR; commits on this branch)

- S1 BE: brands removal (G), customer required (A5), management slug + notifications (F), activity line (E6),
  view_own clause for pending interest (E7, `BE/services/own_scope.py:75-92`), party dedupe (B4), AI extract route +
  matching (C2-C6). Lead wizard `new_customer` refusal (I1) only if Q6 = a.
- S2 FE: form order + textarea + Customer + Lead in Details (A1-A4), party async + create rows (B1-B3), AI extract
  dialog (C1, C7), Register interest flow (D2-D4, D7), Access card Interested + manager actions + Reassign dialog
  (E1-E5), brands UI removal (G3), long titles (H1-H3), MCP sanitizer (G5).

- S3 Salesperson path (Q7 b, UAC J): register route / `register_project` branch on permission (edit = today's
  direct register; `projects.registrations.submit` only = draft or pending); draft save without required fields;
  owner-only draft visibility in `get_project_or_404` / `list_projects` (`BE/services/project_service.py:973-978,
  1073-1076`, same rule as PORTAL-P4 under view_own); submit / resubmit copy `portal_submit` `:671-679` and call
  `project_registration_service.notify` (`:713`); `_applicant_user_id` (`:699-702`) falls back to the owner when the
  contact is not linked. FE: footer Save draft + Submit for approval, Draft pill; `/project-sales/new` gate and the
  Start menu "Register a project" item (`FE/pipeline/components/PipelineClient.tsx:346`) for edit OR submit slug; edit
  page gate (`FE/[projectId]/edit/page.tsx:21`) edit OR submit slug, server limits submit-only users to their own
  draft / rejected rows. Depends on #1944 (PORTAL-P3-ROLE-MENU: view_own page gates, `projectViewPermissions.ts`):
  merge main after it lands; P4 (#1953) defines + grants the slug and merges after #1944.

## Test list (tester writes these red FIRST, from the UAC; coder makes them green)

pytest (BE, Postgres fixture `tests/_pg_fixture.py`, seed own chain): A5, A6, B4, C2 (403 / 422 types / count),
C3 (each status), C4 (row counts unchanged), C5 (429), C6 (502), D5, D6, E2 (403), E3, E4, E6 (activity row), E7,
F1, F2, F3, G1, G2, I1 (if Q6 a), J1-J8 (assert notification + notification_deliveries rows; never a real send). Plus the global guards `tests/test_schema_uuid_id_principle.py` and
`tests/test_list_pagination_limit.py` (list endpoint touched).
vitest (touched files only, `--maxWorkers=2`): ProjectForm (A1-A4, B1-B3, D2-D4, D7, G3), AI extract dialog (C7),
ProjectAccessPanel (E1, E2, E4), Reassign dialog (E5), TruncatedTextCell (H1), ProjectDetailClient header (H2),
ProjectsGrid / PipelineBoard / ClashWarningPanel (G3).
MCP pytest: G5.
BROWSER (agent-browser, crew test copy, 1280 + 375): A, C (one real extract call at most, Gemini org key ledger),
D, E, H4.

## Done when

Red-proof commit + kill-proof posted, reviewer READY, security-reviewer clean, browser pass 1280/375, hand test
script filed, crew-done with the DoD gate. No migration SQL (none needed); confirm at build time.
