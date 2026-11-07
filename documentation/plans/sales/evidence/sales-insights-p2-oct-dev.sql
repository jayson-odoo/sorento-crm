-- SALES-INSIGHTS-P2: read-only, dev copy only (BEGIN READ ONLY ... ROLLBACK). Nothing is written.
-- October 2026 vs September 2026, invoiced net (IV + CS + DN - CN, posted only, by doc_date), the rules of
-- app/services/sales/invoiced_sales.py (signed_line_amount, agent_id, person_label).
-- Customers are selected by CODE only (no names, phones, emails). Paste the output on PR #2231.
-- Round 2: counted lines only, #2230's flags (NOT is_subtotal AND NOT is_duplicate, applied on the dev copy), so the
-- figures match post-#2230 prod. Round 1 (5fd06b86) approximated them; output on PR #2231 comment 6705369461.
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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
  AND NOT l.is_subtotal AND NOT l.is_duplicate
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

-- Q7. Dealer targets (164 ordered, the only targets with values; the 3 agent targets are RM 0.00): how many customers
-- each covers, and how many of October's top 50 customers sit in a dealer target whose period holds 31 Oct.
WITH oct_period AS (
  SELECT t.id, t.company_id, t.target_no, tp.period_start, tp.period_end, tp.target_value
  FROM sales.targets t JOIN sales.target_periods tp ON tp.target_id = t.id
  WHERE t.subject_kind = 'dealer' AND t.replaced_by_target_id IS NULL
    AND tp.period_start <= '2026-10-31' AND tp.period_end >= '2026-10-31'
)
SELECT (SELECT count(*) FROM oct_period) AS dealer_periods_holding_oct,
       (SELECT count(*) FROM oct_period o WHERE (SELECT count(*) FROM sales.target_accounts a WHERE a.target_id = o.id) = 1) AS one_account,
       (SELECT count(*) FROM oct_period o WHERE (SELECT count(*) FROM sales.target_accounts a WHERE a.target_id = o.id) > 1) AS several_accounts,
       (SELECT max((SELECT count(*) FROM sales.target_accounts a WHERE a.target_id = o.id)) FROM oct_period o) AS max_accounts,
       (SELECT count(DISTINCT a.customer_id) FROM oct_period o JOIN sales.target_accounts a ON a.target_id = o.id) AS customers_covered,
       (SELECT count(DISTINCT a.customer_id) FROM oct_period o JOIN sales.target_accounts a ON a.target_id = o.id
         WHERE a.customer_id IN (
           SELECT d.customer_id FROM finance.billing_documents d
           WHERE d.status = 'posted' AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
             AND d.doc_date >= '2026-10-01' AND d.doc_date < '2026-11-01' AND d.customer_id IS NOT NULL
           GROUP BY d.customer_id
           ORDER BY sum(CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END) DESC
           LIMIT 50)) AS top50_customers_with_target;

-- Q8. What the ACCOUNT category items are (no brand; RM 1.1m in October): code, description, unit, Oct lines.
SELECT p.product_code, left(p.description, 60) AS description, count(*) AS oct_lines
FROM finance.billing_document_lines l
JOIN finance.billing_documents d ON d.id = l.document_id
JOIN products p ON p.id = l.product_id
JOIN product_categories pc ON pc.id = p.category_id
WHERE pc.category_name = 'ACCOUNT' AND d.status = 'posted'
  AND d.doc_date >= '2026-10-01' AND d.doc_date < '2026-11-01'
  AND NOT l.is_subtotal AND NOT l.is_duplicate
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10;

ROLLBACK;
