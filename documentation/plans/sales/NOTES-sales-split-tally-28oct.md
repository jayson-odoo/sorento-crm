# NOTES: Sales split tally (Dealer / Project team / Set apart vs AutoCount)

Status: Plan; rule ruled (owner 28 Oct ~09:30: the SO's order type decides). Root cause measured:
the DO feed gap (2b). Waiting on R11 (incident check), R12, R13 and the owner's call on the DO feed. crew-lane: SALES-SPLIT-TALLY.
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
  stale, DATA), none GENUINE.

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
   other + no agent 2,144,760.05 before anything is written. IRENE stays blank (Q4).
2. R9 apply (held for the owner), then `scripts/sales_order_class_rederive.py --company SRT`
   dry run, then `--apply`.
3. The four set-apart debtors with their start month (R6 to confirm 122,232.99).
4. R10 again: only reasons 1, 3, 4, 5 should remain.

R9 and R10 are run as written, on seeded fictional data, by
`sorento_crm_backend/tests/test_sales_split_tally_owner_sql.py` (kill-tested: breaking the
stated-type mapping or the Dealer-list match fails all three tests).
