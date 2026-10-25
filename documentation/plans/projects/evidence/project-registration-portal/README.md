# PROJECT-REG-PORTAL browser pass (agent-browser, headless)

Branch head c8df57c6. Mirrors `laneboard/scripts/1849.md`. Sandbox DB `sorento_browse`, seeded by
`harness/seed_browse.py` (all names invented; admin `browse.admin@example.com`, portal contact
`Salesperson A` with agent code `SA-007`, slug `sa007slug`). Backend uvicorn :8000, frontend
`npm run dev` :3000 (`.env.local` not committed). CRM navigated by sidebar clicks from `/`
(Project Sales > Registrations, Project Sales > Projects); the portal was opened through the contact's
slug link with the contact's token in storage. No console errors or uncaught page errors in either
session.

Not run live: step 4 (AI Extract). No OpenAI key is configured in this sandbox. The AI Extract button and
dialog open (file / paste-from-clipboard dialog, AI Extract button disabled until input); fields were filled
by hand with the script's values (title, Developer, Mukim, Type of building "Factory / industrial").

| Step | Screenshot | Result | Observed |
|---|---|---|---|
| 2-3 New Project Registration, field order, Sales agent | 01-portal-new-form-1280.png | PASS | Order: Project title, Distributor name, Sales agent, Customer name, Type of building, State, Mukim, Your ref, Developer, Main contractor, Architect. Sales agent disabled, shows `Salesperson A` (not `SA-007`). No Attachments card. |
| 5 State empty then Submit | 02-state-required-refused-1280.png | PASS | Submit opens the confirm dialog; confirming shows toast `Missing 1 required field: State`; no POST sent. |
| 6 Pick Johor, debtor "Debtor One Sdn Bhd", Distributor D, Submit | 03-portal-pending-readonly-1280.png | PASS | POST create + POST submit 200; card shows `Pending`; form fully disabled; no PPF shown; no Comments tab; page shows `Possible duplicate: PPF2610001 KILANG ALPHA LOT 9001 MUKIM TEBRAU` (code and title, no link). Minor: a disabled "Save as draft" button and a "Revision history" heading remain on a pending registration. |
| 7-8 CRM Registrations list | 04-crm-registrations-list-1280.png | PASS with note | Sidebar Project Sales > Registrations. Columns Date, Project title (truncated), Developer, State, Sales agent (`Salesperson A`), Possible duplicate (link), Status (`Pending`). Date 25/10/2026. With the sidebar open at 1280 the last columns (Possible duplicate, Status) sit behind the grid's horizontal scroll. |
| 10 Possible duplicate link | 05-duplicate-link-opens-project-1280.png | PASS | Link `PPF2610001 KILANG ALPHA LOT 9001 MUKIM TEBRAU` opens `/project-sales/<id>`, that project's page. |
| 11 Review page | 06-crm-review-page-1280.png | PASS | Metadata line Date 25/10/2026, Sales agent Salesperson A, Distributor, Customer, Your ref; `Possible duplicate:` link line; ProjectForm prefilled (title, Developer matched to party, State Selangor, Mukim); Salesperson prefilled with the linked CRM user; foot CTAs Approve and Reject; no Check / Join / Dispute. |
| 11 Approve exact title + same developer | 07-approve-exact-duplicate-409-1280.png | PASS | POST approve 409; message `PPF2610001 already has this developer and title. Change the title, e.g. add the phase.`; stays on the form; registration stays Pending; next approval got PPF2610003, so no number was used. |
| 12 Add ` PHASE 2`, Approve | (list returns) | PASS | POST approve 200, back to the list, row gone from Pending. Project `PPF2610003`. |
| 13 Clear Developer, Approve | 08-approve-no-developer-error-1280.png | PASS | `Developer is required.` under the field; no POST. |
| 14 Pick developer + Project type, Approve | (list returns) | PASS | POST approve 200, returns to the list. |
| 15 New project | 09-new-project-ppf-state-mukim-1280.png, 10-edit-details-state-mukim-1280.png | PASS with defect D1 | Code `PPF2610004` (PPF + 26 + 10 + 004); Owner `Salesperson A`; DB `sales_profile` state Johor, mukim Tebrau; Edit form Details shows State Johor and Mukim Tebrau. The project overview page does not show State or Mukim (D1). |
| 16 Portal list after approval | 12-portal-list-statuses-1280.png, 13-portal-list-view-1280.png | PARTIAL, defect D3 | Both approved rows show `Approved`. The PPF number is in the API (`ppf_no`) and on the opened registration (`PPF2610003`), but the list cards (board and list view) do not show it. |
| 17 Reject with `Already registered` | 11-reject-dialog-blank-disabled-1280.png, 14-portal-rejected-editable-1280.png | PARTIAL, defect D2 | Reject dialog: Reject disabled until a reason is typed; POST reject 200. Portal: `Rejection reason: Already registered` shown, form editable, Submit works and returns it to Pending with the reason cleared (DB confirms). But the status badge reads `Draft` on the list card and the detail, not `Rejected`. |
| 18 375px: new form, list, review | 15-portal-new-form-375.png, 17-portal-list-375.png, 18-crm-registrations-list-375.png, 19-crm-review-375.png, 20-crm-review-foot-375.png | PASS | No horizontal page overflow (scrollWidth equals clientWidth); form single column, sales agent read-only; CRM list scrolls inside its card; review stacked, Approve and Reject full width at the foot. |

## Defects found (implementation, not fixed here)

- D1 `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/ProjectDetailClient.tsx:328` area:
  "The development" card has no State or Mukim Fact, so the new project's detail page never shows them (CRUD
  standard: the view renders every section). Values are stored and shown in the edit form.
- D2 `sorento_crm_frontend/app/(auth)/portal/lib/landing-fields.ts:85` (`submissionStatusLabel`) and
  `sorento_crm_frontend/app/(auth)/portal/components/PortalLanding.tsx:152` and `:172` (`statusVariant`,
  `statusCardClass`): `is_draft` is checked before `status`, and the backend sends `is_draft: true` for a rejected
  registration, so it shows `Draft` with a neutral card instead of `Rejected` (the script expects `Rejected`).
  The detail page badge has the same cause. The list card does show the reason in red.
- D3 `sorento_crm_frontend/app/(auth)/portal/lib/landing-fields.ts:46`: the `project_registration` landing fields
  are title, developer, state; `ppf_no` (already in the list payload) is not rendered, so an approved card shows no
  PPF number. The script expects it on the list.
- Minor: a rejected registration offers "Delete draft" in the portal; the backend delete rule is drafts only
  (not exercised here).
- Harness note: the people picker lists only users holding a role, so the seeded linked CRM user needed the
  `salesperson` role for Salesperson to prefill. A real linked staff user has one.

## Round 3 final pass (head 65e36bb7, LIVE AI Extract and live embeddings)

Fresh `sorento_browse` DB, `harness/seed_browse.py` updated: it seeds both approver roles named by the
migration's `APPROVER_ROLE_NAMES` before running the migration's own `upgrade()`, so the grant is the
migration's doing, and gives the approver user (`browse.approver@example.com`) the Project Sales
Coordinator role only (not admin, not manager). The role also holds `projects.projects.view/edit/manage`
and `projects.parties.view`, as a real manager or coordinator would (without `projects.parties.view` the
Developer, Architect and Main contractor selects read "No access" for that user: noted, not a defect).
The key was passed as a process env var (`OPENAI_API_KEY=dummy`, proxy-injected); `.env.browse` is not
changed. Embeddings: `scripts/seed_project_embeddings.py` queued 3 projects, processed with
`process_embedding_queue_item`, `embedding_chunks` holds 3 current `project` rows. An approved project
`CADANGAN KILANG 2 TINGKAT DI ATAS LOT 9001 MUKIM TEBRAU JOHOR BAHRU` was seeded near the pasted title.
Console and page-error checks clean in both browser sessions (portal, CRM).

| Step | Screenshot | Result | Observed |
|---|---|---|---|
| Live AI Extract, pasted CADANGAN text | r3-01-ai-extract-pasted-text-1280.png | PASS | Dialog proposes Project title (the pasted text), Type of building `Factory / industrial`, State `Johor`, Mukim `TEBRAU`, Developer `ALPHA PACKAGING SDN BHD` (upper case as pasted; the script writes it mixed case). After Confirm and prefill every field is filled and editable. |
| Live AI Extract, Pillow-rendered PNG of the same text | r3-04-ai-extract-png-1280.png | PASS | Same proposal from the image: title (three lines joined), Factory / industrial, Johor, TEBRAU, developer. |
| Customer picker: pick only, agent's debtors only | r3-02-customer-picker-agent-debtors-1280.png | PASS | Typing `WALK-IN BUYER` + Enter + Tab leaves the field empty. The list offers `Debtor One Sdn Bhd` and `Debtor Two Sdn Bhd` only; typing `Foreign` (a seeded debtor of no agent) offers nothing. A pick fills the field and is saved (`Debtor Two Sdn Bhd` shown on the registration). |
| Submit, portal detail: Date and semantic duplicate | r3-03-portal-pending-date-duplicate-1280.png | PASS | Status `Pending`, read-only `Date` = `25/10/2026` (disabled), and `Possible duplicate: PPF2610003 CADANGAN KILANG 2 TINGKAT DI ATAS LOT 9001 MUKIM TEBRAU JOHOR BAHRU` named by the live embedding match (title differs in spelling and wording). |
| CRM list as Coordinator (non-admin) | r3-05-crm-list-coordinator-1280.png | PASS | Sidebar Project Sales > Registrations opens for a user holding only the Coordinator role: the migration's grant works. Sales agent `Salesperson A`; the live duplicate shows in the Possible duplicate column. |
| Duplicate link in the CRM | r3-06-crm-duplicate-link-opens-project-1280.png | PASS | The link opens `/project-sales/<id>` of `PPF2610003` (heading is that project's title). |
| Review form: legacy fields only | r3-09-review-legacy-fields-type-readonly-1280.png, r3-18-crm-review-375.png, r3-19-crm-review-foot-375.png | PASS | Shown: Developer, Type of building as read-only text `Factory / industrial`, Project title, State, Mukim, Architect, Main contractor, Salesperson; no project type, template, company, location, address, reference, value, dates, brands or lead. Metadata line and `Possible duplicate:` line above. Approve and Reject at the foot. |
| Exact duplicate refused with the link | r3-08-approve-exact-duplicate-existing-link-1280.png | PASS | Registration `TAMAN DELTA FASA 4` under Alpha Packaging, Approve: 409; the review page shows `Already registered as PPF2610002 TAMAN DELTA FASA 4`, the code and title is a link, and it opens that project's page. Nothing created. |
| Approve after a title change | (list returns) | PASS | `TAMAN DELTA FASA 4 PHASE 2` approved as `PPF2610004` (the refused attempt used no number; the possible duplicate never blocks). |
| Approve the pasted-text registration | r3-10-new-project-ppf-state-mukim-1280.png | PASS | `PPF2610005` (PPF + 26 + 10 + 005) although a semantic duplicate was named (never blocks). Project page shows State `Johor`, Mukim `TEBRAU`, Owner `Salesperson A`. |
| Reject with a reason | r3-11-portal-list-statuses-1280.png, r3-12-portal-rejected-editable-1280.png | PASS | Reason `Already registered`. Portal list card badge `Rejected` with the reason; the detail shows `Rejection reason: Already registered`, badge `Rejected`, form editable. Resubmitting returned it to Pending (used for the 375 review). |
| PPF on the portal list | r3-13-portal-list-view-ppf-1280.png | PASS with note | List view has a `PPF` column (`PPF2610004`). Board cards still show no PPF number (the detail does); unchanged from round 2. |
| 375px: portal new form, list, pending detail with Date | r3-14-portal-new-form-375.png, r3-15-portal-list-375.png, r3-16-portal-pending-detail-375.png | PASS | scrollWidth equals clientWidth on all three (375/375); single column, AI Extract button reachable, Date visible. |
| 375px: CRM list and review | r3-17-crm-list-375.png, r3-18-crm-review-375.png, r3-19-crm-review-foot-375.png | PASS | No page overflow (list 375/375, review 360/360 with the scrollbar); the list scrolls inside its card; review stacked with full-width Approve and Reject. |
| Downgrade | (not exercised in the browser) | n/a | Covered by the migration tests only. |

## Round 4 re-run (1c209d876)

Fresh `sorento_browse` DB (`scripts.bootstrap_env`, then `harness/seed_browse.py`, then `scripts/seed_project_embeddings.py` and
the queue processed; 3 `project` chunks). Backend with `OPENAI_API_KEY=dummy` as a process env var only (`.env.browse` unchanged),
frontend `npm run dev`. Portal opened by the contact's slug link with the token in storage; CRM as `browse.admin@example.com`,
reached by sidebar clicks (Project Sales > Registrations). Console and page errors clean in both sessions. All screenshots
under 100 KB. The registration table lives in the `projects` schema (`projects.project_registrations`).

| Check | Screenshot | Result | Observed |
|---|---|---|---|
| 1 Portal Date in Malaysia time | r4-02-portal-date-malaysia-1280.png | PASS | `submitted_at` set to `2026-10-24 17:30:00` (UTC, naive column); portal detail Date reads `25/10/2026` (Malaysia 01:30 on the 25th, the UTC date is the 24th). The CRM list and review show `25/10/2026` too. |
| 2 Board card heads with the PPF number | r4-06-portal-board-approved-ppf-1280.png | PASS | Approved card text is `Approved`, `PPF2610004`, `Customer: Debtor One Sdn Bhd`, `Oct 25, 2026`: the PPF number is the heading line, not the title. |
| 2 List view PPF column | r4-07-portal-list-view-ppf-1280.png | PASS | Headers `Form Number, Status, Project, Developer, State, PPF, Created`; row `PPF2610004, Approved, ..., PPF2610004`. Form Number also carries the PPF code. |
| 3 State required, then submit Pending | r4-01-state-required-refused-1280.png | PASS | Toast `Missing 1 required field: State`, no POST. After Johor: POST create 200 + submit 200, card `Pending`, form read-only, `Possible duplicate: PPF2610001 KILANG ALPHA LOT 9001 MUKIM TEBRAU`. |
| 3 CRM Registrations list | r4-03-crm-registrations-list-1280.png | PASS | Columns Date, title, Developer, State, Sales agent, Possible duplicate (link to `/project-sales/<id>`), Status `Pending`. |
| 3 Review form, legacy fields only | r4-04-crm-review-1280.png | PASS | Developer (typed `Gamma Builders Sdn Bhd` shown as hint), Type of building, Project title, State, Mukim, Architect, Main contractor, Salesperson; metadata line and `Possible duplicate:` link; Reject and Approve at the foot. |
| 3 Exact duplicate refused | r4-05-exact-duplicate-refused-1280.png | PASS | Developer Beta Holdings with the existing title: POST approve 409, `Already registered as PPF2610001 KILANG ALPHA LOT 9001 MUKIM TEBRAU`, the code and title is a link to that project; registration stays Pending. |
| 3 Approve with PPF code | (list returns) | PASS | Title ` PHASE 2` added: POST approve 200, back to the list; project `PPF2610004`, registration `approved` with `project_id` set. |
| 3 Reject, portal Rejected and editable | r4-08-portal-list-rejected-1280.png, r4-09-portal-rejected-detail-editable-1280.png | PASS | Reject dialog: button disabled until a reason is typed; POST reject 200. Portal detail: `Rejection reason: Already registered`, badge `Rejected`, fields editable, `Submit project registration` offered. |
| 4 375px portal | r4-10-portal-rejected-detail-375.png, r4-12-portal-list-375.png, r4-13-portal-new-form-375.png | PASS | scrollWidth equals clientWidth (375/375) on the new form, list and rejected detail. |
| 4 375px CRM list | r4-11-crm-registrations-list-375.png | PASS | 375/375, no page overflow. |

Notes (not defects): the portal's `Possible duplicate:` line is plain text (no link); only the CRM shows a link. The board card's
date is the created date (`Oct 25, 2026`), not `submitted_at`; the 17:30 UTC test row did not shift it because it is a different field.
Harness run note: the list-view `New Project Registration` control is a button there and a link on the board.
