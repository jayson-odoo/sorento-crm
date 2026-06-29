# PLAN — Codebase + UI Audit & Guide Traversal (TODO master list)

**Status:** IN PROGRESS — started 2026-06-29, autonomous /loop session.
**Owner:** Claude (autonomous, user on the road ~1h+).

Three workstreams from the user's brief:

1. **Codebase audit** — security loopholes, bugs, improvements toward "capable SaaS for a listed company."
2. **UI traversal** — every page, mobile + desktop, flag sus / unfriendly / out-of-place UI.
3. **Guides** — user-facing + LLM-readable guides per module, especially **data-analysis oriented** ("list me X records from A→B, customer Y") so the AI assistant can help users query their own data.

This file is the living TODO. Findings get appended under each section with severity + file refs. We tackle items one by one after the sweep.

---

## Workstream 1 — Codebase audit

### 1a. Backend security  ✅ AGENT DONE
Ranked findings (verify each before fixing):

**CRITICAL**
- [x] ~~Secrets committed in `.env`~~ — **VERIFIED FALSE**: `sorento_crm_backend/.env` is gitignored and `git log --all` shows it was NEVER committed. Secrets are on-disk only, not in VCS. (Agent over-claimed.) No action beyond normal hygiene. loadtest `.env.example` is a template (empty/`changeme`).
- [ ] **CONFIRMED CRITICAL (grill-verified): `sorento_crm_backend/private_key.pem` IS tracked in git** (real PKCS8). NOT a sample — actively loaded by `app/services/cloudfront_signer.py:80-85` (`CloudFrontSigner`), `.env` has `CLOUDFRONT_PRIVATE_KEY_PATH=private_key.pem` + key-pair-id `K1NX8MQAUJBE7N` + domain `d1k6bbzmejl1no.cloudfront.net`. Anyone with repo access can forge signed CloudFront URLs → bypass file-access controls. Action: `git rm --cached`, gitignore, **purge history** (git-filter-repo/BFG), **rotate the CloudFront key pair**. Listed-co #1 item.
- [ ] **`app/dependencies.py:212`** logs full request headers (incl Authorization / X-API-Key) on auth-fail: `logger.warning(f"No token found. Headers: {dict(request.headers)}")`. Redact.

**HIGH**
- [x] ✅ DONE (branch `security/audit-hardening-20260629`, commit `6cbd5e4bc`) **`dependencies.py`** API-key compare → `hmac.compare_digest`. Tests: 21 external API-key route tests pass.
- [x] ✅ DONE **`main.py`** CORS `expose_headers` → `["Content-Type","Content-Length","Content-Disposition"]`.
- [x] ✅ DONE **`main.py`** global 500 handler → generic message; `str(exc)`/type only when `settings.debug`; full detail still logged server-side.

DECISIONS (user, 2026-06-29): security FIRST; private_key → purge history + user rotates AWS; slow-load → keep KPI on home + 30-day window + cache; commercial → REMOVE orphan scaffolding.
DONE this session (security branch): private_key.pem untracked + gitignored (commit `6cbd5e4bc`); CORS/exception/api-key fixes; RUNBOOK for history-purge + AWS rotation written (`docs/plans/RUNBOOK-purge-private-key-from-git-history.md`) — force-push left for user.
DONE: timezone −8h SLA log fix ✅ (commit `f108b8961`, 6 sites + regression test; 10 PRE-EXISTING unrelated SLA test failures on main noted separately).
DONE: windowed-KPI perf fix ✅ — `SLAKpiDashboardContent` gained `defaultWindowDays` prop; home `/` renders it with `={30}` (date_from/date_to forwarded to summary/tasks/trend), "Last 30 days" badge, 5-min staleTime cache; dedicated `/sla-management/kpi-dashboard` stays all-time. Build ✓, 5 vitest pass. FE rebuild+restart on :3000 still pending; browser-verify needs a `sla.kpi.view` user.
DONE: commercial module CODE restore ✅ commit `d80a18fd3` (13 model-layer files from SRT-10; ROUTER_PREFIX=None so UI/API stay gated; verified app boots, 24 commercial tables resolve for migrations, ZERO commercial routes mounted — also closed a latent UNAUTH `/public/commercial` exposure that would've activated when the package returned). Fresh-DB `alembic upgrade head` end-to-end still to be run on a throwaway Postgres (couldn't safely run vs dev).
DONE: log-hygiene ✅ commit `6fb5654d7` (no more header dump / token bytes in logs; forced-DEBUG gated on settings.debug).

**SECURITY-FIRST BATCH STATUS: substantively complete** on branch `security/audit-hardening-20260629` (5 commits). Remaining security backlog (lower priority): no HTTP rate limiting (bigger — defer w/ design), `lookup_binding_service.py` f-string SQL (MED, metadata-guarded — harden to literal_column), JWT-secret-length log line (minor), FE `dangerouslySetInnerHTML` audit + OrderLinesCard UUID inputs (FE). 
POST-SECURITY BATCH (branch `feature/post-security-batch`, plan+UAC grilled+user-approved):
- [x] **Item 1 UI/footer leaks** ✅ DONE+VERIFIED (commit `1602d2a20`). Demo mega-nav → Breadcrumb; footer = Support+copyright only (removed Docs/Outline, Purchase, FAQ, License). Browser-verified desktop+mobile, 0 console errors, top-bar utilities + sidebar intact, UAC1.1-1.6 pass.
- [x] **Item 5 — assistant Outline-URL leak** ✅ DONE+VERIFIED (commit on branch). Two layers: redact `url` from guide tool-result before LLM + post-filter `doc.foundryx.my` from answers (`outline_base_url` config-derived). 9 unit tests pass; agent live-verified 3/3 guide Qs; I browser-verified "how do i rename the file" → clean inline steps, NO Outline URL, in-app links preserved (UAC5.1/5.2/5.5 ✅). Bonus: confirmed the rename-guide Outline push is live (answer shows right-click steps).
- [x] **Item 3c (classifier-skip)** ✅ commit `40792e6b0` — `intent_is_record_class(has_record_context=False)` early-returns before any LLM call; record-open path byte-identical. 4 tests.
- [x] **Item 3b (turn-scoped keyed cache)** ✅ commit `f37f4652b` — `_TurnToolCache` keyed `sha256(user_id∥conversation_id∥turn_id∥tool∥sha256(args))`, fresh per turn; raw output cached so Outline redaction still runs. 10 tests incl. cross-user/conversation/turn isolation (UAC3b.2 security). Pyright clean.
- [x] **Item 4 capability + getting-started + publish safeguard** ✅ CODE DONE (committed). Deterministic `_build_capability_answer()` intercepts "what can you do" BEFORE any LLM call (browser-verified: friendly modules + example Qs, no slugs/UUIDs/Outline URL — UAC4.1/4.2). `getting-started-for-new-users.md` written (UAC4.3). Sync-script `HELD_FOLDERS={commercial}` + `_assert_no_held_folders()` RAISES if commercial in allowlist (UAC4.5, tested); `dry-run` subcommand added. 12 new tests pass.
  - ⏳ **LIVE OUTLINE PUSH = USER ACTION** (auto-mode denied the bulk external write — correct per review-gate). Dry-run verified: 63 docs, commercial HELD, getting-started + inventory/delivery/product/sla included. User runs: `! cd <repo> && set -a; . sorento_crm_backend/.env; set +a; sorento_crm_backend/venv/bin/python scripts/sync_user_guides_outline.py push`
- [x] **Item 3d eval harness** ✅ commit `6a28ab562` — `scripts/eval_assistant_routing.py` (132 guide questions → routed category + latency; `--check` diffs vs committed baseline, exits 1 on category/question drift; `--live` optional real-LLM). Baseline committed.
- [x] **Item 2 lookup SQL cleanup** ✅ commit `f82175983` — Core `select(col).where(col.isnot(None)).distinct()` off validated metadata, `except` narrowed to SQLAlchemyError, `_REGISTRY` fallback preserved; 3 tests incl. injection-rejection.

### ✅ POST-SECURITY BATCH COMPLETE (branch `feature/post-security-batch`)
All approved safe-set items done + verified, NO new test failures (105 pre-existing baseline = Python-3.14 sqlite env, not ours). Branch commits: pre-existing-checkpoint → docs → Item1(1602d2a20) → Item5 → Item3c(40792e6b0) → Item3b(f37f4652b) → Item4 → Item2(f82175983) → Item3d(6a28ab562).
**USER-GATED remaining:** (1) Outline push (command above), (2) `private_key.pem` history purge + AWS keypair rotation (RUNBOOK), (3) review + git push/merge of both branches, (4) DEFERRED (need own grilled plans): FE streaming, keyword-gate classifier replacement, admin-QoL roadmap (Workstream 4), commercial restore-to-UI vs keep-gated.
COMMERCIAL DECISION REVISED (user): migrations 151/152 IMPORT the deleted modules at upgrade() and BUILD tables from model metadata → fresh-DB alembic ALREADY fails today. So NOT a trivial delete. **User chose: RESTORE module CODE only from branch `SRT-10` (commercial_core + commercial_activity packages + their minimal backend dep closure), keep UI gated off (no FE pages, don't enable modules for default tenant).** Goal: `alembic upgrade head` works on fresh DB + backend imports. Run AFTER perf agent (serialize commits on the branch). Commercial guides can then publish once feature is actually enabled.
⚠️ Working-tree had pre-existing uncommitted changes NOT mine: `ai_assistant_service.py` (+`_current_date_directive()`), `role-list.tsx` (1-line). Left untouched — confirm provenance before committing.

**MEDIUM**
- [ ] **`app/services/lookup_binding_service.py:42-43`** f-string SQL with table/column from input. Guarded by metadata validation but switch to `literal_column`/quoting.
- [ ] **`guards.py:22-24`** `_tenant_id_for_request()` always returns DEFAULT_TENANT_ID — must add tenant filter at ORM layer BEFORE real multi-tenant onboarding or cross-tenant leak. (Listed-co blocker for multi-tenant.)

**LOW**
- [ ] **`app/main.py:34`** `app.dependencies` forced to DEBUG (logs token length + first 50 chars at dependencies.py:204-209). Guard with `settings.debug`.
- [ ] No HTTP rate limiting (SlowAPI). Add esp. to login / password-reset / portal-OTP.
- [ ] CORS origins: fail startup if `*` in prod.

### 1b. Backend bugs / reliability  ✅ AGENT DONE

**CRITICAL**
- [ ] **Timezone shift in SLA event logs** — `sla_service.py:2184, 3094-97, 3957-60, 3984-87, 4011-14, 4038-41` pass naive-UTC tracking datetimes (`due_at` etc.) straight into `create_event_log`, which treats naive as MYT(+8) → logs shift −8h. Wrap with `_to_aware_utc()`. Corrupts SLA audit/KPI. (Matches known CLAUDE.md gotcha — more sites found.)
- [ ] **Race in idempotent conversation-SLA create** — `sla_service.py:3345-3387` / `sla/sla_tracking.py:735-785`: gap between active-row query and commit; concurrent insert → IntegrityError caught as generic 500 instead of idempotent 200. Catch `IntegrityError`, re-query, return existing.

**HIGH**
- [ ] **Bare `except:`** in `order_service.py:1311,1317,1327` (`_parse_datetime`/`parse_decimal`) — swallows everything incl KeyboardInterrupt; silent import data corruption (bad date→None, bad decimal→0) with no log. Narrow to `(ValueError,TypeError,AttributeError)` + log offending row/value.

**MEDIUM**
- [ ] Post-commit side effects fragile — `_write_assign_event_log` / `_fan_out_assignment_coverage` after commit; failure → row without assign log / missed coverage notify. Consider RQ for fan-out; ensure best-effort+warn (per CLAUDE.md pattern).
- [ ] Respond-workspace default set: race on `is_default=true` partial unique → use ON CONFLICT / catch.

**LOW**
- [ ] `sla_service.py:33` `_utc_now_from_remote` bare except hides network issues — log.
- [ ] `order_service.py:1309-1328` date parse silent fail — log value.
- [ ] `lookup_eligibility.py:29` `query(LookupBinding).all()` unbounded — add limit.
- [ ] Possible N+1 in escalation/embedding list queries — profile, add `selectinload`.
- [ ] Refactor datetime duality: rename helpers (`_naive_utc_to_aware_utc` vs `_naive_myt_to_aware_utc`) to stop the recurring shift class of bug.

### 1c. Frontend bugs / UX / arch-rule violations  ✅ AGENT DONE
(Counts are agent estimates — verify scope before bulk refactor.)

**CRITICAL / HIGH**
- [ ] **UUID inputs in UI** — `order-management/orders/components/OrderLinesCard.tsx` asks user to paste Product/Warehouse UUIDs. Replace with searchable selects (userSelect-style). Violates "no UUIDs in UI" cursor rule.
- [ ] **Hand-rolled `response.json().catch(()=>({}))`** instead of `extractApiError` across ~40 service files (forms, orders, customers, order-statuses, marketing, system-mgmt…). Batch-refactor.
- [ ] **Manual `URLSearchParams`** instead of `buildDataGridParams` in ~14 list services (forms, customers, order-statuses, orders, marketing×4, system-mgmt×6). 
- [ ] **Native `confirm()`** (9): notifications-sheet, PromotionDetail (×2), ticket [id], inventory warehouses [id], workflow submission editor + definitions list, brands [id], UoM [id], portal ticket-draft. Replace with `ConfirmDeleteDialog`/`AlertDialog`.
- [ ] **DataGrid lists missing `tableLayout:{width:'fixed',columnsResizable:true}` + `columnResizeMode:'onChange'`** across most lists (only FormsList compliant). 

**MEDIUM**
- [ ] **`dangerouslySetInnerHTML` (13)** — chat-sheet/sheet-chat (message.text), ticket [id], email-outbox/outgoing-mails body, portal ticket-draft, activities notes. Audit each for sanitization; user-entered ones need DOMPurify.
- [ ] **Responsive headers** not wrapping (`flex items-center justify-between`) on FormDetail, CustomerDetail, OrderStatusDetail, OrderDetail, PromotionDetail. Apply `flex-col gap-3 sm:flex-row …` pattern.
- [ ] **Hidden empty section** — AccessAgentDetail description hidden when empty (`access-agents/components/AccessAgentDetail.tsx:239`). Render with empty state.
- [ ] Missing loading/error states in some dialogs (OrderLinesImportDialog etc.).
- [ ] `.env.local` `NEXT_PUBLIC_VAPID_PUBLIC_KEY` — VAPID public is fine but document intent.

NOTE: a `ticket-management` module exists in FE (not in sidebar menu.config) — verify it's intentional/gated.

### 1g. Bugs found while fact-checking guides (agent, 2026-06-30) — verify before fix

**Likely real bugs / dead UI:**
- [ ] **Marketing Campaign DELETE is a no-op stub** — `delete_campaign` returns success WITHOUT deleting. Violates ADR hard-delete standard. (Notable — silent data-non-deletion.)
- [ ] **Campaign status casing mismatch** — BE `CampaignStatus` UPPERCASE (`PLANNING/ACTIVE/…`), FE types lowercase union → filters/badges silently miss.
- [ ] **Email Outbox "Deferred" filter is dead** — FE + model docstring list `deferred`, but the drainer never writes it (rate-limited rows stay `pending`). Filter always returns 0.
- [ ] **Stock Inquiry "Updated" status filter** (`updated`) — no backend writer; vestigial option.
- [ ] **Complaints `resolved` + `draft` statuses** — appear in pill maps but CS-finalize only writes `processed_by_cs`/`closed`; no confirmed writer for `resolved`/`draft`.
- [ ] **Import Jobs badge config** lists never-emitted values — success is `finished` (not `success`/`completed`); also Import Jobs is PER-USER (`user_id==current_user`) so "all failed imports today" is unanswerable there (use Import Logs).

**Behavioral gotchas (documented in guides as caveats; mostly not bugs):**
- Product-Suppliers read-only in UI (BE has full CRUD); Stock Inquiry `quantity`/`delivery_date` are TEXT (no date math — use `created_at`); SPO Allocation has no business/PO date.
- Complaints UI "Assigned To" = latest unresolved SLA tracker assignee, but the list filter matches raw `complaints.assigned_to` column — mismatch source.
- User-Mgmt labels non-obvious: "AI Agents"=`access_agents` (access-control, NOT LLM), "Internal Users"=`contact_agent_access`, "Administrative Users"=`users`; `tier` overloaded (users vs agent_teams); Users/Roles use SOFT-trash (ADR hard-delete exception); 8 notify toggles must be in all 3 manual `UserResponse` builders.
- Minor: Promotion has no `name` (title=`description`); Product-Suppliers menu vs heading label drift; `notify_*_on_product_discontinued` singular vs FE "products" plural; Respond Outbox `business_id` dual UUID meaning.

### 1f. Security audit PHASE 2 (high-risk surfaces) — agent, 2026-06-30 — ⚠️ VERIFY/GRILL EACH BEFORE FIXING (some flagged "needs deeper check"; phase-1 had a false .env claim)

**CRITICAL (verify first):**
- [ ] **No rate-limit on `/auth/reset-password`** (`auth.py:211-282`) — login has `login_throttle` but reset doesn't → reset-link flooding / token brute-force. Reuse the throttle.
- [ ] **No rate-limit on `/auth/signup`** (`auth.py:142-208`) — account-creation spam + email enumeration (201 new vs 409 exists). Per-IP throttle; don't free-probe emails.
- [ ] **Portal OTP request unauthenticated + no GLOBAL rate-limit** (`public/portal.py:102` → `portal_service.py:460-545`) — per-contact cooldown(60s)/cap(10/day) exist, but no per-IP global limit; contact enumeration via error/timing; can DOS the Respond.io send queue. Add per-IP limit on `/public/portal/*`, genericize invalid-contact responses.

**HIGH (verify):**
- [ ] **Presigned-URL endpoint no owner authz** (`external/presigned_url.py:88-129`) — checks X-API-Key but NOT that the caller may access that attachment; any valid-key holder can presign ANY `file_path` (IDOR). **Check if CloudFront/R2 keys are per-tenant or GLOBAL** (`storage_router.py:84-90`) — if global, cross-customer file leak. (Multi-tenant is currently stubbed to DEFAULT_TENANT, so cross-tenant not active yet, but cross-entity within tenant is.) Fix: verify caller's permission to the parent entity before signing.
- [ ] **Inbound webhook signature verification — NONE FOUND** (agent could not locate inbound handlers; `*_webhook*.py` are all OUTBOUND). NEEDS DEEPER CHECK: do Respond.io/n8n POST inbound to us? If yes and unsigned → anyone can POST. Confirm where inbound lands + add HMAC/JWT verify.
- [ ] **Portal attachment download authz weak** (`public/portal.py:715,734,755`) — `_list_attachments_for` + `_safe_presigned_url` don't re-verify contact ownership; relies on upstream `list_submissions` scoping. Audit `list_submissions` (portal_service.py:622-714) for consistent `token.contact_id == submission.contact_id` filter.

**MEDIUM (verify):**
- [ ] OTP code hashed with **plain SHA256** (`portal_service.py:87`) — 6-digit space → rainbow-table-trivial on DB breach. Use bcrypt/pbkdf2 (codebase already bcrypts passwords).
- [ ] Impersonation token: excluded from sliding renewal but **no audit log** of slides/access (`portal_service.py:349-357`); set short hard expiry on impersonation start.
- [ ] **Lookup permission inconsistency — ELEVATE TO HIGH** (`lookup.py:16-52` requires `master_data.lookup_sets.view`). Beyond the Forms filter: it **breaks CREATE forms**. Verified on **Create Complaint** (`/complaint-management/complaints/new`) at mobile — ALL 4 lookup dropdowns 403 (`complaint_type`, `customer_type`, `defects_discovered`, `within_warranty`), 16 console errors (×4 retries each), and a confusing toast **"Permission required: master_data.lookup_sets.view"**. The Customer Type / Within Warranty selects stay EMPTY → if required, a user who can reach Create Complaint CANNOT complete it. Fix: grant lookup-read implicitly to anyone who can view/create the parent resource (or make the FE degrade), AND stop the 4× retry spam.
- [ ] **Attachment-create permission gap** (`resources/attachments.py:700` requires `resource.attachments.upload`) → a user who can create a complaint can't attach a photo (the 403 I hit in the upload test). Tie to parent-entity permission.

**LOW:** portal `slug-info` leaks name + masked phone (`portal.py:169`) enabling OTP spam; OTP 6-digit entropy (mitigated by caps).

**NOTE:** these are AGENT findings — confirm each against code (grill) before implementing; bundle the rate-limiting ones (auth reset/signup/portal-OTP) into one "rate-limiting" plan, the authz ones (presigned/portal-attachment) into an "object-level authz" plan.

### 1d. Cross-cutting CRITICALs found during traversal

- [ ] **Commercial module deleted from `main`** (commit `02e4d88fa`, misleading title "add DO search capability to MCP"). Survivors: sidebar entries + RBAC perms + migrations `150/151/152`. **GRILL NUANCE:** migrations 151/152 do `import app.modules.commercial_core` **inside `upgrade()`**, not at module load — so the **running app is fine** (no startup/auto-migrate breakage). But `alembic upgrade head` on a **fresh DB / disaster-recovery / new environment WILL fail** (`ModuleNotFoundError` verified). Severity: dormant-but-certain-on-fresh-setup. Full impl on branch `SRT-10`. ACTION: restore (revert/merge SRT-10) vs. remove scaffolding+migrations. Commercial guides written against SRT-10 — DO NOT publish until restored.

### 1e. Performance — slow main-page load  (user-reported 2026-06-29)

- [ ] **ROOT CAUSE: home `/` embeds the full SLA KPI dashboard** since commit `de9c78a9d` ("extract shared KPI dashboard content; reuse on home + dashboard"). Every main-page load for a user with `sla.kpi.view` now fires **3 heavy aggregate queries** — `kpi_summary` + `kpi_tasks` + `kpi_trend` (`SLAKpiDashboardContent.tsx`) — on top of the pending-tasks widget. Previously home was just the lightweight pending widget (`0506c6728`).
  - Not a loop/N+1: `kpi_summary` is one set-based `case()` aggregate (good). But it **scans the entire `conversation_sla_tracking` table with NO default date window** (`_base_filters` only adds date conds when `date_from/date_to` passed; home passes neither, scope=`all`). Grows linearly with all SLA rows ever. `kpi_trend` groups across all time; `kpi_tasks` paginates (ok).
  - Indexes exist on is_resolved/assigned_to/policy_id but a full-table aggregate ignores them.
  - FIXES (ranked): (1) **default the KPI window** to last 30/90 days on the home embed (biggest win, bounds the scan); (2) lazy-load KPI dashboard below the fold / behind a tab so it doesn't block first paint of "My pending tasks"; (3) add `staleTime` + cache so revisits don't refetch; (4) consider a materialized/rollup summary table if SLA volume is large; (5) add covering index on `(source_entity_type, initiated_at, is_resolved, is_responded)` for the scoped variants.
  - QUICK MITIGATION: revert the home embed to just `MyPendingSLAWidget`, keep full KPI on its own `/sla-management/kpi-dashboard` route.
  - **GRILL NUANCE (confirmed):** slowness ONLY affects users WITH `sla.kpi.view` — `summaryQ` is `enabled: canView` and the whole dashboard early-returns otherwise (users without it fire ZERO queries). So this explains the slow load **iff the reporting user has KPI access** (admins do). TODO: confirm `conversation_sla_tracking` row count (if <~10k the scan may not be the dominant cost) and whether react-query `staleTime` already caches across reloads before committing the fix.

---

## 🔴 HIGH BUG (found in sweep 2026-06-30) — 3 broken "Create" buttons + BE 500-on-bad-UUID

**Browser-confirmed (Campaigns):** clicking **Create Campaign** → `/marketing-management/campaigns/new` renders "Campaign not found"; network shows `GET /api/v1/marketing/campaigns/new` → **500** (×2). Create flow is DEAD.

**Root cause:** the list "Create" button `router.push('/…/new')` but there is **no `new/page.tsx`** for that resource, so Next falls through to `[id]/page.tsx` with `id="new"`, which fetches `GET /…/{id}` → backend can't parse "new" as UUID → 500 → FE shows not-found.

**Systemic scan (grep of all `push('…/new')` vs presence of `new/page.tsx`):** 3 BROKEN, 14 OK.
- [ ] **`/forms-management/forms/new`** — `FormsList.tsx:266` — Create Form broken (no `new/` page).
- [ ] **`/inventory-management/stock-batches/new`** — `BatchesList.tsx:231` — Create Batch broken (matches earlier inventory-guide finding).
- [ ] **`/marketing-management/campaigns/new`** — `CampaignsList.tsx:222` — Create Campaign broken (browser-confirmed).
- [ ] **BE defensive bug:** `GET /api/v1/marketing/campaigns/{id}` (and likely other detail GETs) returns **500** for a non-UUID id — should be 404/422. Masks the above + leaks an error. Harden id parsing across detail endpoints.
- Fix options (need grilled+approved plan): add the missing `new/page.tsx` create pages (match the 14 working ones), OR switch these creates to the modal-default per ADR CRUD-UX standard (campaign/form/batch may be simple enough for a modal). Either way also fix the BE 500→404/422.
- OK (have `new/page.tsx`): complaints, warehouses, promotions, products, UoM, customers, order-statuses, orders, grn, packing-lists, spo-allocations, stock-inquiries, suppliers, sla-policies.

## Workstream 2 — UI traversal (mobile + desktop)

Pages to sweep (from `config/menu.config.tsx`). Desktop 1400px + mobile ~375px. For each: renders? overflow? header wraps? empty-state present? UUIDs leaking? action buttons reachable?

- [ ] Dashboards `/`
- [ ] User Management (users, roles, permissions, AI agents, teams, internal users, contact access types, account, logs, settings)
- [ ] Commercial (pipeline, leads, lead-stages, projects, tenders, quotations, quotation-revisions, email-templates, sales-order-progression, tender-quotation-compare, process-configuration)
- [ ] Activity Plans (activities, activity-tasks, project-tasks)
- [ ] Delivery Order Management (orders, order-statuses, customers)
- [ ] Complaint Management (complaints, root-causes, resolutions)
- [ ] SLA Management (policies, conversation-sla, form-sla, team-pending, form-sla-config, escalation-logs, kpi-dashboard)
- [ ] Product Management (products, product-attachments, categories, brands, UoM)
- [ ] Procurement (suppliers, product-suppliers, packing-lists, spo-allocations, grn, picking-lines, stock-inquiries)
- [ ] Project Sales Admin (purchase-requests, sponsorship-forms)
- [ ] Inventory (warehouses, storage-zones, stock, stock-batches, stock-ledger)
- [ ] Marketing (promotions, promotion-attachments, promotion-products, campaigns)
- [ ] Forms Management (forms)
- [ ] Workflow Forms (definitions)
- [ ] Resource Management (files, trash, attachment-types)
- [ ] System Management (app-store, bundles, import-jobs/logs, integration-logs, whatsapp-templates, scheduled-tasks, outgoing-mails, email-outbox, respond-outbox, email-event-configs, email-templates, automation, work-calendar, numbering-rules, lookup-sets, respond-workspaces, ai-assistant settings/usage/wishlist, mcp-tools)

**Dashboard `/` (desktop 1280px) — findings:**
- [ ] **Metronic DEMO nav in production top bar** ✅GRILL-CONFIRMED — `MENU_MEGA` (`config/menu.config.tsx:1589-1911`) rendered by `MegaMenu` in `app/components/layouts/demo1/components/header.tsx`; shows "Profiles/My Account/Network/Apps" demo routes to real users. Remove/replace.
- [ ] **Template footer links** ✅GRILL-CONFIRMED — `app/components/layouts/demo1/components/footer.tsx` reads `config/general.config.ts`: `purchaseLink='https://1.envato.market/Vm7VRE'`, `faqLink='https://keenthemes.com/metronic'`, `licenseLink=''`. Replace with real Foundryx links or remove. "Docs"→Outline is correct.
- [ ] **Support footer link → `/ticket-management/tickets`** but ticket-management isn't in the sidebar — confirm module intent / gating (FE audit also flagged ticket-management not in menu.config).
- [ ] Dashboard for a limited user is sparse: "My pending tasks" + "You don't have access to the SLA KPI dashboard." Consider a fuller role-aware landing (see Workstream 4 admin dashboard idea).
- Note: sidebar shows only modules enabled for this user (Commercial, Inventory, Procurement, Delivery, Product, Activity Plans, Workflow Forms gated off) — expected module-enablement behavior, verify deliberate.

**Dashboard `/` (mobile 390px) — findings:**
- Mostly clean: pending-tasks card, My Pending/My Team/Coverage tabs, and complaint-row truncation all behave well at phone width. ✅
- [ ] Footer link row overflows at right edge ("License" clipped) at 390px; also the floating **AI assistant** FAB overlaps the footer links on short pages. Low severity — wrap footer / add bottom padding so FAB doesn't cover content.
- (KPI dashboard mobile layout not captured — current test user lacks `sla.kpi.view`; revisit with a KPI-enabled user.)

**Complaints list `/complaint-management/complaints` (desktop 1280 + mobile 390) — ✅ CLEAN.**
- Desktop: professional DataGrid (Search/Filters/Columns/Export/refresh/Create Complaint), proper truncation on Customer/Product, row-select checkboxes, breadcrumb. 0 console errors.
- Mobile: toolbar wraps cleanly, DataGrid horizontally scrolls (DO Number + Complaint Date visible, rest via scroll) — no off-screen overflow. Create Complaint prominent.
- Minor: top-bar breadcrumb wraps to 2 lines at 390px (tight but functional). Empty cells render "-" (complaints not linked to a DO) — acceptable.
- Note (ties to admin-QoL): row-select checkboxes present but no bulk-action bar surfaced here.

**Resource Management → Files `/resource-management/attachment-directories` (desktop 1280 + mobile 390) — swept.**
- Responsive: ✅ desktop two-pane (folder tree + attachments table); mobile collapses to a single list with a folder-toggle button — clean, no overflow, toolbar wraps (Search/Filters/Columns/Export/Bulk import ZIP/Upload). 0 console errors.
- [ ] **Junk/test folders in the production tree**: "aaa-drive-reveal-parent-688…", "aaa-drive-search-parent-64…", "aaa-drive-sel-731619-940", "aaa-drive-sel-897231-143", "fdas", "Test", "Testing". Leftover test data (likely from automated e2e hitting a shared DB). Unprofessional in a real tenant — clean up the data, and check whether tests seed into the dev/staging DB.
- [ ] **UUID filenames shown raw as Name** (e.g. "bef38628-f4de-4eae-a8b6-…", Type "-"). Ties to the attachment `original_filename`=key-basename gotcha. FE Files grid should prefer the editable display name (`stored_filename`) as the primary label, falling back to original only when no display name — avoids UUIDs in UI (cursor rule).
- [ ] **Access-column pills clipped/overflow** at the right edge on desktop within the two-pane width ("End Use", "Sorento Office" cut to "3orento Office"). Fix the Access column sizing / allow wrap, or move pills to a tooltip.

**SLA Management → SLA Policies `/sla-management/sla-policies` (desktop + mobile) — ✅ CLEAN.**
- Professional DataGrid (Code/Name/Description/Tiers count-pill/Status Active-pill), Search/Filters/Columns/Export/Create SLA Policy, rows-per-page, 1-8 of 8, proper truncation. 0 console errors. Mobile: toolbar wraps, DataGrid scrolls horizontally. No overflow.
- Recurring minor (all pages): top-bar breadcrumb wraps to 2 lines at 390px — tight but functional; could shorten to current-page only on mobile.

**Sweep pattern note:** list pages (complaints, SLA policies) share a consistent, clean, responsive DataGrid; no per-page sus UI found beyond the fixed template leaks (Item 1) + the Files data-quality items. Remaining: Marketing, Forms, System Mgmt, and detail/create-modal flows.

**Header breadcrumb — REMOVED** ✅ (commit `56b2b48fe`, user-approved). The lone "Dashboards" / duplicate header breadcrumb (leftover from demo mega-nav removal) is gone; each page keeps its own title + breadcrumb below the header; utilities right-aligned (`ms-auto`). Browser-verified clean. Resolves user's "2 breadcrumbs confusing".
- [ ] **Minor: Permissions in-page breadcrumb mislabeled** — `user-management/permissions/page.tsx:38` hardcodes "Home › Users"; pattern is "Home › {Module}" so it should read "User Management" (title is "Permissions"). Odd-one-out copy-paste; low severity. (The other "title≠crumb" hits are the normal Home›Module pattern, NOT bugs.)

**Guides → Outline: PUSHED** ✅ (user-authorized). inventory/delivery-orders/product/sla data-analysis+how-to + `getting-started-for-new-users` now live in Outline; commercial held by forbid-list. Assistant can now serve them.

**Forms Management → Forms `/forms-management/forms` (desktop + mobile) — list ✅ CLEAN, but 403-lookup noise.**
- List renders fine (Form Code/Name/Type/Purpose/Language), truncation OK, mobile collapses cleanly. Header fix confirmed (no top breadcrumb on mobile either).
- [ ] **4× `403 Forbidden` on load** from `GET /api/v1/lookup/by-binding?table=forms&column=form_type` — the form_type filter's lookup options are RBAC-forbidden for this user. Page still works (filter just won't populate), but: (a) is the lookup-binding permission supposed to be denied to users who CAN view forms? mismatch; (b) FE retries it 4× and spams console errors instead of degrading gracefully (hide/disable the filter or show "unavailable"). NOT caused by Item-2 lookup change (that was query internals; this is the endpoint's auth guard). Recommend: align the lookup permission with form-view, AND make the FE filter degrade gracefully on 403.
- Note: "Create Form" here is one of the 3 KNOWN-BROKEN creates (already logged).

**Create Complaint `/complaint-management/complaints/new` (mobile 390) — page-based create, scroll ✅.**
- Long form renders fully at phone width; scrollable; **"Create Complaint" + "Cancel" reachable at bottom** (mobile-scroll standard satisfied for page-based creates).
- 🔴 lookup 403 breaks the form's dropdowns — see §1f #9 (elevated to HIGH).
- [ ] Minor UX: create form exposes raw **"Contact ID / Space ID — Respond.io contact ID / space ID"** as free-text inputs (Technical Team section) — asking a CS user to hand-enter Respond.io integration IDs is odd; should be auto-resolved/hidden or clearly optional.

_still to pass: System Mgmt list pages._

---

## Workstream 3 — Guides

Existing (department how-to): purchasing, warehouse, marketing, project-sales-admin/manager/rep, technical-team. `_shared/` for cover/escalate/dashboard.

**Gap A — uncovered modules (how-to):** Commercial, Activity Plans, Inventory, Product/master-data, Delivery Orders+Customers, SLA Management, System Management, User Management, Workflow Forms, Resource Management (trash/types).

**Gap B — data-analysis guides (NEW genre, for the LLM):** per data-rich module, document *what data lives here, what each field means, what filters/date-ranges exist, and example questions the assistant can answer* ("list orders for customer X delivered between A and B", "complaints open >7 days", "stock below reorder for warehouse Y"). These feed the AI assistant's grounding so it can do data analysis on request.

- [x] **Commercial guides** ✅ 7 files in `docs/user-guides/commercial/` (incl `data-analysis.md`). ⚠️ Written against branch SRT-10 — **gated on module restore to main, do NOT push to Outline yet**.
- [x] **Rename-guide fix** ✅ `purchasing/manage-resource-folders.md` updated (Files page now uses right-click/long-press ContextMenu, not pencil/Actions column) AND **pushed live to Outline** (doc `c850103b…`) so the assistant serves the new steps.
- [x] **Inventory guides** ✅ 6 files in `docs/user-guides/inventory/` (incl `data-analysis.md`). Annotation map updated.
- [x] **Product / master-data guides** ✅ 5 files in `docs/user-guides/product/` (incl `data-analysis.md`). Flags: category modal has no parent picker (nesting via import only); `is_discontinued` not form-editable; `cost_price`/`invoice_price` viewer-hidden — assistant must not leak.
- [x] **Delivery Orders + Customers guides** ✅ 4 files in `docs/user-guides/delivery-orders/` (incl `data-analysis.md`, 17 example NL queries).
- [x] **SLA Management guides** ✅ 6 files in `docs/user-guides/sla/` (incl `data-analysis.md` with verbatim met/breach formulas, conversation-vs-form explainer). Flags: menu "SLA Event Logs" vs in-page "Event Logs" mismatch; `max_extension_*` on model but not in Policies form UI.
- [ ] Complaint data-analysis guide (technical-team has how-to; add data-analysis genre)
- [ ] data-analysis index doc (`_shared/data-analysis-with-the-assistant.md`) tying all module data-analysis guides together for the assistant
- [x] **Remaining module guides** ✅ 12 files on branch `docs/user-guides-data-analysis-uncovered-modules`: procurement (data-analysis + manage-suppliers + review-grn), marketing/data-analysis, complaints/data-analysis, user-management (data-analysis + manage-users-and-roles + manage-teams), system-management (data-analysis + troubleshoot-failed-notifications). NOT pushed to Outline (user-gated) — review the bugs they surfaced (§1g) then push. NOTE: on a separate branch, not main.

**Bugs surfaced by guide agents (verify + fix):**
- [ ] **Stock Batches "Create Batch" → `/stock-batches/new` has NO page implemented** (404/blank). Either build the page or hide the button (batches come from import pipeline today).
- [ ] **Customers list Status filter** sends `status` param but `GET /order-management/customers` ignores it (only page/limit/query/sort/dir; search matches code+name only) — dead filter control. Either wire BE or remove control.
- [ ] order-statuses search + Final-status filter are client-side only (no server filter) — fine for small sets, note.
- [ ] AI assistant can't read Customers master (route uses `get_current_user` only, no API key) — customer analytics come from `/orders/debtors` aggregation. Confirm intended; may want API-key access for assistant.

---

## Workstream 4 — System-admin quality-of-life  (added per user, 2026-06-29)

User ask: make sysadmin work easier — **log tracing, activity tracking, checking activities, mass-updating records**, general admin ergonomics.

Existing surfaces to inventory first (don't rebuild what exists): User Management → Logs, System Management → Import Logs / Integration Logs / Email Outbox / Respond Outbox / Outgoing Mails / Scheduled Tasks, `ActivitiesNotesPanel`, audit_service listeners (BE).

Candidate improvements (agent investigating, then triage):
- [ ] **Unified activity/audit timeline** — one searchable view across audit log + integration log + email/respond outbox, filter by actor / entity / date-range / action. Today they're siloed across separate pages.
- [ ] **Per-record activity tab** consistency — ensure every detail page surfaces "who changed what when" (audit trail) + linked comms.
- [ ] **Mass update / bulk actions** on DataGrids — bulk status change, bulk assign, bulk delete (with count copy per ADR). Inventory which lists support multi-select today.
- [ ] **Log tracing ergonomics** — correlation/request-id surfaced in UI logs; jump from an error log to the related entity; export/download log slices.
- [ ] **Admin dashboard** — failed jobs, stuck SLA, failed sends (outbox), pending imports at a glance.
- [ ] **Saved filters / views** on heavy admin lists.

### 4a. Admin-QoL investigation  ✅ AGENT DONE

**What exists:** AuditLog (before_flush listeners, old/new JSONB, `/api/v1/audit/` GET with filters — but NO FE page); SystemLog (`/user-management/logs`); IntegrationLog (no monitor UI); ImportLog (`/system-management/import-logs`); EmailOutbox (`/email-outbox`, per-row retry/cancel); RespondOutbox; ScheduledTask (`/scheduled-tasks`); per-entity ActivityEvent + InternalNote via `ActivitiesNotesPanel`. Bulk: mostly DELETE endpoints (tickets/complaints/forms/orders). **GRILL CORRECTION:** "only bulk-delete" was REFUTED — bulk-UPDATE endpoints DO exist (`promotions.bulk_update_access_levels`, `users.bulk_update_user_status` / `bulk_users_action`). What's missing is a GENERAL/cross-entity bulk-update framework + bulk-action UI on the system-mgmt queue lists (checkboxes render, no actions wired).

**Audit coverage matrix (the blind spots):** tracked = Ticket, Complaint, Product, StockInquiry, PurchaseRequestHeader. **NOT tracked (high-value gaps): Order, OrderLine, User, Supplier, Promotion, Form, FormSubmission, Automation, EmailTemplate, ScheduledTask, Team, RespondContact, Stock.** Adding `__audit_track__=True` is ~2 lines/model.

**Proposed roadmap (ranked):**
- [ ] **Tier-1 quick wins (~2-3d):** (a) add bulk-action UI to email-outbox / import-logs / respond-outbox / scheduled-tasks (checkboxes already render — copy `FormsList` bulkActions pattern, reuse existing bulk-delete endpoints); (b) **build `/system-management/audit-logs` FE page** on the existing `/api/v1/audit/` API (no BE work) — "who changed what"; (c) write explicit **IMPERSONATE audit event** (today impersonation silently rewrites created_by).
- [ ] **Tier-2 (~3-4d):** bulk retry/cancel for failed emails; **expand `__audit_track__` to Order/User/Form/Supplier/Promotion**; add **request `trace_id`** through LoggingMiddleware → audit_context → AuditLog column → filterable in UI (correlate multi-step ops).
- [ ] **Tier-3 (~4-7d):** **Admin health dashboard** (`/system-management/health`: email queue depth, failed sends 24h, import success rate, overdue scheduled tasks, integration success-by-channel, audit activity trend); **cross-entity activity search/timeline**; **generic bulk record updater** (filter any resource → bulk status/assign/tag with audit trail).
- [ ] Note: SystemLog vs AuditLog are partly redundant — decide canonical source before building the viewer.

Key files: `app/services/audit_service.py`, `app/api/v1/audit/audit_logs.py`, `app/audit_context.py`, `app/middleware/logging_middleware.py`, FE pattern `forms-management/forms/components/FormsList.tsx` (bulkActions), `components/common/ActivitiesNotesPanel/`.

---

## Workstream 5 — AI assistant: novice-first coverage + fast deterministic architecture  (added per user, 2026-06-29)

User directive (verbatim intent):
- Guides + LLM coverage must be written from a **total-novice perspective** — someone who knows NOTHING about the system. So **"what can the system do?"** must be answerable, plus "where do I find X", "what am I looking at on this screen".
- Keep **answering speed fast** — do NOT use the LLM to do everything. Use **tools + deterministic logic + deterministic nodes** wherever possible. The LLM is **NLP only**: understand the language, extract the needed info from natural-language text. (Reference: how n8n MCP uses a semantic parser as the language-understander.)
- Reversely: propose a **better, more industrial-grade AI structure** to improve BOTH this assistant and the n8n structure.

### 5a. Investigation
- [x] **AI assistant architecture + latency profile** ✅ AGENT DONE. Headlines (`ai_assistant_service.py`):
  - **4–7 sequential LLM round-trips per message.** Typical "list X for customer Y" ≈ 1.6s / 3 LLM calls; record-context path ≈ 2.0s / 4+ calls; worst case (agent loop, 3 tools, 2 follow-ups) 3.5–5.5s.
  - **LLM overused where deterministic would do:** (1) **query reformulation** `:435-448` (200-500ms — pronoun/abbrev expansion, regex-able); (2) **intent classification** `:1395-1468` "is this about the open record?" (200-400ms — heuristic on "this/it"+record-type); (3) **tool selection** `:1092` is free LLM choice though RAG scores exist `:747-784` — add threshold gate (RAG>0.85 → force tool, skip a round).
  - **No caching anywhere on hot path:** no Anthropic `cache_control` prompt caching (`llm_provider.py:384-461`), no tool-result memoization, **guide content re-read every turn** (not cached), query embedding recomputed each turn. Biggest cheap wins.
  - **FE does NOT stream** (`AIAssistantBubble.tsx`) — optimistic user msg then blocks for the full response. Streaming would slash perceived latency.
  - **Capability catalog ALREADY EXISTS**: `crm_system_tool_capabilities_summary` (catalog.py:492-502) → `/api/v1/system/tool-capabilities/summary`, grouped by intent. → the "what can the system do?" answer should be **deterministic off this endpoint**, not LLM-guessed. `user_guides_read` is force-bound every turn because RAG won't reliably rank it.
- [x] **MCP + n8n semantic-parser pattern** ✅ AGENT DONE.
  - **Done right:** intent-first tool catalog (`catalog.py` ToolSpec w/ domain+escalation_team+related_tools), **two-call dynamic-params** (422 → `allowed` list → re-call, per-contact, access_levels), **AI Extract + user confirm** (`extract_service.py` — LLM proposes, LookupResolver canonicalizes, human confirms before persist), **lookup canonicalization** (`crm_lookup_resolve` fuzzy→canonical server-side), **name→UUID** (`server.py _resolve_product_reference`), **RAG tool-intents** (`mcp_tool_capability_service.py` typical_user_questions+aliases embedded).
  - **Leaks (LLM/code doing what metadata should):** hardcoded per-tool shaping in `server.py:35-196` (TOOL_REQUIRED_NARROWING_FILTERS, TOOL_DEFAULT_QUERY_PARAMS, row-key drops, warehouse relabel) → should be ToolSpec fields; automation grouping gated on `str(trigger_type)=="..."` (`automation_service.py:368`) → should be TriggerSpec.multi_match; tool→agent assignment manual-only.
  - **CAPABILITY REGISTRY DRIFT (4 registries, no single SoT):** `CATALOG` (code) → auto-syncs `mcp_tools` table ✅ but NOT `TOOL_INTENTS` (manual dict) nor `embedding_chunks` (RAG index) nor `list_query_registry` (5 resources, manual). New/edited tool → RAG stale, unassigned. This is the structural root cause to fix.

➡️ **Architecture proposal written:** `docs/plans/PLAN-ai-assistant-architecture.md`

### 5b. Deliverables (after investigation)
- [ ] **Novice "What can the system do?" capability guide** — a machine-readable + human-readable catalog the assistant can enumerate deterministically (modules → what you can do → example questions). Single source of truth, ideally generated from the tool/registry layer, not hand-maintained.
- [ ] **`_shared/getting-started-for-new-users.md`** — zero-knowledge orientation (login, sidebar map, where each data type lives, how to ask the assistant).
- [ ] **Industrial-grade AI architecture proposal** (`docs/plans/PLAN-ai-assistant-architecture.md`): deterministic intent router BEFORE the LLM; LLM constrained to NL→structured-params extraction; deterministic tool/SQL execution + templated formatting; Anthropic prompt caching for the system prompt + guides; tool-result/guide caching; capability registry as SoT for MCP + UI + "what can it do"; streaming; eval harness + guardrails. Apply same pattern back to n8n (semantic-parse node → deterministic branches).
- [ ] Re-shape per-module data-analysis guides (already drafting) to lead with novice "what is this / what can I ask" framing.

## Tackle order (after sweep)
1. Triage Workstream 1 findings by severity; fix CRITICAL/HIGH security first.
2. Fix UI breakages found in Workstream 2 (mobile overflow, missing empty states).
3. Land guides; sync to Outline via `scripts/sync_user_guides_outline.py push`.
