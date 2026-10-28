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
