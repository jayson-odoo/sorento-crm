# NOTES: Sales split tally (Dealer / Project team / Set apart vs AutoCount)

Status: Plan, behaviour card out for the owner's ruling (28 Oct 2026). crew-lane: SALES-SPLIT-TALLY.
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

## 4. Proposed rule (changes ruling Q1 (b) for the invoiced basis)

A billing document's sales type, first match wins:

1. **Set apart**: the customer has a `sales.set_apart_customers` row covering the document's month
   (unchanged).
2. **The class of the document's own agent on the document date** (`sales.agent_classes`, the
   dated table of ruling Q6; an agent with no dated row reads `sales_agents.demand_class`, the
   same fallback as `agent_class_service.ClassCache`): `retail` Dealer, `project` Project team,
   `other` Other.
3. Else **No agent class** (no agent, or an agent with no class): visible, never guessed.

The agent is `invoiced_sales.agent_id()` (the document's own, or the customer's on Mocha).
Never a sales order, a customer segment or the stored `billing_documents.demand_class`.

Changes ruling **Q1 (b)** ("the sales type should depend on sales order") for invoiced sales:
the SO chain stays for the Related tabs but stops deciding the invoiced block. Q8 (a) (no
customer-segment fallback) holds. Ordered and Delivered bases are unchanged (they read
`sales_orders.demand_class`).

January 2026 SRT under this rule, once the class data matches the AutoCount lists (section 5):

| Block | CRM | AutoCount | Gap |
| --- | ---: | ---: | ---: |
| Dealer | 6,513,047.67 | 6,513,047.67 | 0.00 |
| Project team | 6,084,471.57 | 6,084,471.57 | 0.00 |
| Set apart | 122,232.99 (expected; R6 confirms the debtors) | 122,232.99 | 0.00 |
| Other + No agent class | 2,022,527.06 | (left out) | |
| ALL SALES | 14,742,279.29 | 14,742,279.29 | 0.00 |

The alternative (SO chain first, agent class only for "No sales order") lands Dealer -33,918.02
and Project team -159.00 from AutoCount on January, and drifts further as the invoice chain is
repaired.

## 5. Data steps it needs (owner, crew SQL, after a dry run)

1. Agent classes, from the start, open: the 27 Dealer-list codes `retail`; the 16 Project-list
   codes `project` (one of them is `retail` on prod today); the five left-out codes `other` (prod
   today: three `retail`, two with no class). Crew holds the lists.
2. The four set-apart debtors with their start month (R6 lists January debtors to confirm they
   sum to 122,232.99).
3. Optional for this tally, needed for SCM and the ordered basis: `scripts/sales_order_class_rederive.py`
   dry run, then `--apply`.
