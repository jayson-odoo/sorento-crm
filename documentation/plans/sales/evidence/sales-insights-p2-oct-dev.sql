-- SALES-INSIGHTS-P2: read-only, dev copy only (BEGIN READ ONLY ... ROLLBACK). Nothing is written.
-- October 2026 vs September 2026, invoiced net (IV + CS + DN - CN, posted only, by doc_date), the rules of
-- app/services/sales/invoiced_sales.py (signed_line_amount, agent_id, person_label).
-- Customers are selected by CODE only (no names, phones, emails). Paste the output on PR #2231.
-- The SALES-SUBTOTAL-LINES (#2230) fix is approximated by dropping a line with no item code, no product and no
-- quantity (the blank running-subtotal line found on #2227); say so if #2230 uses a different rule.
BEGIN READ ONLY;

-- p2_lines (inlined as a CTE in each query below: a READ ONLY transaction refuses CREATE, even TEMP):

-- Q0. Reconcile with the board: the October total and the top 3 persons (expect 16,369,803.26; LCL, SEAN, JUSTIN).
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT person, round(sum(rm), 2) AS oct_rm FROM p2_lines WHERE doc_date >= '2026-10-01'
GROUP BY ROLLUP (person) ORDER BY 2 DESC LIMIT 4;

-- Q1. Drilldown: LCL's top 12 customers in October, with September beside (customer code only).
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT cu.customer_code, co.code AS company,
       round(sum(rm) FILTER (WHERE doc_date >= '2026-10-01'), 2) AS oct_rm,
       round(sum(rm) FILTER (WHERE doc_date <  '2026-10-01'), 2) AS sep_rm,
       count(DISTINCT item_code) FILTER (WHERE doc_date >= '2026-10-01') AS oct_items
FROM p2_lines x LEFT JOIN customers cu ON cu.id = x.customer_id JOIN companies co ON co.id = x.company_id
WHERE person = 'LCL'
GROUP BY 1, 2 ORDER BY 3 DESC NULLS LAST LIMIT 12;
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT count(DISTINCT customer_id) AS lcl_oct_customers, count(DISTINCT item_code) AS lcl_oct_items
FROM p2_lines WHERE person = 'LCL' AND doc_date >= '2026-10-01';

-- Q2. Drilldown: LCL's top 12 items in October.
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT item_code, brand_name, category_name,
       round(sum(qty) FILTER (WHERE doc_date >= '2026-10-01'), 0) AS oct_qty,
       round(sum(rm)  FILTER (WHERE doc_date >= '2026-10-01'), 2) AS oct_rm,
       round(sum(rm)  FILTER (WHERE doc_date <  '2026-10-01'), 2) AS sep_rm
FROM p2_lines WHERE person = 'LCL'
GROUP BY 1, 2, 3 ORDER BY 5 DESC NULLS LAST LIMIT 12;

-- Q3. Customer perspective: top 12 customers in October, how many persons sold to each.
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT cu.customer_code, co.code AS company,
       round(sum(rm) FILTER (WHERE doc_date >= '2026-10-01'), 2) AS oct_rm,
       round(sum(rm) FILTER (WHERE doc_date <  '2026-10-01'), 2) AS sep_rm,
       count(DISTINCT person) FILTER (WHERE doc_date >= '2026-10-01') AS oct_persons,
       string_agg(DISTINCT person, ', ') FILTER (WHERE doc_date >= '2026-10-01') AS oct_person_list
FROM p2_lines x LEFT JOIN customers cu ON cu.id = x.customer_id JOIN companies co ON co.id = x.company_id
GROUP BY 1, 2 ORDER BY 3 DESC NULLS LAST LIMIT 12;
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT count(DISTINCT customer_id) AS oct_customers FROM p2_lines WHERE doc_date >= '2026-10-01';

-- Q4. Product perspective: top 12 items, top 10 brands, top 10 categories in October (Sep beside).
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT item_code, brand_name, category_name,
       round(sum(qty) FILTER (WHERE doc_date >= '2026-10-01'), 0) AS oct_qty,
       round(sum(rm)  FILTER (WHERE doc_date >= '2026-10-01'), 2) AS oct_rm,
       round(sum(rm)  FILTER (WHERE doc_date <  '2026-10-01'), 2) AS sep_rm,
       count(DISTINCT customer_id) FILTER (WHERE doc_date >= '2026-10-01') AS oct_customers
FROM p2_lines GROUP BY 1, 2, 3 ORDER BY 5 DESC NULLS LAST LIMIT 12;
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT coalesce(brand_name, '(no brand)') AS brand,
       round(sum(rm) FILTER (WHERE doc_date >= '2026-10-01'), 2) AS oct_rm,
       round(sum(rm) FILTER (WHERE doc_date <  '2026-10-01'), 2) AS sep_rm
FROM p2_lines GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 10;
WITH p2_lines AS (
SELECT d.company_id, d.doc_date, d.customer_id,
       a.sales_agent AS agent_code,
       coalesce(nullif(btrim(a.person_label), ''), a.sales_agent, CASE WHEN c.sales_agent_source = 'customer' THEN NULL ELSE nullif(btrim(d.agent_code), '') END, '(no agent)') AS person,
       coalesce(p.product_code, nullif(btrim(l.item_code), '')) AS item_code,
       b.brand_name, pc.category_name,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * d.currency_rate AS rm,
       CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END * l.quantity AS qty
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN companies c ON c.id = d.company_id
LEFT JOIN customers cu ON cu.id = d.customer_id
LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END
LEFT JOIN products p ON p.id = l.product_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
  AND NOT (nullif(btrim(l.item_code), '') IS NULL AND l.product_id IS NULL AND coalesce(l.quantity, 0) = 0)
)
SELECT coalesce(category_name, '(no category)') AS category,
       round(sum(rm) FILTER (WHERE doc_date >= '2026-10-01'), 2) AS oct_rm,
       round(sum(rm) FILTER (WHERE doc_date <  '2026-10-01'), 2) AS sep_rm
FROM p2_lines GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 10;

-- Q5. Targets: every target touching 2026, its basis, metric, scope, split and the period that holds 31 Oct 2026.
SELECT t.target_no, t.subject_kind, a.sales_agent AS agent_code, a.person_label, tm.name AS team,
       t.metric, t.basis, t.product_scope, t.split_every, t.split_unit, t.start_date, t.end_date,
       (SELECT count(*) FROM sales.target_periods tp WHERE tp.target_id = t.id) AS periods,
       (SELECT tp.period_start || '..' || tp.period_end || ' = ' || tp.target_value
          FROM sales.target_periods tp
         WHERE tp.target_id = t.id AND tp.period_start <= '2026-10-31' AND tp.period_end >= '2026-10-31' LIMIT 1) AS oct_period
FROM sales.targets t
LEFT JOIN sales_agents a ON a.id = t.sales_agent_id
LEFT JOIN sales.teams tm ON tm.id = t.sales_team_id
WHERE t.start_date <= '2026-12-31' AND t.end_date >= '2026-01-01'
ORDER BY t.subject_kind, t.basis, t.target_no;
SELECT subject_kind, basis, metric, count(*) FROM sales.targets GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- Q6. Customisation already in use: saved report views and quick-access pins on the sales reports.
SELECT report_key, count(*) AS views, count(*) FILTER (WHERE is_shared) AS shared, count(*) FILTER (WHERE is_default) AS defaults
FROM report_views GROUP BY 1 ORDER BY 2 DESC;
SELECT path, count(*) AS users FROM user_quick_access WHERE path LIKE '/sales/%' GROUP BY 1 ORDER BY 2 DESC;

ROLLBACK;
