# PLAN: AC-TEST-COMPANY - standing TEST company bound to AutoCount db3

Status: Built (re-scoped 5 Nov to a LOCAL staging kit; script + tests + SS contract + runbook in PR #2202; reviewer + security-reviewer findings fixed; waiting on crew to bring it up locally). Track: small fix (no migration, no app code change, no auth/RBAC change).

Lane: AC-TEST-COMPANY. Owner ask (5 Nov 2026): a company in the real CRM the owner and picked admins can use to
exercise every AutoCount integration end to end against the AutoCount db3 test book, without risk to the live book.

## Owner answers (5 Nov, via crew) - RE-SCOPE

"test company, we can just use local as our staging". The test company lives on a LOCAL staging
copy on the owner's Mac, not in the prod CRM. Q1/Q2/Q3/Q5/Q6 are moot (no `is_test` column, no prod
fencing, no per-company switch logic, no book guard). Q4(a): data comes from db3 through the existing
SS pushes/pulls (hapi `/api/db3/...`), never hand-copied.

Deliverables:
1. `sorento_crm_backend/scripts/staging/seed_db3_staging.py` (+ `tests/test_staging_seed_db3.py`):
   idempotent seed of company SRT_DB3, `foundryx-esb` pointed at the local SS, the SS push key,
   every AutoCount write switch ON, and a staging admin. Refuses non-local DBs and DB names without
   a dev/staging token or with a prod token. Dry run by default.
2. `CONTRACT-db3-local-staging-ss.md`: the SS side.
3. `RUNBOOK-db3-local-staging.md`: start, refresh, reset, what to try.

The sections below are the original prod-company exploration, kept for the record.

## Facts (main @ 9ebae8e9)

- CRM picks the SS company only by `companies.code`, sent as `companyCode` (pull body
  `app/services/foundryx_autocount_client.py:173`, write-capabilities query :236, PO-link writes
  `app/services/scm/stock_debt_po_link_service.py:479,517,542,579,602`). One global `foundryx-esb`
  integration row (`foundryx_autocount_client.py:54-56`). The CRM never names a book.
- A CRM company with code `SRT_DB3` therefore routes every call to SS company `SRT_DB3` with no
  client change. SS today has `SRT_DB3` (db3 only) in the hand-test clone `foundryx_service_qtso_ht`
  only (lane brief; SS repo not readable from this sandbox).
- No CRM-side live-book guard: SS's db3-only guard is the single gate (`PLAN-ac-link-crm-ui-04nov.md:51-54`).
- The PO-link switch `system_settings.stock_debt_po_link_enabled` is global, default off
  (`app/models/user.py:462-467`, checked `app/api/v1/projects/stock_debt_snapshots.py:250-256`).
- `companies` has no test flag (`app/models/company.py:20-52`). Staff requests are scoped to one
  active company; admin/superadmin grant set = ALL companies (`company_scope_resolver.py:303-307`).
- All-companies (`None`) scope today: scheduler ticks (`app/scheduler/task_scheduler.py:34-54`),
  X-API-Key without a contact (`company_scope_resolver.py:361-365`), many `company_scope(db, None)`
  blocks in the chatbot (`chatbot/engine.py:1733-1740`, `chatbot/agent/access.py:73,98,110,220`),
  SCM analytics (`scm/analytics_service.py:435,853`). Report engine admin company picker
  (`api/v1/reports/reports.py:87-94`). Notifications / email outbox carry no company_id.

## Behaviour card (draft, waiting on owner)

Posted as the lane's crew-ask on PR #2202. Recommended shape:
1. Prod CRM company `SRT_DB3` "TEST - AutoCount db3" with new `companies.is_test = true`.
2. Visible only to users with an explicit `user_companies` grant; test companies leave the
   admin "all companies" grant set.
3. Fence centrally: the `None` (all companies) scope becomes "all non-test companies" in
   `build_company_predicate` (+ the raw-SQL twin), so scheduler / n8n / embedder / analytics
   never see test rows; report company pickers list a test company only for granted users;
   outbound email + WhatsApp suppressed when the acting scope is a test company.
4. Seed: products + stock via the existing AutoCount pulls for SRT_DB3 (db3 is the source);
   customers/suppliers by a script copying Sorento rows whose codes exist in db3.
5. Switches: a test company ignores the global AutoCount write switches (writes on);
   live companies keep today's global switch (off).

## Pre-build audit (read-only, 5 Nov)

- 119 `company_scope(db|session, None)` call sites under `app/` (32 in `app/services`, 14 in
  `app/tasks`, rest across dealer_kit, public API, scm, sales, reports, chatbot). Patching per
  surface is not viable; Q3(a) is the only fence that covers them.
- The fence point is two `scope is None` branches: `build_company_predicate`
  (`app/services/company_scope.py:236-237`, returns no predicate) and `company_sql_predicate`
  (`app/services/company_scope_sql.py:40`, returns ""). Under Q3(a) both return
  `company_id NOT IN (SELECT id FROM companies WHERE is_test)`, shared tables keeping `IS NULL OR ...`.

## Owner input (via crew, 5 Nov): seed from db3 through the existing hapi read API

The CRM never calls hapi directly. AutoCount reads reach it through SS in two ways:
- SS pushes into `/api/v1/external/ingest/*` (`app/api/v1/external/ingest.py:284-341`), with
  `companyCode` + free-form `book` (`ingest.py:821-830`, `autocount_doc_ingest_service.py:88-89`),
  and the company is resolved from the body (`app/api/v1/external/company_anchor.py:135-161`).
- The CRM pulls gateway snapshots by `companyCode` (`autocount_pull_service.py:143-147,216`).

A CRM company coded `SRT_DB3` therefore needs no client change. SS-side dependency (foundryx-shared-service
lane, routed by crew):
1. prod SS company `SRT_DB3`, db3 connection only;
2. hapi pollers for SRT_DB3 against `/api/db3/...` (location, itembypage, debtorbypage, creditorbypage,
   ItemGroup/Type/Brand/Category/Class, salesagent, taxcode, terms, itemuombypage,
   itembatchbalqtybypage, branchbypage, purchaseorder*, goodsreceivenote*, salesorder*,
   deliveryorder*), pushing with `companyCode=SRT_DB3, book=db3`;
3. gateway snapshots + write-capabilities answered for SRT_DB3.

New card Q6: a CRM book/company pairing guard (db3 only for test companies, and never for live companies),
on ingest and on PO-link writes.
