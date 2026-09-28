# Evidence: project form for register and edit, salesperson pick, lead link (#1339)

agent-browser 0.27.0 against a cloud lane's own freshly bootstrapped Postgres (empty,
`scripts.bootstrap_env`-seeded reference data only), backend + frontend dev servers on
:8000/:3000. Login as a superadmin seeded for this lane; every page reached by sidebar
clicks from `/` (never a deep URL), except the edit page which the UAC itself reaches
only from the project's gear menu.

| File | Shows |
| --- | --- |
| `register-1-open-1280.png` | `/project-sales/new` via Pipeline > Start > Register a project: title "Register a project", crumbs, one Back to pipeline, no subtitle, one primary CTA. Salesperson defaults to the current user. |
| `register-2-details-expanded-1280.png` | Developer, Project type, Project title and Template filled: Details opens by itself (AC-PF033); Check already ran and shows "No existing project matches this title." |
| `overview-3-after-create-1280.png` | Overview after Register project: PRJ-000001, "Where this came from" shows LEAD-000001, Access panel shows the picked salesperson (Lane1339 Sales) as Owner. |
| `edit-4-open-prefilled-1280.png` | `/project-sales/<id>/edit` reached from the Overview gear (Edit project is the first item): title "Edit project", no subtitle, every field prefilled including Template, Details already expanded (AC-PF034). |
| `overview-5-after-unlink-1280.png` | After changing Location and clearing the lead then Save changes: Overview shows the new location (Shah Alam, Selangor) and "Registered directly, with no lead before it." |
| `overview-6-relinked-1280.png` | After Edit again, re-picking the same lead, Save changes: "Where this came from" shows LEAD-000001 again. |
| `register-7-lead-already-linked-toast-1280.png` | Registering a second project against a lead another project already carries: 409 refused, toast reads "LEAD-000002 is already linked to PRJ-000002 \"Lane1339 Stealer Project\". Unlink it there first, or pick another lead." Nothing was registered (DB still holds only PRJ-000001 and PRJ-000002). |
| `pipeline-8-375.png` | Pipeline at 375px: no horizontal page scroll (`scrollWidth` 375), nothing clipped. |
| `register-9-375.png` | Create page at 375px: `scrollWidth` 360, usable, nothing clipped. |
| `edit-10-375.png` | Edit page at 375px (top and bottom of the form, including Save changes / Cancel full-width): `scrollWidth` 360, nothing clipped. |
| `overview-11-375.png` | Overview at 375px: `scrollWidth` 360, nothing clipped; tab strip scrolls within its own row, not the page. |

## Login recipe used (names only, no values)

Backend env: `sorento_crm_backend/.env.ci-tests` (written by `scripts/cloud-env-setup.sh`).
Frontend env: `sorento_crm_frontend/.env.local` (gitignored) setting `NEXTAUTH_URL`,
`NEXTAUTH_SECRET`, `FASTAPI_INTERNAL_URL`, `NEXT_PUBLIC_API_URL`, `EXTERNAL_API_KEY`.

The freshly bootstrapped DB seeds reference data (roles including `superadmin`,
`salesperson`) but zero `users` rows, so two active users were created directly via
SQLAlchemy against the backend venv (bcrypt-hashed password, `status=ACTIVE`,
role assignment) rather than through the API, since every user-creation endpoint
refuses to set a password itself: one `superadmin` (used to log in and drive the
whole journey) and one `salesperson` (the second user picked as Salesperson in the
form). NextAuth's `authorize()` then calls the real `POST /api/v1/auth/login` for the
session token exactly as it does in production; no auth code path was touched or
bypassed.

## Business data seeded for the walk

Via the API as the seeded superadmin (not by hand-editing the schema): one developer
party (`projects.parties`), one brand, two open leads (`POST /project-sales/leads`).
The `projects` module (plus its `base`/`product`/`resources` dependencies) was
enabled for the default tenant via `POST /api/v1/system/modules/install` - a fresh
tenant has zero module rows, and the frontend sidebar (unlike the backend route
guard) does not show a module's menu group until it is installed and enabled.
`project_seed_service.run()` seeds the project/lead funnels and the `PRJ-`/`LEAD-`
numbering rules on backend startup, so no numbering rule had to be seeded by hand.

## Defects found

None. Every AC in the journey (AC-PF001 through AC-PF007, AC-PF033/034, AC-PF040/041,
AC-PF050/052/053/056/060, AC-PF080) matched on first pass.

## Note on AC-PF053 (already-linked refusal)

The create-mode Lead picker searches `outcome=open` leads only (AC-PF050), so a lead
already linked to another project is correctly absent from the dropdown and cannot be
selected by browsing a second time in the same tab - the UI is doing its job. The 409
this AC defends against is a race: two people have the create form open against the
same still-open lead, and the second submit loses. That race was reproduced faithfully
rather than routed around: the browser's create form was filled and the picker's own
dropdown used to select `LEAD-000002` while it was still open, then a second actor
(same superadmin, a second HTTP call standing in for "another salesperson") registered
a project against that lead first via the real API, and only then was the browser's
already-filled form submitted - landing on the exact 409 the UAC describes. No source
code was read around or modified to produce this.
