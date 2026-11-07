-- SALES-INSIGHTS-P2 evidence round 3: read-only, dev copy only (BEGIN READ ONLY ... ROLLBACK).
-- Every inner SELECT is the shared engine's OWN pivot statement (ask.run_ask -> engine.run_summary), compiled from the
-- code with literal values (scratch generator, not committed logic), so the figures are exactly what the board and
-- Sales & outstanding would show. Grants = every company. Invoiced: #2230 counted lines (NOT is_subtotal AND NOT
-- is_duplicate) added by hand, as #2230 is not on this branch yet.
-- What it gives: (1) Channel (sales type) per basis, Oct and Sep; (2) top sales persons per basis, Oct; (3) top
-- customers BY NAME per basis, Oct (owner: "Customer need to show name"). Outstanding is shown twice: lines due in
-- October, and every open line whatever its date (the report's no-period reading).
-- __m0 = RM, __m1 = qty, as the engine names them.
BEGIN READ ONLY;

-- invoiced by channel, oct
SELECT 'invoiced' AS basis, 'oct' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE doc_sales_type.value WHEN 'dealer' THEN 'Dealer' WHEN 'project' THEN 'Project team' WHEN 'other' THEN 'Other' WHEN 'set_apart' THEN 'Set apart' WHEN 'mixed' THEN 'Mixed sales order types' WHEN 'type_not_set' THEN 'Sales order type not set' WHEN 'no_sales_order' THEN 'No sales order' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -(finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate) ELSE finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate END) AS __m0, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -finance.billing_document_lines.quantity ELSE finance.billing_document_lines.quantity END) AS __m1 
FROM finance.billing_document_lines JOIN finance.billing_documents ON finance.billing_documents.id = finance.billing_document_lines.document_id LEFT OUTER JOIN customers ON customers.id = finance.billing_documents.customer_id LEFT OUTER JOIN products ON products.id = finance.billing_document_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN LATERAL (SELECT CASE WHEN (EXISTS (SELECT set_apart_customers_1.id 
FROM sales.set_apart_customers AS set_apart_customers_1 
WHERE set_apart_customers_1.company_id = finance.billing_documents.company_id AND set_apart_customers_1.customer_id = finance.billing_documents.customer_id AND set_apart_customers_1.from_month <= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE) AND (set_apart_customers_1.to_month IS NULL OR set_apart_customers_1.to_month >= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE)))) THEN 'set_apart' ELSE (SELECT CASE WHEN (count(sales_orders_1.id) = 0) THEN 'no_sales_order' WHEN (count(DISTINCT sales_orders_1.demand_class) > 1) THEN 'mixed' WHEN (count(DISTINCT sales_orders_1.demand_class) = 0) THEN 'type_not_set' WHEN (max(sales_orders_1.demand_class) = 'retail') THEN 'dealer' WHEN (max(sales_orders_1.demand_class) = 'project') THEN 'project' WHEN (max(sales_orders_1.demand_class) = 'other') THEN 'other' ELSE 'type_not_set' END AS anon_1 
FROM ((SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) UNION SELECT inherited_ids.sales_order_id AS sales_order_id 
FROM (SELECT sales_order_lines_3.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_3 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.sales_order_line_id = sales_order_lines_3.id 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id UNION SELECT sales_orders_4.id AS id 
FROM sales_orders AS sales_orders_4 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'SO' AND billing_document_lines_2.from_doc_no = sales_orders_4.so_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND sales_orders_4.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_4.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_4 JOIN order_lines AS order_lines_2 ON order_lines_2.sales_order_line_id = sales_order_lines_4.id 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) UNION SELECT sales_orders_5.id AS id 
FROM sales_orders AS sales_orders_5 JOIN order_lines AS order_lines_2 ON order_lines_2.from_doc_no = sales_orders_5.so_number AND (order_lines_2.from_doc_type IS NULL OR order_lines_2.from_doc_type = 'SO') 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND sales_orders_5.company_id = finance.billing_documents.company_id UNION SELECT orders_2.sales_order_id AS sales_order_id 
FROM orders AS orders_2 
WHERE orders_2.id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND orders_2.sales_order_id IS NOT NULL) AS inherited_ids 
WHERE finance.billing_documents.against_document_id IS NOT NULL AND NOT (EXISTS (SELECT own_ids.sales_order_id 
FROM (SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) AS own_ids))) AS traced_ids JOIN sales_orders AS sales_orders_1 ON sales_orders_1.id = traced_ids.sales_order_id) END AS value
 LIMIT ALL OFFSET 0) AS doc_sales_type ON true 
WHERE finance.billing_documents.status = 'posted' AND NOT finance.billing_document_lines.is_subtotal AND NOT finance.billing_document_lines.is_duplicate AND finance.billing_documents.document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note') AND finance.billing_documents.doc_date >= '2026-10-01' AND finance.billing_documents.doc_date < '2026-11-01' AND finance.billing_documents.company_id IN (SELECT id FROM companies) GROUP BY CASE doc_sales_type.value WHEN 'dealer' THEN 'Dealer' WHEN 'project' THEN 'Project team' WHEN 'other' THEN 'Other' WHEN 'set_apart' THEN 'Set apart' WHEN 'mixed' THEN 'Mixed sales order types' WHEN 'type_not_set' THEN 'Sales order type not set' WHEN 'no_sales_order' THEN 'No sales order' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- invoiced by channel, sep
SELECT 'invoiced' AS basis, 'sep' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE doc_sales_type.value WHEN 'dealer' THEN 'Dealer' WHEN 'project' THEN 'Project team' WHEN 'other' THEN 'Other' WHEN 'set_apart' THEN 'Set apart' WHEN 'mixed' THEN 'Mixed sales order types' WHEN 'type_not_set' THEN 'Sales order type not set' WHEN 'no_sales_order' THEN 'No sales order' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -(finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate) ELSE finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate END) AS __m0, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -finance.billing_document_lines.quantity ELSE finance.billing_document_lines.quantity END) AS __m1 
FROM finance.billing_document_lines JOIN finance.billing_documents ON finance.billing_documents.id = finance.billing_document_lines.document_id LEFT OUTER JOIN customers ON customers.id = finance.billing_documents.customer_id LEFT OUTER JOIN products ON products.id = finance.billing_document_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN LATERAL (SELECT CASE WHEN (EXISTS (SELECT set_apart_customers_1.id 
FROM sales.set_apart_customers AS set_apart_customers_1 
WHERE set_apart_customers_1.company_id = finance.billing_documents.company_id AND set_apart_customers_1.customer_id = finance.billing_documents.customer_id AND set_apart_customers_1.from_month <= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE) AND (set_apart_customers_1.to_month IS NULL OR set_apart_customers_1.to_month >= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE)))) THEN 'set_apart' ELSE (SELECT CASE WHEN (count(sales_orders_1.id) = 0) THEN 'no_sales_order' WHEN (count(DISTINCT sales_orders_1.demand_class) > 1) THEN 'mixed' WHEN (count(DISTINCT sales_orders_1.demand_class) = 0) THEN 'type_not_set' WHEN (max(sales_orders_1.demand_class) = 'retail') THEN 'dealer' WHEN (max(sales_orders_1.demand_class) = 'project') THEN 'project' WHEN (max(sales_orders_1.demand_class) = 'other') THEN 'other' ELSE 'type_not_set' END AS anon_1 
FROM ((SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) UNION SELECT inherited_ids.sales_order_id AS sales_order_id 
FROM (SELECT sales_order_lines_3.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_3 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.sales_order_line_id = sales_order_lines_3.id 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id UNION SELECT sales_orders_4.id AS id 
FROM sales_orders AS sales_orders_4 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'SO' AND billing_document_lines_2.from_doc_no = sales_orders_4.so_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND sales_orders_4.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_4.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_4 JOIN order_lines AS order_lines_2 ON order_lines_2.sales_order_line_id = sales_order_lines_4.id 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) UNION SELECT sales_orders_5.id AS id 
FROM sales_orders AS sales_orders_5 JOIN order_lines AS order_lines_2 ON order_lines_2.from_doc_no = sales_orders_5.so_number AND (order_lines_2.from_doc_type IS NULL OR order_lines_2.from_doc_type = 'SO') 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND sales_orders_5.company_id = finance.billing_documents.company_id UNION SELECT orders_2.sales_order_id AS sales_order_id 
FROM orders AS orders_2 
WHERE orders_2.id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND orders_2.sales_order_id IS NOT NULL) AS inherited_ids 
WHERE finance.billing_documents.against_document_id IS NOT NULL AND NOT (EXISTS (SELECT own_ids.sales_order_id 
FROM (SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) AS own_ids))) AS traced_ids JOIN sales_orders AS sales_orders_1 ON sales_orders_1.id = traced_ids.sales_order_id) END AS value
 LIMIT ALL OFFSET 0) AS doc_sales_type ON true 
WHERE finance.billing_documents.status = 'posted' AND NOT finance.billing_document_lines.is_subtotal AND NOT finance.billing_document_lines.is_duplicate AND finance.billing_documents.document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note') AND finance.billing_documents.doc_date >= '2026-09-01' AND finance.billing_documents.doc_date < '2026-10-01' AND finance.billing_documents.company_id IN (SELECT id FROM companies) GROUP BY CASE doc_sales_type.value WHEN 'dealer' THEN 'Dealer' WHEN 'project' THEN 'Project team' WHEN 'other' THEN 'Other' WHEN 'set_apart' THEN 'Set apart' WHEN 'mixed' THEN 'Mixed sales order types' WHEN 'type_not_set' THEN 'Sales order type not set' WHEN 'no_sales_order' THEN 'No sales order' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- invoiced top persons, oct (agent codes folded by sales_agents.person_label)
SELECT 'invoiced' AS basis, 'oct' AS window, p.person, round(sum(x.__m0)::numeric, 2) AS rm
FROM (
SELECT coalesce(coalesce((SELECT sales_agents_1.sales_agent 
FROM sales_agents AS sales_agents_1 
WHERE sales_agents_1.id = CASE WHEN ((SELECT companies_1.sales_agent_source 
FROM companies AS companies_1 
WHERE companies_1.id = finance.billing_documents.company_id) = 'customer') THEN (SELECT customers_1.sales_agent_id 
FROM customers AS customers_1 
WHERE customers_1.id = finance.billing_documents.customer_id) ELSE finance.billing_documents.sales_agent_id END), CASE WHEN ((SELECT companies_2.sales_agent_source 
FROM companies AS companies_2 
WHERE companies_2.id = finance.billing_documents.company_id) = 'customer') THEN NULL ELSE nullif(btrim(finance.billing_documents.agent_code), '') END), '(no agent)') AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -(finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate) ELSE finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate END) AS __m0, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -finance.billing_document_lines.quantity ELSE finance.billing_document_lines.quantity END) AS __m1 
FROM finance.billing_document_lines JOIN finance.billing_documents ON finance.billing_documents.id = finance.billing_document_lines.document_id LEFT OUTER JOIN customers ON customers.id = finance.billing_documents.customer_id LEFT OUTER JOIN products ON products.id = finance.billing_document_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN LATERAL (SELECT CASE WHEN (EXISTS (SELECT set_apart_customers_1.id 
FROM sales.set_apart_customers AS set_apart_customers_1 
WHERE set_apart_customers_1.company_id = finance.billing_documents.company_id AND set_apart_customers_1.customer_id = finance.billing_documents.customer_id AND set_apart_customers_1.from_month <= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE) AND (set_apart_customers_1.to_month IS NULL OR set_apart_customers_1.to_month >= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE)))) THEN 'set_apart' ELSE (SELECT CASE WHEN (count(sales_orders_1.id) = 0) THEN 'no_sales_order' WHEN (count(DISTINCT sales_orders_1.demand_class) > 1) THEN 'mixed' WHEN (count(DISTINCT sales_orders_1.demand_class) = 0) THEN 'type_not_set' WHEN (max(sales_orders_1.demand_class) = 'retail') THEN 'dealer' WHEN (max(sales_orders_1.demand_class) = 'project') THEN 'project' WHEN (max(sales_orders_1.demand_class) = 'other') THEN 'other' ELSE 'type_not_set' END AS anon_1 
FROM ((SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) UNION SELECT inherited_ids.sales_order_id AS sales_order_id 
FROM (SELECT sales_order_lines_3.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_3 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.sales_order_line_id = sales_order_lines_3.id 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id UNION SELECT sales_orders_4.id AS id 
FROM sales_orders AS sales_orders_4 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'SO' AND billing_document_lines_2.from_doc_no = sales_orders_4.so_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND sales_orders_4.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_4.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_4 JOIN order_lines AS order_lines_2 ON order_lines_2.sales_order_line_id = sales_order_lines_4.id 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) UNION SELECT sales_orders_5.id AS id 
FROM sales_orders AS sales_orders_5 JOIN order_lines AS order_lines_2 ON order_lines_2.from_doc_no = sales_orders_5.so_number AND (order_lines_2.from_doc_type IS NULL OR order_lines_2.from_doc_type = 'SO') 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND sales_orders_5.company_id = finance.billing_documents.company_id UNION SELECT orders_2.sales_order_id AS sales_order_id 
FROM orders AS orders_2 
WHERE orders_2.id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND orders_2.sales_order_id IS NOT NULL) AS inherited_ids 
WHERE finance.billing_documents.against_document_id IS NOT NULL AND NOT (EXISTS (SELECT own_ids.sales_order_id 
FROM (SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) AS own_ids))) AS traced_ids JOIN sales_orders AS sales_orders_1 ON sales_orders_1.id = traced_ids.sales_order_id) END AS value
 LIMIT ALL OFFSET 0) AS doc_sales_type ON true 
WHERE finance.billing_documents.status = 'posted' AND NOT finance.billing_document_lines.is_subtotal AND NOT finance.billing_document_lines.is_duplicate AND finance.billing_documents.document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note') AND finance.billing_documents.doc_date >= '2026-10-01' AND finance.billing_documents.doc_date < '2026-11-01' AND finance.billing_documents.company_id IN (SELECT id FROM companies) GROUP BY coalesce(coalesce((SELECT sales_agents_1.sales_agent 
FROM sales_agents AS sales_agents_1 
WHERE sales_agents_1.id = CASE WHEN ((SELECT companies_1.sales_agent_source 
FROM companies AS companies_1 
WHERE companies_1.id = finance.billing_documents.company_id) = 'customer') THEN (SELECT customers_1.sales_agent_id 
FROM customers AS customers_1 
WHERE customers_1.id = finance.billing_documents.customer_id) ELSE finance.billing_documents.sales_agent_id END), CASE WHEN ((SELECT companies_2.sales_agent_source 
FROM companies AS companies_2 
WHERE companies_2.id = finance.billing_documents.company_id) = 'customer') THEN NULL ELSE nullif(btrim(finance.billing_documents.agent_code), '') END), '(no agent)'), CAST('all' AS TEXT)
) x
CROSS JOIN LATERAL (SELECT coalesce((SELECT max(nullif(btrim(a.person_label), '')) FROM sales_agents a WHERE a.sales_agent = x.__row), x.__row) AS person) p
GROUP BY p.person ORDER BY 4 DESC NULLS LAST LIMIT 10;

-- invoiced top customers by name, oct
SELECT 'invoiced' AS basis, 'oct' AS window, x.__row AS customer, round(x.__m0::numeric, 2) AS rm
FROM (
SELECT coalesce(customers.customer_name, finance.billing_documents.customer_name) AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -(finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate) ELSE finance.billing_document_lines.net_amount * finance.billing_documents.currency_rate END) AS __m0, sum(CASE WHEN (finance.billing_documents.document_type = 'credit_note') THEN -finance.billing_document_lines.quantity ELSE finance.billing_document_lines.quantity END) AS __m1 
FROM finance.billing_document_lines JOIN finance.billing_documents ON finance.billing_documents.id = finance.billing_document_lines.document_id LEFT OUTER JOIN customers ON customers.id = finance.billing_documents.customer_id LEFT OUTER JOIN products ON products.id = finance.billing_document_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN LATERAL (SELECT CASE WHEN (EXISTS (SELECT set_apart_customers_1.id 
FROM sales.set_apart_customers AS set_apart_customers_1 
WHERE set_apart_customers_1.company_id = finance.billing_documents.company_id AND set_apart_customers_1.customer_id = finance.billing_documents.customer_id AND set_apart_customers_1.from_month <= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE) AND (set_apart_customers_1.to_month IS NULL OR set_apart_customers_1.to_month >= CAST(date_trunc('month', finance.billing_documents.doc_date) AS DATE)))) THEN 'set_apart' ELSE (SELECT CASE WHEN (count(sales_orders_1.id) = 0) THEN 'no_sales_order' WHEN (count(DISTINCT sales_orders_1.demand_class) > 1) THEN 'mixed' WHEN (count(DISTINCT sales_orders_1.demand_class) = 0) THEN 'type_not_set' WHEN (max(sales_orders_1.demand_class) = 'retail') THEN 'dealer' WHEN (max(sales_orders_1.demand_class) = 'project') THEN 'project' WHEN (max(sales_orders_1.demand_class) = 'other') THEN 'other' ELSE 'type_not_set' END AS anon_1 
FROM ((SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) UNION SELECT inherited_ids.sales_order_id AS sales_order_id 
FROM (SELECT sales_order_lines_3.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_3 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.sales_order_line_id = sales_order_lines_3.id 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id UNION SELECT sales_orders_4.id AS id 
FROM sales_orders AS sales_orders_4 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'SO' AND billing_document_lines_2.from_doc_no = sales_orders_4.so_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND sales_orders_4.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_4.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_4 JOIN order_lines AS order_lines_2 ON order_lines_2.sales_order_line_id = sales_order_lines_4.id 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) UNION SELECT sales_orders_5.id AS id 
FROM sales_orders AS sales_orders_5 JOIN order_lines AS order_lines_2 ON order_lines_2.from_doc_no = sales_orders_5.so_number AND (order_lines_2.from_doc_type IS NULL OR order_lines_2.from_doc_type = 'SO') 
WHERE order_lines_2.order_id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND sales_orders_5.company_id = finance.billing_documents.company_id UNION SELECT orders_2.sales_order_id AS sales_order_id 
FROM orders AS orders_2 
WHERE orders_2.id IN (SELECT orders_2.id 
FROM orders AS orders_2 JOIN finance.billing_document_lines AS billing_document_lines_2 ON billing_document_lines_2.from_doc_type = 'DO' AND billing_document_lines_2.from_doc_no = orders_2.order_number 
WHERE billing_document_lines_2.document_id = finance.billing_documents.against_document_id AND orders_2.company_id = finance.billing_documents.company_id AND orders_2.deleted_at IS NULL) AND orders_2.sales_order_id IS NOT NULL) AS inherited_ids 
WHERE finance.billing_documents.against_document_id IS NOT NULL AND NOT (EXISTS (SELECT own_ids.sales_order_id 
FROM (SELECT sales_order_lines_1.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.sales_order_line_id = sales_order_lines_1.id 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id UNION SELECT sales_orders_2.id AS id 
FROM sales_orders AS sales_orders_2 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'SO' AND billing_document_lines_1.from_doc_no = sales_orders_2.so_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND sales_orders_2.company_id = finance.billing_documents.company_id UNION SELECT sales_order_lines_2.sales_order_id AS sales_order_id 
FROM sales_order_lines AS sales_order_lines_2 JOIN order_lines AS order_lines_1 ON order_lines_1.sales_order_line_id = sales_order_lines_2.id 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) UNION SELECT sales_orders_3.id AS id 
FROM sales_orders AS sales_orders_3 JOIN order_lines AS order_lines_1 ON order_lines_1.from_doc_no = sales_orders_3.so_number AND (order_lines_1.from_doc_type IS NULL OR order_lines_1.from_doc_type = 'SO') 
WHERE order_lines_1.order_id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND sales_orders_3.company_id = finance.billing_documents.company_id UNION SELECT orders_1.sales_order_id AS sales_order_id 
FROM orders AS orders_1 
WHERE orders_1.id IN (SELECT orders_1.id 
FROM orders AS orders_1 JOIN finance.billing_document_lines AS billing_document_lines_1 ON billing_document_lines_1.from_doc_type = 'DO' AND billing_document_lines_1.from_doc_no = orders_1.order_number 
WHERE billing_document_lines_1.document_id = finance.billing_documents.id AND orders_1.company_id = finance.billing_documents.company_id AND orders_1.deleted_at IS NULL) AND orders_1.sales_order_id IS NOT NULL) AS own_ids))) AS traced_ids JOIN sales_orders AS sales_orders_1 ON sales_orders_1.id = traced_ids.sales_order_id) END AS value
 LIMIT ALL OFFSET 0) AS doc_sales_type ON true 
WHERE finance.billing_documents.status = 'posted' AND NOT finance.billing_document_lines.is_subtotal AND NOT finance.billing_document_lines.is_duplicate AND finance.billing_documents.document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note') AND finance.billing_documents.doc_date >= '2026-10-01' AND finance.billing_documents.doc_date < '2026-11-01' AND finance.billing_documents.company_id IN (SELECT id FROM companies) GROUP BY coalesce(customers.customer_name, finance.billing_documents.customer_name), CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST LIMIT 12;

-- delivered by channel, oct
SELECT 'delivered' AS basis, 'oct' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0)) AS __m0, sum(least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- delivered by channel, sep
SELECT 'delivered' AS basis, 'sep' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0)) AS __m0, sum(least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-09-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-10-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- delivered top persons, oct (agent codes folded by sales_agents.person_label)
SELECT 'delivered' AS basis, 'oct' AS window, p.person, round(sum(x.__m0)::numeric, 2) AS rm
FROM (
SELECT coalesce(sales_agents.sales_agent, '(no agent)') AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0)) AS __m0, sum(least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY coalesce(sales_agents.sales_agent, '(no agent)'), CAST('all' AS TEXT)
) x
CROSS JOIN LATERAL (SELECT coalesce((SELECT max(nullif(btrim(a.person_label), '')) FROM sales_agents a WHERE a.sales_agent = x.__row), x.__row) AS person) p
GROUP BY p.person ORDER BY 4 DESC NULLS LAST LIMIT 10;

-- delivered top customers by name, oct
SELECT 'delivered' AS basis, 'oct' AS window, x.__row AS customer, round(x.__m0::numeric, 2) AS rm
FROM (
SELECT customers.customer_name AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0)) AS __m0, sum(least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY customers.customer_name, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST LIMIT 12;

-- ordered by channel, oct
SELECT 'ordered' AS basis, 'oct' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(sales_order_lines.line_total, 0)) AS __m0, sum(sales_order_lines.qty_ordered) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- ordered by channel, sep
SELECT 'ordered' AS basis, 'sep' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(sales_order_lines.line_total, 0)) AS __m0, sum(sales_order_lines.qty_ordered) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-09-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-10-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- ordered top persons, oct (agent codes folded by sales_agents.person_label)
SELECT 'ordered' AS basis, 'oct' AS window, p.person, round(sum(x.__m0)::numeric, 2) AS rm
FROM (
SELECT coalesce(sales_agents.sales_agent, '(no agent)') AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(sales_order_lines.line_total, 0)) AS __m0, sum(sales_order_lines.qty_ordered) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY coalesce(sales_agents.sales_agent, '(no agent)'), CAST('all' AS TEXT)
) x
CROSS JOIN LATERAL (SELECT coalesce((SELECT max(nullif(btrim(a.person_label), '')) FROM sales_agents a WHERE a.sales_agent = x.__row), x.__row) AS person) p
GROUP BY p.person ORDER BY 4 DESC NULLS LAST LIMIT 10;

-- ordered top customers by name, oct
SELECT 'ordered' AS basis, 'oct' AS window, x.__row AS customer, round(x.__m0::numeric, 2) AS rm
FROM (
SELECT customers.customer_name AS __row, CAST('all' AS TEXT) AS __col, sum(coalesce(sales_order_lines.line_total, 0)) AS __m0, sum(sales_order_lines.qty_ordered) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND sales_orders.doc_type != 'consignment' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY customers.customer_name, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST LIMIT 12;

-- outstanding by channel, oct
SELECT 'outstanding' AS basis, 'oct' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- outstanding by channel, sep
SELECT 'outstanding' AS basis, 'sep' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-09-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-10-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- outstanding by channel, all_open
SELECT 'outstanding' AS basis, 'all_open' AS window, coalesce(x.__row, '(none)') AS channel, round(x.__m0::numeric, 2) AS rm, x.__m1 AS qty
FROM (
SELECT CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2000-01-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2100-01-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY CASE WHEN (sales_orders.demand_class = 'retail') THEN 'Dealer' WHEN (sales_orders.demand_class = 'project') THEN 'Project team' WHEN (sales_orders.demand_class = 'other') THEN 'Other' ELSE NULL END, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST;

-- outstanding top persons, oct (agent codes folded by sales_agents.person_label)
SELECT 'outstanding' AS basis, 'oct' AS window, p.person, round(sum(x.__m0)::numeric, 2) AS rm
FROM (
SELECT coalesce(sales_agents.sales_agent, '(no agent)') AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY coalesce(sales_agents.sales_agent, '(no agent)'), CAST('all' AS TEXT)
) x
CROSS JOIN LATERAL (SELECT coalesce((SELECT max(nullif(btrim(a.person_label), '')) FROM sales_agents a WHERE a.sales_agent = x.__row), x.__row) AS person) p
GROUP BY p.person ORDER BY 4 DESC NULLS LAST LIMIT 10;

-- outstanding top customers by name, oct
SELECT 'outstanding' AS basis, 'oct' AS window, x.__row AS customer, round(x.__m0::numeric, 2) AS rm
FROM (
SELECT customers.customer_name AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2026-10-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2026-11-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY customers.customer_name, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST LIMIT 12;

-- outstanding top persons, all_open (agent codes folded by sales_agents.person_label)
SELECT 'outstanding' AS basis, 'all_open' AS window, p.person, round(sum(x.__m0)::numeric, 2) AS rm
FROM (
SELECT coalesce(sales_agents.sales_agent, '(no agent)') AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2000-01-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2100-01-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY coalesce(sales_agents.sales_agent, '(no agent)'), CAST('all' AS TEXT)
) x
CROSS JOIN LATERAL (SELECT coalesce((SELECT max(nullif(btrim(a.person_label), '')) FROM sales_agents a WHERE a.sales_agent = x.__row), x.__row) AS person) p
GROUP BY p.person ORDER BY 4 DESC NULLS LAST LIMIT 10;

-- outstanding top customers by name, all_open
SELECT 'outstanding' AS basis, 'all_open' AS window, x.__row AS customer, round(x.__m0::numeric, 2) AS rm
FROM (
SELECT customers.customer_name AS __row, CAST('all' AS TEXT) AS __col, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN coalesce(sales_order_lines.line_total, 0) - coalesce(round((coalesce(sales_order_lines.line_total, 0) * least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered)) / CAST(nullif(sales_order_lines.qty_ordered, 0) AS NUMERIC), 2), 0) ELSE 0 END) AS __m0, sum(CASE WHEN (sales_orders.status = 'open' AND sales_order_lines.line_status = 'open') THEN sales_order_lines.qty_ordered - least(sales_order_lines.qty_delivered, sales_order_lines.qty_ordered) ELSE 0 END) AS __m1 
FROM sales_order_lines JOIN sales_orders ON sales_orders.id = sales_order_lines.sales_order_id LEFT OUTER JOIN customers ON customers.id = sales_orders.customer_id LEFT OUTER JOIN sales_agents ON sales_agents.id = sales_orders.sales_agent_id LEFT OUTER JOIN products ON products.id = sales_order_lines.product_id LEFT OUTER JOIN brands ON brands.id = products.brand_id LEFT OUTER JOIN product_categories ON product_categories.id = products.category_id LEFT OUTER JOIN warehouses ON warehouses.id = sales_order_lines.warehouse_id 
WHERE sales_orders.status != 'cancelled' AND sales_order_lines.line_status != 'cancelled' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) IS NOT NULL AND coalesce(sales_order_lines.required_date, sales_orders.order_date) >= '2000-01-01' AND coalesce(sales_order_lines.required_date, sales_orders.order_date) < '2100-01-01' AND sales_orders.company_id IN (SELECT id FROM companies) GROUP BY customers.customer_name, CAST('all' AS TEXT)
) x ORDER BY x.__m0 DESC NULLS LAST LIMIT 12;

-- Names for the customer codes already in the mockup (rounds 1-2), so frames B / C / E show names.
SELECT c.customer_code, co.code AS company, c.customer_name
FROM customers c JOIN companies co ON co.id = c.company_id
WHERE c.customer_code IN ('304-R015','300-S289','304-R016','300-P121','303-P001','301-K001','300-P122','303-M004',
  '302-S002','303-K001','305-M002','302-S001','300-K154','300-E095','300-E082','300-A115','300-F004','300-O024',
  '300-D016','300-d018','300-S321')
ORDER BY 1, 2;
ROLLBACK;
