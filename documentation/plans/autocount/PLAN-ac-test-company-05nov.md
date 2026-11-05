# PLAN: AC-TEST-COMPANY - standing TEST company bound to AutoCount db3

Status: Plan (behaviour card drafted, waiting on owner answers before build). Track: full (migration + RBAC/scoping).

Lane: AC-TEST-COMPANY. Owner ask (5 Nov 2026): a company in the real CRM the owner and picked admins can use to
exercise every AutoCount integration end to end against the AutoCount db3 test book, without risk to the live book.

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
