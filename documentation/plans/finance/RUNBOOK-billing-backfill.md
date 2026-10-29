# RUNBOOK: billing documents backfill and outstanding, first live run (S4, S5)

Status: DRAFT (lane AC-BILLING, 17 Oct). Runs after 25 Oct, once AutoCount grants read access. UAC S4-1 to
S4-3 and S5-10. Schema reference: `REF-autocount-billing-schema.md`. Contract: cross-repo plan section 12
(2.6 `billing_documents`) and the `ar_outstanding` section (2.10). Nothing here writes to AutoCount.

## 0. Preconditions

1. AutoCount admin grants the read-only SQL login SELECT on `IV, IVDTL, CS, CSDTL, CN, CNDTL, DN, DNDTL,
   DODTL, ARInvoice, ARDN, ARCN` (Debtor and Item are already readable), on every company DB that is in
   scope. Done 27 Oct for `AED_SORENTO` only (plus `DO`, `ARPayment*`, `ARCNKnockOff`); the login cannot
   open the other company DBs yet. `DODTL` is for the DO-line hop (foundryx-shared-service PR #127,
   restored by PR #132): a line with `FromDocType = 'DO'` joins `DODTL ON DODTL.DtlKey =
   <line>.FromDocDtlKey` to build the exact DO line ref `{book}:DO:{DODTL.DocKey}:{DODTL.DtlKey}` (`book`
   = the company's Delivery Orders feed book), which the CRM resolves to its own DO line and that line's
   sales order line. Crew ruling: the link is exact, never by `FromDocNo`; if `DODTL` is unreadable the
   shared service fails loudly at Preview rather than pushing DO-sourced lines unlinked. A 2025-26 line
   carries only `FromDocNo` (`FromDocDtlKey` NULL): it goes out with type + number and no line ref, so its
   order class falls back to the agent / debtor rungs. Check before the dry run: `SELECT TOP 1 DtlKey FROM
   DODTL` under the read-only login, on every company DB.
2. The REF section 6 checks have run and every [I] that the presets rely on is confirmed; the presets are
   corrected where a check failed. Record the results in section 5 below.
3. The `finance` module is switched on for the tenant (App Store).
4. Permission grant: the feed's act-as role holds `finance.billing_documents.edit`, `.delete` and `.view`.
   fin_0001 granted them to every role holding `scm.sales_orders.edit` (Q16 built as (a)); confirm on the
   Roles screen before the first push, or every record answers 403.

## 1. Start date

Shared-service configuration, not CRM configuration: `from_date = 2023-01-01` on the four billing presets.
The CRM holds no copy and has no date floor.

## 2. Order and size

- Dry run first: one day of each type through `?dry_run=true`, read the verdicts, expect no `failed`.
- Then oldest first, day by day. Within a day: IV and CS before CN and DN (a note links its invoice by
  `against_source_ref` / `against_doc_no` at ingest; a note that lands first is linked when its invoice lands).
- The DO backfill must reach a day before that day's invoices are pushed: an invoice line's DO hop
  (`{book}:DO:{DocKey}:{DtlKey}` to the sales order line) is decided at its push, so an invoice pushed
  before its DO stays unlinked until the invoice is pushed again.
- Batch size 1000 records (the door's cap; 413 above it).
- Each company pushes under its own `companyCode`.
- Outstanding (`ar_outstanding`) runs only after the billing backfill has reached today, so every listed
  document exists; before that the verdicts count `documents_unknown`.

## 3. Re-run rule

Safe. An identical push answers `unchanged` and writes nothing (UAC S0-5); an older `source_modified_at`
answers `unchanged` + `stale_ignored`. Re-run any failed day as a whole.

## 4. Check queries (CRM, read-only)

```sql
-- documents per type per month (compare with AutoCount's own counts, S4-2)
SELECT document_type, date_trunc('month', doc_date) AS month, count(*), sum(net_total)
FROM finance.billing_documents
WHERE company_id = :company_id AND status = 'posted'
GROUP BY 1, 2 ORDER BY 2, 1;

-- unclassified documents per month (the "(blank)" row of the Yearly comparison)
SELECT date_trunc('month', doc_date) AS month, count(*)
FROM finance.billing_documents
WHERE company_id = :company_id AND demand_class IS NULL AND status = 'posted'
GROUP BY 1 ORDER BY 1;

-- unresolved masters (fix the master, then re-push the day)
SELECT count(*) FILTER (WHERE customer_id IS NULL) AS no_customer,
       count(*) FILTER (WHERE sales_agent_id IS NULL AND agent_code IS NOT NULL) AS no_agent
FROM finance.billing_documents WHERE company_id = :company_id;

-- outstanding per customer vs the sum of its documents (S5-10; a gap = AR entries keyed straight in AR)
SELECT c.customer_code, c.ar_outstanding, c.ar_as_of, sum(b.outstanding) AS docs_sum
FROM customers c LEFT JOIN finance.billing_documents b
  ON b.customer_id = c.id AND b.status = 'posted'
WHERE c.company_id = :company_id AND c.ar_outstanding IS NOT NULL
GROUP BY 1, 2, 3 ORDER BY abs(c.ar_outstanding - coalesce(sum(b.outstanding), 0)) DESC LIMIT 50;
```

## 5. Results (fill in on the run)

| Check | Result |
|---|---|
| REF section 6 checks (per item) | 27 Oct, `AED_SORENTO`, read-only: drafts = `D` (filtered by the shared-service preset, PR #132); `E` kept, meaning open; `CS` has 0 rows and no `DocStatus`; `DNDTL` has no `FromDoc*`; ARDN/ARCN carry `Cancelled` (excluded); `NetTotal = TotalExTax + Tax`, `FinalTotal = NetTotal + RoundAdj`, `LocalNetTotal - LocalTax = LocalAnalysisNetTotal`: 0 exceptions; non-MYR 0 (ARInvoice: 2 USD rows all time); package children carry no money; `ARInvoice.SourceType`/`SourceKey` agrees with `DocNo` + `DebtorCode` on 370,532/370,532 rows |
| Test months (2024 or later) and per-type counts vs AutoCount | Raw tables only (no AutoCount UI access), PR #132 presets replayed read-only: IV 22-26 Oct 2026 593 docs = raw non-draft count, NetTotal RM 1,193,742.30 exact, 1,597 lines, 0 fingerprint mismatches (14 drafts dropped); IV 1-3 Mar 2023 887 docs and 1-2 Oct 2024 998 docs exact, every DO line linked through `DODTL`; CN Jul-Oct 2026 463 docs exact; DN 2026 44 docs exact; CS 0 rows; AR 3,304 debtors, total RM 37,285,479.04 = raw IV + DN - CN excluding cancelled (cancelled ARDN RM 74,620.55 and ARCN RM 1,384,734.44 no longer counted). Comparison against AutoCount's own screens: pending the owner |
| Yearly comparison, Basis = Invoiced, vs the AutoCount PDF (S4-3, within RM 1 per cell) | |
| Three debtors: CRM outstanding vs AutoCount Outstanding AR Invoice report (S5-10) | |
