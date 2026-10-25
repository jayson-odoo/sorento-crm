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

## Round 5 rework pass (4f41b208)

Registrations are now projects (owner ruling 25 Oct 17:50): a portal registration is a `projects.projects` row with
`approval_state = pending` and no code. Fresh `sorento_browse` (`scripts.bootstrap_env`, `alembic upgrade head` at
`prreg_0001_project_registrations`, then `harness/seed_browse.py`). The harness was updated for the new storage: no
registration table; the Coordinator approver holds the role from `APPROVER_ROLE_NAMES` plus project view / edit and
`projects.parties.view` only (the old `manage` grant is dropped); a viewer user (`browse.viewer@example.com`, project
view and parties view, no approve slug) is added for check 5. Backend and frontend run as in the brief
(`OPENAI_API_KEY=dummy` as a process env var; `.env.browse` unchanged, `git diff --quiet` holds). CRM reached by sidebar
clicks (Project Sales > Projects, which is the Pipeline at `/project-sales/pipeline`); portal by the contact's slug link.
Two CRM sessions (Coordinator, viewer) and one portal session; all closed by name.

**Environment limit, read first.** The proxy-injected OpenAI account returned `429 insufficient_quota`
(`credit_balance_exhausted`) for both `chat/completions` and `embeddings` from about 12:34 UTC. The seed's embeddings
were made live a few minutes earlier, then the credit ran out. So:
- Live AI Extract could NOT be run. The pasted text (paste event, saved as a .txt) went to `POST /public/portal/ai-extract`
  and came back 502 `AI provider call failed: Error code: 429 ... credit_balance_exhausted`; the dialog shows that message
  (r5-02). Form fields were typed by hand. AI Extract: BLOCKED (not a product failure).
- For the possible-duplicate display, the backend was started through a process-local launcher that swaps the embedding
  POST for a deterministic hashed bag-of-words vector (`harness/hash_embed.py`, 1536 dims, nothing in the repo changed) and
  the three approved projects were re-embedded the same way. So the duplicate lines below prove the wiring, the threshold
  and the links, not live semantic quality (calibrated earlier, rounds 3 and 4).

| # | Check | Screenshot | Result | Observed |
|---|---|---|---|---|
| 1 | Portal new form: legacy fields, Sales agent name | r5-01-portal-new-form-1280.png | PASS | Fields: Project title, Distributor name, Sales agent (disabled, `Salesperson A`), Customer name, Type of building, State, Mukim, Your ref, Developer, Main contractor, Architect. No attachments, no extra fields. |
| 1 | AI Extract live on a pasted title | r5-02-ai-extract-provider-quota-1280.png | BLOCKED | Provider 429 insufficient_quota, 502 to the browser, message shown in the dialog. See above. |
| 1 | Customer pick-only, agent's debtors | (r5-01 flow) | PASS | Typing `WALK-IN BUYER`, Enter, Tab leaves the field empty; typing `Debtor` offers `Debtor One Sdn Bhd DEB-A1` and `Debtor Two Sdn Bhd DEB-A2` only; a pick fills it. |
| 1 | State required refusal | r5-03-state-required-refused-1280.png | PASS | Submit, confirm: toast `Missing 1 required field: State`; no create / submit POST. |
| 1 | Developer required refusal, then submit | r5-06-developer-required-refused-1280.png | PASS | Toast `Missing 1 required field: Developer`; no POST. After typing the developer, create 200 + submit 200, status Pending. |
| 1 | Date in Malaysia time | r5-04-portal-pending-date-duplicate-1280.png | PASS | Read-only `Date` `25/10/2026`. With `submitted_at` set to `2026-10-24 17:30:00` (UTC) the portal still reads `25/10/2026` (Malaysia 01:30 on the 25th). |
| 1 | Possible duplicate named | r5-04 | PASS with note | `Possible duplicate: PPF2610003 CADANGAN KILANG 2 TINGKAT DI ATAS LOT 9001 MUKIM TEBRAU JOHOR BAHRU` (code + title, plain text). Substitute embedding, see above. |
| 6 | No Registrations in the sidebar | r5-07-sidebar-no-registrations-1280.png | PASS | Project Sales group (Coordinator and viewer): Projects, Leads, Awaiting Acceptance, My Tasks, Stock Claims, AutoCount Differences, Parties. No FE reference to a registrations route remains (grep). |
| 2 | Board: pending in "Awaiting approval" lane | r5-08-board-awaiting-lane-1280.png | PASS | Lanes before the stages: `Awaiting approval` (count 2 with two pending) and `Rejected` (0, `Nothing rejected`). The pending card reads `Awaiting approval` where the PPF code would be, then the title and `Salesperson A`. |
| 2 | Drag a pending card into a stage | r5-08 | PASS | Card `<li draggable="false">`, no grab cursor (approved cards `draggable="true"`). `drag` onto the Identified lane: no non-GET request, DB row unchanged (`pending`, no status). |
| 2 | Grid view pill + code label | r5-09-grid-pills-1280.png | PASS | Code cell `Awaiting approval` (a link), Stage cell pill `Awaiting Approval`; approved rows show `PPF2610001` and `Registered`. Note: Developer is `-` for a pending row (the typed developer is not shown). |
| 3 | Header as Coordinator | r5-10-detail-header-approver-1280.png | PASS | `Reject`, `Edit`, `Approve` in the header; code label `Awaiting approval`, badge `Awaiting Approval`. |
| 3 | Read-only line + duplicate link | r5-10 | PASS with note | `Date 24 Oct 2026, Sales agent Salesperson A, Distributor Distributor Delta Trading, Customer Debtor One Sdn Bhd, Your ref REF-R5-01`; `Possible duplicate: PPF2610003 ...` is a link to that project. Note D1 below (Date). |
| 3 | Approve with no developer | (toast read from the page text) | PASS | `POST .../approve` 422, toast `Pick the developer before approving.`; stays pending. |
| 3 | Edit: "Typed:" hint, pick developer, save | r5-12-edit-typed-developer-hint-1280.png, r5-13-detail-after-edit-developer-1280.png | PASS | Edit page shows `Typed: Gamma Builders Sdn Bhd` under Developer (empty select); picking `Gamma Builders Sdn Bhd` and Save: PUT 200, back on the detail, still pending with the three buttons. |
| 3 | Approve | r5-14-approved-ppf-code-1280.png, r5-15-board-after-approve-1280.png | PASS | `POST approve` 200; header code `PPF2610004` (PPF + 26 + 10 + 004), stage `Registered`; Approve / Reject / Edit gone. Board: `Awaiting approval` 2 to 1, `Registered` 3 to 4. |
| 3 | Edit blocks an exact duplicate before Approve | r5-16-edit-clash-blocks-save-1280.png | OBSERVATION | Picking `Alpha Packaging Sdn Bhd` on a pending `TAMAN DELTA FASA 4` opens the edit form's clash panel `Already registered to someone else` (PPF2610002) and disables Save (`Blocked by an existing project`). So the 409 below cannot be reached from the UI by saving the party; it was reached by setting `developer_party_id` in the DB (allowed by the partial index). |
| 3 | Exact duplicate on Approve | r5-17-approve-exact-duplicate-409-1280.png | PASS | `POST approve` 409; alert `Already registered as PPF2610002 TAMAN DELTA FASA 4`, the code and title is a link to `/project-sales/<id of PPF2610002>`; project stays pending, no number drawn (next approval was not needed). |
| 4 | Reject dialog, blank reason | r5-18-reject-dialog-blank-disabled-1280.png | PASS | `Reject this registration`, Reason textbox, `Reject` disabled until text is typed. |
| 4 | Reject, "Rejected" lane | r5-19-rejected-detail-reason-1280.png, r5-20-board-rejected-lane-1280.png | PASS | `POST reject` 200; detail shows `Reason for rejecting: Already registered`, no Approve / Reject; board `Rejected` 1, `Awaiting approval` 0. Note D2 below. |
| 4 | Portal shows Rejected + reason, editable | r5-21-portal-board-statuses-1280.png, r5-22-portal-rejected-editable-1280.png | PASS | Board card `Rejected TAMAN DELTA FASA 4 ... Already registered`; detail badge `Rejected`, `Rejection reason: Already registered`, every field editable, Date shown. |
| 4 | Resubmit, back in the lane | r5-23-board-resubmitted-back-in-lane-1280.png | PASS | Title changed to `... PHASE 2`, submit 200; DB `pending`, `reject_reason` cleared; board `Awaiting approval` 1, `Rejected` 0. |
| 5 | User without the permission | r5-24-detail-no-approve-viewer-1280.png | PASS | `browse.viewer@example.com` (project view + parties view): the pending card shows on the board; the detail has a `Read only` tag and no Approve, Reject or Edit (page text contains neither word). |
| 7 | 375 px portal form + list | r5-25-portal-new-form-375.png, r5-26-portal-list-375.png | PASS | scrollWidth equals clientWidth (375/375) on both. |
| 7 | 375 px board | r5-27-board-375.png | PASS | 360/360 (scrollbar), lanes scroll inside the page; pending card reachable. |
| 7 | 375 px project detail header | r5-28-detail-header-375.png | PASS | 360/360; Reject (180-244), Edit (252-302) and Approve (267-344, second row) all inside the viewport; the read-only Date / Sales agent / Distributor / Customer / Your ref card and the duplicate link stack in one column. |

Console and page errors: no uncaught page errors in any session. Console noise only: Fast Refresh logs, `JWT token extracted`
debug lines and one `[tiptap warn] Duplicate extension names found: ['link']` on the project pages (not from this change).
The 422 and 409 above are the intended refusals.

### Findings (implementation, not fixed here)

- D1 `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/ProjectDetailClient.tsx:519`:
  `Fact label="Date" value={formatDate(project.submitted_at)}` uses the browser's zone; the portal uses Malaysia time. For
  the same `submitted_at` (`2026-10-24 17:30` UTC) the portal reads `25/10/2026` and the CRM `24 Oct 2026` in a UTC browser.
  `formatDateInMalaysia` (`lib/helpers.ts:330`) is what the sample-request screens use. Not visible to a browser already in
  Malaysia.
- D2 Same file, the approve error alert: after a refused Approve (409) the alert `Already registered as PPF... ` stays on
  the page after the project is then rejected (r5-19 shows it under the reason). It should clear on a successful decision.
- D3 Rejected projects show the code label `Awaiting approval` in the header and on board / grid cells where a rejected
  project is no longer awaiting; the badge says `Rejected`. Wording, low priority.
- Observation: the grid's Developer column is `-` for a pending row (typed developer name is not shown); the Coordinator's
  `Project type` select reads `No access` on the edit form (the role has no project-type view).
- Observation (r5-16): the edit form refuses to save a developer that makes a pending project an exact duplicate of an
  approved one, so the Approve 409 is reachable from the UI only for a pending-vs-pending pair. Matches the UAC's wording
  only if the 409 was meant as a backstop.
- Harness note: `harness/hash_embed.py` is the process-local embedding substitute used because the OpenAI credit ran out.

## Round 6 final smoke (bba1e66f11)

Head `bba1e66f11`. Fresh `sorento_browse` (`scripts.bootstrap_env`, `alembic upgrade head`, `harness/seed_browse.py`, then
`scripts.seed_project_embeddings` drained with the hash embedding substitute). Backend through a process-local launcher that
installs `harness/hash_embed.py` (`OPENAI_API_KEY=dummy` as a process env var; `.env.browse` unchanged, `git diff --quiet`
holds); frontend `npm run dev` with an uncommitted `.env.local`. Harness unchanged. CRM as the Coordinator
(`browse.approver@example.com`), reached by sidebar clicks (Project Sales > Projects); portal by the contact's slug link.
**AI Extract was skipped**: the sandbox provider quota was exhausted in round 5 and the hash launcher does not cover chat; fields were typed by hand.
Both sessions (`r6c`, `r6p`) closed by name; servers stopped.

| # | Check | Screenshot | Result | Observed |
|---|---|---|---|---|
| 1 | Portal required refusal | r6-01-state-required-refused-1280.png | PASS | Submit and confirm with State empty: toast `Missing 1 required field: State`, no create or submit POST. |
| 1 | Portal submit, Pending | (flow) | PASS | After State, Johor and a picked debtor: POST create 200 + submit 200, card `Pending`. |
| 1 | Date in Malaysia time | r6-02-portal-pending-date-1280.png | PASS | `submitted_at` set to `2026-10-24 17:30:00` UTC; portal read-only `Date` reads `25/10/2026`. CRM detail (below) also reads `25/10/2026` (round 5 D1 is fixed). |
| 2 | Board lane and count | r6-03-board-awaiting-lane-1280.png | PASS | `Awaiting approval` count 1 with the card (`Awaiting approval` in the code slot, title, `Salesperson A`); `Rejected` lane 0. |
| 2 | Grid pill | r6-04-grid-pills-1280.png | PASS | Row `Awaiting approval` / stage pill `Awaiting Approval`; Developer cell now reads `Typed: Gamma Builders Sdn Bhd`; approved rows `Registered`. |
| 2 | Approval filter | r6-05-approval-filter-1280.png | PASS | Filters > Approval offers `Awaiting approval` and `Rejected`; choosing Awaiting approval narrows 4 rows to 1. |
| 3 | Coordinator header | r6-06-detail-header-coordinator-1280.png | PASS | `Reject`, `Edit`, gear, `Approve`. |
| 3 | Delete not offered | r6-07-project-actions-no-delete-1280.png | PASS with note | The gear menu has zero items (no Delete, no Edit project, no Reassign). Note N1. |
| 3 | Tabs offer no Add buttons | r6-08-documents-tab-1280.png | FAIL (one tab) | Stakeholders, Tasks, Quotations, Samples, Sponsorships, Orders, Activity: no add control (empty states only; Sample requests reads `You don't have access`). Documents shows `Upload documents`. Defect F1. |
| 3 | Edit to an exact-duplicate developer, Save not blocked | r6-09-edit-duplicate-save-not-blocked-1280.png | PASS | Developer `Alpha Packaging Sdn Bhd` on `TAMAN DELTA FASA 4`: no `Blocked by an existing project` text, PUT 200, back on the detail, still pending. |
| 3 | Approve gives 409 with link | r6-10-approve-409-existing-link-1280.png | PASS | `POST .../approve` 409; alert `Already registered as PPF2610002 TAMAN DELTA FASA 4`, a link to `/project-sales/<id of PPF2610002>`. |
| 3 | Title change, Approve, PPF | r6-11-detail-after-title-edit-alert-1280.png, r6-12-approved-ppf-code-1280.png | PASS | After the title edit (`... PHASE 2`) the 409 alert is already gone (r6-11). Approve 200: code `PPF2610004`, `Registered`, no Approve / Reject / Edit; `Already registered as` count 0. |
| 3 | Alert clears on Reject | r6-13-rejected-detail-alert-cleared-1280.png | PASS | A second pending project (same title) edited to Alpha, Approve 409, then Reject: the alert is gone from the Rejected detail (round 5 D2 is fixed). |
| 4 | Reject with reason, Rejected lane, code slot | r6-13, r6-14-board-rejected-lane-1280.png | PASS | `POST reject` 200 after typing a reason (button disabled while blank); header code slot reads `Rejected`, badge `Rejected`; board `Rejected` 1, `Awaiting approval` 0, card code slot `Rejected`. |
| 4 | Portal shows Rejected, resubmit | r6-15-portal-board-statuses-1280.png, r6-16-board-resubmitted-back-in-lane-1280.png | PASS | Portal card `Rejected ... Already registered`; detail shows `Rejection reason`, fields editable. Title changed to `... PHASE 3`, submit 200, DB `pending`, board `Awaiting approval` 1, `Rejected` 0 (the board needs a reload to show it). |
| 5 | 375 px board | r6-17-board-375.png | PASS | 360/360 (scrollbar), lanes scroll inside the page. |
| 5 | 375 px project header | r6-18-detail-header-375.png | PASS | 360/360; Reject (180-244), Edit (252-302), Approve (267-344, second row) all inside the viewport. |

Console and page errors: `errors` empty in both sessions, no `[error]` console lines. Console noise only: Fast Refresh, i18next debug
and `[tiptap warn] Duplicate extension names found: ['link']` on project pages (not from this change). The 409 and the 422-style refusals are the intended ones.
Not checked this round: the portal / CRM `Possible duplicate:` line (the new pending rows were not embedded because the API process does not run the embedding worker here).

### Findings (implementation, not fixed here)

- F1 `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/ProjectDocumentsPanel.tsx:213`: the `Upload documents` toolbar
  button is gated on `project.can_edit` only, so a Coordinator sees it on a pending or rejected project, unlike the other tabs' add buttons
  (gated in `bba1e66f11`). Gate it on the same approved-or-manager rule.
- N1 `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/ProjectDetailClient.tsx:294`: for an approver on an unapproved project
  with no manage grant, every `DetailActionsMenu` item is excluded, so the gear opens an empty menu (r6-07). Render the menu only when it has an item.
