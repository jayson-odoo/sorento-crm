# PLAN: PORTAL-P4-REQUESTS, MY REQUESTS opens the staff pages with server-side "only theirs" (28 Oct 2026)

Status: Build. Card v1 answered (28 Oct ~14:3x: Q1 a, Q2 a, Q3 a, Q4 follow the revision setting, Q5 c all 9 kinds); card v1.1 (5 extra kinds, Q6-Q8) filed 28 Oct, pending. S0 red tests (4 forms) in progress. Throwaway DB sorento_pp4_throwaway + .env.ci-tests (redis idx 2). Track: full (RBAC + permission slugs migration + new write surface), security review required. Size L, LEAD pattern. Lane PORTAL-P4-REQUESTS, draft PR #1953, stacked on #1944 (PORTAL-P3-ROLE-MENU); this PR merges right after it.

Source: `PLAN-portal-p3-role-menu-28oct.md` (open MY REQUESTS decision), PR #1944 crew-note 6461917897, owner
28 Oct ~14:1x option (b), owner requirement 28 Oct ~14:2x (end-to-end exactly like the portal, card section
"End-to-end flows").

## Goal

A salesperson's MY REQUESTS > Stock Inquiry / Complaint / Purchase Request / Sponsorship Form opens the STAFF page
for that form (list, detail, edit, new), showing only their own rows, enforced on the server. Create, save as draft,
submit, revise, comments and attachments behave exactly like the portal because they run the portal's own code.
Everything after submit is unchanged. Staff and admin: no change.

## Rule (card; Q1 pending)

LIMITED in a form = holds its `view_own`, not its `view` (P2 rule, `app/services/own_scope.py:41-49`). Admin and
superadmin are never limited. "Theirs" = `contact_id` = `me().contact_id` (`own_scope.py:59-69`); no linked contact =
nothing. Space is not matched (dev: one space for all 620 rows); create stamps the contact's workspace space.

## Architecture (fixed before code)

Layer: the owned-row rule lives in ONE place on the server (`own_scope.request_clause` + one router dependency per
form router); the write path lives in ONE place (the portal service, reused). No per-form copy of draft / submit /
revise logic, no FE-only hiding as the security boundary.

Server (shared slice S0, before the per-form slices):

1. Migration `pp4_0001_request_view_own` (insert-only, copies `pp2_0001_view_own_perms.py:23-71` and the grant shape
   of `pp3_0001_salesperson_grants.py:25-38`): slugs `procurement.stock_inquiries.view_own`,
   `complaint_management.complaints.view_own`, `procurement.purchase_requests.view_own`,
   `procurement.sponsorship_forms.view_own`, plus `projects.registrations.submit` (owned here for lane PROJECT-REGISTER-V2,
   its owner-ruled Q7 (b), 28 Oct; that lane's page only references the string); grant role `salesperson` those 5
   plus the 4 `.add` slugs. Registry
   mirror next to `permission_registry.py:1030-1058`. Dev SQL to `crew/state/migrations/PORTAL-P4-REQUESTS.sql`.
2. `own_scope.request_clause(model, me)` = `model.contact_id == me.contact_id`.
3. Staff routers (`procurement/stock_inquiries.py`, `procurement/purchase_requests.py`, `complaints/complaints.py`):
   a router dependency for a LIMITED user: list and detail (+ revisions) pass `contact_id=me.contact_id`
   (services already accept it: `procurement_service.py:5614-5625, 9222-9234`, `complaints_service.py:715-730`);
   a foreign id answers 404; every other staff route answers 403 (P2 `_own_scope.py` pattern). The complaints list
   accepts `view_own` next to `view` (`complaints.py:268`). Form comments accept `view_own` on an own row
   (`form_comment_service.py:46-51`).
4. Write surface for a LIMITED user, CONTRACT: router mounted at `/api/v1/my-requests` exposing the SAME paths,
   bodies and responses as the portal router (`public/portal.py`), so FE and tests reuse the portal shapes:
   `GET /requestor-options` (787), `GET /submissions/{kind}/{id}` (1058), revisions GETs (1076, 1197),
   `POST /submissions/{kind}/{id}/revise` (1098), `PUT|DELETE /submissions/{kind}/{id}/revision-draft` (1148, 1173),
   `POST /submissions/{kind}` (1223), `PUT /submissions/{kind}/{id}` (1235), `DELETE /submissions/{kind}/{id}` (1248),
   `POST /submissions/{kind}/{id}/submit` (1259), `GET|POST /attachments` (1369, 1549),
   `GET /attachments/{id}/download` (1497), `DELETE /attachments/{link_id}` (1756),
   `GET|POST /submissions/{kind}/{id}/comments`, `PATCH|DELETE .../comments/{comment_id}` (1652-1736).
   Kinds allowed in S0: `stock_inquiry`, `complaint`, `purchase_request`, `sponsorship_form`; any other kind 404 until
   card v1.1 is answered. Caller must hold `<kind>.view_own` and have a linked contact (else 403); create also needs
   the kind's `.add`. Staff (holders of `.view`) are refused (403): they keep the staff create.
   Identity = a transient, never-persisted portal identity
   (contact_id = `me().contact_id`, space_id = the contact's workspace space, `contact_impersonation.py:69-88`) passed
   to the SAME functions (`portal_service.create_or_update_draft` 1042, `submit_draft` 1089, `delete` ~1391,
   `portal_revision_service.revise` 1507). The portal code reads only `contact_id` / `space_id` off the token in these
   paths (grep: 27 / 17 uses; `token.id` 2, `expires_at` 3, `verified_at` 1, to be checked by the coder). Session =
   CRM session, so impersonation applies (`dependencies.py:182-238`).
5. Grid rules (owner, every grid; Q3): server sort for every column of the 4 lists, multi-select filters on
   Purchase Request / Sponsorship.

Frontend (per-form slices after S0; one coder each, parallel worktrees, folded by the lead):

- Menu: the 4 MY REQUESTS items point at the staff list routes (`config/menu.config.tsx:66-89`), gated on `view_own`;
  `/my-requests?type=<one of 4>` and `/my-requests/<kind>/<id>` redirect to the staff list / detail (deep links,
  P3 Q5 (b)); landing on a favourite among the 4 opens its staff list.
- List: unchanged component; Create gated on `.add` for a limited user, staff unchanged.
- New / Edit: the staff form; for a limited user staff-only fields hidden (card), Save as draft + Submit via the
  my-requests service, requestor picker from `my-requests/{kind}/requestor-options`, frozen on revise; Duplicate via
  `/new?from=<id>`.
- Detail: for a limited user the portal action set only (Q2); responses, status, comments, attachments and revision
  history visible (owner requirement 5).

## Slices (status 28 Oct)

| Slice | Scope | Red test | Fix | State |
| --- | --- | --- | --- | --- |
| S0-A | pp4_0001 + registry + own_scope REQUEST_KINDS / request_clause + staff router guard (`app/api/v1/_request_own_scope.py`) + comments read | 9841649735 | 9f1f74f29f | green 30/30 |
| S0-A2 | staff comments: limited user reads only (POST/PATCH 403); pp3 head test -> ancestry | 59935edb0f | 80cf000466 | green |
| S0-B | `/api/v1/my-requests` = portal routes from the CRM session (`public/portal.py:1281` register_submission_routes, `api/v1/my_requests.py:66` token adapter); fixture fixes 534f3a7b6e | 24a7e991c8 | 80cf000466 | green 86/87 (1 = S2 red); kill-proof posted |
| S-FE0 + S1 | shared FE (menu, redirects, myRequestsService, useRequestScope, comments) + Stock Inquiry FE + SI sort keys; test fixes 2c08f90e06, 137a2d6ca2 | 7413655e9f | c7f61dfa08 | green 75 FE + 16 BE; kill-proof posted |
| S2 | Complaint FE + complaint revision (adapter `portal_revision_service.py:624-700`, migration pp4_0002, staff revisions route, Revisions tab); test fixes bc3b12df8f | bee982f9f3 | cabc107a41 | green 58 FE + 43 BE; kill-proof posted |
| S3 | Purchase Request + Sponsorship FE + PR/SF sort keys; + own comment delete via my-requests (red 137a2d6ca2) | 8afda83c66 | 567f545163 | green 93 FE + 48 BE; kill-proof posted |
| S4 + S6 | Sample Request + Sales Opportunity (own portal routers registered on my-requests, staff guard, sort keys) + pp4_0001 grants for the extra kinds (no dealer_kit.page.view); test fixes cb84a4059a | c26c787622 | 25d2878e5d | green 33 FE + 67 BE; kill-proof posted |
| S5 | New Product Application (staff detail portal-shaped for a salesperson, portal rows editable via my-requests) | 88facc513f | 7872c6724d | green 31 FE + 32 BE; kill-proof posted |
| S7 | Price Tag on the Dealer Kit table + request page (`?edit=1`, `/new`); staff guard; sort keys | b074ecca37 | d54954b62a | green 31 FE + 36/37 BE (1 seeding bug, tester fixing) |
| S7b | price tag parity (crew answer a81067665 = (a)): share the portal's proof viewer, pinned-comment review, per-line combos/parts/promotions editor on the CRM request page; portal unchanged | tester running | - | - |
| S-ATT | salesperson attachments (own upload/delete immediate like the portal; staff uploads locked) | 2d07b537be | 76ea23c8af | green 23 FE (+16 BE guards); kill-proof posted |
| S8 | no embedded portal view in the CRM; `/my-requests` = landing redirect honouring the favourite star; no portal token in the CRM; deep links to staff pages | db8a85a639 | - | red 32 FE (29 pins) |

Dropped: Project Registration (owner v1.1 Q7: one Projects page, lane PROJECT-REGISTER-V2; P4 ships only
`projects.registrations.submit` + grant). Dev SQL: `crew/state/migrations/PORTAL-P4-REQUESTS.sql` (dry-run OK).
Known: `tests/test_record_action_endpoints.py` 3 failures pre-exist (fail with the S0-A patch reverted).
Follow-up for S2: `test_p4_14_revise_refused_for_a_complaint` flips when complaint revision lands (Q6).

## Known pre-existing gaps (not closed here, P3 Q4 accepted)

Staff PUT / DELETE / bulk delete on these 4 forms need sign-in only; PUT accepts `contact_id` / `space_id` / `status`
(`stock_inquiries.py:457-467, 785-794`, `schemas/procurement.py:1357-1358`, `schemas/complaints.py:214-217`).
Closed for limited users only (item 3).

## Acceptance criteria

`portal-p4-requests-acceptance-criteria.md` (written after the owner answers).

## Review round (28 Oct, head c001fdfd1b)

Reviewer NOT READY (2 major, 5 minor), security-reviewer FINDINGS (2 should-fix, 2 nits); crew-notes on #1953.
Fix round, red first:
- Hidden for a salesperson: SLA Tracking tab, complaint Fulfilment DOs tab (both 403 for view_own).
- D7 (crew answer a85478781 = (a)): salesperson "Delete draft" and "remove my attachment" become server-deferred
  actions `my_request.delete` (10s) / `my_request_attachment.unlink` (5s), DeferredActionButton, running the portal's
  own delete under the salesperson's identity. Portal and staff paths unchanged.
- Security: upload gate reads the form `kind` (query/form mismatch 422); impersonated comments record the admin;
  each my-requests kind gated on its own module; write-route enumeration test.
- Minor: portal link sales_opportunity/new -> list; attachment downloads via apiFetch + saveBlobAs (impersonation);
  usePermissions try/catch reverted, tests get a SessionProvider.

## Release notes (for the PR body)

- Complaint revision goes live in the PORTAL on deploy wherever the complaint `portal_revision_configs` row is ON
  with allowed statuses (dev copy: ON). Confirm the production row with the owner before the release dispatch.
- `projects.registrations.submit` is granted to salespeople but enforced only once PROJECT-REGISTER-V2 lands.
- Merging #1953 ships #1944 (P3) with it: #1944's head 9d6372f976 is contained.

## Merge note: #1961 (PROJECT-STAGES-SAMPLE) merges BEFORE #1953

Done 29 Oct in merge 3653b8a8d2: both form paths get `defaultProjectId`. R2 replaces `LimitedPurchaseRequestForm` with the
portal form, so R2 owns the limited-branch case: a salesperson opening `/sponsorship-forms/new?project_id=<own project>`
(the project Sponsorship stage action) lands on the portal form with that project seeded (owner (a), 29 Oct; see
"R3 architecture" below).

On the next main merge, `sponsorship-forms/new/page.tsx` and `PurchaseRequestForm.tsx` conflict. Resolution agreed with
that lane (PR #1953 crew-note 6470523547): keep #1961's async page (`searchParams.project_id`) inside the P4 Suspense
wrapper; the PurchaseRequestForm default-export wrapper passes `defaultProjectId` to BOTH the staff form (#1961 effect,
`getProject`, `selectedOption`) and `LimitedPurchaseRequestForm`; add one vitest for the limited branch; #1961 tests stay green.
#1961 tests that must stay green after that merge: FE `purchase-requests/components/PurchaseRequestForm.defaultProject.test.tsx`
(5 cases; mocks `getProject` from `@/app/(protected)/project-sales/_shared/services/projectService`),
`project-sales/[projectId]/components/ProjectDetailClient.test.tsx` (describe "the prod-shaped ladder"; routes
`/procurement-management/sponsorship-forms/new?project_id=` and `/project-sales/sample-requests/new?project_id=`),
`project-sales/[projectId]/components/ProjectStatusPill.test.tsx`; BE `tests/test_project_stages_ladder.py`.

## Hand test 1 FAIL -> form parity rework (owner 28 Oct ~22:50-23:10; crew answers Q1-Q5 all (a))

Parity table: #1953 crew-note 6472424819. Rule: a salesperson's create / edit / VIEW of every kind renders the PORTAL's
own form component inside the CRM page, through an injected client pointing at `/api/v1/my-requests`; the portal itself
is unchanged; staff list / detail / every action button unchanged (staff detail gains missing portal fields read-only);
complaint staff edit of root cause / resolution / technical response untouched and never a salesperson-side revision diff;
CRM keeps D7 deferred deletes. Canonical data = the portal's (price tag `debtor_code ?? customer_code`, `print_by='self'`;
opportunity amount as the portal form sends it): identical by construction once the same component is used.

| Slice | Scope |
| --- | --- |
| R1 | `SubmissionClient` injection (SF + children), CRM client, BE shared `/me` + `/lookups/*` + ai-extract on my-requests; SI + Complaint create/edit/view; delete MyStockInquiryForm + ComplaintForm limited branch |
| R2 | PR + Sponsorship (SF); staff detail read-only portal fields (External reference ...) |
| R3 | Price Tag (PriceTagRequestForm), NPA, Sample Request, Opportunity portal components; delete OwnPriceTagRequest + limited branches |
| R4 | side-by-side browser pass per kind (portal vs CRM + staff buttons), crew re-files hand test |

### Parity rework progress (checkpoint 28/29 Oct)

| Slice | Red | Fix | State |
| --- | --- | --- | --- |
| R1 shared SubmissionClient + SI + Complaint (salesperson renders the portal form; BE `register_profile_routes` /me + 5 lookups and ai-extract on my-requests) | a3943deeba | 97801a93d3 (+ test fixes e4b8c3df1c, 16b23b3589) | green (FE 3417, BE 1667 over portal / my-requests files); kill-proof posted 6482225526 (FE 38 red, BE 35 red); main merged 3653b8a8d2 (#1961, #1951); pushed 16b23b3589 |
| R2 PR + Sponsorship + staff PR detail External reference read-only + stage-action project seed (owner (a)) | abdc9de399 (red-proof 6482508557; test adj. 2f4ed1e6c4, 02b53d7e5f) | d1f50a135d | green (R2 38/38, FE 8989); kill-proof 6483276477 (28 red); pushed d1f50a135d |
| R3a NPA / Sample Request / Opportunity portal components (shared service-injection mechanism, SR stage-action seed, NPA `?stock_inquiry_id=` start) | 41d054b713 (red-proof 6486682988: FE 21 red, BE 43 parity pins green by design) | fe665cbe22 (+ test adj 9ddf9c8c25) | green (R3a 35/35, keep-green FE 9459, BE 51); kill-proof 22 red; main merged ac5faae57b (#1965, #1922), pp3_0001 re-parented onto unpaid_0001 (0fbb849f89); menu snapshot owes main's "Sales & outstanding" |
| R3b Price Tag portal component (delete OwnPriceTagRequest + dead S7/S7b pieces) | 0e37765831 (red-proof 6487351187: FE 15 red, portal pin 2 + BE 7 green) | bbd4e3a332 (+ red 8b5037b465 PAR-3 saved promotion, test adj aec20cb932) | green (R3b 17/17 + 2/2 + pin 2, keep-green FE 8092, BE 50) |

PAR-3 check per R3 kind (29 Oct, read of portal form vs staff detail by data key): Sample Request, NPA, Opportunity no
gap (NPA staff renders the same shared header and lines components). Price Tag: the line package (`combo_id`) is not
shown on staff, but the portal's own read view does not show it either and staff shows the parts it expands to, so no
gap; revision history is not a field (PAR-3 is fields) and staff price tag detail never had it, logged as a known gap;
the saved line promotion is the one real gap (staff names it only from today's live options, so an ended promotion
reads "-" while the portal shows its name), fixed in R3b read-only.
| R4 side-by-side browser pass (portal vs CRM + staff buttons), crew re-files hand test | - | - | todo |

#### R3 architecture (fixed before code, 29 Oct)

Measured 29 Oct at head 16b23b3589 (route table diff, `app.routes`): every portal FORM route is already mounted on
`/api/v1/my-requests` at the same relative path (72 of 72; the per-kind `register_*_routes` in
`public/portal_{sample_request,new_product_application,sales_opportunity,price_tag}.py`, mounted at
`my_requests.py:407-415`). Portal-only today, and staying so: landing `GET /submissions`, conversations,
customer-asks, ideas, OTP / token / logout / impersonation stop, slug-info. So R3 needs no new BE route.

FE: the four portal components call module services (`lib/sample-request-service.ts`,
`lib/new-product-application-service.ts`, `lib/price-tag-request-service.ts`, `lib/sales-opportunity-service.ts`)
that hard-code `/api/v1/public/portal` and `portalFetch`. One mechanism, R1's: each service module gains a
`make<Kind>Service(fetcher)` factory holding its functions, its named exports stay the portal instance (portal
callers and every `vi.mock` of those names unchanged), and the component reads the service from the injected client
(default = the module namespace, read at call time as R1 does). The CRM side builds each service over ONE fetcher,
`apiFetch` with the `/api/v1/public/portal` prefix swapped for `/api/v1/my-requests` (in
`services/myRequestsSubmissionClient.ts`). No per-kind CRM copy of any call.
BE: one parity test per R3 kind pinning PAR-6 (price tag customer `debtor_code ?? customer_code`, `print_by='self'`;
opportunity amount / qty / unit price as the portal sends them): the same body POSTed to the portal and to
my-requests stores the same row.
Owner ruling 29 Oct (answer to a26432800 = (a), Sponsorship AND Sample Request): a salesperson's stage action
(`ProjectDetailClient.tsx:117-121`, `?project_id=`) seeds project_id + project title into the PORTAL form on the CRM
page; portal unchanged, same payload shape, server gate unchanged. A 422 from the gate
(`sponsorship_contact_no_company` / `sponsorship_project_not_permitted`, `sponsorship_link_service.py:110-132`;
Sample Request `SAMPLE_REQUEST_PROJECT_NOT_ALLOWED`, `sample_request_service.py:273-276`) keeps today's toast with
the server's own message, on both portal and CRM (crew answer a27154084 = (c): CRM = portal behaviour; no inline
alert); one test pins that the toast carries the message text, never the code. Red-first: Sponsorship in R2, Sample
Request in R3; both in the R4 side-by-side pass.
Count (read-only, `sorento_cagent_stack` 15 Oct copy, `p4-salesperson-no-company-count.sql`): 31 salesperson
contacts, 0 with no linked company, 0 flagged (crew-note 6482381218).

Known unrelated: `PageHeader.inventory.test.ts` S5-05 flags main's `StockPositionGrid.tsx` (RELEASE5-FIX 8e56966136).
Dead after R1, delete in a cleanup slice: own-request mode of the SI / Complaint attachment sections; limited complaint branch in `FormRevisionsTab`.
