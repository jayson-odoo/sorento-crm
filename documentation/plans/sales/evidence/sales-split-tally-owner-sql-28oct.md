# SALES-SPLIT-TALLY: read-only SQL for the owner (prod), round 1, 28 Oct 2026

Every block is `BEGIN READ ONLY; ... ROLLBACK;`: nothing is written. Run in psql on prod, paste the
output back to crew. Company SRT, January 2026, posted documents only (the `invoiced_sales.posted()`
filter). Table and column names are from `app/models/finance.py`, `app/models/order.py`,
`app/models/sales.py`, `app/models/sales_agent.py`.

The chain being diagnosed is `app/services/sales/invoiced_sales.py:166-230`
(`_traced_sales_order_ids`): a billing line traces to an SO by (1) `sales_order_line_id`, (2)
`from_doc_type='SO'` + `from_doc_no = so_number`, (3) `from_doc_type='DO'` + `from_doc_no =` a DO's
`order_number` in the same company, then that DO's SO by its lines or header.

## R1. What the January lines carry (the push shape)

Purpose: how many Jan 2026 SRT lines name a source document at all, and of which type.
Expected if the push is the cause: invoice lines mostly `from_doc_type` NULL and
`with_so_line_id` 0. Expected if the DO side is the cause: invoice lines mostly `DO` with a
`from_doc_no`, and R2 shows those DO numbers missing.

```sql
BEGIN READ ONLY;
SELECT d.document_type,
       coalesce(l.from_doc_type, '(null)')               AS from_doc_type,
       count(DISTINCT d.id)                               AS docs,
       count(l.id)                                        AS lines,
       count(l.from_doc_no)                               AS with_from_doc_no,
       count(l.from_line_ref)                             AS with_from_line_ref,
       count(l.sales_order_line_id)                       AS with_so_line_id,
       min(l.from_doc_no)                                 AS sample_min_no,
       max(l.from_doc_no)                                 AS sample_max_no,
       min(l.from_line_ref)                               AS sample_line_ref
FROM finance.billing_documents d
JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
LEFT JOIN finance.billing_document_lines l ON l.document_id = d.id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
GROUP BY 1, 2 ORDER BY 1, 2;
ROLLBACK;
```

## R2. Do the DOs the invoices name exist in the CRM?

Purpose: for lines transferred from a DO, is that DO in `orders` under SRT, under another
company, or nowhere. Expected: if `in_srt` is near 0 and `nowhere` near all, the DO feed does
not carry these DOs (or numbers them differently: compare the samples).

```sql
BEGIN READ ONLY;
WITH srt AS (SELECT id FROM companies WHERE code = 'SRT'),
lines AS (
  SELECT DISTINCT l.from_doc_no
  FROM finance.billing_documents d
  JOIN finance.billing_document_lines l ON l.document_id = d.id
  WHERE d.company_id = (SELECT id FROM srt) AND d.status = 'posted'
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
    AND l.from_doc_type = 'DO' AND l.from_doc_no IS NOT NULL)
SELECT count(*)                                                         AS do_numbers,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM orders o WHERE o.order_number = lines.from_doc_no
                                     AND o.company_id = (SELECT id FROM srt) AND o.deleted_at IS NULL)) AS in_srt,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM orders o WHERE o.order_number = lines.from_doc_no
                                     AND o.company_id <> (SELECT id FROM srt)))                       AS other_company_only,
       count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_number = lines.from_doc_no)) AS nowhere,
       (array_agg(from_doc_no ORDER BY from_doc_no))[1:5]               AS sample_numbers
FROM lines;
-- What SRT DO numbers look like, and how current the AutoCount DO feed is.
SELECT date_trunc('month', o.order_date)::date AS month,
       count(*)                                  AS dos,
       count(*) FILTER (WHERE o.doc_key IS NOT NULL) AS from_autocount,
       min(o.order_number) AS min_no, max(o.order_number) AS max_no
FROM orders o JOIN companies c ON c.id = o.company_id AND c.code = 'SRT'
WHERE o.order_date >= '2025-10-01' AND o.order_date < '2026-03-01' AND o.deleted_at IS NULL
GROUP BY 1 ORDER BY 1;
ROLLBACK;
```

## R3. The DOs that are there: do they reach an SO?

Purpose: of the SRT DOs named by January invoice lines, how many link to an SO by any of the
three DO -> SO rules. Expected: if R2 `in_srt` is high but `reaches_so` low, the break is DO ->
SO (DO lines not ingested or not linked).

```sql
BEGIN READ ONLY;
WITH srt AS (SELECT id FROM companies WHERE code = 'SRT'),
dos AS (
  SELECT DISTINCT o.id, o.sales_order_id
  FROM finance.billing_documents d
  JOIN finance.billing_document_lines l ON l.document_id = d.id
  JOIN orders o ON o.order_number = l.from_doc_no AND o.company_id = d.company_id AND o.deleted_at IS NULL
  WHERE d.company_id = (SELECT id FROM srt) AND d.status = 'posted'
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01' AND l.from_doc_type = 'DO')
SELECT count(*) AS dos,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = dos.id)) AS with_lines,
       count(*) FILTER (WHERE dos.sales_order_id IS NOT NULL) AS header_so,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = dos.id
                                      AND ol.sales_order_line_id IS NOT NULL)) AS line_so,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_lines ol JOIN sales_orders so
                                        ON so.so_number = ol.from_doc_no AND so.company_id = (SELECT id FROM srt)
                                      WHERE ol.order_id = dos.id
                                        AND (ol.from_doc_type IS NULL OR ol.from_doc_type = 'SO'))) AS number_so,
       count(*) FILTER (WHERE dos.sales_order_id IS NOT NULL
         OR EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = dos.id AND ol.sales_order_line_id IS NOT NULL)
         OR EXISTS (SELECT 1 FROM order_lines ol JOIN sales_orders so
                      ON so.so_number = ol.from_doc_no AND so.company_id = (SELECT id FROM srt)
                    WHERE ol.order_id = dos.id AND (ol.from_doc_type IS NULL OR ol.from_doc_type = 'SO'))) AS reaches_so
FROM dos;
ROLLBACK;
```

## R4. The 24 documents that do trace

Purpose: confirm the tracing documents are credit notes inheriting an OLDER invoice's orders
(their `against` invoice in 2025), which would mean the chain works for older documents and the
break is recent. Expected: `credit_note`, against month before 2026-01.

```sql
BEGIN READ ONLY;
SELECT d.document_type, date_trunc('month', a.doc_date)::date AS against_month,
       count(*) AS docs, sum(d.local_net_total) AS rm_unsigned,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM finance.billing_document_lines l
                                      WHERE l.document_id = a.id AND l.from_doc_type IS NOT NULL)) AS against_has_from_doc
FROM finance.billing_documents d
JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
LEFT JOIN finance.billing_documents a ON a.id = d.against_document_id
WHERE d.status = 'posted' AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
  AND d.document_type IN ('credit_note','debit_note')
GROUP BY 1, 2 ORDER BY 1, 2;
-- Same R1 shape for the invoices of Oct to Dec 2025: did older pushes carry from_doc_*?
SELECT date_trunc('month', d.doc_date)::date AS month,
       count(l.id) AS lines, count(l.from_doc_type) AS with_from_doc_type,
       count(l.sales_order_line_id) AS with_so_line_id
FROM finance.billing_documents d
JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
JOIN finance.billing_document_lines l ON l.document_id = d.id
WHERE d.status = 'posted' AND d.document_type = 'invoice'
  AND d.doc_date >= '2025-07-01' AND d.doc_date < '2026-03-01'
GROUP BY 1 ORDER BY 1;
ROLLBACK;
```

## R5. Sales by the invoice's own agent (the candidate rule)

Purpose: the figure per agent and per agent class (dated class on the document date, else the
agent's current class), so crew can put each agent beside the AutoCount report's DEALER and
PROJECT TEAM agent lists and compute the block totals the agent rule gives, to the cent.
Expected: the per-agent RM sum is 14,742,279.29; the agents AutoCount lists under DEALER sum to
6,513,047.67 and under PROJECT TEAM to 6,084,471.57 (less any set-apart debtor).

```sql
BEGIN READ ONLY;
WITH srt AS (SELECT id FROM companies WHERE code = 'SRT'),
docs AS (
  SELECT d.*, CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END AS rm,
         date_trunc('month', d.doc_date)::date AS month
  FROM finance.billing_documents d
  WHERE d.company_id = (SELECT id FROM srt) AND d.status = 'posted'
    AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01')
SELECT coalesce(a.sales_agent, nullif(btrim(docs.agent_code), ''), '(no agent)') AS agent,
       coalesce((SELECT ac.demand_class FROM sales.agent_classes ac
                 WHERE ac.sales_agent_id = docs.sales_agent_id
                   AND (ac.from_month IS NULL OR ac.from_month <= docs.month)
                   AND (ac.to_month IS NULL OR ac.to_month >= docs.month) LIMIT 1),
                a.demand_class, '(none)') AS class_on_doc_date,
       count(*) AS docs, sum(docs.rm) AS rm
FROM docs LEFT JOIN sales_agents a ON a.id = docs.sales_agent_id
GROUP BY 1, 2 ORDER BY 2, 1;
ROLLBACK;
```

## R6. The debtors AutoCount sets apart

Purpose: AutoCount's SET APART block is 122,232.99 but `sales.set_apart_customers` has no SRT row
covering January. Lists the January debtors with their RM so crew can match the four set-apart
debtor codes to the 122,232.99. Expected: some subset of debtors summing to 122,232.99.

```sql
BEGIN READ ONLY;
SELECT d.debtor_code, count(*) AS docs,
       sum(CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END) AS rm,
       string_agg(DISTINCT coalesce(d.agent_code, '-'), ',') AS agents
FROM finance.billing_documents d JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
WHERE d.status = 'posted' AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
GROUP BY 1 ORDER BY 3 DESC LIMIT 60;
ROLLBACK;
```

# Round 2 (28 Oct, after the owner's Q1 pushback: the block follows the SO's order type)

Run R1 to R4 first (above), then R7. R8 answers "an agent can handle both retail and project".
R9 is the class-data dry run (Q3): a SELECT only; its apply block is held for the owner.

## R7. Why `sales_order_line_id` stays empty (the ingest-time DO hop)

Purpose: `sales_order_line_id` is resolved ONCE, when the invoice is pushed
(`billing_document_ingest_service.py:550-604`): the line's `from_line_ref`
`{book}:DO:{DocKey}:{DtlKey}` must name a DO line already in `orders` / `order_lines` that already
carries a `sales_order_line_id`. Nothing re-resolves it later. This shows, per outcome, whether the
ref is missing or malformed, the DO or its line is missing, the DO line has no SO line, or the DO
arrived AFTER the invoice (so the hop missed it). Expected: one outcome holds most lines.

```sql
BEGIN READ ONLY;
WITH srt AS (SELECT id FROM companies WHERE code = 'SRT'),
l AS (
  SELECT l.id, l.from_line_ref, l.sales_order_line_id, d.created_at AS doc_created,
         split_part(l.from_line_ref, ':', 1) AS book,
         split_part(l.from_line_ref, ':', 2) AS kind,
         split_part(l.from_line_ref, ':', 3) AS doc_key,
         split_part(l.from_line_ref, ':', 4) AS dtl_key
  FROM finance.billing_documents d
  JOIN finance.billing_document_lines l ON l.document_id = d.id
  WHERE d.company_id = (SELECT id FROM srt) AND d.status = 'posted' AND d.document_type = 'invoice'
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'),
r AS (
  SELECT l.*, o.id AS do_id, o.created_at AS do_created, ol.id AS do_line_id,
         ol.sales_order_line_id AS do_so_line
  FROM l
  LEFT JOIN orders o ON l.kind = 'DO' AND l.doc_key ~ '^[0-9]{1,18}$'
        AND o.company_id = (SELECT id FROM srt) AND o.source_book = l.book AND o.doc_key = l.doc_key::bigint
  LEFT JOIN order_lines ol ON ol.order_id = o.id AND l.dtl_key ~ '^[0-9]{1,18}$' AND ol.dtl_key = l.dtl_key::bigint)
SELECT CASE
         WHEN sales_order_line_id IS NOT NULL THEN '0 linked'
         WHEN from_line_ref IS NULL           THEN '1 no from_line_ref'
         WHEN kind <> 'DO'                    THEN '2 ref not a DO ref: ' || kind
         WHEN do_id IS NULL                   THEN '3 DO (book + DocKey) not in CRM'
         WHEN do_line_id IS NULL              THEN '4 DO there, line (DtlKey) not'
         WHEN do_so_line IS NULL              THEN '5 DO line has no SO line'
         WHEN do_created > doc_created        THEN '6 DO arrived after the invoice'
         ELSE                                      '7 resolvable now, not resolved'
       END AS outcome,
       count(*) AS lines,
       (array_agg(from_line_ref ORDER BY from_line_ref))[1:3] AS sample_refs
FROM r GROUP BY 1 ORDER BY 1;
-- The books the DO feed has, against the books the invoice refs name.
SELECT 'orders' AS src, source_book, count(*) FROM orders
WHERE company_id = (SELECT id FROM companies WHERE code = 'SRT') AND doc_key IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'invoice refs', split_part(l.from_line_ref, ':', 1), count(*)
FROM finance.billing_documents d JOIN finance.billing_document_lines l ON l.document_id = d.id
WHERE d.company_id = (SELECT id FROM companies WHERE code = 'SRT') AND d.doc_date >= '2026-01-01'
  AND d.doc_date < '2026-02-01' AND l.from_line_ref IS NOT NULL GROUP BY 2
ORDER BY 1, 2;
ROLLBACK;
```

## R8. Do agents sell both types on their sales orders?

Purpose: the owner's point, "sometimes the agent can be handling both retail and project". Per
agent, SRT sales orders dated Nov 2025 to Jan 2026 by stored class, and how many carry an order
type AutoCount STATED (only a stated type can differ from the agent's class: the re-derive rule
is stated order type, else the agent's class on the SO date,
`agent_class_service.py` `_rederive`). Expected: on the dev copy 4,979 of 5,000 SOs stated no type,
so most agents show one class; an agent with real rows in two classes is the case the owner means.

```sql
BEGIN READ ONLY;
SELECT coalesce(a.sales_agent, '(no agent)') AS agent,
       coalesce(so.demand_class, '(none)')   AS so_class,
       count(*)                               AS sos,
       count(*) FILTER (WHERE nullif(btrim(so.order_type), '') IS NOT NULL) AS stated_type,
       string_agg(DISTINCT nullif(btrim(so.order_type), ''), ', ') AS stated_values,
       coalesce(sum((SELECT sum(sol.line_total) FROM sales_order_lines sol WHERE sol.sales_order_id = so.id)), 0) AS rm
FROM sales_orders so
JOIN companies c ON c.id = so.company_id AND c.code = 'SRT'
LEFT JOIN sales_agents a ON a.id = so.sales_agent_id
WHERE so.order_date >= '2025-11-01' AND so.order_date < '2026-02-01'
GROUP BY 1, 2 ORDER BY 1, 2;
ROLLBACK;
```

## R9. Class data (Q3): dry run

Purpose: the agent-class fix, as a SELECT that changes nothing. Every SRT agent with a January
2026 billing document, its class today (dated rows, and the `sales_agents.demand_class` mirror),
the proposed class, and January RM, plus the RM per proposed class. Proposed (crew lists, owner
Q3/Q4): an area-suffixed code (ending ` I`, ` II`, ` III`, ` IV`, ` V`) `retail`; the five codes in
`other_codes` `other`; every other agent with January sales `project`; the agent Q4 leaves blank is untouched.
Crew fills `other_codes` from its Q10 list before relaying (the list is not committed here).

Expected per proposed class: retail 6,513,047.67, project 6,084,471.57, other + no agent
2,144,760.05 (set apart comes out of that once the 4 debtors are entered), total 14,742,279.29.
That proves the class lists are AutoCount's lists before anything is written. It does NOT
predict the SO-type split: that also needs the re-derive and the invoice chain (R1 to R7).

```sql
BEGIN READ ONLY;
WITH other_codes(code) AS (VALUES ('<OTHER 1>'), ('<OTHER 2>'), ('<OTHER 3>'), ('<OTHER 4>'), ('<OTHER 5>')),
jan AS (
  SELECT d.sales_agent_id,
         sum(CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END) AS rm
  FROM finance.billing_documents d JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
  WHERE d.status = 'posted' AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
  GROUP BY 1),
plan AS (
  SELECT a.id, a.sales_agent, a.demand_class AS mirror_now, jan.rm,
         (SELECT string_agg(ac.demand_class || ' ' || coalesce(ac.from_month::text, 'start') || '..'
                            || coalesce(ac.to_month::text, 'open'), '; ' ORDER BY ac.from_month NULLS FIRST)
          FROM sales.agent_classes ac WHERE ac.sales_agent_id = a.id) AS rows_now,
         (SELECT count(*) FROM sales.agent_classes ac WHERE ac.sales_agent_id = a.id) AS n_rows,
         CASE WHEN upper(btrim(a.sales_agent)) IN (SELECT code FROM other_codes) THEN 'other'
              WHEN upper(btrim(a.sales_agent)) ~ ' (I|II|III|IV|V)$'             THEN 'retail'
              ELSE 'project' END AS proposed
  FROM jan JOIN sales_agents a ON a.id = jan.sales_agent_id)
SELECT sales_agent, rows_now, mirror_now, proposed, n_rows,
       CASE WHEN n_rows > 1 THEN 'CHECK BY HAND: dated history'
            WHEN coalesce(rows_now, '') = proposed || ' start..open' AND mirror_now = proposed THEN 'no change'
            ELSE 'change' END AS action,
       rm
FROM plan ORDER BY proposed, sales_agent;
-- RM per proposed class (the tally check), and the documents with no agent.
WITH other_codes(code) AS (VALUES ('<OTHER 1>'), ('<OTHER 2>'), ('<OTHER 3>'), ('<OTHER 4>'), ('<OTHER 5>')),
jan AS (
  SELECT d.sales_agent_id,
         sum(CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END) AS rm
  FROM finance.billing_documents d JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
  WHERE d.status = 'posted' AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
  GROUP BY 1)
SELECT proposed, count(*) AS agents, sum(rm) AS rm FROM (
  SELECT CASE WHEN upper(btrim(a.sales_agent)) IN (SELECT code FROM other_codes) THEN 'other'
              WHEN upper(btrim(a.sales_agent)) ~ ' (I|II|III|IV|V)$' THEN 'retail'
              WHEN a.id IS NULL THEN '(no agent)' ELSE 'project' END AS proposed, jan.rm
  FROM jan LEFT JOIN sales_agents a ON a.id = jan.sales_agent_id) x
GROUP BY 1 ORDER BY 1;
ROLLBACK;
```

### R9 apply (HELD: the owner runs it only after reading the dry run)

Incident 29 Oct: this block was once run on prod with `<OTHER n>` unfilled, which sets the five
left-out agents to `project`. Check and correction: section R11 below. The guard now refuses an
unfilled run.

Writes, for every agent the dry run marks `change` and that has at most one dated row: one dated
row `{proposed} from start to open` (the existing single row is updated in place, else one is
inserted), and the `sales_agents.demand_class` mirror. Agents marked `CHECK BY HAND` are skipped.
After it: `python -m scripts.sales_order_class_rederive --company SRT` (dry run), read it, then
the same with `--apply` (the SO classes follow the agent classes; plan 2.9 Q8).

```sql
BEGIN;
-- Guard (added 29 Oct after the apply was run once with the placeholders unfilled): stops here,
-- writing nothing, unless every <OTHER n> is filled with the code of an existing agent.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM (VALUES ('<OTHER 1>'), ('<OTHER 2>'), ('<OTHER 3>'), ('<OTHER 4>'), ('<OTHER 5>')) v(code)
    WHERE v.code LIKE '<%'
       OR NOT EXISTS (SELECT 1 FROM public.sales_agents a WHERE upper(btrim(a.sales_agent)) = v.code))
  THEN RAISE EXCEPTION 'R9 apply: fill every <OTHER n> with an existing agent code first; nothing written';
  END IF;
END $$;
WITH other_codes(code) AS (VALUES ('<OTHER 1>'), ('<OTHER 2>'), ('<OTHER 3>'), ('<OTHER 4>'), ('<OTHER 5>')),
jan_agents AS (
  SELECT DISTINCT d.sales_agent_id AS id
  FROM finance.billing_documents d JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
  WHERE d.status = 'posted' AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
    AND d.sales_agent_id IS NOT NULL),
plan AS (
  SELECT a.id,
         CASE WHEN upper(btrim(a.sales_agent)) IN (SELECT code FROM other_codes) THEN 'other'
              WHEN upper(btrim(a.sales_agent)) ~ ' (I|II|III|IV|V)$' THEN 'retail'
              ELSE 'project' END AS proposed
  FROM sales_agents a JOIN jan_agents j ON j.id = a.id
  WHERE (SELECT count(*) FROM sales.agent_classes ac WHERE ac.sales_agent_id = a.id) <= 1),
upd AS (
  UPDATE sales.agent_classes ac SET demand_class = p.proposed, from_month = NULL, to_month = NULL,
         updated_at = now()
  FROM plan p WHERE ac.sales_agent_id = p.id AND ac.demand_class IS DISTINCT FROM p.proposed
  RETURNING ac.sales_agent_id),
ins AS (
  INSERT INTO sales.agent_classes (id, sales_agent_id, demand_class, from_month, to_month)
  SELECT gen_random_uuid(), p.id, p.proposed, NULL, NULL FROM plan p
  WHERE NOT EXISTS (SELECT 1 FROM sales.agent_classes ac WHERE ac.sales_agent_id = p.id)
  RETURNING sales_agent_id)
UPDATE sales_agents a SET demand_class = p.proposed
FROM plan p WHERE a.id = p.id AND a.demand_class IS DISTINCT FROM p.proposed;
-- Check before COMMIT: re-run the R9 dry run inside this transaction; every row 'no change'
-- except CHECK BY HAND. Then COMMIT (or ROLLBACK).
```

# Round 3 (28 Oct ~09:30, owner FINAL on Q1: the SO's order type decides the block)

## R10. Every gap against AutoCount, document by document: DATA or GENUINE

Purpose: owner, 28 Oct: "maybe the agent class or customer class is wrong? if it is data setting
then we fix the data setting". For each January SRT document this puts the CRM block (the SO
type rule as built, `invoiced_sales.sales_type()`, same trace as crew query 3) beside the AutoCount
block (the document's own agent's AutoCount list, set-apart debtors first) and names the FIRST
reason that explains a difference:

| reason | kind | fixed by |
| --- | --- | --- |
| `1 match` | - | - |
| `2 set-apart debtor not entered` | DATA | entering the 4 set-apart debtors |
| `3 no sales order traced` | CHAIN | the trace repair (R1 to R7) |
| `4 SO states an order type of the other kind` | GENUINE cross-type sale (or a wrong SO type field in AutoCount: owner reads the samples) | nothing in the CRM, or AutoCount's SO |
| `5 SO sold by another agent than the invoice` | GENUINE (AutoCount files by the invoice's agent) | nothing, or the SO's / invoice's agent in AutoCount |
| `6 SO class stale` | DATA | `sales_order_class_rederive.py --apply` |
| `7 SO agent's class is not AutoCount's list` | DATA | R9 apply, then the re-derive |
| `8 other` | look at the samples | |

A customer's debtor type does not choose a block in either system (it is the report's COLUMN), so
it is not a reason here. Crew fills `other_codes` (5 agent codes) and `set_apart_codes` (4 debtor
codes) before relaying. Run it now (before the class fix) and again after R9 apply + re-derive:
after both, only reasons 1, 3, 4 and 5 should remain.

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '300s';
WITH other_codes(code) AS (VALUES ('<OTHER 1>'), ('<OTHER 2>'), ('<OTHER 3>'), ('<OTHER 4>'), ('<OTHER 5>')),
set_apart_codes(code) AS (VALUES ('<DEBTOR 1>'), ('<DEBTOR 2>'), ('<DEBTOR 3>'), ('<DEBTOR 4>')),
docs AS (
    SELECT bd.id, bd.company_id, bd.customer_id, bd.doc_date, bd.against_document_id, bd.doc_no,
           bd.sales_agent_id, upper(btrim(bd.debtor_code)) AS debtor_code,
           CASE WHEN bd.document_type = 'credit_note' THEN -bd.local_net_total ELSE bd.local_net_total END AS signed_rm
    FROM finance.billing_documents bd JOIN public.companies c ON c.id = bd.company_id
    WHERE c.code = 'SRT' AND bd.status = 'posted'
      AND bd.document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note')
      AND bd.doc_date >= DATE '2026-01-01' AND bd.doc_date < DATE '2026-02-01'),
need AS (SELECT id AS doc_id, company_id FROM docs
         UNION SELECT against_document_id, company_id FROM docs WHERE against_document_id IS NOT NULL),
do_hit AS (
    SELECT DISTINCT n.doc_id, n.company_id, o.id AS do_id
    FROM need n JOIN finance.billing_document_lines l ON l.document_id = n.doc_id
    JOIN public.orders o ON l.from_doc_type = 'DO' AND l.from_doc_no = o.order_number
    WHERE o.company_id = n.company_id AND o.deleted_at IS NULL),
traced AS (
    SELECT n.doc_id, n.company_id, sol.sales_order_id AS so_id
    FROM need n JOIN finance.billing_document_lines l ON l.document_id = n.doc_id
    JOIN public.sales_order_lines sol ON sol.id = l.sales_order_line_id
    UNION
    SELECT n.doc_id, n.company_id, so.id
    FROM need n JOIN finance.billing_document_lines l ON l.document_id = n.doc_id
    JOIN public.sales_orders so ON l.from_doc_type = 'SO' AND l.from_doc_no = so.so_number
    WHERE so.company_id = n.company_id
    UNION
    SELECT h.doc_id, h.company_id, sol.sales_order_id
    FROM do_hit h JOIN public.order_lines ol ON ol.order_id = h.do_id
    JOIN public.sales_order_lines sol ON sol.id = ol.sales_order_line_id
    UNION
    SELECT h.doc_id, h.company_id, so.id
    FROM do_hit h JOIN public.order_lines ol ON ol.order_id = h.do_id
    JOIN public.sales_orders so ON ol.from_doc_no = so.so_number
     AND (ol.from_doc_type IS NULL OR ol.from_doc_type = 'SO')
    WHERE so.company_id = h.company_id
    UNION
    SELECT h.doc_id, h.company_id, o.sales_order_id
    FROM do_hit h JOIN public.orders o ON o.id = h.do_id WHERE o.sales_order_id IS NOT NULL),
doc_sos AS (
    SELECT d.id AS document_id, t.so_id FROM docs d JOIN traced t ON t.doc_id = d.id AND t.company_id = d.company_id
    UNION
    SELECT d.id, t.so_id FROM docs d JOIN traced t ON t.doc_id = d.against_document_id AND t.company_id = d.company_id
    WHERE d.against_document_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM traced own WHERE own.doc_id = d.id AND own.company_id = d.company_id)),
agent_list AS (     -- the AutoCount list an agent is on (crew's Q10 lists; R9's rule)
    SELECT a.id,
           CASE WHEN upper(btrim(a.sales_agent)) IN (SELECT code FROM other_codes) THEN 'left_out'
                WHEN upper(btrim(a.sales_agent)) ~ ' (I|II|III|IV|V)$' THEN 'retail'
                ELSE 'project' END AS list_class
    FROM public.sales_agents a),
so_facts AS (       -- each traced SO: stored class, stated type's class, its agent's class on its date
    SELECT ds.document_id, so.id AS so_id, so.so_number, so.sales_agent_id AS so_agent, so.demand_class,
           CASE WHEN nullif(btrim(so.order_type), '') IS NULL THEN NULL
                WHEN lower(so.order_type) ~ '(project|contract)' THEN 'project' ELSE 'retail' END AS stated_class,
           coalesce(
             (SELECT ac.demand_class FROM sales.agent_classes ac
              WHERE ac.sales_agent_id = so.sales_agent_id
                AND (ac.from_month IS NULL OR ac.from_month <= date_trunc('month', so.order_date)::date)
                AND (ac.to_month IS NULL OR ac.to_month >= date_trunc('month', so.order_date)::date) LIMIT 1),
             CASE WHEN NOT EXISTS (SELECT 1 FROM sales.agent_classes ac WHERE ac.sales_agent_id = so.sales_agent_id)
                  THEN (SELECT a.demand_class FROM public.sales_agents a WHERE a.id = so.sales_agent_id) END
           ) AS so_agent_class_now
    FROM doc_sos ds JOIN public.sales_orders so ON so.id = ds.so_id),
kind AS (
    SELECT d.*,
           (SELECT list_class FROM agent_list al WHERE al.id = d.sales_agent_id) AS doc_list,
           (SELECT count(*) FROM so_facts f WHERE f.document_id = d.id) AS n_so,
           (SELECT count(DISTINCT f.demand_class) FROM so_facts f WHERE f.document_id = d.id) AS n_cls,
           (SELECT max(f.demand_class) FROM so_facts f WHERE f.document_id = d.id) AS one_cls,
           EXISTS (SELECT 1 FROM sales.set_apart_customers s
                   WHERE s.company_id = d.company_id AND s.customer_id = d.customer_id
                     AND s.from_month <= date_trunc('month', d.doc_date)::date
                     AND (s.to_month IS NULL OR s.to_month >= date_trunc('month', d.doc_date)::date)) AS set_apart_row
    FROM docs d),
blocks AS (
    SELECT k.*,
           CASE WHEN k.set_apart_row THEN 'set_apart'
                WHEN k.n_so = 0 THEN 'no_sales_order'
                WHEN k.n_cls > 1 THEN 'mixed'
                WHEN k.n_cls = 0 THEN 'type_not_set'
                WHEN k.one_cls = 'retail' THEN 'dealer'
                WHEN k.one_cls = 'project' THEN 'project'
                WHEN k.one_cls = 'other' THEN 'other' ELSE 'type_not_set' END AS crm_block,
           CASE WHEN k.debtor_code IN (SELECT code FROM set_apart_codes) THEN 'set_apart'
                WHEN k.doc_list = 'retail' THEN 'dealer'
                WHEN k.doc_list = 'project' THEN 'project'
                ELSE 'left_out' END AS ac_block
    FROM kind k),
want AS (SELECT b.*, CASE b.ac_block WHEN 'dealer' THEN 'retail' WHEN 'project' THEN 'project' END AS ac_cls FROM blocks b),
reasoned AS (
    SELECT w.*,
      CASE
        WHEN w.crm_block = w.ac_block OR (w.ac_block = 'left_out' AND w.crm_block IN ('other', 'type_not_set'))
             THEN '1 match'
        WHEN w.ac_block = 'set_apart' THEN '2 set-apart debtor not entered'
        WHEN w.n_so = 0 THEN '3 no sales order traced'
        WHEN EXISTS (SELECT 1 FROM so_facts f WHERE f.document_id = w.id AND f.stated_class IS NOT NULL
                     AND f.stated_class IS DISTINCT FROM coalesce(w.ac_cls, 'other'))
             THEN '4 SO states an order type of the other kind'
        WHEN EXISTS (SELECT 1 FROM so_facts f WHERE f.document_id = w.id
                     AND f.so_agent IS DISTINCT FROM w.sales_agent_id)
             THEN '5 SO sold by another agent than the invoice'
        WHEN EXISTS (SELECT 1 FROM so_facts f WHERE f.document_id = w.id
                     AND f.demand_class IS DISTINCT FROM coalesce(f.stated_class, f.so_agent_class_now))
             THEN '6 SO class stale'
        WHEN EXISTS (SELECT 1 FROM so_facts f WHERE f.document_id = w.id
                     AND f.stated_class IS NULL
                     AND f.so_agent_class_now IS DISTINCT FROM coalesce(w.ac_cls, 'other'))
             THEN '7 SO agent''s class is not AutoCount''s list'
        ELSE '8 other' END AS reason
    FROM want w)
SELECT reason, ac_block, crm_block, count(*) AS docs, sum(signed_rm) AS rm,
       (array_agg(doc_no ORDER BY abs(signed_rm) DESC))[1:3] AS sample_docs,
       (array_agg(DISTINCT (SELECT f.so_number FROM so_facts f WHERE f.document_id = reasoned.id LIMIT 1)))[1:3] AS sample_sos
FROM reasoned
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
ROLLBACK;
```

Expected now (before the class fix and the chain repair), from the owner's 28 Oct run (query 3
and 3b): reason 3 holds 5,760 documents, 14,871,452.95. Of the 24 traced: 10 match (Dealer 5 docs
-2,063.26, Project team 5 docs -92,874.38); 13 sit on `retail` SOs of two agents AutoCount leaves
out (-34,077.02: reason 6 or 7, DATA, fixed by R9 apply + re-derive); 1 sits on a `project` SO of a
Dealer-list agent (-159.00: reason 4, 5 or 7; R10 says which).

# Incident, 29 Oct: R9 apply run on prod with `<OTHER n>` unfilled

With no `<OTHER n>` filled, no agent matches `other_codes`, so the apply gives every agent with a
January 2026 SRT document (and at most one class row) ONE row `{class} from start to open` and the
same `sales_agents.demand_class`: an area-suffixed code `retail`, every other code `project`. The
five left-out agents become `project` instead of `other`. Every other agent gets exactly the class
the dry run proposed (its per-class sums matched AutoCount: retail 27 agents 6,513,047.67). It
writes no sales order; only an SO ingested afterwards reads the new class.
`tests/test_sales_split_tally_owner_sql.py` rehearses the incident, this check and this
correction.

## R11. Did it land? (READ ONLY)

`<OTHER n>` = the five left-out codes, `<PROJECT 1>` = the agent Q10 moves to project, `<NONE 1>` =
the agent Q4 leaves blank. Landed = D1 shows the five with ONE row `project start..open` and mirror
`project`, created or updated at the same second (D2). D3 shows a transaction still open (not
committed): ROLLBACK it in that client. D4: SOs stamped since, for the five.

```sql
BEGIN READ ONLY;
-- D1. The decisive check. Before the apply (owner's 3a / R5, 28 Oct 08:35 MYT): two of the five had NO
-- agent_classes row, the other three and <PROJECT 1> were 'retail'. The unfilled apply gives all six
-- ONE row 'project' from start to open, and mirror 'project'.
SELECT a.sales_agent, a.demand_class AS mirror_now,
       count(ac.id) AS class_rows,
       string_agg(ac.demand_class || ' ' || coalesce(ac.from_month::text, 'start') || '..'
                  || coalesce(ac.to_month::text, 'open')
                  || ' created ' || ac.created_at::text || ' updated ' || ac.updated_at::text, '; ') AS rows_now
FROM public.sales_agents a
LEFT JOIN sales.agent_classes ac ON ac.sales_agent_id = a.id
WHERE upper(btrim(a.sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>', '<PROJECT 1>', '<NONE 1>')
GROUP BY a.id, a.sales_agent, a.demand_class ORDER BY 1;
-- D2. Every class row created or updated after the owner's 3a run (28 Oct 08:35 MYT = 00:35 UTC;
-- if the server clock is MYT, read 08:35). The apply's footprint: same second, from start to open.
SELECT a.sales_agent, ac.demand_class, ac.from_month, ac.to_month, ac.created_at, ac.updated_at, a.demand_class AS mirror
FROM sales.agent_classes ac JOIN public.sales_agents a ON a.id = ac.sales_agent_id
WHERE ac.created_at >= TIMESTAMP '2026-10-28 00:30' OR ac.updated_at >= TIMESTAMP '2026-10-28 00:30'
ORDER BY greatest(ac.created_at, ac.updated_at), 1;
-- D3. Is the owner's client still holding the transaction open (uncommitted)? A row here with
-- state 'idle in transaction' that started at the apply time = NOT committed yet: in that client,
-- run ROLLBACK (or disconnect WITHOUT committing).
SELECT pid, usename, application_name, client_addr, state, xact_start, now() - xact_start AS open_for,
       left(query, 120) AS last_statement
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%' ORDER BY xact_start;
-- D4. Sales orders stamped since then for the five 'other' agents (the SO ingest reads the agent's
-- class on the SO date, so a landed apply stamps their NEW SOs 'project').
SELECT a.sales_agent, so.demand_class, count(*) AS sos, min(so.created_at) AS first, max(so.created_at) AS last
FROM public.sales_orders so JOIN public.sales_agents a ON a.id = so.sales_agent_id
WHERE upper(btrim(a.sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>')
  AND so.created_at >= TIMESTAMP '2026-10-28 00:30'
GROUP BY 1, 2 ORDER BY 1, 2;
ROLLBACK;
```

## R11 correction (HELD for the owner; only if R11 shows the apply landed)

Moves the five to `other` from start to open, row and mirror, which is the class rulings Q7 / Q10
give them; the rest of what the apply wrote is the approved target and stays. Its guard writes
nothing unless all five codes name an agent. After COMMIT: R11 D1 again, then
`python -m scripts.sales_order_class_rederive --company SRT` (dry run; it also re-derives any SO
D4 listed), then `--apply` once the owner has read it.

```sql
BEGIN;
-- C0. Guard: the five codes must each name exactly one agent, or nothing is written.
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.sales_agents
  WHERE upper(btrim(sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>');
  IF n <> 5 THEN RAISE EXCEPTION 'expected 5 agents, found %; nothing written', n; END IF;
END $$;
-- C1. The five left-out agents: their ONE class row (the one the apply wrote or overwrote) to
-- 'other' from start to open, the class Q10 / Q7 rules for them. An agent with more than one row
-- is left alone (fix it by hand on the Sales Agents screen).
UPDATE sales.agent_classes ac
SET demand_class = 'other', from_month = NULL, to_month = NULL, updated_at = now()
FROM public.sales_agents a
WHERE a.id = ac.sales_agent_id
  AND upper(btrim(a.sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>')
  AND (SELECT count(*) FROM sales.agent_classes x WHERE x.sales_agent_id = a.id) = 1;
-- C2. The same five with no row at all (apply did not land for them): one open 'other' row.
INSERT INTO sales.agent_classes (id, sales_agent_id, demand_class, from_month, to_month)
SELECT gen_random_uuid(), a.id, 'other', NULL, NULL FROM public.sales_agents a
WHERE upper(btrim(a.sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>')
  AND NOT EXISTS (SELECT 1 FROM sales.agent_classes x WHERE x.sales_agent_id = a.id);
-- C3. The mirror the Sales Agents grid and the weekly upload read.
UPDATE public.sales_agents SET demand_class = 'other'
WHERE upper(btrim(sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>');
-- C4. Check BEFORE COMMIT: five rows, each 'other', class_rows 1, mirror 'other'.
SELECT a.sales_agent, a.demand_class AS mirror, count(ac.id) AS class_rows,
       string_agg(ac.demand_class || ' ' || coalesce(ac.from_month::text, 'start') || '..'
                  || coalesce(ac.to_month::text, 'open'), '; ') AS rows_now
FROM public.sales_agents a LEFT JOIN sales.agent_classes ac ON ac.sales_agent_id = a.id
WHERE upper(btrim(a.sales_agent)) IN ('<OTHER 1>', '<OTHER 2>', '<OTHER 3>', '<OTHER 4>', '<OTHER 5>')
GROUP BY a.id, a.sales_agent, a.demand_class ORDER BY 1;
-- Then type COMMIT; (or ROLLBACK; if C4 is not five 'other' rows).
```

# Round 3 results (owner, 28/29 Oct) and the next queries

Read from the owner's round-2 output: no January invoice line carries `from_line_ref` (0 of
17,392 DO lines), and no invoice line in any month July 2025 to February 2026 has a
`sales_order_line_id`. So the ingest-time link (`billing_document_ingest_service.py:550-604`) never
fires. The read-time path needs the DO in `orders`, but SRT holds 0 AutoCount DOs (`doc_key` set)
dated October 2025 to February 2026 and only 11 to 24 CRM-made DOs a month (no lines). The DO book
`db1` holds 132,730 older rows. R12 dates the gap; R13 checks the set-apart debtors.

## R12. When did AutoCount DOs stop arriving?

Purpose: per month of DO date, the AutoCount DOs in SRT (rows, with lines, lines naming an SO, lines
linked to an SO line) and when they were written; then the DO pushes the audit log saw in the last
120 days. Expected: rows stop at some month (the feed gap); the audit shows no recent integration
writes on `orders`, or a backfill only.

```sql
BEGIN READ ONLY;
SELECT date_trunc('month', o.order_date)::date AS do_month,
       count(*) AS dos,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = o.id)) AS with_lines,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = o.id
                                      AND ol.from_doc_no IS NOT NULL)) AS naming_an_so,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = o.id
                                      AND ol.sales_order_line_id IS NOT NULL)) AS linked_to_so_line,
       min(o.created_at)::date AS first_written, max(o.created_at)::date AS last_written,
       min(o.order_number) AS min_no, max(o.order_number) AS max_no
FROM orders o JOIN companies c ON c.id = o.company_id AND c.code = 'SRT'
WHERE o.doc_key IS NOT NULL AND o.order_date >= '2024-07-01'
GROUP BY 1 ORDER BY 1;
SELECT max(o.order_date) AS latest_do_date, max(o.created_at) AS latest_written, max(o.updated_at) AS latest_updated,
       count(*) FILTER (WHERE o.order_date IS NULL) AS no_date
FROM orders o JOIN companies c ON c.id = o.company_id AND c.code = 'SRT' WHERE o.doc_key IS NOT NULL;
SELECT changed_at::date AS day, action, actor_type, count(*) AS rows
FROM audit_logs
WHERE entity_type = 'orders' AND changed_at >= now() - interval '120 days'
  AND (integration_id IS NOT NULL OR actor_type = 'integration')
GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2 LIMIT 60;
ROLLBACK;
```

## R13. The set-apart debtors' January sales

Purpose: AutoCount's SET APART block is 122,232.99. Sum the four debtor codes crew holds, per
agent, so the set-apart rows can be entered with confidence (and to confirm they are sold by
left-out agents only, which is what the per-agent tally says). Expected: total 122,232.99.

```sql
BEGIN READ ONLY;
SELECT upper(btrim(d.debtor_code)) AS debtor, coalesce(a.sales_agent, '(no agent)') AS agent, count(*) AS docs,
       sum(CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END) AS rm
FROM finance.billing_documents d
JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
LEFT JOIN sales_agents a ON a.id = d.sales_agent_id
WHERE d.status = 'posted' AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01'
  AND upper(btrim(d.debtor_code)) IN ('<DEBTOR 1>', '<DEBTOR 2>', '<DEBTOR 3>', '<DEBTOR 4>')
GROUP BY ROLLUP (1, 2) ORDER BY 1 NULLS LAST, 2 NULLS LAST;
ROLLBACK;
```

# Round 4 results (crew, 29 Oct, READ ONLY on the prod backup of 28 Oct 19:00)

- **R12.** SRT holds AutoCount DOs dated Jul 2024 to Aug 2025, all written 24 Oct 2026 (the
  DO-HISTORY shared-service backfill; the audit log shows its one IMPORT row per batch that day),
  and DOs dated Aug 2026 onwards, written from 17 Aug 2026 (the live push, daily integration
  writes through 28 Oct). **Nothing is dated Sep 2025 to Jul 2026: 11 months.** So the history
  backfill stopped after Aug 2025, and the live push started in Aug 2026. No DO has an empty
  date. Every month that is present has most lines naming their SO (`naming_an_so`).
- **R13.** The set-apart group is **three** debtors, not four: 300-H030 (31 documents,
  81,346.10), 300-H118 (10, 22,715.64), 300-H119 (7, 18,171.25). Total 48 documents,
  **122,232.99 = AutoCount SET APART to the cent.** One agent sells all three.

## R14. After the DO backfill: do the January invoices reach an SO now? (READ ONLY)

Purpose: the check to run once the Sep 2025 to Jul 2026 DOs have landed, before the tally.
For January 2026 SRT invoice lines that name a DO: how many find an AutoCount DO in the CRM, and
how many of those reach an SO (the same three hops as `invoiced_sales._traced_sales_order_ids`:
the DO line's SO line link, its `FromDocNo`, or the DO header's SO).

Expected after the backfill: `do_found` and `reaches_so` close to `lines` (round 2 showed the push
names a DO on 17,392 of 17,541 lines). Before it: `do_found` 0.

```sql
BEGIN READ ONLY;
WITH l AS (
  SELECT l.id, l.from_doc_no, d.company_id
  FROM finance.billing_document_lines l
  JOIN finance.billing_documents d ON d.id = l.document_id
  JOIN companies c ON c.id = d.company_id AND c.code = 'SRT'
  WHERE d.status = 'posted' AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND d.doc_date >= '2026-01-01' AND d.doc_date < '2026-02-01' AND l.from_doc_type = 'DO')
SELECT count(*) AS lines,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM orders o WHERE o.company_id = l.company_id AND o.order_number = l.from_doc_no
           AND o.deleted_at IS NULL AND o.doc_key IS NOT NULL)) AS do_found,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM orders o
         LEFT JOIN order_lines ol ON ol.order_id = o.id
         WHERE o.company_id = l.company_id AND o.order_number = l.from_doc_no AND o.deleted_at IS NULL
           AND (o.sales_order_id IS NOT NULL OR ol.sales_order_line_id IS NOT NULL
                OR EXISTS (SELECT 1 FROM sales_orders so WHERE so.company_id = o.company_id
                           AND so.so_number = ol.from_doc_no
                           AND (ol.from_doc_type IS NULL OR ol.from_doc_type = 'SO'))))) AS reaches_so
FROM l;
ROLLBACK;
```

# Round 5 (owner 29 Oct ~22:45: ask 1 (a), resume the shared-service DO history load)

## R15. The gap months on a database, before and after the load (READ ONLY)

Purpose: per DO month, Sep 2025 to Jul 2026, SRT: AutoCount DOs (`doc_key` set), CRM-made rows
(no `doc_key`: the Order Tracking rows the load adopts by DocNo, keeping their tracking), how many
of those carry a delivery date, and how many rows read assumed delivered. Run on the prod copy
before the dry run, after the copy's real run, and on prod after the prod run.

Expected before: `autocount_dos` 0 in every month. After: `autocount_dos` about AutoCount's own
DO count for the month (4,000 to 6,000 for SRT); `crm_made` falls by the dry run's `adopted`
count; `assumed_delivered` grows for months before Jul 2026 only (the 1 Jul 2026 cutover).

```sql
BEGIN READ ONLY;
SELECT date_trunc('month', o.order_date)::date AS do_month,
       count(*) FILTER (WHERE o.doc_key IS NOT NULL) AS autocount_dos,
       count(*) FILTER (WHERE o.doc_key IS NULL) AS crm_made,
       count(*) FILTER (WHERE o.doc_key IS NULL AND o.actual_delivery_date IS NOT NULL) AS crm_made_with_date,
       count(*) FILTER (WHERE o.tracking_assumed_at IS NOT NULL) AS assumed_delivered
FROM orders o JOIN companies c ON c.id = o.company_id AND c.code = 'SRT'
WHERE o.deleted_at IS NULL AND o.order_date >= '2025-09-01' AND o.order_date < '2026-08-01'
GROUP BY 1 ORDER BY 1;
ROLLBACK;
```
