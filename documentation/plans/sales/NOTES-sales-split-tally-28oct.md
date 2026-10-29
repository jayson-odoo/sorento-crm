# NOTES: Sales split tally (Dealer / Project team / Set apart vs AutoCount)

Status: Plan; rule ruled (owner 28 Oct ~09:30: the SO's order type decides). Root cause measured:
the DO feed gap (2b), dated by R12 and crew's dry run: 19 Aug 2025 to 19 Aug 2026 (2d, 2e). R11: the incident apply did not land.
Owner 29 Oct ~22:45: ask 1 (a), the shared-service DO history load for the gap, dry run on a prod copy first
(run plan and dry-run result: 2e; dry run clean 29 Oct, real run on the copy next); ask 2 (a), set apart from Jan 2026 (crew fills R9). crew-lane: SALES-SPLIT-TALLY.
Track: small fix (expected diff well under 300 lines, no migration, no RBAC change). Follows
`PLAN-sales-unified-27oct.md` (#1916, live in prod 745be3f35b). Read-only owner SQL:
`evidence/sales-split-tally-owner-sql-28oct.md`. No agent code or per-agent figure is committed
(public repo): crew holds them.

## 1. What prod showed (owner, 28 Oct ~08:35 MYT; SRT, January 2026, Invoiced)

| Block | Docs | CRM (SO chain) | AutoCount |
| --- | ---: | ---: | ---: |
| Dealer | 18 | -36,140.28 | 6,513,047.67 |
| Project team | 6 | -93,033.38 | 6,084,471.57 |
| Set apart | 0 | 0.00 | 122,232.99 |
| Other, Mixed, Type not set | 0 | 0.00 | |
| No sales order | 5,760 | 14,871,452.95 | |
| ALL SALES | 5,784 | 14,742,279.29 | 14,742,279.29 |

Only credit-note-like (negative) documents trace to a sales order. No January invoice traces.

## 2. Root cause of "No sales order"

The trace is `app/services/sales/invoiced_sales.py:166-230` (`_traced_sales_order_ids`). A
billing line reaches a sales order only through what the AutoCount push stored on it:
`sales_order_line_id` (resolved at ingest, `app/services/finance/billing_document_ingest_service.py:550-604`),
or `from_doc_type` / `from_doc_no` (stored as sent, `:490-492`; schema
`app/schemas/canonical_documents.py:475-479`, all optional). The CRM has no other way in: billing
documents arrive only by the shared-service push (`BillingDocumentIngestService`, no pull exists).

What the prod result already proves, before any new query:

- The chain code works: 24 documents trace, and the 27 Oct query mirrored the code path for path.
- No January invoice traces, and a January credit note can inherit only from an invoice that
  traces (`in_traced_sales_orders`, `invoiced_sales.py:259-272`). So the 24 trace by their own
  lines or by an older invoice: the break is on the January invoices' lines, not in the SQL.

Which of the three it is (the push leaves `from_doc_*` empty; the push sends them but the DOs
they name are not in `orders`; the DOs are there but not linked to an SO) is what owner SQL
R1 to R4 decide. Under the rule proposed below the answer no longer moves a sales figure; it
still matters for the Related tabs (DOC-RELATIONS) and is fixed as its own step.

### 2b. Measured on prod (owner, round 2)

- **The ingest-time link never fires.** 0 of 17,392 January invoice lines carry `from_line_ref`, and
  no invoice line in any month July 2025 to February 2026 has a `sales_order_line_id`. The push sends
  `from_doc_type = 'DO'` and the DO number (`from_doc_no`) on 17,392 of 17,541 lines, never the DO
  line ref the hop needs (`billing_document_ingest_service.py:550-604`).
- **The read-time path has no DO to follow.** SRT holds 0 AutoCount DOs (`doc_key` set) dated
  October 2025 to February 2026. The 11 to 24 DOs a month it does hold are CRM-made (no `doc_key`,
  no lines), so the 11 January DOs an invoice names reach no SO. The DO book `db1` holds 132,730
  older rows. R12 dates when DOs stopped arriving.
- So the trace code is right and has nothing to follow: **the DO feed has a gap.** Fix: the DO
  push (or the DO pull's `backfill`) for July 2025 onwards. Once the DOs land, their lines name
  their SO (`FromDocNo`) and the invoices trace with no CRM code change. A second, independent
  fix on the shared service would send `from_line_ref` on invoice lines.
- **No genuine cross-type selling on SOs** (R8, SOs Nov 2025 to Jan 2026): every SO with a STATED
  order type is a Project-list agent stating `project`. The agents whose SOs sit in two classes
  have 0 stated types: stale stamps that the re-derive fixes.
- **Class lists confirmed to the cent** (R9 dry run): retail 27 agents 6,513,047.67 = AutoCount
  Dealer; project 21 agents 8,229,111.30 = Project team 6,084,471.57 + the five left-out agents
  2,144,639.73 (unfilled in that run); no agent 120.32.
- **R10**: 5,760 documents untraced (reason 3); the 14 traced gaps are all reason 6 (SO class
  stale, DATA), none GENUINE. Reason 6 also fires when a document traces to a `retail` SO AND an
  SO with no stored class (the class count ignores NULLs, so the block reads Dealer); the
  re-derive fills that class.
- **Incident 29 Oct** (R9 apply run with `<OTHER n>` unfilled): R11 D1 shows the class rows as
  before the run (the two agents without a row still have none; the four with one `retail` row
  keep it, written 27 Oct 19:38). The apply did NOT land; no correction needed.

### 2c. Repair (the DO feed gap)

No CRM code change: the trace reads DO numbers at report time, so DOs that land now trace every
past invoice that names them. Options, after R12 dates the gap:

1. **Backfill with the existing DO pull**, month by month from July 2025 (`POST
   /api/v1/autocount/pulls`, entity `delivery_orders`, scope `fromDay` / `toDay`; at most 10,000
   DOs a snapshot, `autocount_pull_service.py:57`, `:701`): preview, then apply. A CRM-made DO with
   the same number is adopted, not duplicated (`autocount_doc_ingest_service.py`, Q8 a).
2. **Restore the shared-service DO push** for new DOs (outside this repo), so the gap does not
   reopen.
3. Optional, shared service: send `from_line_ref` on invoice lines so `sales_order_line_id` is
   filled at push time. Not needed for the sales figure.

After the DOs land: R10 again (expected only reasons 1, 5 and any genuine 4), then the tally.

Proven on seeded data (`sorento_crm_backend/tests/test_sales_split_tally_do_backfill.py`): a
January invoice naming a DO reads No sales order; the DO ingest the pull's apply runs
(`autocount_pull_tasks.py:868-901` -> `AutocountDocIngestService`, `FromDocNo` kept at
`autocount_doc_ingest_service.py:1165`) lands the DO; the same invoice then reads its SO's block
(retail -> Dealer, project -> Project team). A CRM-made DO with the same number is adopted (one
row, `doc_key` set, its new line names the SO) and traces too. Kill test: removing the DO-number
hop from `_traced_sales_order_ids` fails all three. The pull's preview sheet leaves `FromDocNo`
out (`autocount_pull_service.map_delivery_order_rows`), but the apply never reads that sheet.

### 2d. The gap, dated (R12, R13; crew, prod backup of 28 Oct 19:00)

- AutoCount DOs in SRT: Jul 2024 to Aug 2025 (written 24 Oct by the DO-HISTORY shared-service
  backfill) and Aug 2026 onwards (the live push since 17 Aug 2026). **Missing: Sep 2025 to Jul
  2026, 11 months** (by day: 19 Aug 2025 to 19 Aug 2026, crew's dry run, 2e), which holds every January 2026 DO. The history backfill stopped after Aug 2025.
- Set apart: the HANLIM group is three debtors, 300-H030, 300-H118, 300-H119, January 2026
  122,232.99 = AutoCount SET APART to the cent, one agent.
- Repair (superseded in detail by 2e): the shared service's DocDate DO backfill for the gap (the DO-HISTORY
  path, quiet: one IMPORT audit row per batch, no embedding work). Fallback: the CRM DO pull, one
  month at a time (about 4,000 to 6,000 DOs a month, under the 10,000 cap); it writes per-DO
  audit rows and queues embedding work, so it is the slower, noisier path. Check: R14, then R10.

### 2e. Run plan for the load (owner ask 1 (a)); crew runs it, nothing on prod until the owner approves

The load is the DO-HISTORY job (`documentation/plans/autocount/PLAN-do-history-backfill-13oct.md`
sections 2 (S3 rules), 4, 5 and 7). The shared service (SS) is not in this repo. Revised 29 Oct
after crew's dry run on the prod copy (crew-local record; no figures that name anyone are kept here):

- **Why the 24 Oct load stopped:** the SS job's 2-hour time limit, part way through 19 Aug 2025.
  No day failed. **The real gap is 19 Aug 2025 to 19 Aug 2026** (AutoCount DOs resume 20 Aug 2026).
- **The stopped load cannot simply be resumed for this:** it only spans to 27 Nov 2025, resuming it
  is itself a live run, and while it sits stopped the SS starts no new load. So the prod path is:
  discard the stopped load, then start ONE live load for the full range.
- **"Assume DOs delivered before":** prod (28 Oct backup) holds 27 Nov 2025. It must read
  **2026-07-01** for the run and be cleared after it (plan section 7.5), or about 25,600 of the
  loaded DOs read outstanding.

Steps:

1. **Where:** a prod copy behind a local CRM backend on `main`; the SS points at that backend.
2. **Before:** R15 on the copy; set "Assume DOs delivered before" = 2026-07-01 on the copy.
3. **Range and rules:** book db1 (Sorento) only, DocDate **2025-08-19 to 2026-08-19**, oldest
   first, one call in flight, envelope `"backfill": true` (one IMPORT audit row per batch, no
   per-DO audit and no search indexing; the SS sends 200 DOs a call).
4. **Dry run** (`?dry_run=true`), done 29 Oct on the 28 Oct copy: 0 failed, 0 retryable, no HTTP
   errors, DOs read = AutoCount's count in every month. Created 44,613, adopted 23,430, unchanged
   200 (the first call overlaps the DOs the 24 Oct load wrote on 19 Aug 2025); lines 161,576 new,
   64,367 matched. January 2026 invoice lines reaching an SO (R14): 17,236 of 17,392 (today 0).
5. **Real run on the copy**, then on the copy: R15 (gap months filled), R14, R10, and the owner's
   query 3 for SRT January 2026 (No sales order should fall from 14,871,452.95 to the share of
   the 156 lines that still reach no SO).
6. **Prod, after the owner approves 4 and 5:** discard the stopped load in the SS; set "Assume
   DOs delivered before" = 2026-07-01; start one live load for 2025-08-19 to 2026-08-19
   (about 70 to 75 minutes, about 500 audit rows, no emails, no embeddings); then R15 and R14;
   then clear the date.

## 3. How AutoCount builds the blocks

Measured on the owner's per-agent figures (query 3b, every agent, to the cent):

- **Dealer = the agents on the AutoCount Dealer list**: 27 agent codes, all the area-suffixed ones
  (code ending ` I`, ` III`, ` IV`), sum 6,513,047.67. Gap 0.00.
- **Project team = the agents on the Project list**: the 16 plain-named codes, sum 6,084,471.57.
  Gap 0.00.
- **Left out**: five codes (the Q10 "other" agents) plus `(no agent)`, sum 2,144,760.05. AutoCount
  shows 122,232.99 of it as **Set apart** (the set-apart debtors are sold by these agents) and
  leaves out 2,022,527.06 (= 14,742,279.29 - 12,719,752.23, to the cent).

So the AutoCount blocks are the document's own agent's list membership, with set-apart debtors
pulled out. They are not a sales order property: the 24 documents that do trace show it: 14 of them (three agents)
land in a different block by their SO than by their agent.

## 4. The rule (owner FINAL, 28 Oct ~09:30): the sales order's type decides

Ruling Q1 (b) stands, unchanged in code (`invoiced_sales.sales_type()`): set apart, else the
traced SOs' class (`retail` Dealer, `project` Project team, `other` Other, both Mixed, none set
Type not set), else No sales order. A document with no agent, or an agent with no class, follows
its SO too (Q2). The agent-class rule offered in round 1 is withdrawn. Owner, on the AutoCount
gap: "maybe the agent class or customer class is wrong? if it is data setting then we fix the data
setting". So every gap left after the trace repair is classified (R10) as:

- **DATA**: the set-apart debtors not entered (reason 2); the SO's stored class stale against its
  rule (6); the SO agent's class on the SO date not AutoCount's list (7). Fixed by R9 apply, the
  re-derive and the set-apart rows; nothing in code.
- **GENUINE cross-type sale**: the SO states an order type of the other kind (4), or the SO was sold
  by another agent than the invoice (5). AutoCount files these by the invoice's agent, the CRM by
  the SO: they stay as a stated difference (or the owner corrects the SO in AutoCount).
- **CHAIN**: no SO traced (3). Fixed by the trace repair (Q5, this lane, after R1 to R7).

A customer's debtor type is the report's column in both systems and never picks a block.

### Expected January 2026 SRT under the rule

| Block | Today (prod) | After R9 apply + re-derive + set-apart rows, before the trace repair | AutoCount |
| --- | ---: | ---: | ---: |
| Dealer | -36,140.28 | -2,063.26 if GENUINE, -2,222.26 if DATA (note) | 6,513,047.67 |
| Project team | -93,033.38 | -93,033.38 if GENUINE, -92,874.38 if DATA | 6,084,471.57 |
| Other | 0.00 | -34,077.02 | (left out) |
| Set apart | 0.00 | the set-apart debtors' share of the 24 (0.00 on the 24 today) | 122,232.99 |
| No sales order | 14,871,452.95 | 14,871,452.95 | |
| ALL SALES | 14,742,279.29 | 14,742,279.29 | 14,742,279.29 |

Note: one traced credit note, -159.00, is on a `project` SO of a Dealer-list agent: Project team if
R10 calls it GENUINE (reason 4 or 5), Dealer if DATA (reason 7).

After the trace repair, each block is AutoCount's figure minus the GENUINE documents (reasons 4
and 5), which R10 lists one by one, plus whatever still traces to no SO. On the 24 that trace
today, the GENUINE share is at most -159.00. The figure to the cent can only be stated once the
January invoices trace, which needs R1 to R7.

## 5. Data steps (owner Q3 (a) and Q4, crew SQL after a dry run)

1. R9 dry run (SELECT): every January agent, its class today, the proposed class (AutoCount's
   lists) and January RM; the per-class sums must read retail 6,513,047.67, project 6,084,471.57,
   other + no agent 2,144,760.05 before anything is written. the agent Q4 leaves blank stays blank.
2. R9 apply (held for the owner), then `scripts/sales_order_class_rederive.py --company SRT`
   dry run, then `--apply`.
3. The four set-apart debtors with their start month (R6 to confirm 122,232.99).
4. R10 again: only reasons 1, 3, 4, 5 should remain.

R9 and R10 are run as written, on seeded fictional data, by
`sorento_crm_backend/tests/test_sales_split_tally_owner_sql.py` (kill-tested: breaking the
stated-type mapping or the Dealer-list match fails all three tests).
